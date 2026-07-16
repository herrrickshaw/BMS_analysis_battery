#!/usr/bin/env python3
"""
pead_walkforward_validate.py — out-of-sample validation of the sector-
spillover "leader" candidates from pead_sector_spillover_v3.py, focused on
MCHP/ANET/WDAY (US Technology), the only 3 tickers that have survived
three separate full-sample re-runs of that script (p=1e-05, 0.00046,
0.00046, FDR-significant at q=0.10 every time).

WHY: every number pead_sector_spillover*.py has reported so far is
IN-SAMPLE — the same events used to compute a ticker's same-direction
hit-rate are the events used to test its significance. Surviving several
re-runs on growing data is reassuring but is not a held-out test. Two
distinct threats need checking before trusting this as a real effect:

  A. CONSTRUCTION CONFOUND — same_direction = sign(peer_reaction) ==
     sign(own surprise). MCHP/ANET/WDAY's surprise sign is almost always
     +1 (26/28, 28/28, 27/28), so same_direction collapses to roughly
     "was the sector up on this stock's earnings day" — which in a
     multi-year tech bull market could be elevated for ANY stock's
     earnings days, not evidence these 3 specifically move their peers.
  B. TEMPORAL INSTABILITY — the standard walk-forward question: is the
     effect stable across time, or concentrated in a handful of quarters
     that happened to dominate the full-sample fit?

FOUR CHECKS, in order of how directly they attack the confound in (A)
before getting to the temporal question in (B):

  1. Negative-surprise days: on the FEW quarters where each ticker missed
     estimates, did peer_reaction actually flip negative too? If the
     hit-rate is just riding a positive sector trend, negative-surprise
     days should NOT show the same pattern.
  2. Unconditional base rate: P(Technology leave-one-out return > 0) on
     ANY trading day in the panel, vs. the ~82-89% hit rate observed
     specifically on these tickers' earnings days. If close, the hit rate
     is just sector drift; if the earnings-day rate is well above the
     base rate, that's the elevation a genuine spillover effect predicts.
  3. Within-sector peer comparison: other Technology-sector candidates
     with the same n=28 events (MPWR, MRVL) — do they show similarly
     inflated hit rates? If yes, this is a sector-wide/earnings-season
     artifact, not something specific to MCHP/ANET/WDAY.
  4. Temporal train/test split: the full US event history's median date
     as a cutoff, re-running pead_sector_spillover.py's EXACT statistical
     core (unchanged, via the existing events_loader plug-in point) on
     each half independently. Do MCHP/ANET/WDAY clear significance in
     BOTH halves, and do they remain FDR-significant if candidates are
     selected fresh in each fold?

Usage:
    python3 pead_walkforward_validate.py --market US
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

import cross_sectional_momentum as csm
import pead_sector_spillover as pss
import pead_sector_spillover_v3 as v3

TARGET = ["MCHP", "ANET", "WDAY"]


def _panel_and_sectors(market: str):
    sector_of = pss._classified_symbols(market)
    symbols = list(sector_of.keys())
    panel = csm.load_close_panel(market, symbols)
    rets = panel.pct_change()
    sectors, sector_sum, sector_n = pss._sector_leave_one_out_returns(rets, sector_of)
    return sector_of, rets, sectors, sector_sum, sector_n


def per_event_detail(market: str, tickers: list[str]) -> pd.DataFrame:
    sector_of, rets, sectors, sector_sum, sector_n = _panel_and_sectors(market)
    events = v3.load_combined_events(market, set(sector_of.keys()))
    events = events[events["ticker"].isin(tickers)]
    dates = rets.index
    rows = []
    for ev in events.itertuples():
        sym, sec = ev.ticker, sector_of[ev.ticker]
        ev_date, surprise, sign = ev.event_date, ev.surprise, ev.surprise_sign
        pos = dates.searchsorted(ev_date)
        if pos >= len(dates) or pos == 0 or sec not in sector_sum:
            continue
        t0 = pos
        own_r = rets[sym].iloc[t0] if sym in rets.columns else np.nan
        n_peers = sector_n[sec].iloc[t0] - (1 if pd.notna(own_r) else 0)
        if n_peers < pss.MIN_SECTOR_PEERS:
            continue
        peer_sum = sector_sum[sec].iloc[t0] - (own_r if pd.notna(own_r) else 0)
        peer_mean = peer_sum / n_peers
        same_dir = bool(np.sign(peer_mean) == sign) if peer_mean != 0 else False
        rows.append({"ticker": sym, "event_date": ev_date, "surprise": surprise,
                      "surprise_sign": sign, "peer_reaction_pct": peer_mean * 100,
                      "same_direction": same_dir})
    return pd.DataFrame(rows).sort_values(["ticker", "event_date"])


def unconditional_base_rate(market: str, sector_name: str) -> tuple[float, int]:
    _, _, _, sector_sum, sector_n = _panel_and_sectors(market)
    sec_ret = (sector_sum[sector_name] / sector_n[sector_name]).dropna()
    return float((sec_ret > 0).mean()), len(sec_ret)


def _date_filtered_loader(start=None, end=None):
    def _loader(market, symbols):
        df = v3.load_combined_events(market, symbols)
        if start is not None:
            df = df[df["event_date"] >= start]
        if end is not None:
            df = df[df["event_date"] < end]
        return df
    return _loader


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="US")
    a = ap.parse_args()
    market = a.market

    print("=" * 78)
    print("CHECK 1: negative-surprise days — does peer_reaction actually flip sign?")
    print("=" * 78)
    detail = per_event_detail(market, TARGET)
    for tk in TARGET:
        sub = detail[detail.ticker == tk]
        neg = sub[sub.surprise_sign < 0]
        print(f"\n{tk}: {len(sub)} total events, {len(neg)} negative-surprise events")
        if len(neg):
            print(neg[["event_date", "surprise", "peer_reaction_pct", "same_direction"]].to_string(index=False))
        else:
            print("  (no negative-surprise events — this check can't discriminate for this ticker)")

    print("\n" + "=" * 78)
    print("CHECK 2: unconditional sector base rate vs. observed earnings-day hit rate")
    print("=" * 78)
    base_rate, n_days = unconditional_base_rate(market, "Technology")
    print(f"P(Technology leave-one-out return > 0 on ANY trading day) = {base_rate:.3f} (n={n_days} days)")
    with open("cache_seed/pead_sector_spillover_v3_results.json") as f:
        full_results = json.load(f)
    us_full = [r for r in full_results if r["market"] == market][0]
    for l in us_full["top_sector_leaders"]:
        if l["ticker"] in TARGET:
            print(f"  {l['ticker']}: observed hit_rate={l['same_direction_hit_rate']:.3f} vs "
                  f"base_rate={base_rate:.3f}  (elevation={l['same_direction_hit_rate']-base_rate:+.3f})")

    print("\n" + "=" * 78)
    print("CHECK 3: other Technology-sector candidates with n=28 events (sector-wide artifact test)")
    print("=" * 78)
    tech_peers = [l for l in us_full["top_sector_leaders"] if l["sector"] == "Technology"]
    for l in tech_peers:
        flag = " <- TARGET" if l["ticker"] in TARGET else ""
        print(f"  {l['ticker']:8s} n={l['n_events']:3d} hit={l['same_direction_hit_rate']:.3f} "
              f"p={l['binomial_pvalue']:.5f} fdr_sig={l['fdr_significant']}{flag}")

    print("\n" + "=" * 78)
    print("CHECK 4: temporal walk-forward split (train/test at median event date)")
    print("=" * 78)
    full_events = v3.load_combined_events(market, set(pss._classified_symbols(market).keys()))
    cutoff = full_events["event_date"].median()
    print(f"cutoff (median of all {len(full_events)} {market} events) = {cutoff}")

    train_res = pss.run_market(market, events_loader=_date_filtered_loader(end=cutoff), top_n=1000)
    test_res = pss.run_market(market, events_loader=_date_filtered_loader(start=cutoff), top_n=1000)

    def show(res, label):
        print(f"\n[{label}] n_candidates_tested={res['n_leader_candidates_tested']} "
              f"fdr_significant={res['n_leaders_fdr_significant_q10']}")
        for l in res["top_sector_leaders"]:
            if l["ticker"] in TARGET:
                print(f"  {l['ticker']}: n={l['n_events']} hit={l['same_direction_hit_rate']:.3f} "
                      f"p={l['binomial_pvalue']:.5f} fdr_sig={l['fdr_significant']}")
        sig = sorted(l["ticker"] for l in res["top_sector_leaders"] if l.get("fdr_significant"))
        print(f"  ALL fdr-significant tickers in this fold ({len(sig)}): {sig}")

    show(train_res, "TRAIN (earlier half)")
    show(test_res, "TEST (later half)")

    out = {
        "market": market, "cutoff_date": str(cutoff),
        "unconditional_base_rate_technology": base_rate,
        "negative_surprise_events": detail[detail.surprise_sign < 0].to_dict("records"),
        "train": {k: v for k, v in train_res.items() if k != "pead_summary"},
        "test": {k: v for k, v in test_res.items() if k != "pead_summary"},
    }
    with open("cache_seed/pead_walkforward_validate_results.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\n-> cache_seed/pead_walkforward_validate_results.json")


if __name__ == "__main__":
    main()
