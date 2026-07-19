#!/usr/bin/env python3
"""
bear_market_data_collector.py

Verifies and backfills OHLCV coverage for real historical bear-market
windows (COVID 2020, the 2022 bear market) across all 5 markets, so
regime-segmented backtests can actually include crash data.

WHY THIS EXISTS: a research pass on this repo's existing regime
classification (walk_forward_backtest.py's classify_regime(), backtest_
screeners.py's own BULL/BEAR split) found that the *reported* regime-
segmented results come from short, recent windows that exclude both the
2020 COVID crash and the 2022 bear market -- India's 10-year walk-forward
VAL set only covers 2024-2026, and the standalone backtest_screeners.py
run only covers ~14 months (Apr 2025-Jun 2026). The raw price data pulled
during those runs may include earlier history, but nobody has verified
COVERAGE during the actual crash windows specifically, and the one
confirmed measurement (India's 10-year OHLC backtest) found only 28/144
tickers (19%) actually had usable data -- a coverage problem that could
easily also affect crash-specific windows without anyone noticing, since
"we have 10 years of history" doesn't mean "we have complete coverage
during the 8 weeks that actually matter."

WHAT THIS SCRIPT DOES (does NOT hardcode bear-market dates from memory --
computes them empirically per market from each market's own benchmark
index, since exact crash timing/magnitude differs by 1-4 weeks and a few
percentage points across markets):

  1. Fetch each market's benchmark index (10y+ history) directly via
     yfinance -- these are NOT in the stocks/ohlcv_history warehouse
     tables (indices aren't equities, so they were never seeded).
  2. Detect the actual bear window per market within two known crisis
     calendar windows (2020 Q1-Q2, all of 2022): the longest sustained
     peak-to-trough drawdown >= BEAR_THRESHOLD within each crisis window.
  3. Check stock-level OHLCV coverage in the warehouse for that market's
     full stock universe, specifically during the detected bear window
     (not just "any data exists somewhere in history").
  4. For symbols with insufficient coverage, backfill via stock_utils.
     bulk_download() (existing rate-limit-aware yfinance batcher) scoped
     to just the bear window's date range -- not a full re-collection.
  5. Load backfilled rows into ohlcv_history via the existing batch-
     versioned warehouse loader (see warehouse_versioning.sql /
     load_ohlcv_to_warehouse.py) -- a new batch, not an overwrite.
  6. Write a coverage report (before/after) to cache_seed/ so the gap is
     visible even for markets/periods this run couldn't fully backfill.

Usage:
    .venv/bin/python3 bear_market_data_collector.py                  # all 5 markets, both crisis windows
    .venv/bin/python3 bear_market_data_collector.py --market india   # one market
    .venv/bin/python3 bear_market_data_collector.py --check-only     # coverage report, no backfill/writes
    .venv/bin/python3 bear_market_data_collector.py --dry-run        # backfill fetch only, no warehouse writes
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
import yfinance as yf

sys.path.insert(0, "/Users/umashankar/market-pipeline/code/python_files")
from stock_utils import bulk_download  # noqa: E402 -- reused verbatim, not reimplemented
from warehouse_batch import finish_batch, start_batch  # noqa: E402
from warehouse_common import (  # noqa: E402
    MARKET_IDS,
    PG_CONN_KWARGS,
    copy_dataframe,
    log,
)

CACHE_DIR = Path("/Users/umashankar/market-pipeline/code/python_files/cache_seed")

# Benchmark index per market -- fetched directly via yfinance, NOT from the
# warehouse (indices aren't in the equity-seeded `stocks` table).
BENCHMARK_TICKERS = {
    "usa": "^GSPC",
    "india": "^NSEI",
    "japan": "^N225",
    "korea": "^KS11",
    "europe": "^STOXX50E",
}

# Two known crisis CALENDAR windows to search within -- deliberately not the
# bear-market dates themselves. The actual start/end/magnitude of each
# market's drawdown is detected empirically from that market's own index in
# detect_bear_window() below, since exact timing/depth genuinely differs by
# market (this repo's own India backtest already showed a much milder 2022
# correction than the US, for example -- hardcoding "2022 bear market =
# Jan-Oct" for every market would be wrong for at least one of them).
CRISIS_SEARCH_WINDOWS = {
    "covid_2020": ("2020-01-01", "2020-06-30"),
    "bear_2022": ("2022-01-01", "2022-12-31"),
}

BEAR_THRESHOLD = -0.15  # peak-to-trough drawdown to count as a bear window
MIN_COVERAGE_DAYS_PCT = 0.85  # a symbol "has coverage" if it has data on
                                # >=85% of the trading days in the window
                                # (some gaps tolerated -- holidays, halts)


def fetch_benchmark(market: str, ticker: str) -> pd.DataFrame:
    log(f"[{market}] fetching benchmark {ticker} (2018-01-01 to today) …")
    df = yf.download(ticker, start="2018-01-01", auto_adjust=True, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"[{market}] benchmark {ticker} returned no data")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Close"]].dropna()
    log(f"[{market}]   {len(df):,} bars, {df.index.min().date()} to {df.index.max().date()}")
    return df


def detect_bear_window(index_df: pd.DataFrame, search_start: str, search_end: str,
                        threshold: float = BEAR_THRESHOLD):
    """Longest sustained peak-to-trough drawdown >= threshold within
    [search_start, search_end]. Returns (peak_date, trough_date, drawdown_pct)
    or None if no window in range crossed the threshold."""
    window = index_df.loc[search_start:search_end, "Close"]
    if window.empty:
        return None
    running_max = window.cummax()
    drawdown = (window - running_max) / running_max
    trough_idx = drawdown.idxmin()
    max_drawdown = drawdown.loc[trough_idx]
    if max_drawdown > threshold:
        return None
    peak_idx = window.loc[:trough_idx].idxmax()
    return peak_idx.date(), trough_idx.date(), round(float(max_drawdown) * 100, 2)


def check_coverage(conn, market: str, peak: str, trough: str) -> pd.DataFrame:
    """Per-symbol coverage in [peak, trough] from the warehouse. Uses the
    natural trading-day count of the market's OWN data in that window as the
    denominator (not a fixed calendar-day count), since holiday calendars
    differ by market and this avoids penalizing every symbol for exchange
    holidays that aren't gaps.

    Excludes synthetic placeholder seed rows -- confirmed present in stocks
    under names like 'USA Company 2' (1,018 rows, market_id=2) and 'South
    Korea Company 1' (416 rows, market_id=7), i.e. `^<Market> Company <N>$`.
    No real listed company is named that way, and no data source will ever
    resolve these -- fetching them just wastes yfinance calls."""
    market_id = MARKET_IDS[market]
    query = """
        SELECT s.ticker, count(DISTINCT o.date) AS days_present
        FROM stocks s
        LEFT JOIN ohlcv_history o
          ON o.stock_id = s.stock_id AND o.date BETWEEN %s AND %s
        WHERE s.market_id = %s
          AND s.name !~ '^[A-Za-z ]+ Company [0-9]+$'
        GROUP BY s.ticker
    """
    df = pd.read_sql(query, conn, params=(peak, trough, market_id))
    expected_days = int(df["days_present"].max()) if not df.empty else 0
    df["coverage_pct"] = (df["days_present"] / expected_days * 100).round(1) if expected_days else 0.0
    df["expected_days"] = expected_days
    return df.sort_values("coverage_pct")


_KR_SUFFIX_MAP = None  # lazy, cached: bare Korea ticker -> ".KS"/".KQ"


def _korea_suffix_map() -> dict:
    """bare Korea ticker -> yfinance suffix (.KS for KOSPI, .KQ for KOSDAQ/
    KOSDAQ GLOBAL). Unlike India/Japan (one suffix fits the whole market),
    Korea genuinely needs a per-ticker lookup -- a bare 6-digit code alone
    doesn't say which exchange it's on. pykrx (this repo's usual KRX
    source) returned an empty ticker list on every date tried 2026-07-19 --
    a live break in that library/its upstream, not something to route
    around silently -- so this uses FinanceDataReader's StockListing('KRX')
    instead, confirmed working the same day (2,872 rows, real KOSPI/KOSDAQ
    split). KONEX-listed tickers are left unmapped (no reliable yfinance
    suffix convention for that board) rather than guessed."""
    global _KR_SUFFIX_MAP
    if _KR_SUFFIX_MAP is not None:
        return _KR_SUFFIX_MAP
    try:
        import FinanceDataReader as fdr
        listing = fdr.StockListing("KRX")
        sfx = {"KOSPI": ".KS", "KOSDAQ": ".KQ", "KOSDAQ GLOBAL": ".KQ"}
        _KR_SUFFIX_MAP = {
            str(row.Code): sfx[row.Market]
            for row in listing.itertuples()
            if row.Market in sfx
        }
    except Exception as e:
        log(f"[korea] WARNING: FinanceDataReader KOSPI/KOSDAQ lookup failed ({e}) "
            f"-- Korea backfill will skip unmapped tickers")
        _KR_SUFFIX_MAP = {}
    return _KR_SUFFIX_MAP


def backfill_gaps(market: str, tickers: list[str], peak: str, trough: str) -> dict:
    """bulk_download scoped to just the bear window -- not a full
    re-collection. `end` is bounded a few days past `trough` (not left open
    to today) so the fetch doesn't waste calls re-pulling years of already-
    covered recent history and so the returned rows are actually dominated
    by the window we're trying to fill.

    Warehouse tickers are stored bare for India/Japan/Korea (yfinance needs
    a suffix to resolve any of them) but pre-suffixed for Europe (RIO.L is
    the warehouse's own convention there, not a yfinance-only addition).
    CORRECTED 2026-07-19: this docstring previously claimed Japan/Korea
    were "already stored pre-suffixed" -- checked directly against the
    `stocks` table and that was wrong for both (0/3,709 Japan and 0/3,184
    Korea tickers carry any suffix). That false assumption is why every
    Japan/Korea backfill attempt returned 0 rows loaded in the runs before
    this fix -- yfinance was being asked for bare "7203"/"005930", which it
    can't resolve to the right exchange. `stock_utils.bulk_download` strips
    .NS/.BO/.T/.KS/.KQ back off its result keys, so the caller still gets
    back bare tickers matching the `stocks` table regardless of market."""
    if not tickers:
        return {}
    if market == "india":
        query_tickers = [f"{t}.NS" for t in tickers]
    elif market == "japan":
        query_tickers = [f"{t}.T" for t in tickers]
    elif market == "korea":
        sfx_map = _korea_suffix_map()
        query_tickers = [t + sfx_map[t] for t in tickers if t in sfx_map]
        skipped = len(tickers) - len(query_tickers)
        if skipped:
            log(f"[korea] skipping {skipped}/{len(tickers)} tickers with no "
                f"KOSPI/KOSDAQ match (KONEX-listed or delisted)")
    else:
        query_tickers = tickers
    if not query_tickers:
        return {}
    end = (pd.to_datetime(trough) + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    log(f"[{market}] backfilling {len(query_tickers)} symbols for {peak} to {end} …")
    return bulk_download(query_tickers, start=peak, end=end, batch_size=100,
                          sleep_between=1.5, min_bars=5)


def load_backfill_to_warehouse(conn, market: str, data: dict[str, pd.DataFrame],
                                source_note: str) -> int:
    if not data:
        return 0
    rows = []
    for ticker, df in data.items():
        d = df.reset_index()
        d["ticker"] = ticker
        rows.append(d)
    combined = pd.concat(rows, ignore_index=True)
    combined = combined.rename(columns={
        "Date": "date", "Open": "open_price", "High": "high_price",
        "Low": "low_price", "Close": "close_price", "Volume": "volume",
    })
    combined["date"] = pd.to_datetime(combined["date"]).dt.date
    combined["volume"] = pd.to_numeric(combined["volume"], errors="coerce").round().astype("Int64")
    combined["adj_close"] = None

    market_id = MARKET_IDS[market]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker, stock_id FROM stocks WHERE market_id = %s AND ticker = ANY(%s)",
            (market_id, combined["ticker"].unique().tolist()),
        )
        ticker_map = {t: sid for t, sid in cur.fetchall()}
    combined["stock_id"] = combined["ticker"].map(ticker_map)
    combined = combined[combined["stock_id"].notna()].copy()
    combined["stock_id"] = combined["stock_id"].astype(int)

    batch_id = start_batch(conn, "ohlcv_history", f"bear_market_backfill_{market}", source_note)
    combined["batch_id"] = batch_id
    staging_cols = ["stock_id", "date", "open_price", "high_price", "low_price",
                     "close_price", "volume", "adj_close", "batch_id"]
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS stg_bear_backfill")
            cur.execute("CREATE TEMP TABLE stg_bear_backfill (LIKE ohlcv_history INCLUDING DEFAULTS)")
            cur.execute("ALTER TABLE stg_bear_backfill DROP COLUMN ohlcv_id, DROP COLUMN created_at")
        conn.commit()
        copy_dataframe(conn, combined[staging_cols], "stg_bear_backfill", staging_cols)
        with conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO ohlcv_history ({', '.join(staging_cols)})
                SELECT DISTINCT ON (stock_id, date) {', '.join(staging_cols)}
                FROM stg_bear_backfill
                ORDER BY stock_id, date
                ON CONFLICT (stock_id, date, batch_id) DO UPDATE SET
                    open_price = EXCLUDED.open_price, high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price, close_price = EXCLUDED.close_price,
                    volume = EXCLUDED.volume
            """)
            inserted = cur.rowcount
        conn.commit()
        finish_batch(conn, batch_id, inserted, status="success")
        log(f"[{market}] loaded {inserted:,} backfilled rows (batch_id={batch_id})")
        return inserted
    except Exception as e:
        conn.rollback()
        finish_batch(conn, batch_id, 0, status="failed", notes=str(e)[:500])
        raise


