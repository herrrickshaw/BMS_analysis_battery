#!/usr/bin/env python3
"""
financial_ratios.py — one ratio table for India + US, rebuilt from the
fundamentals stores + latest closes. The "finding the financial ratios" surface.

INPUTS (all local, no network):
  * market_cache/fundamentals/IN_current.parquet  (INR, yfinance off-hours store)
  * market_cache/fundamentals/US_current.parquet  (USD, SEC EDGAR store)
  * data/bhavcopy_cache/cleaned_long.parquet      (India closes, NSE precedence)
  * data/bhavcopy_cache/ohlcv_US.parquet          (US closes)
  * market_cache/symbol_master.parquet            (names — live tree, never ~/Downloads)

RATIOS, per ticker, latest fiscal year vs latest close:
  market_cap, pe, pb, roe, roa, roce, debt_to_equity, current_ratio,
  gross_margin, operating_margin, net_margin, fcf_yield, cfo_to_ni,
  asset_turnover, revenue_growth (vs prior FY)

CURRENCY: never mixed. India rows are INR-on-INR, US rows USD-on-USD — every
ratio is a pure number except market_cap, which is reported in the market's own
currency (mcap_local) precisely so nobody averages ₹ and $ by accident.

OUTPUTS:
  * market_cache/fundamentals/ratios_latest.parquet     (atomic replace)
  * Postgres fundamentals.ratios                         (full replace per run)
  * reports/financial_ratios.csv                         (for extraction)

Usage:
    /usr/bin/python3 financial_ratios.py                 # rebuild everything
    /usr/bin/python3 financial_ratios.py --ticker RELIANCE
    /usr/bin/python3 financial_ratios.py --ticker AAPL --market us
    /usr/bin/python3 financial_ratios.py --status        # coverage per market
NB: run with /usr/bin/python3 — duckdb lives there, not in the venv.
"""

from __future__ import annotations

import argparse
import os
import datetime as dt
import sys
from pathlib import Path

import duckdb
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import data_registry as _R
    FUND_DIR = _R.FUND_DIR
    PG_DSN = _R.PG_DSN
except Exception:
    FUND_DIR = Path("/Users/umashankar/market-pipeline/market_cache/fundamentals")
    PG_DSN = "dbname=market_data host=/tmp user=umashankar"

BHAV = Path("/Users/umashankar/market-pipeline/data/bhavcopy_cache")
# Live tree, NOT ~/Downloads (TCC-denied under launchd — see symbol_master.py's
# two-trees warning; the 2026-07-23 00:30 run failed on the Downloads path).
SYMBOL_MASTER = Path(os.environ.get(
    "MARKET_CACHE", "/Users/umashankar/market-pipeline/market_cache")) / "symbol_master.parquet"
OUT_PARQUET = FUND_DIR / "ratios_latest.parquet"
OUT_CSV = HERE / "reports" / "financial_ratios.csv"

MARKETS = {
    # market -> (store parquet, close parquet, currency)
    "india": (FUND_DIR / "IN_current.parquet", BHAV / "cleaned_long.parquet", "INR"),
    "us":    (FUND_DIR / "US_current.parquet", BHAV / "ohlcv_US.parquet",     "USD"),
}


def _latest_closes(con, path: Path) -> pd.DataFrame:
    """(symbol, close, close_date) at each symbol's own last bar."""
    return con.execute(f"""
        SELECT Symbol AS symbol, Close AS close, CAST(Date AS DATE) AS close_date
        FROM (SELECT *, row_number() OVER (PARTITION BY Symbol ORDER BY Date DESC) rn
              FROM read_parquet('{path}'))
        WHERE rn = 1 AND Close IS NOT NULL
    """).df()


def _names(con) -> pd.DataFrame:
    if not SYMBOL_MASTER.exists():
        return pd.DataFrame(columns=["symbol", "name"])
    return con.execute(f"""
        SELECT symbol, name FROM (
          SELECT symbol, name, row_number() OVER (PARTITION BY symbol
                 ORDER BY CASE exchange WHEN 'NSE' THEN 0 WHEN 'BSE' THEN 1 ELSE 2 END) rn
          FROM read_parquet('{SYMBOL_MASTER}')
          WHERE symbol IS NOT NULL AND name IS NOT NULL)
        WHERE rn = 1
    """).df()


