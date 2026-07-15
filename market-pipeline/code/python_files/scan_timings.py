#!/usr/bin/env python3
"""
scan_timings.py — per-step run times for the daily pipeline.

WHY
---
Until 2026-07-15 nothing recorded what each step cost. The only evidence was
artifact mtimes, hand-diffed after the fact — which is how Korea sat at 28 minutes
(per-ticker pykrx with a 0.3s sleep x 2,637 tickers) while Europe took 3, unnoticed
for as long as the pipeline has existed. Optimising what you can't measure is
guesswork; this makes each step's cost a number you can watch drift.

TWO SOURCES
-----------
1. MEASURED — `[STEP] <epoch> <iso> <label>` markers emitted by daily_pipeline.sh's
   step() helper. Exact, from 2026-07-15 onward.
2. BACKFILL — older logs predate the markers, so their steps are reconstructed
   from scan-artifact mtimes and the run banner. Clearly labelled `est` because
   they are inferred, not measured: an mtime says when a file was finished, not
   when its step began, and steps that produced no artifact are invisible.

Stores to Postgres market_daily.step_timings when reachable (idempotent per
run_date+step), and always prints a table.

Usage:
    python3 scan_timings.py                 # parse all logs, store, report
    python3 scan_timings.py --report        # report only
    python3 scan_timings.py --slowest 5
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_GLOBS = [str(HERE / "daily_pipeline_*.log"),
             str(Path.home() / "Downloads/code/python_files/daily_pipeline_*.log")]
DSN = "dbname=market_data host=/tmp user=umashankar"

STEP_RE = re.compile(r"^\[STEP\] (\d+) (\S+) (\[[^\]]+\][^\n]*)")
BANNER_RE = re.compile(r"^=== Daily pipeline (.+?) ===")
DONE_RE = re.compile(r"^=== done (.+?) ===")

# step label -> the artifact it produces, for backfilling pre-marker runs
ARTIFACTS = {
    "[2/14]": "indian_full_scan/indian_full_scan_*.xlsx",
    "[4/14]": "us_full_scan/us_full_scan_*.xlsx",
    "[6/14]": "european_scan/european_market_scan*.xlsx",
    "[7/14]": "japan_scan/japan_market_scan_*.xlsx",
    "[8/14]": "korea_scan/korea_market_scan_*.xlsx",
}


def _parse_banner(t: str):
    for fmt in ("%a %b %d %H:%M:%S %Z %Y", "%a %b %e %H:%M:%S %Z %Y"):
        try:
            return _dt.datetime.strptime(t.strip(), fmt)
        except ValueError:
            continue
    return None


def measured(path: Path) -> list:
    """Steps with real [STEP] markers: duration = next marker - this one."""
    marks = []
    for line in path.read_text(errors="replace").splitlines():
        m = STEP_RE.match(line)
        if m:
            marks.append((int(m.group(1)), m.group(3).strip()))
    out = []
    for i, (ts, label) in enumerate(marks):
        if "__end__" in label:
            continue
        nxt = marks[i + 1][0] if i + 1 < len(marks) else None
        if nxt is None:
            continue
        out.append({"step": label, "seconds": nxt - ts, "source": "measured"})
    return out


def backfill(path: Path) -> list:
    """Reconstruct pre-marker runs from artifact mtimes. Inferred, not measured."""
    txt = path.read_text(errors="replace")
    b = BANNER_RE.search(txt)
    d = DONE_RE.search(txt)
    if not b:
        return []
    start = _parse_banner(b.group(1))
    end = _parse_banner(d.group(1)) if d else None
    if not start:
        return []
    day = start.strftime("%Y%m%d")

    # artifacts produced on this run's date, in completion order
    seen = []
    for label, pat in ARTIFACTS.items():
        best = None
        for f in glob.glob(str(HERE / pat)) + glob.glob(
                str(Path.home() / "Downloads/code/python_files" / pat)):
            mt = _dt.datetime.fromtimestamp(os.path.getmtime(f))
            if mt.strftime("%Y%m%d") != day:
                continue
            if start <= mt and (best is None or mt > best):
                best = mt
        if best:
            seen.append((best, label))
    seen.sort()
    out, prev = [], start
    for mt, label in seen:
        out.append({"step": label, "seconds": int((mt - prev).total_seconds()),
                    "source": "est"})
        prev = mt
    if end and seen:
        out.append({"step": "[9-14] correlations+mailer", "source": "est",
                    "seconds": int((end - prev).total_seconds())})
    return out


def collect() -> list:
    rows = []
    files = []
    for g in LOG_GLOBS:
        files.extend(glob.glob(g))
    for f in sorted(set(files)):
        p = Path(f)
        m = re.search(r"(\d{8})", p.name)
        run = m.group(1) if m else "?"
        got = measured(p)
        src = "measured"
        if not got:
            got = backfill(p)
            src = "est"
        for r in got:
            r["run_date"] = f"{run[:4]}-{run[4:6]}-{run[6:]}"
            r["log"] = p.name
            rows.append(r)
    return rows


def store(rows: list) -> str:
    try:
        import duckdb
        c = duckdb.connect()
        c.execute("INSTALL postgres"); c.execute("LOAD postgres")
        c.execute(f"ATTACH '{DSN}' AS pg (TYPE postgres)")
        c.execute('CREATE SCHEMA IF NOT EXISTS pg."market_daily"')
        c.execute('''CREATE TABLE IF NOT EXISTS pg."market_daily".step_timings (
                       run_date DATE, step VARCHAR, seconds BIGINT,
                       source VARCHAR, log VARCHAR)''')
        n = 0
        for r in rows:
            ex = c.execute('SELECT count(*) FROM pg."market_daily".step_timings '
                           'WHERE run_date=? AND step=?',
                           [r["run_date"], r["step"]]).fetchone()[0]
            if ex:
                continue
            c.execute('INSERT INTO pg."market_daily".step_timings VALUES (?,?,?,?,?)',
                      [r["run_date"], r["step"], r["seconds"], r["source"], r["log"]])
            n += 1
        c.close()
        return f"stored {n} new rows (idempotent per run_date+step)"
    except Exception as e:
        return f"not stored ({str(e)[:60]})"


def report(rows: list, slowest: int) -> None:
    if not rows:
        print("  no timings found")
        return
    runs = sorted({r["run_date"] for r in rows})
    print(f"\n=== PER-STEP RUN TIMES ({len(runs)} runs: {', '.join(runs)}) ===")
    print(f"  {'RUN':11s} {'STEP':34s} {'TIME':>9s}  SRC")
    for run in runs:
        rs = [r for r in rows if r["run_date"] == run]
        for r in sorted(rs, key=lambda x: -x["seconds"]):
            s = r["seconds"]
            t = f"{s//60}m {s%60:02d}s" if s >= 60 else f"{s}s"
            print(f"  {run:11s} {r['step'][:34]:34s} {t:>9s}  {r['source']}")
        tot = sum(r["seconds"] for r in rs)
        print(f"  {'':11s} {'TOTAL':34s} {tot//60}m {tot%60:02d}s")
        print()
    agg = {}
    for r in rows:
        agg.setdefault(r["step"], []).append(r["seconds"])
    print(f"=== SLOWEST STEPS (max across runs) ===")
    for step, ss in sorted(agg.items(), key=lambda kv: -max(kv[1]))[:slowest]:
        mx = max(ss)
        print(f"  {step[:36]:36s} max {mx//60}m {mx%60:02d}s   runs={len(ss)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--slowest", type=int, default=6)
    a = ap.parse_args()
    rows = collect()
    if not a.report:
        print("  " + store(rows))
    report(rows, a.slowest)
