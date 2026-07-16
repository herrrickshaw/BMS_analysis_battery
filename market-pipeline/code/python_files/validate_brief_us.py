#!/usr/bin/env python3
"""
validate_brief_us.py — cross-check the US scan against an INDEPENDENT price source
(EODHD, eodhd.com) BEFORE sending, mirroring validate_brief.py's India check.

WHY THIS EXISTS
---------------
validate_brief.py already proved the class of bug this catches: on 2026-07-15 the
India pipeline confidently emitted a stock frozen 7 weeks stale as a fresh pick,
and every INTERNAL check (scan vs parquet vs warehouse) agreed because they all
inherited the same bug. Only a source outside the pipeline's own data flow can
catch that. US had no equivalent check — the exact gap flagged when the
cross-market warehouse audit found the same class of bug in a different place
(Korea's byte-size file-selection heuristic, 2026-07-16).

DATA SOURCE
-----------
EODHD's /eod/ endpoint (End Of Day) — NOT a live-quote endpoint, so it always
returns the last COMPLETED trading day's close, avoiding the "market open ->
live quote has no date" ambiguity validate_brief.py had to guard against for
screener.in. Requires EODHD_KEY (see .env / _load_dotenv below).

WHAT IT CHECKS
--------------
Samples the most liquid US picks (by Turnover_USD) and compares against EODHD's
most recent daily bar:
  1. CLOSE DATE — detects stale/frozen data directly.
  2. PRICE       — within tolerance (EODHD reports to the cent; US closes are
                   exact, so tolerance here is much tighter than screener.in's
                   ~4-sig-fig rounding case).

Exit codes:
  0  validated — safe to send
  1  MISMATCH or unverifiable — caller must NOT send

Usage:
    python3 validate_brief_us.py                 # sample 6, 1% tolerance
    python3 validate_brief_us.py --sample 8 --json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

_ENV_PATHS = (
    Path(__file__).parent / ".env",
    Path.home() / "repos" / "global-stock-screener" / ".env",
    Path.home() / ".env",
)


def _load_dotenv() -> None:
    for envf in _ENV_PATHS:
        if not envf.exists():
            continue
        try:
            lines = envf.read_text().splitlines()
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and val and key not in os.environ:
                os.environ[key] = val


_load_dotenv()

EODHD_URL = "https://eodhd.com/api/eod/{}.US"
PRICE_TOL_PCT = 1.0     # US closes are exact; not screener.in's ~4-sig-fig rounding case
MIN_VERIFIED = 3
STALE_DAYS = 4           # a liquid US name trades daily; allow for a long weekend


def _latest_scan() -> str:
    fs = sorted(glob.glob("us_full_scan/us_full_scan_*.xlsx"))
    return fs[-1] if fs else ""


def _fetch(sym: str, key: str) -> dict:
    try:
        r = requests.get(EODHD_URL.format(sym), params={
            "api_token": key, "fmt": "json", "period": "d", "order": "d", "limit": 1,
        }, timeout=20)
    except Exception as e:
        return {"error": f"fetch: {str(e)[:60]}"}
    if r.status_code == 401:
        return {"error": "401 unauthorized — EODHD_KEY missing/invalid"}
    if r.status_code == 404:
        return {"error": "404"}          # delisted / not on EODHD's US list
    if r.status_code != 200:
        return {"error": f"http {r.status_code}"}
    try:
        rows = r.json()
    except Exception as e:
        return {"error": f"parse: {str(e)[:60]}"}
    if not rows:
        return {"error": "empty response"}
    row = rows[0]
    if "close" not in row or "date" not in row:
        return {"error": "unexpected response shape"}
    return {"price": float(row["close"]), "date": row["date"]}


def validate(sample: int, tol: float) -> dict:
    key = os.environ.get("EODHD_KEY", "")
    if not key:
        return {"ok": False, "reason": "EODHD_KEY not set (.env)", "checks": []}

    f = _latest_scan()
    if not f:
        return {"ok": False, "reason": "no US scan workbook found", "checks": []}
    d = pd.read_excel(f, "All_Stocks")
    if "Turnover_USD" in d.columns:
        d = d.sort_values("Turnover_USD", ascending=False)
    picks = d.head(sample * 2)          # over-sample: some tickers may 404 on EODHD

    today = pd.Timestamp.today().normalize()
    checks, verified = [], 0
    for r in picks.to_dict("records"):
        if verified >= sample:
            break
        sym = str(r["Symbol"])
        got = _fetch(sym, key)
        time.sleep(0.3)
        if got.get("error"):
            checks.append({"symbol": sym, "status": "skip", "why": got["error"]})
            continue
        ours, theirs = float(r["LTP"]), got["price"]
        diff = abs(ours - theirs) / theirs * 100 if theirs else 999
        ok = diff <= tol
        verified += 1
        checks.append({"symbol": sym, "status": "ok" if ok else "MISMATCH",
                       "ours": ours, "eodhd": theirs,
                       "diff_pct": round(diff, 2), "date": got.get("date")})

    bad = [c for c in checks if c["status"] == "MISMATCH"]

    # Staleness: EODHD's /eod/ endpoint always returns a completed trading day
    # (never a live intraday quote), so unlike screener.in there is no
    # market-hours ambiguity to guard against here — a date is either recent
    # or it isn't.
    dates = [c["date"] for c in checks if c.get("date")]
    stale = []
    for c in checks:
        if not c.get("date"):
            continue
        age = (today - pd.Timestamp(c["date"])).days
        if age > STALE_DAYS:
            stale.append((c["symbol"], c["date"], age))

    ok = (verified >= MIN_VERIFIED) and not bad and not stale
    reason = ""
    if verified < MIN_VERIFIED:
        reason = f"only {verified} of {sample} verifiable (need {MIN_VERIFIED}) — cannot confirm"
    elif bad:
        reason = f"{len(bad)} price mismatch(es) beyond {tol}%"
    elif stale:
        reason = (f"{len(stale)} name(s) stale beyond {STALE_DAYS}d: "
                  + ", ".join(f"{s}({d}, {a}d old)" for s, d, a in stale))
    return {"ok": ok, "reason": reason, "scan": f.split("/")[-1],
            "verified": verified, "checks": checks}


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

    print(f"  validating {r.get('scan','?')} against EODHD (tolerance {a.tolerance}%)")
    for c in r["checks"]:
        if c["status"] == "skip":
            print(f"    -  {c['symbol']:12s} skipped ({c['why']})")
        else:
            mark = "ok" if c["status"] == "ok" else "!!"
            print(f"    {mark} {c['symbol']:12s} ours={c['ours']:<10} "
                  f"eodhd={c['eodhd']:<10} diff={c['diff_pct']}%  {c.get('date')}")
    if r["ok"]:
        print(f"  ✓ validated: {r['verified']} names agree against EODHD")
        return 0
    bar = "=" * 72
    print(f"\n{bar}\n  ❌  US BRIEF FAILED EXTERNAL VALIDATION — DO NOT SEND\n  {r['reason']}\n{bar}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
