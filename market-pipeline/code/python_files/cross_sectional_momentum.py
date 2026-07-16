#!/usr/bin/env python3
"""
cross_sectional_momentum.py — peer (sector-relative) momentum test, run
because regime_price_model.py's single-stock time-series test (yesterday's
own return -> tomorrow's own return) found no edge in any of the four
markets. That is NOT the same test as classic cross-sectional momentum
(Jegadeesh & Titman 1993, JF) or its sector-neutral form, industry momentum
(Moskowitz & Grinblatt 1999, JF): those compare a stock's recent return to
its SECTOR PEERS' recent returns, not to its own past — a stock can show
zero autocorrelation in its own returns while still reliably out- or
under-performing its peer group. This script runs that different test.

METHOD (industry/sector-neutral momentum, [MG99]-style)
---------------------------------------------------------
For each market (IN/US/JP/KR) and each formation horizon H in {3, 5, 10, 21}
trading days (~3 days / 1 week / 2 weeks / 1 month):
  1. At each REBALANCE date (stepped every H days, non-overlapping — avoids
     the overlapping-window autocorrelation that would otherwise inflate
     apparent significance), compute each stock's trailing H-day return.
  2. WITHIN EACH SECTOR (GICS-style, from yfinance .info, cached), rank
     stocks by trailing return:
       n >= 6 peers  -> top/bottom TERCILE = winners/losers
       3 <= n < 6    -> top 1 / bottom 1 stock = winner/loser
       n < 3         -> sector skipped that date (not enough peers to rank)
  3. Forward H-day return (the NEXT, non-overlapping H days) is measured for
     the winner and loser groups, equal-weighted.
  4. The sector-neutral long-short spread (winners minus losers) is averaged
     ACROSS ALL SECTORS on that date, giving one observation per rebalance
     date. This is exactly the sector-neutral construction in [MG99] — it
     cancels out sector-level moves (e.g. all of Tech moving together) and
     isolates PEER-RELATIVE momentum specifically.
Aggregated across all rebalance dates: mean spread, t-stat (spread / (std/
sqrt(n))), and hit-rate (% of periods the winner group beat the loser
group) — the three numbers a real momentum effect needs to show together
(non-zero mean, t-stat that survives the n-periods available, hit-rate
consistently above 50%).

Full history is used (2016-2026, not train<=2023/test>=2024) because this is
a DESCRIPTIVE FACTOR BACKTEST (does the effect exist at all in this data),
the same convention as this repo's other factor backtests (sweep_*.py,
backtest_piotroski_in.py) — not a fitted model being asked to generalize,
so there is no in-sample/out-of-sample split to violate.

SECTOR DATA: yfinance .info (sector field), fetched once per symbol and
cached to cache_seed/sector_map_cache.json — the same source and caching
pattern as sector_analysis.py already in this repo, reused via
stock_utils.parallel_map rather than reimplemented.

Usage:
    python3 cross_sectional_momentum.py --market IN US JP KR --sample 300
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from stock_utils import parallel_map

LTM_DIR = "/Users/umashankar/repos/global-market-data/cache_seed/ltm"
LIQ_INDEX = "cache_seed/liquidity_index.parquet"
SECTOR_CACHE_PATH = Path("cache_seed/sector_map_cache.json")
HORIZONS = {"3d": 3, "1w": 5, "2w": 10, "1mo": 21}
MIN_TERCILE_N = 6
MIN_SECTOR_N = 3


def _yf_ticker(market: str, symbol: str) -> str:
    if market == "IN":
        return f"{symbol}.NS"
    return symbol   # US bare; JP/KR already suffixed (.T / .KS/.KQ) in our data


def _load_sector_cache() -> dict:
    if SECTOR_CACHE_PATH.exists():
        try:
            return json.loads(SECTOR_CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_sector_cache(d: dict):
    SECTOR_CACHE_PATH.write_text(json.dumps(d))


def _fetch_one(args) -> tuple | None:
    market, symbol = args
    try:
        import yfinance as yf
        from yf_session import configure_yfinance, call_with_backoff
        configure_yfinance()
        info = call_with_backoff(lambda: yf.Ticker(_yf_ticker(market, symbol)).info)
        sector = info.get("sector") or "Unknown"
        return (symbol, sector)
    except Exception:
        return None


def fetch_sectors(market: str, symbols: list[str], workers: int = 8) -> dict[str, str]:
    cache = _load_sector_cache()
    key = f"{market}:"
    have = {s: v for s, v in cache.items() if s.startswith(key)}
    missing = [s for s in symbols if f"{key}{s}" not in cache]
    if missing:
        print(f"  [{market}] fetching sectors for {len(missing)} symbols (cached: {len(have)})...")
        results = parallel_map(lambda s: _fetch_one((market, s)), missing,
                               workers=workers, progress_every=50, label=f"{market} sectors")
        for sym, sector in results:
            cache[f"{key}{sym}"] = sector
        _save_sector_cache(cache)
    return {s: cache.get(f"{key}{s}", "Unknown") for s in symbols}


def pick_liquid_sample(market: str, n: int) -> list[str]:
    idx = pd.read_parquet(LIQ_INDEX)
    idx = idx[idx["Market"] == market].sort_values("turnover_usd", ascending=False)
    return idx["Symbol"].head(n).tolist()


def pick_tier_sample(market: str, tier: str, n: int) -> list[str]:
    """Large/mid/small-cap proxy via liquidity.py's EXACT High/Medium/Low
    turnover cutoffs (same per-market USD thresholds used everywhere else
    in this codebase — build_mailer.py's Liquidity column, the earlier
    regime_price_model_filtered_eval.py tiering) rather than an arbitrary
    percentile split, so "High/Medium/Low" means the same thing here as it
    does in the mailer. Liquidity is a PROXY for cap size, not identical to
    it (a large-cap with unusually thin trading could land in Medium) —
    flagged here, not papered over."""
    import liquidity as liq
    idx = pd.read_parquet(LIQ_INDEX)
    idx = idx[idx["Market"] == market].copy()
    idx["tier"] = [liq.tier(t, market) for t in idx["turnover_usd"]]
    sub = idx[idx["tier"] == tier].sort_values("turnover_usd", ascending=False)
    return sub["Symbol"].head(n).tolist()


def load_close_panel(market: str, symbols: list[str]) -> pd.DataFrame:
    df = pd.read_parquet(f"{LTM_DIR}/{market}.parquet", columns=["Date", "Symbol", "Close"])
    df = df[df["Symbol"].isin(symbols)].dropna(subset=["Close"])
    panel = df.pivot_table(index="Date", columns="Symbol", values="Close")
    return panel.sort_index()


def run_horizon(panel: pd.DataFrame, sector_of: dict[str, str], H: int) -> dict:
    trailing = panel / panel.shift(H) - 1
    forward = panel.shift(-H) / panel - 1
    rebal_dates = panel.index[::H]

    sectors = {}
    for sym, sec in sector_of.items():
        sectors.setdefault(sec, []).append(sym)
    sectors = {s: cols for s, cols in sectors.items() if s != "Unknown" and len(cols) >= MIN_SECTOR_N}

    period_spreads, period_winner, period_loser = [], [], []
    for dt in rebal_dates:
        if dt not in trailing.index or dt not in forward.index:
            continue
        tr_row = trailing.loc[dt]
        fw_row = forward.loc[dt]
        sector_winner_rets, sector_loser_rets = [], []
        for sec, cols in sectors.items():
            cols_here = [c for c in cols if c in tr_row.index]
            sub = tr_row[cols_here].dropna()
            if len(sub) < MIN_SECTOR_N:
                continue
            sub_sorted = sub.sort_values(ascending=False)
            if len(sub_sorted) >= MIN_TERCILE_N:
                k = max(1, len(sub_sorted) // 3)
                winners, losers = sub_sorted.index[:k], sub_sorted.index[-k:]
            else:
                winners, losers = sub_sorted.index[:1], sub_sorted.index[-1:]
            w_fwd = fw_row[winners].dropna()
            l_fwd = fw_row[losers].dropna()
            if len(w_fwd) == 0 or len(l_fwd) == 0:
                continue
            sector_winner_rets.append(w_fwd.mean())
            sector_loser_rets.append(l_fwd.mean())
        if not sector_winner_rets:
            continue
        w_mean = float(np.mean(sector_winner_rets))
        l_mean = float(np.mean(sector_loser_rets))
        period_winner.append(w_mean)
        period_loser.append(l_mean)
        period_spreads.append(w_mean - l_mean)

    if len(period_spreads) < 5:
        return {"n_periods": len(period_spreads), "insufficient": True}

    spreads = np.array(period_spreads)
    n = len(spreads)
    mean_spread = float(spreads.mean())
    std_spread = float(spreads.std(ddof=1))
    tstat = mean_spread / (std_spread / np.sqrt(n)) if std_spread > 0 else np.nan
    hit_rate = float(np.mean(spreads > 0))
    return {
        "n_periods": n,
        "mean_winner_fwd_ret_pct": round(float(np.mean(period_winner)) * 100, 4),
        "mean_loser_fwd_ret_pct": round(float(np.mean(period_loser)) * 100, 4),
        "mean_spread_pct": round(mean_spread * 100, 4),
        "spread_tstat": round(float(tstat), 3) if not np.isnan(tstat) else None,
        "hit_rate": round(hit_rate, 4),
    }


def run_market(market: str, sample: int, tier: str | None = None) -> dict:
    tag = f"{market}/{tier}" if tier else market
    if tier:
        print(f"\n[{tag}] sampling up to {sample} symbols from the {tier} liquidity tier...")
        symbols = pick_tier_sample(market, tier, sample)
    else:
        print(f"\n[{tag}] sampling {sample} most-liquid symbols...")
        symbols = pick_liquid_sample(market, sample)
    if len(symbols) < MIN_SECTOR_N * 3:
        return {"market": market, "tier": tier, "error": f"only {len(symbols)} symbols in tier"}

    sector_of = fetch_sectors(market, symbols)
    n_sectors = len(set(v for v in sector_of.values() if v != "Unknown"))
    n_unknown = sum(1 for v in sector_of.values() if v == "Unknown")
    print(f"[{tag}] {len(symbols)} symbols, {n_sectors} sectors, {n_unknown} unclassified")

    panel = load_close_panel(market, symbols)
    print(f"[{tag}] price panel: {panel.shape[0]} dates x {panel.shape[1]} symbols")

    out = {"market": market, "tier": tier, "n_symbols": len(symbols), "n_sectors": n_sectors,
           "n_unclassified": n_unknown, "n_dates": int(panel.shape[0])}
    for label, H in HORIZONS.items():
        r = run_horizon(panel, sector_of, H)
        out[label] = r
        print(f"[{tag}] {label} (H={H}d): {r}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--tiers", nargs="+", default=None,
                     help="e.g. --tiers High Medium Low (liquidity.py's exact per-market "
                          "cutoffs, a large/mid/small-cap proxy). Omit to run the single "
                          "most-liquid sample as before (backward compatible).")
    ap.add_argument("--out", default="cache_seed/cross_sectional_momentum_results.json")
    a = ap.parse_args()

    results = []
    tiers = a.tiers or [None]
    for m in a.market:
        for t in tiers:
            try:
                results.append(run_market(m, a.sample, tier=t))
            except Exception as e:
                results.append({"market": m, "tier": t, "error": str(e)})

    with open(a.out, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n\n" + "=" * 78)
    print("CROSS-SECTIONAL (SECTOR-PEER) MOMENTUM SUMMARY")
    print("=" * 78)
    for r in results:
        tag = f"{r['market']}/{r['tier']}" if r.get("tier") else r["market"]
        if "error" in r:
            print(f"{tag}: ERROR {r['error']}")
            continue
        print(f"\n{tag}  ({r['n_symbols']} symbols, {r['n_sectors']} sectors)")
        for label in HORIZONS:
            h = r.get(label, {})
            if h.get("insufficient"):
                print(f"  {label}: insufficient periods ({h.get('n_periods')})")
                continue
            print(f"  {label}: spread={h['mean_spread_pct']:+.3f}%  t={h['spread_tstat']}  "
                  f"hit_rate={h['hit_rate']:.1%}  n_periods={h['n_periods']}")


if __name__ == "__main__":
    main()
