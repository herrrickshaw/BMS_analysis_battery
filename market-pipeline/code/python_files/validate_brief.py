#!/usr/bin/env python3
"""
validate_brief.py — cross-check the India scan against screener.in BEFORE sending.

WHY THIS EXISTS
---------------
The screeners emit *recommendations* (Darvas / golden cross / DMA). Checking the
brief against our own scan artifact only proves internal consistency — it cannot
detect a scan that is confidently wrong about the world. On 2026-07-15 every
internal check passed while the pipeline was:

  * quoting MODISONLTD at 284.6 / +3.6% from **2026-05-29**, seven weeks stale,
    and emitting it as a GOLDEN_CROSS pick (screener.in: Rs 289 / -2.71% on 14 Jul).
    Cause: NSE-precedence was applied per SYMBOL, so a stock that left NSE but
    still trades on BSE froze at its last NSE bar. 270 of 7,833 symbols, up to
    313 days stale. The brief, the scan, the parquet and the warehouse all agreed
    with each other and were all wrong together.
  * recommending LIQUIDSBI — an ETF — as a golden cross.
  * leading with AUSTENG on +16% while it turned over Rs 2.1 lakh/day.

Only an EXTERNAL source catches that class of bug. This encodes the rule so the
unattended 00:30 run is held to it too, not just the runs a human watches.

WHAT IT CHECKS
--------------
Samples the most liquid India picks (most liquid => most likely NSE-listed and
present on screener.in) and compares against screener.in's public company page:

  1. CLOSE DATE   — the strong check. Detects stale data directly; a price can
                    coincidentally look plausible, a wrong date cannot hide.
  2. PRICE        — within tolerance (screener.in rounds to ~4 significant
                    figures: it shows Rs 1,099 for 1098.8, Rs 289 for 289.75).

Exit codes:
  0  validated — safe to send
  1  MISMATCH or unverifiable — caller must NOT send

Usage:
    python3 validate_brief.py                 # sample 6, 2% tolerance
    python3 validate_brief.py --sample 8 --json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import re
import sys
import time

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (research)"}
BASE = "https://www.screener.in/company/{}/"

# screener.in rounds to ~4 sig figs, so exact equality is wrong to demand:
#   1098.8 -> "Rs 1,099" (0.02%)   860.55 -> "Rs 861" (0.05%)   289.75 -> "Rs 289" (0.26%)
PRICE_TOL_PCT = 2.0
MIN_VERIFIED = 3          # below this we cannot claim the brief was validated


def _latest_scan() -> str:
    fs = sorted(glob.glob("indian_full_scan/indian_full_scan_*.xlsx"))
    return fs[-1] if fs else ""


def _fetch(sym: str) -> dict:
    """Parse screener.in's header: '<Name> Rs 1,099 -1.72% 14 Jul - close price'."""
    try:
        r = requests.get(BASE.format(sym), headers=UA, timeout=25)
    except Exception as e:
        return {"error": f"fetch: {str(e)[:60]}"}
    if r.status_code == 404:
        # BSE-only names 404 on the NSE-shaped URL (AUSTENG = Austin Engineering).
        # NOT evidence the pick is bogus — just unverifiable here.
        return {"error": "404"}
    if r.status_code != 200:
        return {"error": f"http {r.status_code}"}
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")
        top = soup.select_one("#top") or soup
        txt = re.sub(r"\s+", " ", top.get_text(" ", strip=True))[:400]
    except Exception as e:
        return {"error": f"parse: {str(e)[:60]}"}

    price = re.search(r"₹\s*([\d,]+(?:\.\d+)?)", txt)
    chg = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", txt)
    date = re.search(r"(\d{1,2}\s+[A-Z][a-z]{2})\s*-?\s*close price", txt)
    if not price:
        return {"error": "no price in header"}
    return {
        "price": float(price.group(1).replace(",", "")),
        "change": float(chg.group(1)) if chg else None,
        "date": date.group(1) if date else None,
    }


def validate(sample: int, tol: float) -> dict:
    f = _latest_scan()
    if not f:
        return {"ok": False, "reason": "no India scan workbook found", "checks": []}
    d = pd.read_excel(f, "All_Stocks")
    if "Median_Turnover" in d.columns:
        d = d.sort_values("Median_Turnover", ascending=False)
    picks = d.head(sample * 3)          # over-sample: BSE-only names will 404

    checks, verified = [], 0
    for r in picks.to_dict("records"):
        if verified >= sample:
            break
        sym = str(r["Symbol"])
        got = _fetch(sym)
        time.sleep(0.6)                 # be polite to screener.in
        if got.get("error"):
            checks.append({"symbol": sym, "status": "skip", "why": got["error"]})
            continue
        ours, theirs = float(r["LTP"]), got["price"]
        diff = abs(ours - theirs) / theirs * 100 if theirs else 999
        ok = diff <= tol
        verified += 1
        checks.append({"symbol": sym, "status": "ok" if ok else "MISMATCH",
                       "ours": ours, "screener": theirs,
                       "diff_pct": round(diff, 2), "date": got.get("date")})

    bad = [c for c in checks if c["status"] == "MISMATCH"]

    # Date agreement across verified names. A single odd date is a holiday/listing
    # quirk; a majority disagreeing means the whole scan is on the wrong day —
    # which is exactly the frozen-data failure this exists to catch.
    dates = [c["date"] for c in checks if c.get("date")]
    common = max(set(dates), key=dates.count) if dates else None
    off = [c["symbol"] for c in checks if c.get("date") and c["date"] != common]

    ok = (verified >= MIN_VERIFIED) and not bad and len(off) <= max(1, verified // 4)
    reason = ""
    if verified < MIN_VERIFIED:
        reason = f"only {verified} of {sample} verifiable (need {MIN_VERIFIED}) — cannot confirm"
    elif bad:
        reason = f"{len(bad)} price mismatch(es) beyond {tol}%"
    elif off:
        reason = f"close dates disagree: {off} vs majority {common}"
    return {"ok": ok, "reason": reason, "scan": f.split("/")[-1],
            "verified": verified, "close_date": common, "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=6)
    ap.add_argument("--tolerance", type=float, default=PRICE_TOL_PCT)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    r = validate(a.sample, a.tolerance)
    if a.json:
        print(json.dumps(r, indent=1))
        return 0 if r["ok"] else 1

    print(f"  validating {r.get('scan','?')} against screener.in "
          f"(tolerance {a.tolerance}%)")
    for c in r["checks"]:
        if c["status"] == "skip":
            print(f"    -  {c['symbol']:12s} skipped ({c['why']})")
        else:
            mark = "ok" if c["status"] == "ok" else "!!"
            print(f"    {mark} {c['symbol']:12s} ours={c['ours']:<10} "
                  f"screener={c['screener']:<10} diff={c['diff_pct']}%  {c.get('date')}")
    if r["ok"]:
        print(f"  ✓ validated: {r['verified']} names agree, close date {r['close_date']}")
        return 0
    bar = "=" * 72
    print(f"\n{bar}\n  ❌  BRIEF FAILED EXTERNAL VALIDATION — DO NOT SEND\n  {r['reason']}\n{bar}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
