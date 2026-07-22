#!/usr/bin/env python3
"""
factor_zscore_panel.py -- Phase 1 of PPO regime-conditional factor-weight
scoring (see /Users/umashankar/.claude/plans/bright-hatching-scone.md).

Builds a curated, z-scored continuous-factor panel for US + India, reusing
factorial_screener_test.py's load_fundamentals()/compute_fundamental_
screens()/attach_market_cap() VERBATIM (not reimplemented) -- same
discipline as every _IN_full/_analysis sibling script this session -- and
factorial_screener_test_IN_full.py's India-only merge_backup_fields() for
industry/receivables/inventory enrichment.

CORRECTIONS TO THE APPROVED PLAN, found while implementing this file:

  1. The plan claimed bhavcopy's raw cached CSVs (~/Downloads/data/
     bhavcopy_cache/{nse,bse}/*.csv) already contain DELIV_PER (India
     delivery %) and only need a re-parse ("zero new network calls").
     Checked a live NSE and BSE cached day-file directly (2026-07-19):
     neither has a delivery-quantity column -- the unified "F_0000"
     bhavcopy schema (TradDt...Rsvd4, see bhavcopy_history.py's own
     OHLC_MAP) does not carry it. NSE publishes delivery position as a
     SEPARATE report ("Security-wise Delivery Position",
     sec_bhavdata_full_DDMMYYYY.csv), never collected here. This is a
     genuine NEW collection, not a re-parse -- out of scope for this pass,
     same tier as the plan's own already-acknowledged bulk/block-deals
     gap. Flagged here, not silently dropped.

  2. The plan assumed a Damodaran industry P/B benchmark table exists
     alongside pe/roe/beta/margin. Checked DAMO_FILES in reference_data.py:
     only pe, roe, beta, margin, wacc are fetched -- no P/B file. Sector-
     relative P/B (and P/E, for consistency) is instead computed from
     WITHIN THIS PANEL's own (Industry Group, fiscal year) cross-section,
     which sidesteps reconciling Damodaran's ~90-bucket industry taxonomy
     against this panel's own Industry Group values (company_industry()
     is exact-match only, no fuzzy join exists in this codebase).

METHODOLOGY:
  - Curated factor set (~15% coverage floor, per the approved plan):
    pb_ratio, pe_ttm, roe, roic, operating_margin, net_margin, de_ratio,
    rev_growth, eps_growth, ebit_growth (+ fcf_yield, US only -- India's
    capex coverage is ~1%, making FCF unusable there).
  - has_<factor>: boolean, true wherever the raw value is non-null BEFORE
    any z-scoring or winsorizing -- lets the downstream RL env see which
    factors actually existed for a row, instead of treating missing as 0.
  - Winsorize (1st/99th pct, within non-null values) before z-scoring --
    same convention as factorial_screener_analysis.py's winsorize(), a
    few extreme filings (mcap/ratio artifacts from stale or split-
    contaminated prices) would otherwise dominate every z-score.
  - z_<factor>: z-scored within its own non-null values, market-wide.
  - sector_z_<factor> (pb_ratio, pe_ttm only): z-scored within (Industry
    Group, fiscal year) instead of market-wide -- operationalizes "P/B
    needs sector context" from the user's own pasted material. Falls back
    to NaN (not the market-wide z) when a row has no Industry Group match
    or its industry-year cell has fewer than MIN_SECTOR_CELL rows -- an
    unreliable sector mean is worse than an honest missing value.
  - Damodaran Industry Group join: damodaran_companies.parquet, matched on
    bare ticker, Exchange=='NSEI' for India (confirmed NSEI tickers use
    the same bare-symbol convention as this warehouse, e.g. RELIANCE,
    20MICRONS) and Country=='United States' for US (confirmed NasdaqGS/
    NasdaqGM/NYSE/OTCPK tickers match this warehouse's bare US tickers
    directly) -- both spot-checked against the cached parquet, 2026-07-19.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/umashankar/market-pipeline/code/python_files")
import factorial_screener_test as fst  # noqa: E402
import factorial_screener_test_IN as fst_in  # noqa: E402
import factorial_screener_test_IN_full as fst_in_full  # noqa: E402
# NOTE: importing factorial_screener_test_IN_full monkeypatches fst.FUND_PATH
# to IN.parquet as a MODULE-LEVEL side effect (its own line 61). build_us_
# panel() below explicitly restores fst.FUND_PATH before every US load, so
# import order here does not silently corrupt the US run.

US_FUND_PATH = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/US.parquet"
DAMO_COMPANIES_PATH = "/Users/umashankar/repos/global-stock-screener/reference_seed/damodaran_companies.parquet"

CURATED_FACTORS_COMMON = [
    "pb_ratio", "pe_ttm", "roe", "roic", "operating_margin", "net_margin",
    "de_ratio", "rev_growth", "eps_growth", "ebit_growth",
]
US_ONLY_FACTORS = ["fcf_yield"]
SECTOR_RELATIVE_FACTORS = ["pb_ratio", "pe_ttm"]  # the ones with a real sector-dependence story
MIN_SECTOR_CELL = 5  # below this, an (Industry Group, year) mean isn't trustworthy


def _winsorize(s: pd.Series, lower=0.01, upper=0.99) -> pd.Series:
    """Cap extreme values at the 1st/99th percentile of the NON-NULL values
    only -- same convention as factorial_screener_analysis.py's winsorize()."""
    valid = s.dropna()
    if len(valid) < 20:
        return s
    lo, hi = valid.quantile(lower), valid.quantile(upper)
    return s.clip(lo, hi)


