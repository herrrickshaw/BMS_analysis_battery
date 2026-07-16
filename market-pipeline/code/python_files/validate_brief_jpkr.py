#!/usr/bin/env python3
"""
validate_brief_jpkr.py — cross-check Japan and Korea scans against yfinance,
the one previously-identified gap ("no external validator for JP/KR") from
today's cross-market validation audit.

WHY yfinance HERE, WHEN screener.in/moneycontrol/EODHD/Alpha Vantage ARE
"EXTERNAL" FOR OTHER MARKETS
------------------------------------------------------------------------------
yfinance is not independent of this pipeline in the abstract — it's already
the PRIMARY data source for JP/KR daily scans (full_japan_market_scan.py /
full_korea_market_scan.py both pull LTP via yfinance) AND for their
fundamentals collection (yf_fundamentals.py, wired today). Using it to
"validate" the scan it fed sounds circular.

It isn't, for the specific failure mode this whole validation effort exists
to catch (see validate_brief.py's MODISONLTD incident: a scan that is
STALE/FROZEN while every internal check agrees, because they all read the
same frozen artifact). This validator makes a FRESH yfinance call at
validation time, independent of whatever cache/session the scan itself used
hours earlier — so it catches "the scan's yfinance snapshot from 04:42 this
morning is now stale" (a real, useful check) even though it can't catch "the
scan's yfinance snapshot was wrong AT THE TIME" (a check only a genuinely
different provider — screener.in vs moneycontrol vs EODHD's own database —
can make). Reported explicitly as PARTIAL, not the same guarantee as the
other four validators.

Alpha Vantage was tried first and confirmed NOT to cover Tokyo/Korea
(7203.T, 005930.KS both return empty GLOBAL_QUOTE) — see validate_brief_eu.py.
No other free, no-login source with confirmed JP/KR coverage was found.

WHAT IT CHECKS
--------------
  1. FRESHNESS — is the LATEST available yfinance bar within STALE_DAYS?
  2. PRICE      — does the scan's LTP match yfinance's latest close within
                  tolerance? (Loosened to 2% vs US's 1% — JP/KR closes can
                  carry more yfinance-side lag/rounding than US large caps.)

Exit codes:
  0  validated (with the PARTIAL caveat above) — safe to send
  1  MISMATCH or unverifiable — caller must NOT send

Usage:
    python3 validate_brief_jpkr.py --market japan
    python3 validate_brief_jpkr.py --market korea --sample 8 --json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time

import pandas as pd

PRICE_TOL_PCT = 2.0
MIN_VERIFIED = 3
STALE_DAYS = 4

SCAN_GLOB = {
    "japan": "japan_scan/japan_market_scan_*.xlsx",
    "korea": "korea_scan/korea_market_scan_*.xlsx",
}
LTP_COL = {"japan": "LTP_JPY", "korea": "LTP_KRW"}


def _latest_scan(market: str) -> str:
    fs = sorted(glob.glob(SCAN_GLOB[market]))
    return fs[-1] if fs else ""


def _fetch(yf_ticker: str) -> dict:
    try:
        import yfinance as yf
        h = yf.Ticker(yf_ticker).history(period="5d")
    except Exception as e:
        return {"error": f"yfinance: {str(e)[:60]}"}
    if h is None or h.empty:
        return {"error": "yfinance: no data"}
    # MARKET-HOURS GUARD. Tokyo/Seoul were both mid-session when this was first
    # tested (11:58 local) — the naive "last row" was a still-forming intraday
    # price, not a close, so it diverged from the scan's LTP by 3-13% on EVERY
    # ticker even though the scan (captured pre-market, ~04:42 IST / before
    # Tokyo's 9am open) was correctly using the prior completed session.
    # If the last bar's calendar date (in the ticker's own exchange timezone)
    # is today, that session may not be settled — prefer the PRIOR row, the
    # last one guaranteed complete. Same discipline validate_brief.py already
    # applies for screener.in's live-vs-close ambiguity.
    last_date = h.index[-1].date()
    today_local = pd.Timestamp.now(tz=h.index[-1].tz).date()
    if last_date == today_local and len(h) >= 2:
        row = h.iloc[-2]
        return {"price": float(row["Close"]), "date": h.index[-2].strftime("%Y-%m-%d")}
    last = h.iloc[-1]
    return {"price": float(last["Close"]), "date": h.index[-1].strftime("%Y-%m-%d")}


def validate(market: str, sample: int, tol: float) -> dict:
    f = _latest_scan(market)
    if not f:
        return {"ok": False, "reason": f"no {market} scan workbook found", "checks": []}
    d = pd.read_excel(f, "All_Stocks")
    ltp_col = LTP_COL[market]
    if "Turnover_USD" in d.columns:
        d = d.sort_values("Turnover_USD", ascending=False)
    picks = d.head(sample * 2)

    today = pd.Timestamp.today().normalize()
    checks, verified = [], 0
    for r in picks.to_dict("records"):
        if verified >= sample:
            break
        tk = str(r["YF_Ticker"])
        got = _fetch(tk)
        time.sleep(0.3)
        if got.get("error"):
            checks.append({"symbol": tk, "status": "skip", "why": got["error"]})
            continue
        ours, theirs = float(r[ltp_col]), got["price"]
        diff = abs(ours - theirs) / theirs * 100 if theirs else 999
        ok = diff <= tol
        verified += 1
        checks.append({"symbol": tk, "status": "ok" if ok else "MISMATCH",
                       "ours": ours, "theirs": theirs, "diff_pct": round(diff, 2),
                       "date": got.get("date")})

    bad = [c for c in checks if c["status"] == "MISMATCH"]
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
                  + ", ".join(f"{s}({dt}, {a}d old)" for s, dt, a in stale))
    return {"ok": ok, "reason": reason, "scan": f.split("/")[-1], "market": market,
            "verified": verified, "checks": checks,
            "caveat": "PARTIAL — same provider (yfinance) as the scan's own source; "
                      "catches staleness but not an at-the-time pricing error. "
                      "No independent JP/KR source with confirmed coverage was found."}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["japan", "korea"])
    ap.add_argument("--sample", type=int, default=6)
    ap.add_argument("--tolerance", type=float, default=PRICE_TOL_PCT)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    r = validate(a.market, a.sample, a.tolerance)
    if a.json:
        print(json.dumps(r, indent=1))
        return 0 if r["ok"] else 1

    print(f"  validating {r.get('scan','?')} against yfinance (tolerance {a.tolerance}%)")
    print(f"  ⚠ {r.get('caveat','')}")
    for c in r["checks"]:
        if c["status"] == "skip":
            print(f"    -  {c['symbol']:14s} skipped ({c['why']})")
        else:
            mark = "ok" if c["status"] == "ok" else "!!"
            print(f"    {mark} {c['symbol']:14s} ours={c['ours']:<12} "
                  f"theirs={c['theirs']:<12} diff={c['diff_pct']}%  {c.get('date')}")
    if r["ok"]:
        print(f"  ✓ validated (partial): {r['verified']} names agree")
        return 0
    bar = "=" * 72
    print(f"\n{bar}\n  ❌  {a.market.upper()} BRIEF FAILED VALIDATION — DO NOT SEND\n  {r['reason']}\n{bar}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