def _safe_div(a, b):
    try:
        if a is None or b is None or pd.isna(a) or pd.isna(b) or b == 0:
            return None
        return float(a) / float(b)
    except (TypeError, ValueError):
        return None


def build_market(con, market: str) -> pd.DataFrame:
    store_path, close_path, ccy = MARKETS[market]
    if not store_path.exists():
        print(f"  {market}: store missing ({store_path.name}) — skipped")
        return pd.DataFrame()
    fund = pd.read_parquet(store_path)
    if fund.empty:
        return pd.DataFrame()
    fund = fund.sort_values(["ticker", "fy_end"])
    latest = fund.groupby("ticker").tail(1).set_index("ticker")
    prior = fund.groupby("ticker").nth(-2)
    if isinstance(prior, pd.DataFrame) and "ticker" in prior.columns:
        prior = prior.set_index("ticker")

    closes = _latest_closes(con, close_path).set_index("symbol")

    rows = []
    for tkr, f in latest.iterrows():
        c = closes.loc[tkr] if tkr in closes.index else None
        close = float(c["close"]) if c is not None else None
        shares = f.get("shares")
        equity = f.get("stockholders_equity")
        ni, rev, assets = f.get("net_income"), f.get("revenue"), f.get("total_assets")
        ebit, cfo, fcf = f.get("ebit"), f.get("cfo"), f.get("free_cash_flow")
        debt = f.get("total_debt")
        if debt is None or pd.isna(debt):
            debt = f.get("long_term_debt")
        mcap = (close * shares) if (close is not None and shares is not None
                                    and not pd.isna(shares)) else None
        prev_rev = None
        if tkr in prior.index:
            pr = prior.loc[tkr]
            prev_rev = pr.get("revenue") if not isinstance(pr, pd.DataFrame) else None
        cap_employed = None
        if equity is not None and not pd.isna(equity):
            cap_employed = equity + (debt if (debt is not None and not pd.isna(debt)) else 0)

        rows.append({
            "market": market, "ticker": tkr, "currency": ccy,
            "fy_end": f.get("fy_end"), "source": f.get("source"),
            "close": close,
            "close_date": (c["close_date"] if c is not None else None),
            "mcap_local": mcap,
            "pe": _safe_div(mcap, ni) if (ni is not None and not pd.isna(ni) and ni > 0) else None,
            "pb": _safe_div(mcap, equity) if (equity is not None and not pd.isna(equity) and equity > 0) else None,
            "roe": _safe_div(ni, equity),
            "roa": _safe_div(ni, assets),
            "roce": _safe_div(ebit, cap_employed),
            "debt_to_equity": _safe_div(debt, equity),
            "current_ratio": _safe_div(f.get("current_assets"), f.get("current_liabilities")),
            "gross_margin": _safe_div(f.get("gross_profit"), rev),
            "operating_margin": _safe_div(ebit, rev),
            "net_margin": _safe_div(ni, rev),
            "fcf_yield": _safe_div(fcf, mcap),
            "cfo_to_ni": _safe_div(cfo, ni),
            "asset_turnover": _safe_div(rev, assets),
            "revenue_growth": _safe_div(rev - prev_rev, abs(prev_rev))
                if (rev is not None and prev_rev is not None
                    and not pd.isna(rev) and not pd.isna(prev_rev) and prev_rev != 0) else None,
        })
    return pd.DataFrame(rows)


