#!/usr/bin/env python3
"""
check_deps.py — fail LOUDLY at startup when a pipeline dependency is missing.

WHY THIS EXISTS
---------------
Every step in daily_pipeline.sh is guarded with `|| echo "... failed (continuing)"`
so one market's hiccup can't sink the run. That resilience has a cost: a missing
dependency looks exactly like a bad network day. The step logs one line, the
pipeline moves on, and the market silently goes stale — for days.

Four dependencies were found missing this way on 2026-07-15 alone:
  networkx   -> all 5 correlation scans dead ("ModuleNotFoundError" x5 in the log)
  lmdb       -> "LMDB store not synced", OHLCV store never written
  duckdb     -> absent from the venv entirely (only /usr/bin/python3 has it)
  pykrx      -> UNDECLARED in requirements.txt; full_korea_market_scan.py aborted
                with "pip install pykrx" and produced NO output for the day

None of these were noticed from the log. That is the failure this script prevents.

WHAT IT DOES
------------
Walks the pipeline's entry scripts, follows LOCAL imports transitively (so
indirect deps like feedparser-via-sentiment_pipeline are caught), and reports
exactly which pipeline STEPS break for each missing module.

An import wrapped in try/except is treated as OPTIONAL — that is the author's own
signal that the code degrades without it (kabupy has a JPX fallback; lmdb only
skips a cache sync). Everything else is REQUIRED.

Exit codes:
  0  all required deps present (optional ones may be missing; still reported)
  1  a required dependency is missing -> the caller should shout, not shrug

Usage:
    python3 check_deps.py            # human readable, loud
    python3 check_deps.py --json     # machine readable
    python3 check_deps.py --quiet    # only print when something is wrong
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOME = HERE.parents[2]                     # portfolio_analysis lives at ~/ (parents[3] in callers)

# pipeline step -> entry script, mirroring daily_pipeline.sh
STEPS = {
    "1  India EOD refresh":      "bhavcopy_history.py",
    "2  India screener scan":    "scan_bhavcopy.py",
    "3  India combined report":  "daily_combined_report.py",
    "4  US market scan":         "full_us_market_scan.py",
    "6  Europe market scan":     "full_european_market_scan.py",
    "7  Japan market scan":      "full_japan_market_scan.py",
    "8  Korea market scan":      "full_korea_market_scan.py",
    "9  Correlation scans (x5)": "market_correlation_scan.py",
    "14 Build + send mailer":    "build_mailer.py",
}

# stdlib we must not flag. sys.stdlib_module_names exists on 3.10+; 3.9 needs help.
_STDLIB = set(getattr(sys, "stdlib_module_names", ())) | set(sys.builtin_module_names) | {
    "os", "sys", "json", "time", "re", "math", "csv", "io", "glob", "argparse", "ast",
    "pathlib", "typing", "datetime", "collections", "itertools", "functools", "warnings",
    "subprocess", "concurrent", "threading", "random", "smtplib", "email", "zipfile",
    "hashlib", "plistlib", "textwrap", "statistics", "dataclasses", "shutil", "urllib",
    "ssl", "logging", "copy", "string", "decimal", "traceback", "tempfile", "base64",
    "unicodedata", "importlib", "contextlib", "enum", "abc", "pickle", "sqlite3",
    "operator", "html", "http", "socket", "uuid", "calendar", "gzip", "struct", "codecs",
}


def _local_modules() -> set:
    mods = {p.stem for p in HERE.glob("*.py")}
    mods |= {p.stem for p in HOME.glob("*.py")}      # portfolio_analysis etc.
    return mods


def _imported(node) -> list:
    if isinstance(node, ast.Import):
        return [a.name.split(".")[0] for a in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module.split(".")[0]]
    return []


def _handler_is_fatal(handlers) -> bool:
    """True when an except block exits or re-raises — i.e. the dep is mandatory.

    THIS is the signal, not the mere presence of try/except. Compare, both real:

        try: from pykrx import stock          try: from openpyxl.styles import ...
        except ImportError:                   except ImportError:
            sys.exit("pip install pykrx")         OPENPYXL_OK = False
        # FATAL -> required                    # graceful -> optional

    Treating "wrapped in try" as optional would have marked pykrx optional — the
    exact dependency whose absence silently produced no Korea output on 2026-07-15.
    """
    for h in handlers:
        for sub in ast.walk(h):
            if isinstance(sub, ast.Raise):
                return True
            if isinstance(sub, ast.Call):
                f = sub.func
                name = getattr(f, "attr", None) or getattr(f, "id", None)
                if name in ("exit", "_exit"):
                    return True
    return False


def _classify(tree) -> dict:
    """{module: required} for one file.

    module-level import            -> required (it runs on import; nothing to catch it)
    module-level try, fatal except -> required (author exits without it)
    module-level try, soft except  -> optional (author coded a fallback)
    import inside a function       -> LAZY: only fails if that path runs, so not a
                                      startup blocker. bhavcopy_store does a bare
                                      `import lmdb` inside build(); its callers either
                                      guard it or gate it behind `if rebuild_store:`,
                                      so flagging lmdb as required reported every step
                                      as broken — a false alarm that trains people to
                                      ignore the check.
    """
    out: dict = {}

    def mark(mods, required):
        for m in mods:
            out[m] = out.get(m, False) or required

    for node in tree.body:                       # TOP LEVEL ONLY
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mark(_imported(node), True)
        elif isinstance(node, ast.Try):
            fatal = _handler_is_fatal(node.handlers)
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    mark(_imported(sub), fatal)

    for node in ast.walk(tree):                  # lazy (in-function) imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for m in _imported(node):
                out.setdefault(m, False)
    return out


def _scan(path: Path, local: set, seen: set, out: dict, depth: int = 0,
          ctx_required: bool = True) -> None:
    """Collect {module: required_bool}, following local imports transitively.

    `ctx_required` propagates optionality DOWN through local imports. A module can
    hard-import something while its *caller* guards the whole import — e.g.
    bhavcopy_store.py does a bare `import lmdb` inside build(), but
    bhavcopy_history.py wraps `from bhavcopy_store import build` in try/except and
    degrades with "LMDB store not synced". Only looking for guards inside the same
    file marks lmdb REQUIRED and reports every step as broken, which is exactly the
    kind of false alarm that trains people to ignore the check.
    """
    key = (path.name, ctx_required)
    if depth > 4 or key in seen or not path.exists():
        return
    seen.add(key)
    try:
        tree = ast.parse(path.read_text())
    except Exception:
        return

    for m, req in _classify(tree).items():
        if m in _STDLIB or m.startswith("_"):
            continue
        here_required = ctx_required and req
        if m in local:                                        # follow local modules
            for base in (HERE, HOME):
                if (base / f"{m}.py").exists():
                    _scan(base / f"{m}.py", local, seen, out, depth + 1,
                          ctx_required=here_required)
                    break
            continue
        out[m] = out.get(m, False) or here_required           # required wins


def audit() -> dict:
    local = _local_modules()
    per_step, all_mods = {}, {}
    for step, script in STEPS.items():
        mods: dict = {}
        _scan(HERE / script, local, set(), mods)
        per_step[step] = mods
        for m, req in mods.items():
            all_mods[m] = all_mods.get(m, False) or req

    missing = {m: req for m, req in all_mods.items()
               if importlib.util.find_spec(m) is None}
    broken = {}
    for step, mods in per_step.items():
        bad = [m for m in mods if m in missing and missing[m] and mods[m]]
        if bad:
            broken[step] = sorted(bad)
    return {"checked": len(all_mods), "missing": missing, "breaks": broken,
            "python": sys.executable}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    r = audit()
    req_missing = sorted(m for m, req in r["missing"].items() if req)
    opt_missing = sorted(m for m, req in r["missing"].items() if not req)

    if a.json:
        print(json.dumps(r, indent=1, default=str))
        return 1 if req_missing else 0

    if not req_missing and a.quiet:
        return 0

    if not req_missing:
        print(f"  deps OK — {r['checked']} modules checked ({Path(r['python']).parent.parent.name})")
        if opt_missing:
            print(f"  optional absent (guarded, degrades gracefully): {', '.join(opt_missing)}")
        return 0

    # LOUD. This is the whole point — a missing dep must not read like a bad network day.
    bar = "=" * 72
    print(f"\n{bar}\n  ❌  MISSING REQUIRED DEPENDENCIES — the pipeline WILL produce\n"
          f"      silently stale or empty output for the steps below.\n{bar}")
    print(f"  interpreter: {r['python']}\n")
    for m in req_missing:
        print(f"    ✗ {m}")
    print("\n  pipeline steps that will break:")
    for step, mods in sorted(r["breaks"].items()):
        print(f"    {step:28s} needs: {', '.join(mods)}")
    if opt_missing:
        print(f"\n  (optional, guarded, fine to ignore: {', '.join(opt_missing)})")
    print(f"\n  fix:  {r['python']} -m pip install {' '.join(req_missing)}")
    print(f"{bar}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
