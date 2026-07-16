#!/usr/bin/env python3
"""
validate_brief_eu.py — cross-check the Europe scan against an INDEPENDENT price
source (Alpha Vantage) BEFORE sending, mirroring validate_brief.py (India,
screener.in) and validate_brief_us.py (US, EODHD).

COVERAGE CAVEAT, stated up front rather than discovered by a silent all-skip
--------------------------------------------------------------------------
Alpha Vantage's free tier does NOT cover every European exchange — confirmed
live: SAP.DE (Frankfurt) returns real data, but this has NOT been verified
exchange-by-exchange across all 17 exchanges europe_broad_list.csv spans
(London, Paris, Milan, Madrid, Stockholm, etc.). Expect a lower verified-count
than validate_brief_us.py for the same sample size; MIN_VERIFIED below is
sized accordingly (4, not 3) — over-sampling harder here matters more.

RATE LIMIT: Alpha Vantage's free tier is ~5 requests/minute. Default sample is
5 (not 6 like the other two validators) with a 13s delay between calls to stay
under that with margin, since a validator that trips the provider's own rate
limit mid-run would itself become a source of false MISMATCH/skip noise.

WHAT IT CHECKS
--------------
  1. CLOSE DATE ("latest trading day") — detects stale/frozen data.
  2. PRICE       — within tolerance.

Exit codes:
  0  validated — safe to send
  1  MISMATCH or unverifiable — caller must NOT send

Usage:
    python3 validate_brief_eu.py                 # sample 5, 1.5% tolerance
    python3 validate_brief_eu.py --sample 8 --json
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

AV_URL = "https://www.alphavantage.co/query"
PRICE_TOL_PCT = 1.5      # slightly wider than US: some EU exchanges trade in local
                          # currency vs. LTP's currency handling — not proven identical
MIN_VERIFIED = 4
STALE_DAYS = 4
RATE_DELAY = 13          # ~4.6 req/min, under AV free tier's ~5/min limit


def _latest_scan() -> str:
    fs = sorted(glob.glob("european_scan/european_market_scan_broad_*.xlsx"))
    return fs[-1] if fs else ""


def _fetch(sym: str, key: str) -> dict:
    try:
        r = requests.get(AV_URL, params={
            "function": "GLOBAL_QUOTE", "symbol": sym, "apikey": key,
        }, timeout=20)
    except Exception as e:
        return {"error": f"fetch: {str(e)[:60]}"}
    if r.status_code != 200:
        return {"error": f"http {r.status_code}"}
    try:
        body = r.json()
    except Exception as e:
        return {"error": f"parse: {str(e)[:60]}"}
    if "Note" in body or "Information" in body:
        return {"error": "rate-limited by Alpha Vantage — slow down or retry later"}
    q = body.get("Global Quote") or {}
    if not q or "05. price" not in q:
        return {"error": "not covered by Alpha Vantage free tier"}
    return {"price": float(q["05. price"]), "date": q.get("07. latest trading day")}


def validate(sample: int, tol: float) -> dict:
    key = os.environ.get("ALPHAVANTAGE_KEY", "")
    if not key:
        return {"ok": False, "reason": "ALPHAVANTAGE_KEY not set (.env)", "checks": []}

    f = _latest_scan()
    if not f:
        return {"ok": False, "reason": "no Europe scan workbook found", "checks": []}
    d = pd.read_excel(f, "All_Stocks")
    if "Turnover_USD" in d.columns:
        d = d.sort_values("Turnover_USD", ascending=False)
    picks = d.head(sample * 3)          # over-sample harder: partial AV exchange coverage

    today = pd.Timestamp.today().normalize()
    checks, verified = [], 0
    for r in picks.to_dict("records"):
        if verified >= sample:
            break
        sym = str(r["Symbol"])
        got = _fetch(sym, key)
        time.sleep(RATE_DELAY)
        if got.get("error"):
            checks.append({"symbol": sym, "status": "skip", "why": got["error"]})
            continue
        ours, theirs = float(r["LTP"]), got["price"]
        diff = abs(ours - theirs) / theirs * 100 if theirs else 999
        ok = diff <= tol
        verified += 1
        checks.append({"symbol": sym, "status": "ok" if ok else "MISMATCH",
                       "ours": ours, "alphavantage": theirs,
                       "diff_pct": round(diff, 2), "date": got.get("date")})

    bad = [c for c in checks if c["status"] == "MISMATCH"]
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
        reason = (f"only {verified} of {sample} verifiable (need {MIN_VERIFIED}) — "
                  f"Alpha Vantage's free tier doesn't cover every European exchange")
    elif bad:
        reason = f"{len(bad)} price mismatch(es) beyond {tol}%"
    elif stale:
        reason = (f"{len(stale)} name(s) stale beyond {STALE_DAYS}d: "
                  + ", ".join(f"{s}({dt}, {a}d old)" for s, dt, a in stale))
    return {"ok": ok, "reason": reason, "scan": f.split("/")[-1],
            "verified": verified, "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=5)
    ap.add_argument("--tolerance", type=float, default=PRICE_TOL_PCT)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    r = validate(a.sample, a.tolerance)
    if a.json:
        print(json.dumps(r, indent=1))
        return 0 if r["ok"] else 1

    print(f"  validating {r.get('scan','?')} against Alpha Vantage (tolerance {a.tolerance}%)")
    for c in r["checks"]:
        if c["status"] == "skip":
            print(f"    -  {c['symbol']:12s} skipped ({c['why']})")
        else:
            mark = "ok" if c["status"] == "ok" else "!!"
            print(f"    {mark} {c['symbol']:12s} ours={c['ours']:<10} "
                  f"av={c['alphavantage']:<10} diff={c['diff_pct']}%  {c.get('date')}")
    if r["ok"]:
        print(f"  ✓ validated: {r['verified']} names agree against Alpha Vantage")
        return 0
    bar = "=" * 72
    print(f"\n{bar}\n  ❌  EUROPE BRIEF FAILED EXTERNAL VALIDATION — DO NOT SEND\n  {r['reason']}\n{bar}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