def build(con) -> pd.DataFrame:
    parts = [build_market(con, m) for m in MARKETS]
    df = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    names = _names(con)
    if not names.empty:
        df = df.merge(names, left_on="ticker", right_on="symbol", how="left") \
               .drop(columns=["symbol"])
    else:
        df["name"] = None
    df["computed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    cols = ["market", "ticker", "name", "currency", "fy_end", "close", "close_date",
            "mcap_local", "pe", "pb", "roe", "roa", "roce", "debt_to_equity",
            "current_ratio", "gross_margin", "operating_margin", "net_margin",
            "fcf_yield", "cfo_to_ni", "asset_turnover", "revenue_growth",
            "source", "computed_at"]
    return df[cols]


def write_outputs(con, df: pd.DataFrame) -> None:
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PARQUET.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(OUT_PARQUET)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    # Postgres: full replace — this is a derived table, the stores are the truth
    try:
        con.execute("INSTALL postgres"); con.execute("LOAD postgres")
        con.execute(f"ATTACH '{PG_DSN}' AS pg (TYPE postgres)")
        con.execute("CALL postgres_execute('pg', 'CREATE SCHEMA IF NOT EXISTS fundamentals')")
        con.execute("CALL pg_clear_cache()")
        con.register("ratios_df", df)
        con.execute("CALL postgres_execute('pg', 'DROP TABLE IF EXISTS fundamentals.ratios')")
        con.execute("CALL pg_clear_cache()")
        con.execute("CREATE TABLE pg.fundamentals.ratios AS SELECT * FROM ratios_df")
        con.unregister("ratios_df")
        print(f"  pg fundamentals.ratios replaced ({len(df):,} rows)")
    except Exception as e:
        print(f"  ! postgres write skipped: {str(e)[:80]}")
    print(f"  wrote {OUT_PARQUET}")
    print(f"  wrote {OUT_CSV} ({len(df):,} rows)")


def show_status(df: pd.DataFrame) -> None:
    print(f"\n=== FINANCIAL RATIOS COVERAGE (as of {dt.date.today()}) ===")
    for m, g in df.groupby("market"):
        n = len(g)
        with_pe = g["pe"].notna().sum()
        with_roe = g["roe"].notna().sum()
        with_roce = g["roce"].notna().sum()
        fy = g["fy_end"].max()
        print(f"  {m:6s} {n:5,} tickers | pe {with_pe:,} | roe {with_roe:,} | "
              f"roce {with_roce:,} | newest FY {fy}")


def show_ticker(df: pd.DataFrame, ticker: str, market: str | None) -> None:
    sel = df[df["ticker"].str.upper() == ticker.upper()]
    if market and market != "all":
        sel = sel[sel["market"] == market]
    if sel.empty:
        print(f"{ticker}: not in the ratio table (not yet collected, or no fundamentals)")
        return
    for _, r in sel.iterrows():
        print(f"\n{r['ticker']} — {r['name'] or '?'} [{r['market']}, {r['currency']}] "
              f"FY {r['fy_end']}, close {r['close']} @ {r['close_date']}")
        for k in ("mcap_local", "pe", "pb", "roe", "roa", "roce", "debt_to_equity",
                  "current_ratio", "gross_margin", "operating_margin", "net_margin",
                  "fcf_yield", "cfo_to_ni", "asset_turnover", "revenue_growth"):
            v = r[k]
            if v is None or pd.isna(v):
                print(f"  {k:18s} —")
            elif k == "mcap_local":
                print(f"  {k:18s} {v:,.0f}")
            else:
                print(f"  {k:18s} {v:.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", help="print one ticker's ratios (from last build)")
    ap.add_argument("--market", default="all", choices=["all", "india", "us"])
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    con = duckdb.connect()

    if (a.ticker or a.status) and OUT_PARQUET.exists():
        df = pd.read_parquet(OUT_PARQUET)
        if a.ticker:
            show_ticker(df, a.ticker, a.market)
        else:
            show_status(df)
        return 0

    print("=== building financial ratios (india + us) ===")
    df = build(con)
    if df.empty:
        print("no store data — run the off-hours collectors first")
        return 1
    write_outputs(con, df)
    show_status(df)
    if a.ticker:
        show_ticker(df, a.ticker, a.market)
    return 0


if __name__ == "__main__":
    sys.exit(main())
