#!/usr/bin/env python3
"""
pead_monitor.py — reacts to NEW earnings filings landing in
fundamentals_history, rather than firing on a blind calendar schedule.
"After every quarter" in practice means "whenever a company's fiscal-year
filing actually shows up in our data" — since collection isn't perfectly
synchronized to calendar quarters, this checks the ACTUAL max filing date
per market against what was seen last time, and only re-runs the (fairly
expensive) PEAD/sector-spillover analysis when something changed.

IMPORTANT DEPENDENCY: this script does NOT itself collect fresh
fundamentals data — it only reacts to fundamentals_history/{market}.parquet
being refreshed by ITS OWN collector:
  US  -> sec_history_collector.py (SEC EDGAR)
  JP  -> the JP fundamentals collector (yf_fundamentals.py-style)
  KR  -> the KR fundamentals collector
  IN  -> screener_history_collector.py (screener.in) — STILL BLOCKED this
         session (75/3,476 tickers, see project memory) — India will keep
         reporting "no new filings" until that collection is unblocked and
         re-run separately. This is a real, not cosmetic, limitation.
If nothing ever re-runs those collectors, this monitor will correctly and
honestly report "no new filings" forever — it is not a substitute for
running them.

STATE: cache_seed/pead_monitor_state.json tracks the last-seen max event
date per market. Each detected change writes a dated snapshot to
cache_seed/pead_snapshots/{market}_{date}.json and diffs it against the
most recent prior snapshot for that market (FDR-significant leader count,
PEAD pos-minus-neg spread sign) — the same statistical discipline
(Benjamini-Hochberg correction, not just "results changed") as the initial
run.

Usage (also the intended cron/launchd entry point):
    python3 pead_monitor.py
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

import pead_sector_spillover as pss

STATE_PATH = Path("cache_seed/pead_monitor_state.json")
SNAP_DIR = Path("cache_seed/pead_snapshots")
SNAP_DIR.mkdir(exist_ok=True)
LOG_PATH = Path("cache_seed/pead_monitor_history.log")


def _latest_event_date(market: str) -> str:
    df = pd.read_parquet(f"{pss.FUND_HIST_DIR}/{market}.parquet")
    if "filed" in df.columns and df["filed"].notna().any():
        return pd.to_datetime(df["filed"]).max().strftime("%Y-%m-%d")
    return (pd.to_datetime(df["fy_end"]).max() + pd.Timedelta(days=pss.IN_LAG_DAYS)).strftime("%Y-%m-%d")


def seed_from_existing_run(existing_results_path: str = "cache_seed/pead_sector_spillover_results.json"):
    """One-time bootstrap: treat an already-computed run as the quarter-0
    baseline instead of discarding it and recomputing on first invocation."""
    if not Path(existing_results_path).exists():
        return
    results = json.loads(Path(existing_results_path).read_text())
    state = {}
    today = date.today().isoformat()
    for r in results:
        if "error" in r:
            continue
        m = r["market"]
        latest = _latest_event_date(m)
        state[m] = latest
        (SNAP_DIR / f"{m}_{today}.json").write_text(json.dumps(r, indent=2, default=str))
    STATE_PATH.write_text(json.dumps(state, indent=2))
    print(f"seeded baseline state from {existing_results_path}: {state}")


def check_and_run(markets=("IN", "US", "JP", "KR")) -> tuple[list[str], list[str]]:
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    today = date.today().isoformat()
    changed, report = [], []

    for m in markets:
        latest = _latest_event_date(m)
        prev = state.get(m)
        if prev == latest:
            report.append(f"{m}: no new filings since {prev}")
            continue

        print(f"[{m}] new filings detected: {prev} -> {latest}, re-running PEAD analysis...")
        r = pss.run_market(m)
        snap_path = SNAP_DIR / f"{m}_{today}.json"
        snap_path.write_text(json.dumps(r, indent=2, default=str))

        prior_snaps = sorted(p for p in SNAP_DIR.glob(f"{m}_*.json") if p != snap_path)
        if prior_snaps:
            prior = json.loads(prior_snaps[-1].read_text())
            prior_fdr = prior.get("n_leaders_fdr_significant_q10", 0)
            new_fdr = r.get("n_leaders_fdr_significant_q10", 0)
            prior_spread = prior.get("pead_summary", {}).get("3mo_pos_minus_neg_spread_pct")
            new_spread = r.get("pead_summary", {}).get("3mo_pos_minus_neg_spread_pct")
            diff_note = (f"FDR-significant leaders {prior_fdr}->{new_fdr} ({new_fdr - prior_fdr:+d}); "
                         f"3mo pos-neg spread {prior_spread}->{new_spread}")
        else:
            diff_note = "(first snapshot for this market — nothing to diff against yet)"

        line = f"{m}: UPDATED ({prev} -> {latest}, {r['n_events']} events). {diff_note}"
        report.append(line)
        changed.append(m)
        state[m] = latest

    STATE_PATH.write_text(json.dumps(state, indent=2))
    with open(LOG_PATH, "a") as f:
        f.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] check run:\n")
        f.write("\n".join(report) + "\n")
    return changed, report


def refresh_key_dates(markets=("IN", "US", "JP", "KR")) -> None:
    """Refresh the next-scheduled-earnings-date parquet table (point
    estimates only — the .calendar RANGE layer makes an extra network call
    per symbol and is deliberately NOT run on this daily cadence to avoid
    piling more load onto the same Yahoo Finance rate limit this monitor
    already has to share with the PEAD event checks above; run
    `earnings_key_dates.py --ranges` by hand when a fresher range layer is
    wanted). Point estimates alone still update daily since they're free —
    derived from whatever earnings_dates_cache.py already has cached, no
    new fetches here."""
    import earnings_key_dates as ekd
    try:
        ekd.refresh_all(markets, with_ranges=False)
    except Exception as e:
        print(f"key-dates refresh failed (non-fatal): {e}")


if __name__ == "__main__":
    changed, report = check_and_run()
    print("\n".join(report))
    print(f"\n{len(changed)} market(s) updated." if changed else "\nNo markets had new filings — nothing to update.")
    refresh_key_dates()
