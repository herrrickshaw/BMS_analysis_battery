#!/usr/bin/env python3
"""
earnings_price_dataset.py — the final consolidated dataset: for every
symbol with a known earnings date (from ANY source collected this
session), the price change around that date, computed directly from the
already-local LTM OHLCV panels (repos/global-market-data/cache_seed/ltm/
{market}.parquet) — NO new network calls, pure local computation, so this
can run immediately and re-run cheaply as more date coverage lands from
the still-running yahooquery/DART/NSE/SEC background collections.

SOURCES UNIONED PER MARKET (first match wins per ticker+quarter, order
reflects how authoritative/precise each source's DATE is — note NONE of
the date-only sources carry a surprise number, so they contribute date-only
rows; a symbol can appear with price-change data even with surprise_pct
null):
  1. earnings_dates_yahooquery_full/{m}.parquet  — full-universe batch
     (real reportedDate + surprisePct together)
  2. earnings_dates_cache/{m}.parquet             — yfinance per-ticker
     (real Earnings Date + Surprise(%), classified-subset scale)
  3. earnings_dates_nse/IN.parquet (India only)   — NSE actual_result
     filingDate, no surprise number (date-only cross-check/fill)
  4. earnings_dates_sec_8k/US.parquet (US only)   — SEC 8-K Item 2.02
     filing_date, no surprise number (date-only cross-check/fill)
  5. earnings_dates_dart/KR.parquet (Korea only)  — DART periodic-report
     filing_date, no surprise number (date-only cross-check/fill)

PRICE-CHANGE WINDOWS: 1-day (announcement reaction), 5-day (~1 week), and
21-day (~1 month) forward log-returns from the LTM close-price panel,
computed as log(close[t+H] / close[t]) where t is the first trading day
on/after the earnings date. Symbols whose earnings date falls in the last
21 trading days of available history won't have a full 21-day window —
those cells are left null rather than computed on a truncated window.

OUTPUT: cache_seed/earnings_price_dataset/{market}.parquet — columns:
  ticker, market, earnings_date, source, surprise_pct,
  price_change_1d, price_change_5d, price_change_21d

Usage:
    python3 earnings_price_dataset.py --market IN US JP KR
"""
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from regime_price_model import CIRCUIT_BOUND_PCT  # {"IN":20.0,"KR":30.0,"US":100.0,"JP":50.0}, literature-backed

LTM_DIR = "/Users/umashankar/repos/global-market-data/cache_seed/ltm"
OUT_DIR = Path("cache_seed/earnings_price_dataset")
OUT_DIR.mkdir(parents=True, exist_ok=True)
WINDOWS = {"1d": 1, "5d": 5, "21d": 21}

# Sanity bound on surprise_pct — the classic tiny-EPS-estimate-denominator
# artifact (flagged earlier this session in earnings_calendar.py: QDEL
# showed +207%, ROKU +93%, NAGE +184% from real-but-tiny estimate bases;
# here yfinance_cache alone produced -6902%/-5097%/-3618% for Korea names,
# unambiguously a near-zero-denominator artifact, not a real earnings
# surprise). Same "flag, don't display" discipline as
# build_mailer.py's _CIRCUIT_BREAKER_PCT and factor_growth_risk.py's
# Altman Z-Score bound — nulled, not silently passed through.
SURPRISE_PCT_SANITY_BOUND = 500.0

# price_change_* sanity bound, reusing the SAME literature-backed circuit-
# breaker constants regime_price_model.py already established (IN/KR are
# exact regulatory single-day limits, US/JP are conservative heuristics —
# see that file's docstring for citations) rather than inventing a second,
# possibly-inconsistent bound. Applied per market so all four get sanitized
# by their OWN real regime, not one blanket cutoff that would be wrong for
# a market with no daily price cap (US) or a tighter one (India).
# Confirmed empirically before adding this: IN showed a -69.2% ONE-DAY move
# (impossible under India's 20% limit) and KR showed the exact same 230.3%
# value repeated across the 1d/5d/AND 21d windows for one bad print
# (impossible under KRX's hard 30% daily limit) -- both unambiguous data
# errors (bad split adjustment / corrupted price row), not real trading.
# 5d/21d use a worst-case "N consecutive limit days" ceiling (multiplicative
# compounding of the same daily bound) rather than the 1-day bound directly,
# since a genuine multi-day drift can legitimately exceed one day's limit.
def _price_change_bound_pct(market: str, window_days: int) -> float:
    daily_pct = CIRCUIT_BOUND_PCT.get(market, 20.0) / 100
    return float(np.log((1 + daily_pct) ** window_days) * 100)


