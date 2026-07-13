#!/usr/bin/env python3
# test_screener_in.py
# ====================
# Daily data-quality test for the screener.in Cash Conversion Cycle scrape
# (screens/228040, via screener_in.ccc_screen()).
#
# WHY THIS EXISTS: screener_in.py parses screener.in's HTML with regex — it has
# no error if the site changes its table structure, blocks the request, or the
# screen itself returns nothing; it just silently returns an empty/malformed
# DataFrame. build_mailer.py's CCC section already degrades gracefully in that
# case (renders "n/a" for India CCC), but that degradation was ALSO silently
# masking a real bug for a full session (a schema mismatch, fixed 2026-07-13) —
# nobody noticed because nothing ever flagged it. This script is the visible
# tripwire: run it daily as a pipeline step so a broken scrape shows up as a
# clear PASS/FAIL in the log instead of a quietly empty report section.
#
# Not a pytest suite (this repo has none) — a standalone script matching the
# rest of the codebase's style, with an exit code for pipeline gating.
#
# Usage:
#   python3 test_screener_in.py                 # run against the live site
#   python3 test_screener_in.py --min-rows 10    # stricter row-count floor
# Exit code: 0 = pass, 1 = fail.

from __future__ import annotations

import argparse
import re
import sys

import pandas as pd

REQUIRED_COLUMNS = ["Symbol", "Name", "Cash_Cycle"]
_SYMBOL_RE = re.compile(r"^[A-Z0-9&.-]+$")


def run(min_rows: int = 5) -> tuple[bool, list[str]]:
    """Live-fetch the screener.in CCC screen and sanity-check the result.
    Returns (all_required_checks_passed, human-readable check lines)."""
    checks = []
    ok = True

    try:
        import screener_in as sin
        df = sin.ccc_screen()
    except Exception as e:
        return False, [f"FAIL live fetch raised {type(e).__name__}: {e}"]

    if df.empty:
        return False, ["FAIL screener.in/screens/228040 returned 0 rows "
                        "(site down, blocked, or the screen was removed/renamed)"]
    checks.append(f"PASS fetched {len(df)} rows from screener.in")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        ok = False
        checks.append(f"FAIL missing expected columns {missing} (got {list(df.columns)}) "
                       "— screener.in likely changed its table headers")
    else:
        checks.append(f"PASS has all required columns {REQUIRED_COLUMNS}")

    if len(df) < min_rows:
        ok = False
        checks.append(f"FAIL only {len(df)} rows, expected >= {min_rows} "
                       "(screen may be broken, paginating wrong, or genuinely empty)")
    else:
        checks.append(f"PASS row count {len(df)} >= floor of {min_rows}")

    if "Cash_Cycle" in df.columns:
        cc = pd.to_numeric(df["Cash_Cycle"], errors="coerce")
        n_valid = int(cc.notna().sum())
        if n_valid == 0:
            ok = False
            checks.append("FAIL Cash_Cycle column present but 0 numeric values parsed "
                           "(regex/column extraction is picking up the wrong cell)")
        else:
            checks.append(f"PASS {n_valid}/{len(df)} rows have a numeric Cash_Cycle")
            # Sanity range: a real CCC in days is rarely beyond ±400. A large
            # fraction outside that band usually means the wrong column got
            # parsed (e.g. Market Cap or P/E landed in the Cash_Cycle slot).
            frac_extreme = float((cc.abs() > 400).sum()) / n_valid
            if frac_extreme > 0.3:
                ok = False
                checks.append(f"FAIL {frac_extreme:.0%} of Cash_Cycle values have |x|>400 days "
                               "— looks like the wrong column was parsed")
            else:
                checks.append(f"PASS Cash_Cycle values are in a plausible range "
                               f"({1 - frac_extreme:.0%} within ±400 days)")

    if "Symbol" in df.columns:
        n_dupe = int(df["Symbol"].duplicated().sum())
        if n_dupe:
            checks.append(f"WARN {n_dupe} duplicate symbols in the result")
        bad = df.loc[~df["Symbol"].astype(str).str.match(_SYMBOL_RE), "Symbol"].tolist()
        if bad:
            checks.append(f"WARN {len(bad)} symbols look malformed: {bad[:5]}")

    if ok and "Cash_Cycle" in df.columns:
        top = df.assign(_cc=pd.to_numeric(df["Cash_Cycle"], errors="coerce")) \
                .dropna(subset=["_cc"]).sort_values("_cc").iloc[0]
        checks.append(f"  top pick today: {top['Symbol']} ({top.get('Name','')}) "
                       f"CCC={top['_cc']:.1f}d")

    return ok, checks


def main():
    ap = argparse.ArgumentParser(description="Daily data-quality test for the screener.in CCC scrape")
    ap.add_argument("--min-rows", type=int, default=5,
                     help="Minimum row count to pass (default 5; the live screen typically has ~20-30)")
    args = ap.parse_args()

    print("Testing screener.in Cash Conversion Cycle screen (screens/228040) …")
    ok, checks = run(args.min_rows)
    for c in checks:
        print(f"  {c}")
    print(f"\n{'PASS' if ok else 'FAIL'} — screener.in CCC scrape "
          f"{'looks healthy' if ok else 'needs attention (build_mailer.py will show n/a for CCC until fixed)'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
