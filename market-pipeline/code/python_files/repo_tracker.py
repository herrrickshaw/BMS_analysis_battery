#!/usr/bin/env python3
# repo_tracker.py
# ===============
# What is in this repo, what is wired into a pipeline section, and what has
# drifted out of the conventions that keep the sections runnable.
#
# WHY THIS EXISTS
# ───────────────
# ~200 scripts, four sections, and no way to answer "is this file still used?"
# without reading all of them. The concrete costs so far:
#
#   * market_data_cache.py hardcoded ~/Downloads/market_cache while its five
#     siblings honoured $MARKET_CACHE. Nothing compared them, so the drift was
#     invisible until launchd hit TCC and the US scan died mid-run.
#   * Orphaned outputs accumulated until they had to be swept up in bulk (see
#     commits 302d9e2a, e84c81d5).
#   * market_ingest.py is nobody's scheduled job, so the warehouse silently went
#     6-7 days stale.
#
# The checks below are regression guards for exactly those, not general lint:
#
#   repo_tracker.py              # full report
#   repo_tracker.py --paths      # hardcoded-path audit only (the US-scan bug class)
#   repo_tracker.py --orphans    # scripts no section invokes
#   repo_tracker.py --json
#
# Exits non-zero when a hardcoded-path violation is found, so it can run as a
# pre-commit or CI check.
#
# stdlib only.

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set

HERE = Path(__file__).resolve().parent
SECTION_SCRIPTS = ["ingest.sh", "mailer.sh", "modelling.sh", "factor_tests.sh"]

# A python module named on a section script's command line.
INVOKE_RE = re.compile(r"\$PY\s+(?:-\S+\s+)*([A-Za-z_][\w]*\.py)")
# Also catch `import x as s; s.f()` one-liners run via $PY -c.
IMPORT_IN_C_RE = re.compile(r"import\s+([a-z_][\w]*)")

# Two severities, because they are two different problems and conflating them
# buries the one that actually breaks the nightly run:
#
#   FATAL — resolves under ~/Downloads. macOS TCC denies launchd ALL access
#           there, so under the scheduler this raises PermissionError. This is
#           the exact bug that killed the US scan on 2026-07-20.
#   DRIFT — some other absolute /Users/... path. Runs fine today (it points at
#           the migrated tree), but it is unrelocatable and invisible to the
#           registry. A latent version of the same mistake, not an outage.
#
# Comments and docstrings are excluded — the registry and this file both quote
# these paths in prose on purpose.
TCC_FATAL_RE = re.compile(r'Path\.home\(\)\s*/\s*"Downloads"|"/Users/[a-z]+/Downloads/')
ABS_DRIFT_RE = re.compile(r'"/Users/[a-z]+/')
ENV_IDIOM_RE = re.compile(r'environ\.get\(\s*"(MARKET_CACHE|BHAV_CACHE|FUND_HIST_DIR|PGDSN)"')


def _py_files() -> List[Path]:
    return sorted(p for p in HERE.glob("*.py") if not p.name.startswith("."))


def section_wiring() -> Dict[str, Set[str]]:
    """section script -> set of .py modules it invokes."""
    wiring: Dict[str, Set[str]] = {}
    for s in SECTION_SCRIPTS:
        p = HERE / s
        if not p.exists():
            continue
        text = p.read_text(errors="replace")
        mods = set(INVOKE_RE.findall(text))
        for m in IMPORT_IN_C_RE.findall(text):
            if (HERE / f"{m}.py").exists():
                mods.add(f"{m}.py")
        wiring[s] = mods
    return wiring


def _code_lines(text: str) -> List[tuple]:
    """[(original_lineno, line)] for executable lines only.

    Comments and triple-quoted blocks are dropped: the registry, this file, and
    most of the analysis scripts quote ~/Downloads paths in prose. A guard that
    flags its own documentation gets muted, and a muted guard catches nothing.

    ORIGINAL line numbers are carried through deliberately. The first version of
    this scanned stripped text and reported indices into it, which pointed at
    unrelated code — train_ppo_walk_forward.py:121 landed on a walk-forward loop
    with no path in it. A tracker that misreports locations is worse than none,
    because the numbers look authoritative.
    """
    out: List[tuple] = []
    in_doc, doc_delim = False, ""
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if in_doc:
            if doc_delim in s:
                in_doc = False
            continue
        if s.startswith(('"""', "'''")):
            delim = s[:3]
            body = s[3:]
            # A one-line docstring closes on the same line; anything else opens a block.
            if delim not in body:
                in_doc, doc_delim = True, delim
            continue
        if s.startswith("#") or not s:
            continue
        # Strip trailing comments so a path mentioned after code isn't counted.
        out.append((i, line.split("  #")[0]))
    return out


def path_audit() -> List[dict]:
    """Files with a hardcoded home path and no env-var escape hatch."""
    findings = []
    for p in _py_files():
        try:
            raw = p.read_text(errors="replace")
        except OSError:
            continue
        code = _code_lines(raw)
        joined = "\n".join(l for _, l in code)
        has_escape = bool(ENV_IDIOM_RE.search(joined))

        fatal = [n for n, l in code if TCC_FATAL_RE.search(l)]
        drift = [n for n, l in code if ABS_DRIFT_RE.search(l) and not TCC_FATAL_RE.search(l)]
        if not fatal and not drift:
            continue

        # An env-var escape only excuses the FATAL class — it is what lets the
        # path relocate out of ~/Downloads. It does nothing for a bare absolute.
        if fatal and not has_escape:
            sev = "TCC-FATAL"
        elif fatal:
            sev = "OK-ish"
        else:
            sev = "DRIFT"

        findings.append({
            "file": p.name,
            "lines": (fatal or drift)[:6],
            "fatal_lines": fatal[:6],
            "drift_lines": drift[:6],
            "has_env_escape": has_escape,
            "severity": sev,
        })
    order = {"TCC-FATAL": 0, "DRIFT": 1, "OK-ish": 2}
    return sorted(findings, key=lambda f: (order[f["severity"]], f["file"]))