def _load_yahooquery_full(market: str) -> pd.DataFrame:
    """Unions the full-universe run with the classified-subset run (both
    same schema, same source, different symbol scope/timing) -- NOT a
    strict superset relationship: a market can succeed in one run and be
    fully rate-limited in the other. Confirmed empirically for Korea:
    earnings_dates_yahooquery_full/KR.parquet has 2,600 tickers but 0 with
    real historical data (that run was completely blocked), while
    earnings_dates_yahooquery/KR.parquet (classified-subset, run earlier
    under different rate-limit conditions) has 656 real events across 579
    tickers. Reading only the full-universe file silently dropped Korea's
    best yahooquery source from this dataset."""
    frames = []
    for p in (Path(f"cache_seed/earnings_dates_yahooquery_full/{market}.parquet"),
              Path(f"cache_seed/earnings_dates_yahooquery/{market}.parquet")):
        if p.exists():
            frames.append(pd.read_parquet(p).dropna(subset=["reported_date"]))
    if not frames:
        return pd.DataFrame(columns=["ticker", "earnings_date", "surprise_pct", "source"])
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["ticker", "period_end_date"])
    return pd.DataFrame({
        "ticker": df["ticker"], "earnings_date": pd.to_datetime(df["reported_date"]).dt.tz_localize(None),
        "surprise_pct": df["surprise_pct"], "source": "yahooquery_full",
    })


def _load_yfinance_cache(market: str) -> pd.DataFrame:
    p = Path(f"cache_seed/earnings_dates_cache/{market}.parquet")
    if not p.exists():
        return pd.DataFrame(columns=["ticker", "earnings_date", "surprise_pct", "source"])
    df = pd.read_parquet(p).copy()
    df["Reported EPS"] = pd.to_numeric(df["Reported EPS"], errors="coerce")
    df["Surprise(%)"] = pd.to_numeric(df["Surprise(%)"], errors="coerce")
    df = df.dropna(subset=["Reported EPS"])
    return pd.DataFrame({
        "ticker": df["ticker"], "earnings_date": pd.to_datetime(df["Earnings Date"]).dt.tz_localize(None),
        "surprise_pct": df["Surprise(%)"], "source": "yfinance_cache",
    })


def _load_date_only(path: str, ticker_col: str, date_col: str, source_name: str,
                     filter_fn=None) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=["ticker", "earnings_date", "surprise_pct", "source"])
    df = pd.read_parquet(p)
    if filter_fn is not None:
        df = filter_fn(df)
    df = df.dropna(subset=[date_col])
    # some NSE result rows carry a literal "-" placeholder instead of a real
    # filingDate — coerce rather than crash, drop what fails to parse
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    out = pd.DataFrame({
        "ticker": df[ticker_col], "earnings_date": parsed,
        "surprise_pct": np.nan, "source": source_name,
    }).dropna(subset=["earnings_date"])
    out["earnings_date"] = out["earnings_date"].dt.tz_localize(None)
    return out


def load_all_events(market: str) -> pd.DataFrame:
    parts = [_load_yahooquery_full(market), _load_yfinance_cache(market)]
    if market == "IN":
        parts.append(_load_date_only(
            "cache_seed/earnings_dates_nse/IN.parquet", "symbol", "event_date", "nse",
            filter_fn=lambda d: d[d["event_type"] == "actual_result"]))
    if market == "US":
        parts.append(_load_date_only(
            "cache_seed/earnings_dates_sec_8k/US.parquet", "ticker", "filing_date", "sec_8k",
            filter_fn=lambda d: d[d["is_earnings_8k"] == True]))  # noqa: E712
    if market == "KR":
        parts.append(_load_date_only(
            "cache_seed/earnings_dates_dart/KR.parquet", "ticker", "filing_date", "dart",
            # DART's 기재정정 (amendment/correction) filings re-file an
            # ALREADY-counted quarterly/half-year/annual report, not a new
            # earnings event -- confirmed empirically: 2,124/22,642 raw DART
            # rows are amendments, and unlike the other three markets'
            # date-only sources (NSE actual_result, SEC 8-K Item 2.02, both
            # already one-event-per-filing) Korea's raw feed was silently
            # counting the correction as a second event. Excluding them
            # brings Korea back to the same "one row per genuine filing"
            # granularity as IN/US.
            filter_fn=lambda d: d[~d["report_name"].str.contains("기재정정", na=False)]))
    combined = pd.concat(parts, ignore_index=True)
    combined = combined.dropna(subset=["ticker", "earnings_date"])
    bad_surprise = combined["surprise_pct"].abs() > SURPRISE_PCT_SANITY_BOUND
    if bad_surprise.any():
        combined.loc[bad_surprise, "surprise_pct"] = np.nan  # flagged, not displayed
    # de-dup: same ticker within the same week counts as one event. Keep the
    # row with a real surprise_pct over one without, and among rows that both
    # have a real surprise_pct, keep by SOURCE PRIORITY (yahooquery_full >
    # yfinance_cache > date-only sources) per this module's own docstring --
    # NOT by sorting on the surprise_pct VALUE itself (confirmed bug, caught
    # by code review: sort_values("surprise_pct") sorts by magnitude/sign, so
    # keep="first" kept whichever source happened to report the numerically
    # smallest value, e.g. a -3% yfinance row beating a +5% yahooquery row
    # purely because -3 < +5 -- silently flipping the surprise sign fed into
    # pead_sector_spillover_v4.py regardless of which source is authoritative).
    SOURCE_PRIORITY = {"yahooquery_full": 0, "yfinance_cache": 1}
    combined["_has_surprise"] = combined["surprise_pct"].notna()
    combined["_src_rank"] = combined["source"].map(SOURCE_PRIORITY).fillna(9)
    combined = combined.sort_values(["_has_surprise", "_src_rank"], ascending=[False, True])
    combined["date_bucket"] = combined["earnings_date"].dt.to_period("W").astype(str)
    combined = combined.drop_duplicates(subset=["ticker", "date_bucket"], keep="first")
    return combined.drop(columns=["date_bucket", "_has_surprise", "_src_rank"])


