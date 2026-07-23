#!/usr/bin/env python3
"""
morning_runtimes.py — durable per-run duration ledger for the morning surfaces.

WHY: the pipeline's [STEP] markers time steps WITHIN a run, and n8n keeps
startedAt/stoppedAt per execution — but nothing accumulates run durations
across days, so drift (Korea creeping 3→28 min was found by hand once already)
only shows up when someone diffs artifact mtimes. This appends one row per
finished run to reports/morning_runtimes.csv and prints the recent trend.

SURFACES
  pipeline       daily_pipeline_YYYYMMDD.log sections ("=== Daily pipeline" →
                 "=== done") — every run that day, including manual reruns
  digest_chain   n8n watchlistdigest001 trigger executions (gate → movers →
                 justified → digest)
  backup         n8n dropboxbackup001 trigger executions (backup → GATE)

APPEND-ONLY + IDEMPOTENT: a run already in the ledger (same surface + start
stamp) is never re-added, and in-flight executions (no stoppedAt) are skipped —
they get picked up by the next sweep, so it doesn't matter that the 09:00
backup run can't record its own end mid-run.

Usage:
    /usr/bin/python3 morning_runtimes.py            # sweep + print trend
    /usr/bin/python3 morning_runtimes.py --days 14  # longer trend window
NB: /usr/bin/python3 (pandas lives there and in the venv; sqlite3 is stdlib).
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "reports" / "morning_runtimes.csv"
N8N_DB = Path.home() / ".n8n" / "database.sqlite"
IST = timezone(timedelta(hours=5, minutes=30))

N8N_SURFACES = {"watchlistdigest001": "digest_chain", "dropboxbackup001": "backup"}


def pipeline_runs() -> list[dict]:
    """Every completed run section in the last few days of pipeline logs."""
    rows = []
    for log in sorted(HERE.glob("daily_pipeline_*.log"))[-5:]:
        text = log.read_text(errors="replace")
        # sections: "=== Daily pipeline <date> ===" ... "=== done <date> ==="
        starts = [(m.start(), m.group(1))
                  for m in re.finditer(r"=== Daily pipeline (.+?) ===", text)]
        for i, (pos, start_s) in enumerate(starts):
            end_pos = starts[i + 1][0] if i + 1 < len(starts) else len(text)
            section = text[pos:end_pos]
            done = re.search(r"=== done (.+?) ===", section)
            if not done:
                continue          # still running or killed — next sweep
            try:
                fmt = "%a %b %d %H:%M:%S IST %Y"
                t0 = datetime.strptime(start_s.strip(), fmt)
                t1 = datetime.strptime(done.group(1).strip(), fmt)
            except ValueError:
                continue
            # The [ALERT] trailer is authoritative: guarded steps register
            # failures without printing "failed (continuing)" (the 2026-07-23
            # run had 2 ALERT failures and zero "failed (continuing)" lines —
            # this ledger's first version scored it "ok").
            alert = re.search(r"\[ALERT\] (\d+) step\(s\) failed", section)
            fails = int(alert.group(1)) if alert else \
                len(re.findall(r"failed \(continuing\)", section))
            rows.append({"surface": "pipeline",
                         "started_ist": t0.strftime("%Y-%m-%d %H:%M:%S"),
                         "duration_min": round((t1 - t0).total_seconds() / 60, 1),
                         "status": "ok" if fails == 0 else f"{fails} step-failures",
                         "ref": log.name})
    return rows


def n8n_runs() -> list[dict]:
    if not N8N_DB.exists():
        return []
    con = sqlite3.connect(f"file:{N8N_DB}?mode=ro", uri=True)
    q = """SELECT workflowId, status, startedAt, stoppedAt, id
           FROM execution_entity
           WHERE mode='trigger' AND stoppedAt IS NOT NULL"""
    rows = []
    for wf, status, t0s, t1s, eid in con.execute(q):
        if wf not in N8N_SURFACES:
            continue
        t0 = datetime.fromisoformat(t0s.split(".")[0]).replace(tzinfo=timezone.utc)
        t1 = datetime.fromisoformat(t1s.split(".")[0]).replace(tzinfo=timezone.utc)
        rows.append({"surface": N8N_SURFACES[wf],
                     "started_ist": t0.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S"),
                     "duration_min": round((t1 - t0).total_seconds() / 60, 1),
                     "status": status,
                     "ref": f"n8n exec {eid}"})
    con.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()

    old = pd.read_csv(LEDGER) if LEDGER.exists() else pd.DataFrame(
        columns=["surface", "started_ist", "duration_min", "status", "ref"])
    have = set(zip(old["surface"], old["started_ist"]))
    fresh = [r for r in pipeline_runs() + n8n_runs()
             if (r["surface"], r["started_ist"]) not in have]
    ledger = pd.concat([old, pd.DataFrame(fresh)], ignore_index=True) \
               .sort_values("started_ist")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(LEDGER, index=False)
    print(f"  +{len(fresh)} new run(s) -> {LEDGER.name} ({len(ledger)} total)")

    cutoff = (datetime.now(IST) - timedelta(days=a.days)).strftime("%Y-%m-%d")
    recent = ledger[ledger["started_ist"] >= cutoff]
    print(f"\n=== MORNING RUN DURATIONS (last {a.days}d) ===")
    print(f"  {'STARTED (IST)':20s} {'SURFACE':13s} {'MIN':>7s}  STATUS")
    for _, r in recent.iterrows():
        print(f"  {r['started_ist']:20s} {r['surface']:13s} {r['duration_min']:>7.1f}  {r['status']}")
    if not recent.empty:
        agg = recent.groupby("surface")["duration_min"].agg(["count", "median", "max"])
        print("\n  per-surface: " + " · ".join(
            f"{s} n={int(c)} med={m:.1f}m max={x:.1f}m"
            for s, (c, m, x) in agg.iterrows()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