def build_us_panel() -> pd.DataFrame:
    print("=== US: loading fundamentals + OHLCV, computing screens ===")
    fst.FUND_PATH = US_FUND_PATH
    fund = fst.load_fundamentals()
    ohlcv = fst.load_ohlcv()
    scored = fst.compute_fundamental_screens(fund)
    merged = fst.attach_market_cap(scored, ohlcv)
    merged["market"] = "us"
    return merged


def build_india_panel() -> pd.DataFrame:
    print("\n=== India: loading fundamentals + OHLCV, computing screens ===")
    fst.FUND_PATH = fst_in_full.FUND_PATH_IN
    fund = fst.load_fundamentals()
    ohlcv = fst_in.load_ohlcv_in()
    fund = fst_in_full.merge_backup_fields(fund)
    scored = fst.compute_fundamental_screens(fund)
    merged = fst.attach_market_cap(scored, ohlcv)
    merged = fst_in_full.fix_currency_scaled_thresholds(merged)
    merged = fst_in_full.add_working_capital_ratios(merged)
    merged["market"] = "india"
    return merged


def attach_industry(panel: pd.DataFrame) -> pd.DataFrame:
    """Join Damodaran Industry Group by bare ticker, market-specific
    exchange filter (see module docstring for why these two filters are
    the right ones for this warehouse's ticker convention)."""
    damo = pd.read_parquet(DAMO_COMPANIES_PATH)[["Ticker", "Exchange", "Country", "Industry Group"]]
    damo_us = (damo[damo["Country"] == "United States"][["Ticker", "Industry Group"]]
               .drop_duplicates("Ticker").rename(columns={"Ticker": "ticker"}))
    damo_in = (damo[damo["Exchange"] == "NSEI"][["Ticker", "Industry Group"]]
               .drop_duplicates("Ticker").rename(columns={"Ticker": "ticker"}))

    us_part = panel[panel["market"] == "us"].merge(damo_us, on="ticker", how="left")
    in_part = panel[panel["market"] == "india"].merge(damo_in, on="ticker", how="left")
    out = pd.concat([us_part, in_part], ignore_index=True)
    matched = out["Industry Group"].notna()
    for mkt in ("us", "india"):
        sub = out[out["market"] == mkt]
        n_tickers = sub["ticker"].nunique()
        n_matched = sub.loc[sub["Industry Group"].notna(), "ticker"].nunique()
        print(f"  {mkt}: {n_matched:,}/{n_tickers:,} tickers matched to a Damodaran Industry Group "
              f"({n_matched / n_tickers * 100:.1f}%)")
    out = out.rename(columns={"Industry Group": "industry_group"})
    return out


