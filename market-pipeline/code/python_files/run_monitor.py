#!/usr/bin/env python3
# run_monitor.py
# ==============
# Runtime monitor across all four pipeline sections.
#
# WHY THIS EXISTS
# ───────────────
# Before the [STEP] markers, the only evidence of what a step cost was artifact
# mtimes hand-diffed after the fact — which is how the Korea scan sat at 28
# minutes unnoticed while Europe took 3. The markers made durations measurable;
# this reads them back.
#
# Splitting one pipeline into four made this necessary rather than merely useful:
# with a single log you could eyeball the trailer, but four sections on three
# schedules need something that answers "what ran, when, and did it get slower"
# in one place.
#
#   run_monitor.py                 # last run of each section
#   run_monitor.py --section mailer --history 10
#   run_monitor.py --slowest 15    # worst steps across all sections
#   run_monitor.py --json
#
# Reads <section>_pipeline_YYYYMMDD.log, plus legacy daily_pipeline_*.log so
# history from before the split stays visible.
#
# stdlib only.

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent

# New format carries the section:  [STEP] <epoch> <iso> <section> <label>
# Legacy format does not:          [STEP] <epoch> <iso> <label>
STEP_RE = re.compile(r"^\[STEP\] (\d+) (\S+) (.*)$")
DONE_RE = re.compile(r"^=== done (?:(\S+) )?(.+?) ===")
SECTIONS = ("ingest", "mailer", "modelling", "factor_tests")


def _logs() -> List[Path]:
    out = []
    for s in SECTIONS:
        out += [Path(p) for p in glob.glob(str(HERE / f"{s}_pipeline_*.log"))]
    # Pre-split history: one combined log per day.
    out += [Path(p) for p in glob.glob(str(HERE / "daily_pipeline_*.log"))]
    return sorted(out, key=lambda p: p.name)


def _section_of(path: Path, marker_section: Optional[str]) -> str:
    if marker_section and marker_section in SECTIONS:
        return marker_section
    name = path.name
    for s in SECTIONS:
        if name.startswith(f"{s}_pipeline_"):
            return s
    return "daily (pre-split)"


def parse(path: Path) -> Optional[dict]:
    """One log -> {section, date, steps[{label, start, dur}], total}.

    Duration is the delta to the NEXT marker, so the final step needs the
    __end__ marker to be knowable. Pre-split logs have no __end__, so their last
    step's duration is reported as None rather than guessed from the trailer —
    a step that ran until the log ended is not the same as one that finished.
    """
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None

    marks: List[tuple] = []
    section = None
    for line in text.splitlines():
        m = STEP_RE.match(line)
        if not m:
            continue
        epoch, _iso, rest = int(m.group(1)), m.group(2), m.group(3).strip()
        parts = rest.split(None, 1)
        if parts and parts[0] in SECTIONS:
            section = parts[0]
            label = parts[1] if len(parts) > 1 else ""
        else:
            label = rest
        marks.append((epoch, label))

    if not marks:
        return None

    steps = []
    for i, (epoch, label) in enumerate(marks):
        if label == "__end__":
            continue
        nxt = marks[i + 1][0] if i + 1 < len(marks) else None
        steps.append({"label": label, "start": epoch,
                      "dur": (nxt - epoch) if nxt is not None else None})

    total = marks[-1][0] - marks[0][0]
    return {"section": _section_of(path, section), "log": path.name,
            "date": path.name.split("_")[-1].replace(".log", ""),
            "steps": steps, "total": total,
            "complete": any(l == "__end__" for _, l in marks)}


def _fmt(sec: Optional[int]) -> str:
    if sec is None:
        return "    ?"
    if sec < 90:
        return f"{sec:4d}s"
    return f"{sec // 60:4d}m"


def show_run(r: dict, verbose: bool = True) -> None:
    flag = "" if r["complete"] else "   ⚠️  no __end__ marker — run did not finish cleanly"
    print(f"\n  {r['section']:<18} {r['date']}   total {_fmt(r['total'])}   ({r['log']}){flag}")
    if not verbose:
        return
    for s in r["steps"]:
        bar = ""
        if s["dur"]:
            bar = "█" * min(40, max(1, s["dur"] // 60))
        print(f"     {_fmt(s['dur'])}  {s['label'][:52]:<52} {bar}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Pipeline runtime monitor")
    ap.add_argument("--section", choices=SECTIONS)
    ap.add_argument("--history", type=int, default=1,
                    help="how many past runs per section (default: 1)")
    ap.add_argument("--slowest", type=int, metavar="N",
                    help="show the N slowest steps across all runs instead")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    runs = [r for r in (parse(p) for p in _logs()) if r]
    if args.section:
        runs = [r for r in runs if r["section"] == args.section]
    if not runs:
        print("  no [STEP]-marked logs found")
        return 1

    if args.json:
        print(json.dumps(runs, indent=2))
        return 0

    if args.slowest:
        allsteps = []
        for r in runs:
            for s in r["steps"]:
                if s["dur"]:
                    allsteps.append((s["dur"], r["section"], r["date"], s["label"]))
        allsteps.sort(reverse=True)
        print("=" * 78)
        print(f"  SLOWEST {args.slowest} STEPS (all sections, all runs)")
        print("=" * 78)
        for dur, sec, date, label in allsteps[:args.slowest]:
            print(f"  {_fmt(dur)}  {sec:<18} {date}  {label[:44]}")
        return 0

    # Latest N runs per section, newest first.
    by_section: Dict[str, List[dict]] = defaultdict(list)
    for r in runs:
        by_section[r["section"]].append(r)

    print("=" * 78)
    print("  PIPELINE RUNTIME MONITOR")
    print("=" * 78)
    for sec in sorted(by_section):
        for r in sorted(by_section[sec], key=lambda x: x["date"], reverse=True)[:args.history]:
            show_run(r, verbose=True)

    # Cross-run trend: is a section getting slower?
    print("\n" + "=" * 78)
    print("  TOTALS BY SECTION")
    print("=" * 78)
    for sec in sorted(by_section):
        hist = sorted(by_section[sec], key=lambda x: x["date"])[-5:]
        line = "  ".join(f"{h['date'][-4:]}:{_fmt(h['total']).strip()}" for h in hist)
        print(f"   {sec:<18} {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