def run_market(conn, market: str, args) -> list[dict]:
    ticker = BENCHMARK_TICKERS[market]
    try:
        index_df = fetch_benchmark(market, ticker)
    except Exception as e:
        log(f"[{market}] ERROR fetching benchmark: {e}")
        return []

    reports = []
    for crisis_name, (search_start, search_end) in CRISIS_SEARCH_WINDOWS.items():
        window = detect_bear_window(index_df, search_start, search_end)
        if window is None:
            log(f"[{market}] {crisis_name}: no drawdown >= {BEAR_THRESHOLD:.0%} detected in "
                f"[{search_start}, {search_end}] -- skipping")
            continue
        peak, trough, drawdown_pct = window
        log(f"[{market}] {crisis_name}: peak {peak} -> trough {trough}, "
            f"{drawdown_pct:+.2f}% drawdown")

        coverage = check_coverage(conn, market, str(peak), str(trough))
        n_total = len(coverage)
        n_covered = (coverage["coverage_pct"] >= MIN_COVERAGE_DAYS_PCT * 100).sum()
        log(f"[{market}] {crisis_name}: {n_covered}/{n_total} symbols "
            f"({n_covered/n_total*100:.1f}%) have >={MIN_COVERAGE_DAYS_PCT:.0%} day coverage "
            f"in the window (BEFORE backfill)")

        report = {
            "market": market, "crisis": crisis_name,
            "peak_date": str(peak), "trough_date": str(trough), "drawdown_pct": drawdown_pct,
            "symbols_total": n_total, "symbols_covered_before": int(n_covered),
            "coverage_pct_before": round(n_covered / n_total * 100, 1) if n_total else 0.0,
        }

        if args.check_only:
            reports.append(report)
            continue

        gap_tickers = coverage.loc[coverage["coverage_pct"] < MIN_COVERAGE_DAYS_PCT * 100, "ticker"].tolist()
        if not gap_tickers:
            report["symbols_covered_after"] = n_covered
            report["coverage_pct_after"] = report["coverage_pct_before"]
            reports.append(report)
            continue

        backfilled = backfill_gaps(market, gap_tickers, str(peak), str(trough))
        if not args.dry_run and backfilled:
            load_backfill_to_warehouse(
                conn, market, backfilled,
                source_note=f"bear_market_data_collector.py:{crisis_name}",
            )
            coverage_after = check_coverage(conn, market, str(peak), str(trough))
            n_covered_after = (coverage_after["coverage_pct"] >= MIN_COVERAGE_DAYS_PCT * 100).sum()
        else:
            n_covered_after = n_covered + len(backfilled)  # optimistic estimate, dry-run only

        report["symbols_covered_after"] = int(n_covered_after)
        report["coverage_pct_after"] = round(n_covered_after / n_total * 100, 1) if n_total else 0.0
        reports.append(report)

    return reports


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=list(BENCHMARK_TICKERS.keys()), default=None,
                     help="Run only this market (default: all 5)")
    ap.add_argument("--check-only", action="store_true",
                     help="Coverage report only -- no backfill fetch, no warehouse writes")
    ap.add_argument("--dry-run", action="store_true",
                     help="Fetch backfill data but don't write to the warehouse")
    args = ap.parse_args()

    markets = [args.market] if args.market else list(BENCHMARK_TICKERS.keys())
    conn = psycopg2.connect(**PG_CONN_KWARGS)
    all_reports = []
    try:
        for market in markets:
            t0 = time.time()
            all_reports.extend(run_market(conn, market, args))
            log(f"[{market}] done in {time.time()-t0:.1f}s\n")
    finally:
        conn.close()

    out_path = CACHE_DIR / "bear_market_coverage_report.json"
    out_path.write_text(json.dumps(all_reports, indent=2, default=str))
    log(f"Saved coverage report -> {out_path}")

    pd.set_option("display.width", 160)
    print("\n" + "=" * 100)
    print("BEAR-MARKET COVERAGE SUMMARY")
    print("=" * 100)
    if all_reports:
        print(pd.DataFrame(all_reports).to_string(index=False))
    else:
        print("No bear windows detected in the searched crisis calendar ranges.")


if __name__ == "__main__":
    sys.exit(main())