def orphans() -> List[str]:
    """.py files no section invokes and nothing imports.

    Import-reachability is one level deep on purpose: a module imported by a
    wired script is reachable, but this is not a call-graph analysis and should
    not be read as one. It answers "obviously unused", not "safe to delete".
    """
    wired: Set[str] = set()
    for mods in section_wiring().values():
        wired |= mods

    all_py = {p.name for p in _py_files()}
    imported: Set[str] = set()
    for name in wired:
        p = HERE / name
        if not p.exists():
            continue
        for m in re.findall(r"^\s*(?:import|from)\s+([a-z_][\w]*)",
                            p.read_text(errors="replace"), re.M):
            if f"{m}.py" in all_py:
                imported.add(f"{m}.py")

    infra = {"data_registry.py", "data_index.py", "run_monitor.py", "repo_tracker.py",
             "pipeline_lib.sh", "send_alert.py", "send_mailer.py", "check_deps.py",
             "validate_brief.py", "consistency_audit.py"}
    return sorted(all_py - wired - imported - infra)


def git_state() -> dict:
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=HERE,
                             capture_output=True, text=True, timeout=20).stdout
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=HERE,
                                capture_output=True, text=True, timeout=20).stdout.strip()
        mod = [l for l in out.splitlines() if l.startswith(" M")]
        untracked = [l for l in out.splitlines() if l.startswith("??")]
        return {"branch": branch, "modified": len(mod), "untracked": len(untracked)}
    except Exception as e:
        return {"error": str(e)[:60]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Repo wiring and path-drift tracker")
    ap.add_argument("--paths", action="store_true", help="hardcoded-path audit only")
    ap.add_argument("--orphans", action="store_true", help="unwired scripts only")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    pa, orph, wiring = path_audit(), orphans(), section_wiring()
    violations = [f for f in pa if f["severity"] == "TCC-FATAL"]
    drift = [f for f in pa if f["severity"] == "DRIFT"]

    if args.json:
        print(json.dumps({"path_audit": pa, "orphans": orph,
                          "wiring": {k: sorted(v) for k, v in wiring.items()},
                          "git": git_state()}, indent=2))
        # Always 0: the caller is reading the JSON, and a non-zero exit on a
        # machine-readable dump reads as "the tool broke" to every wrapper.
        return 0

    if args.paths or not (args.orphans):
        print("=" * 78)
        print("  HARDCODED-PATH AUDIT  (the bug class that killed the US scan)")
        print("=" * 78)
        print("\n  TCC-FATAL — resolves under ~/Downloads, raises PermissionError under launchd")
        if not violations:
            print("     none — every ~/Downloads literal has a $MARKET_CACHE/$BHAV_CACHE escape")
        for f in violations:
            print(f"     ❌ {f['file']:<40} lines {f['fatal_lines']}")

        print(f"\n  DRIFT — hardcoded absolute path, runs today but unrelocatable ({len(drift)})")
        for f in drift[:20]:
            wired_in = [s for s, m in wiring.items() if f["file"] in m]
            tag = f"  ← wired into {', '.join(wired_in)}" if wired_in else ""
            print(f"     ·  {f['file']:<40} lines {f['drift_lines']}{tag}")
        if len(drift) > 20:
            print(f"     ... and {len(drift) - 20} more")

        soft = [f for f in pa if f["severity"] == "OK-ish"]
        if soft:
            print(f"\n  OK — {len(soft)} file(s) name a ~/Downloads default but honour the env idiom:")
            print("     " + ", ".join(f["file"] for f in soft[:14]))
        if args.paths:
            return 1 if violations else 0

    if args.orphans or not args.paths:
        print("\n" + "=" * 78)
        print("  SECTION WIRING")
        print("=" * 78)
        for s in SECTION_SCRIPTS:
            mods = sorted(wiring.get(s, []))
            print(f"\n  {s}  ({len(mods)} scripts)")
            for m in mods:
                mark = " " if (HERE / m).exists() else "❌"
                print(f"     {mark} {m}")

        print("\n" + "=" * 78)
        print(f"  UNWIRED SCRIPTS ({len(orph)})")
        print("=" * 78)
        print("  Not invoked by any section and not imported by one that is.")
        print("  Reachability is one level deep — 'obviously unused', not 'safe to delete'.\n")
        for o in orph[:40]:
            print(f"     {o}")
        if len(orph) > 40:
            print(f"     ... and {len(orph) - 40} more")

    g = git_state()
    print("\n" + "=" * 78)
    print(f"  GIT: branch {g.get('branch','?')} · {g.get('modified','?')} modified · "
          f"{g.get('untracked','?')} untracked")
    print("=" * 78)
    # Non-zero only when the path audit was actually requested — --orphans asks a
    # different question and should not inherit the guard's exit code.
    return 1 if (violations and not args.orphans) else 0


if __name__ == "__main__":
    sys.exit(main())