def add_zscores(panel: pd.DataFrame, factors: list[str]) -> pd.DataFrame:
    df = panel.copy()
    df["fy_year"] = pd.to_datetime(df["fy_end"]).dt.year

    for f in factors:
        if f not in df.columns:
            print(f"  [skip] {f}: not present in panel for this market")
            continue
        df[f"has_{f}"] = df[f].notna() & np.isfinite(df[f].replace([np.inf, -np.inf], np.nan))
        raw = df[f].where(df[f"has_{f}"])
        wins = raw.groupby(df["market"]).transform(_winsorize)
        mean = wins.groupby(df["market"]).transform("mean")
        std = wins.groupby(df["market"]).transform("std")
        df[f"z_{f}"] = ((wins - mean) / std).where(std > 0)

        if f in SECTOR_RELATIVE_FACTORS and "industry_group" in df.columns:
            cell = df.groupby(["market", "industry_group", "fy_year"])
            cell_n = cell[f].transform("count")
            cell_mean = wins.groupby([df["market"], df["industry_group"], df["fy_year"]]).transform("mean")
            cell_std = wins.groupby([df["market"], df["industry_group"], df["fy_year"]]).transform("std")
            sector_z = ((wins - cell_mean) / cell_std).where((cell_std > 0) & (cell_n >= MIN_SECTOR_CELL))
            df[f"sector_z_{f}"] = sector_z

    return df


def report_coverage(df: pd.DataFrame, factors: list[str]) -> None:
    for mkt in df["market"].unique():
        sub = df[df["market"] == mkt]
        print(f"\n  {mkt} (n={len(sub):,} filings, {sub['ticker'].nunique():,} tickers):")
        for f in factors:
            col = f"has_{f}"
            if col not in sub.columns:
                continue
            pct = sub[col].mean() * 100
            flag = "  <-- BELOW 15% FLOOR" if pct < 15 else ""
            print(f"    {f:<20s} {pct:5.1f}% populated{flag}")


def main():
    us = build_us_panel()
    india = build_india_panel()
    panel = pd.concat([us, india], ignore_index=True, sort=False)
    panel = attach_industry(panel)

    all_factors = CURATED_FACTORS_COMMON + US_ONLY_FACTORS
    panel = add_zscores(panel, all_factors)

    print("\n=== Coverage report (curated factor set) ===")
    report_coverage(panel, CURATED_FACTORS_COMMON)
    india_us_only_check = panel[panel["market"] == "india"]["fcf_yield"].notna().mean() * 100
    print(f"\n  India fcf_yield populated: {india_us_only_check:.1f}% "
          f"(excluded from India's factor set per the approved plan -- capex "
          f"coverage too sparse for a reliable FCF-based ratio there)")

    keep_cols = (
        ["ticker", "market", "fy_end", "filed", "industry_group", "fy_year"]
        + all_factors
        + [f"has_{f}" for f in all_factors]
        + [f"z_{f}" for f in all_factors]
        + [f"sector_z_{f}" for f in SECTOR_RELATIVE_FACTORS]
    )
    keep_cols = [c for c in keep_cols if c in panel.columns]
    out = panel[keep_cols].dropna(subset=["filed"]).sort_values(["market", "ticker", "fy_end"])

    out_path = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/factor_zscore_panel.parquet"
    out.to_parquet(out_path, index=False)
    print(f"\nSaved {len(out):,} rows -> {out_path}")

    print("\n=== Spot-check: AAPL (US), RELIANCE (India), latest filing each ===")
    for tkr in ("AAPL", "RELIANCE"):
        row = out[out["ticker"] == tkr].sort_values("fy_end").tail(1)
        if row.empty:
            print(f"  {tkr}: not found in panel")
            continue
        r = row.iloc[0]
        print(f"  {tkr} (fy_end={r['fy_end'].date()}, industry={r.get('industry_group')}):")
        for f in all_factors:
            if f in r.index and pd.notna(r.get(f"z_{f}", np.nan)):
                print(f"    {f}: raw={r[f]:.3f}  z={r[f'z_{f}']:.2f}"
                      + (f"  sector_z={r[f'sector_z_' + f]:.2f}"
                         if f"sector_z_{f}" in r.index and pd.notna(r[f"sector_z_{f}"]) else ""))


if __name__ == "__main__":
    main()
