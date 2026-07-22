#!/usr/bin/env python3
"""
pead_sector_spillover.py — two related event-study measurements, both keyed
off the SAME earnings-filing events and the SAME sector-peer construction
already built for cross_sectional_momentum.py (reused, not reimplemented):

  1. PEAD (Post-Earnings-Announcement Drift, Ball & Brown 1968; Bernard &
     Thomas 1989/1990) — after a positive earnings surprise a stock's
     sector-adjusted return keeps DRIFTING UP for weeks afterward (and down
     after a negative surprise), because the market underreacts to the news
     at the announcement itself. Measured here as sector-adjusted CAR over
     [+1,+21]/[+1,+42]/[+1,+63] trading days after the filing, split by
     surprise sign.
  2. Sector-spillover / "sector leader" identification (Foster 1981;
     Thomas & Zhang 2008, "intra-industry information transfers around
     earnings announcements") — when stock A announces, do the OTHER stocks
     in A's sector move too, in the SAME direction as A's surprise? A
     "consistent sector leader" is a stock whose announcements reliably
     move its peers across MULTIPLE separate events, not a one-quarter
     fluke — measured via a same-direction hit-rate across that ticker's
     own announcement history, not a single correlation number.

CAVEAT ON EVENT FREQUENCY: the fundamentals_history collection this repo
has is ANNUAL (one fy_end/filed row per fiscal year), not quarterly 10-Qs —
so this is really "post-ANNUAL-FILING drift," coarser than the classic
quarterly-SUE literature (which gets 4x the events per ticker). Flagged
here rather than silently presented as textbook quarterly PEAD.

DATA / PROXIES:
  US, JP, KR — real 'filed' dates from SEC EDGAR / local-filing collections
               (cache_seed/fundamentals_history/{US,JP,KR}.parquet).
  IN         — screener.in has fy_end but NOT a real filing date; uses the
               same fy_end + 90 calendar-day lag proxy as
               backtest_piotroski_in.py (SEBI LODR: audited annuals filed
               within ~60 days of FY-end; 90 days is the same conservative,
               no-look-ahead margin already used elsewhere in this repo).
               Only 75 India tickers have fundamentals history at all (the
               screener.in collection block noted throughout this session)
               — India's results here will be thin, flagged as such.
  SURPRISE PROXY — no analyst consensus (I/B/E/S) data exists in this
               pipeline, so surprise = YoY net_income growth (a "seasonal
               random walk" proxy for expected earnings, the same
               simplification used in Foster, Olsen & Shevlin (1984) when
               consensus estimates aren't available).
  ABNORMAL RETURN — sector-adjusted (own return minus the equal-weighted,
               leave-one-out return of the OTHER stocks in the same
               sector that day), the same construction already used in
               cross_sectional_momentum.py, not a full CAPM/Fama-French
               residual — a standard short-window event-study
               simplification (Brown & Warner 1980/1985 found simple
               mean/market-adjusted models perform comparably to more
               complex ones at these horizons).
  UNIVERSE — restricted to symbols already sector-classified for
               cross_sectional_momentum.py (cache_seed/sector_map_cache.json)
               so peer groups have both sector labels AND price history
               without a fresh, expensive sector-fetch pass.

Usage:
    python3 pead_sector_spillover.py --market IN US JP KR
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

warnings.filterwarnings("ignore")

import cross_sectional_momentum as csm   # reuse load_close_panel, sector cache

FUND_HIST_DIR = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history"
IN_LAG_DAYS = 90
DRIFT_WINDOWS = {"1mo": 21, "2mo": 42, "3mo": 63}
MIN_EVENTS_FOR_LEADER = 3
MIN_SECTOR_PEERS = 3


def _classified_symbols(market: str) -> dict[str, str]:
    """Symbols already sector-classified for cross_sectional_momentum.py,
    read straight from its cache — no new fetches."""
    cache = csm._load_sector_cache()
    key = f"{market}:"
    return {k[len(key):]: v for k, v in cache.items() if k.startswith(key) and v != "Unknown"}


def load_events(market: str, symbols: set[str]) -> pd.DataFrame:
    df = pd.read_parquet(f"{FUND_HIST_DIR}/{market}.parquet")
    df = df[df["ticker"].isin(symbols)].copy()
    df["net_income"] = pd.to_numeric(df["net_income"], errors="coerce")
    df = df.sort_values(["ticker", "fy_end"])
    df["prior_ni"] = df.groupby("ticker")["net_income"].shift(1)
    df["surprise"] = (df["net_income"] - df["prior_ni"]) / df["prior_ni"].abs()
    df = df.dropna(subset=["surprise"])
    df = df[np.isfinite(df["surprise"])]

    if "filed" in df.columns and df["filed"].notna().any():
        df["event_date"] = pd.to_datetime(df["filed"])
        df["date_is_proxy"] = False
    else:
        df["event_date"] = pd.to_datetime(df["fy_end"]) + pd.Timedelta(days=IN_LAG_DAYS)
        df["date_is_proxy"] = True
    df["surprise_sign"] = np.sign(df["surprise"])
    return df[["ticker", "fy_end", "event_date", "surprise", "surprise_sign", "date_is_proxy"]]


def _sector_leave_one_out_returns(rets: pd.DataFrame, sector_of: dict[str, str]) -> dict[str, pd.Series]:
    """For each sector, the equal-weighted daily return of ITS MEMBERS,
    precomputed once (not per-event) — leave-one-out done at lookup time
    via (sector_sum - own)/(n-1), O(1) per event instead of a groupby scan."""
    sectors = {}
    for sym, sec in sector_of.items():
        if sym in rets.columns:
            sectors.setdefault(sec, []).append(sym)
    sector_sum = {sec: rets[cols].sum(axis=1, skipna=True) for sec, cols in sectors.items()}
    sector_n = {sec: rets[cols].notna().sum(axis=1) for sec, cols in sectors.items()}
    return sectors, sector_sum, sector_n


def run_market(market: str, events_loader=None, top_n: int = 15) -> dict:
    """events_loader(market, symbols_set) -> DataFrame with columns
    [ticker, event_date, surprise, surprise_sign, date_is_proxy] (fy_end
    optional). Defaults to load_events() (annual filing-date + YoY-growth
    proxy) — pead_sector_spillover_v2.py passes a real-quarterly-dates
    loader instead, reusing every line of statistical machinery below
    unchanged (CAR construction, leave-one-out sector benchmark,
    Benjamini-Hochberg FDR correction) so the two runs are apples-to-apples
    comparable, not two independently-written pipelines that might quietly
    diverge in some methodological detail."""
    events_loader = events_loader or load_events
    print(f"\n[{market}] loading classified symbols + price panel...")
    sector_of = _classified_symbols(market)
    if len(sector_of) < 20:
        return {"market": market, "error": f"only {len(sector_of)} classified symbols — run "
                                            f"cross_sectional_momentum.py for this market first"}
    symbols = list(sector_of.keys())
    panel = csm.load_close_panel(market, symbols)
    rets = panel.pct_change()
    print(f"[{market}] panel: {panel.shape[0]} dates x {panel.shape[1]} symbols, "
          f"{len(set(sector_of.values()))} sectors")

    sectors, sector_sum, sector_n = _sector_leave_one_out_returns(rets, sector_of)

    events = events_loader(market, set(sector_of.keys()))
    events = events[events["ticker"].isin(panel.columns)]
    date_is_proxy = bool(events["date_is_proxy"].iloc[0]) if len(events) and "date_is_proxy" in events.columns else None
    print(f"[{market}] {len(events)} earnings events across {events['ticker'].nunique()} tickers "
          f"(proxy filing date: {date_is_proxy})")

    dates = rets.index
    pead_rows = []       # own-stock drift
    spillover_rows = []  # peer reaction per event

    for ev in events.itertuples():
        sym, sec, ev_date, surprise, sign = ev.ticker, sector_of[ev.ticker], ev.event_date, ev.surprise, ev.surprise_sign
        pos = dates.searchsorted(ev_date)
        if pos >= len(dates) or pos == 0:
            continue
        t0 = pos if dates[pos] >= pd.Timestamp(ev_date) else pos  # first trading day >= event date

        # --- peer spillover: peers' leave-one-out return on the event day itself ---
        if sec in sector_sum and t0 < len(dates):
            own_r = rets[sym].iloc[t0] if sym in rets.columns else np.nan
            n_peers = sector_n[sec].iloc[t0] - (1 if pd.notna(own_r) else 0)
            if n_peers >= MIN_SECTOR_PEERS:
                peer_sum = sector_sum[sec].iloc[t0] - (own_r if pd.notna(own_r) else 0)
                peer_mean = peer_sum / n_peers
                same_dir = bool(np.sign(peer_mean) == sign) if peer_mean != 0 else False
                spillover_rows.append({"ticker": sym, "sector": sec, "event_date": ev_date,
                                        "surprise": surprise, "peer_reaction": peer_mean,
                                        "same_direction": same_dir, "n_peers": int(n_peers)})

        # --- own-stock PEAD: sector-adjusted CAR over post-event windows ---
        for label, H in DRIFT_WINDOWS.items():
            end = t0 + H
            if end >= len(dates) or sym not in rets.columns:
                continue
            own_car = np.log(panel[sym].iloc[end] / panel[sym].iloc[t0]) if panel[sym].iloc[t0] > 0 else np.nan
            if sec not in sector_sum:
                continue
            # sector benchmark CAR over the same window (equal-weight, leave-one-out at t0)
            sec_cols = [c for c in sectors.get(sec, []) if c != sym]
            if len(sec_cols) < MIN_SECTOR_PEERS:
                continue
            sec_idx = panel[sec_cols].mean(axis=1, skipna=True)
            if sec_idx.iloc[t0] <= 0 or sec_idx.iloc[end] <= 0:
                continue
            sec_car = np.log(sec_idx.iloc[end] / sec_idx.iloc[t0])
            if pd.isna(own_car):
                continue
            pead_rows.append({"ticker": sym, "sector": sec, "event_date": ev_date,
                               "surprise_sign": sign, "window": label,
                               "abnormal_car": own_car - sec_car})

    pead_df = pd.DataFrame(pead_rows)
    spill_df = pd.DataFrame(spillover_rows)

    # --- aggregate PEAD by surprise sign x window ---
    pead_summary = {}
    if not pead_df.empty:
        for label in DRIFT_WINDOWS:
            for sign_label, sign_val in [("positive_surprise", 1), ("negative_surprise", -1)]:
                sub = pead_df[(pead_df["window"] == label) & (pead_df["surprise_sign"] == sign_val)]
                if len(sub) < 5:
                    continue
                x = sub["abnormal_car"].values
                t = float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if x.std(ddof=1) > 0 else None
                pead_summary[f"{label}_{sign_label}"] = {
                    "n_events": len(sub), "mean_car_pct": round(float(x.mean()) * 100, 4),
                    "tstat": round(t, 3) if t is not None else None,
                    "hit_rate": round(float(np.mean(x * sign_val > 0)), 4)}
        # THE real PEAD test: does the pos-neg SPREAD stay positive and grow
        # with horizon? A generic positive-drift artifact (unrelated to the
        # earnings surprise) shows up as similar CARs for both signs — only
        # a genuine surprise-driven effect produces a persistent, growing gap.
        for label in DRIFT_WINDOWS:
            p, n = pead_summary.get(f"{label}_positive_surprise"), pead_summary.get(f"{label}_negative_surprise")
            if p and n:
                pead_summary[f"{label}_pos_minus_neg_spread_pct"] = round(p["mean_car_pct"] - n["mean_car_pct"], 4)

    # --- aggregate spillover per announcer ticker -> "sector leader" candidates ---
    leaders = []
    n_candidates_tested = 0
    n_fdr_significant = 0
    if not spill_df.empty:
        # Benjamini-Hochberg FDR at q=0.10 across all tickers actually tested,
        # not just the ones that happen to look good — testing ~hundreds of
        # tickers at face-value p<0.05 would produce dozens of false positives
        # from chance alone (multiple-testing correction, not a nice-to-have).
        raw = []
        for sym, g in spill_df.groupby("ticker"):
            if len(g) < MIN_EVENTS_FOR_LEADER:
                continue
            k = int(g["same_direction"].sum())
            n = len(g)
            # one-sided binomial test: is the same-direction hit-rate above
            # the 50% expected under "peers move independently of the news"?
            pval = float(sps.binomtest(k, n, 0.5, alternative="greater").pvalue)
            raw.append({"ticker": sym, "sector": g["sector"].iloc[0], "n_events": n,
                        "same_direction_hit_rate": round(k / n, 3),
                        "mean_abs_peer_reaction_pct": round(float(g["peer_reaction"].abs().mean()) * 100, 4),
                        "binomial_pvalue": pval})
        raw.sort(key=lambda r: r["binomial_pvalue"])
        m = len(raw)
        n_candidates_tested = m
        fdr_q = 0.10
        # standard BH: largest i with p_(i) <= (i/m)*q; reject the i smallest
        cutoff_i = 0
        for i, r in enumerate(raw, start=1):
            if r["binomial_pvalue"] <= (i / m) * fdr_q:
                cutoff_i = i
        for i, r in enumerate(raw, start=1):
            r["fdr_significant"] = i <= cutoff_i
            r["binomial_pvalue"] = round(r["binomial_pvalue"], 5)
        n_fdr_significant = cutoff_i
        leaders = raw

    return {
        "market": market, "n_symbols": len(sector_of), "n_events": len(events),
        "date_is_proxy": date_is_proxy,
        "pead_summary": pead_summary,
        "n_leader_candidates_tested": n_candidates_tested,
        "n_leaders_fdr_significant_q10": n_fdr_significant,
        "top_sector_leaders": leaders[:top_n],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", nargs="+", default=["IN", "US", "JP", "KR"])
    a = ap.parse_args()

    results = []
    for m in a.market:
        try:
            r = run_market(m)
        except Exception as e:
            r = {"market": m, "error": str(e)}
        results.append(r)
        print(f"\n[{m}] DONE: {json.dumps(r, indent=2, default=str)[:3000]}")

    with open("cache_seed/pead_sector_spillover_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n\n" + "=" * 78)
    print("PEAD + SECTOR-SPILLOVER SUMMARY")
    print("=" * 78)
    for r in results:
        if "error" in r:
            print(f"{r['market']}: ERROR {r['error']}")
            continue
        print(f"\n{r['market']}  ({r['n_symbols']} symbols, {r['n_events']} events, "
              f"proxy_date={r['date_is_proxy']})")
        for k, v in r["pead_summary"].items():
            if isinstance(v, dict):
                print(f"  PEAD {k}: n={v['n_events']} car={v['mean_car_pct']:+.3f}% "
                      f"t={v['tstat']} hit={v['hit_rate']:.1%}")
            else:
                print(f"  {k}: {v:+.4f}%  <- must stay positive & grow with horizon for real PEAD")
        print(f"  sector-leader candidates tested: {r['n_leader_candidates_tested']}, "
              f"FDR-significant (q=0.10): {r['n_leaders_fdr_significant_q10']}")
        for l in r["top_sector_leaders"][:5]:
            sig = "***" if l["fdr_significant"] else ""
            print(f"    {l['ticker']:12s} ({l['sector']}) n={l['n_events']} "
                  f"same_dir_hit={l['same_direction_hit_rate']:.1%} p={l['binomial_pvalue']} {sig} "
                  f"|peer_reaction|={l['mean_abs_peer_reaction_pct']:.3f}%")


if __name__ == "__main__":
    main()