def compute_price_changes(market: str, events: pd.DataFrame) -> pd.DataFrame:
    panel = pd.read_parquet(f"{LTM_DIR}/{market}.parquet", columns=["Date", "Symbol", "Close"])
    panel = panel.dropna(subset=["Close"])
    panel = panel[panel["Symbol"].isin(events["ticker"].unique())]
    wide = panel.pivot_table(index="Date", columns="Symbol", values="Close").sort_index()
    dates = wide.index

    rows = []
    for row in events.itertuples(index=False):
        sym = row.ticker
        if sym not in wide.columns:
            continue
        col = wide[sym]
        pos = dates.searchsorted(row.earnings_date)
        if pos >= len(dates):
            continue
        t0 = pos
        base = col.iloc[t0]
        out = {"ticker": sym, "market": market, "earnings_date": row.earnings_date,
               "source": row.source, "surprise_pct": row.surprise_pct}
        for label, H in WINDOWS.items():
            end = t0 + H
            if end >= len(dates) or pd.isna(base) or base <= 0:
                out[f"price_change_{label}"] = None
                continue
            fut = col.iloc[end]
            chg = (float(np.log(fut / base)) * 100) if pd.notna(fut) and fut > 0 else None
            if chg is not None and abs(chg) > _price_change_bound_pct(market, H):
                chg = None  # flagged as a data error, not displayed -- see _price_change_bound_pct
            out[f"price_change_{label}"] = chg
        rows.append(out)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    a = ap.parse_args()

    compiled = []
    for m in a.market:
        events = load_all_events(m)
        print(f"[{m}] {events['ticker'].nunique()} tickers, {len(events)} events "
              f"(sources: {events['source'].value_counts().to_dict()})")
        df = compute_price_changes(m, events)
        # granularity flag: every market's raw feed mixes surprise-bearing
        # rows (yahooquery/yfinance) with date-only cross-check rows
        # (NSE/SEC-8K/DART) in wildly different proportions -- KR is ~94%
        # date-only, JP has NONE at all. Any cross-market comparison MUST
        # filter on this rather than treat "n_events" as apples-to-apples.
        df["has_surprise"] = df["surprise_pct"].notna()
        out_path = OUT_DIR / f"{m}.parquet"
        df.to_parquet(out_path, index=False)
        n_with_surprise = int(df["has_surprise"].sum())
        n_with_1d = df["price_change_1d"].notna().sum()
        print(f"[{m}] -> {out_path}: {len(df)} rows, {df['ticker'].nunique()} tickers, "
              f"{n_with_surprise} with surprise% ({n_with_surprise/len(df):.1%}), "
              f"{n_with_1d} with a computed 1d price change")
        compiled.append(df)

    if compiled:
        all_df = pd.concat(compiled, ignore_index=True)
        all_path = OUT_DIR / "ALL.parquet"
        all_df.to_parquet(all_path, index=False)
        print(f"\n-> {all_path}: {len(all_df)} rows across {all_df['market'].nunique()} markets, "
              f"same schema/columns/sanitization applied uniformly "
              f"(surprise% bound={SURPRISE_PCT_SANITY_BOUND}, price-change bound=per-market circuit regime)")
        print("\nCross-market granularity (use has_surprise to filter to comparable rows):")
        summary = all_df.groupby("market").agg(
            tickers=("ticker", "nunique"), rows=("ticker", "size"),
            surprise_bearing=("has_surprise", "sum")).reset_index()
        summary["surprise_bearing_pct"] = (summary["surprise_bearing"] / summary["rows"] * 100).round(1)
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
