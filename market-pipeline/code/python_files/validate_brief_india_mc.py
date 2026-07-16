#!/usr/bin/env python3
"""
validate_brief_india_mc.py — cross-check the India scan against moneycontrol.com,
with yfinance as an automatic per-ticker fallback, for when screener.in (the
primary source validate_brief.py uses) is blocked.

WHY THIS EXISTS
---------------
2026-07-16: screener.in went from "occasionally IP-blocked, clears with a wait"
(the documented pattern this project already knew about) to a sustained,
multi-hour, connection-level block — even its plain homepage stopped
responding. validate_brief.py alone left India's mailer section with NO way
to validate for the rest of that day. A single source is a single point of
failure; this adds two more, tried in order, so one source's outage doesn't
block the whole India brief.

SOURCE 1 — moneycontrol.com: resolved via its own public autosuggest API
(`/mccode/common/autosuggestion_solr.php`), which returns each match's ISIN/
NSE-symbol/BSE-code triple — matched exactly against the NSE symbol rather
than trusting result order, since a name like "Reliance" also matches
"Reliance Power". The quote page then exposes NSE price (`id="nsecp"`), BSE
price (`id="bsecp"`), and an "As on <date> | <time>" stamp in plain HTML —
no login, no JS rendering required.

SOURCE 2 — yfinance (`<SYMBOL>.NS`): the same dependency this project already
uses as its PRIMARY source for Europe/Japan/Korea fundamentals, and for the
live Piotroski scorer. If moneycontrol has no match or its page format has
shifted, this is the fallback, tried before giving up on a ticker.

WHAT IT CHECKS (same discipline as validate_brief.py / validate_brief_us.py)
-----------------------------------------------------------------------------
  1. CLOSE DATE — detects stale/frozen data.
  2. PRICE       — within tolerance (moneycontrol reports to the paisa; yfinance
                   ~2 decimals — tolerance is tighter than screener.in's
                   ~4-sig-fig-rounded case).

Exit codes:
  0  validated — safe to send
  1  MISMATCH or unverifiable — caller must NOT send

Usage:
    python3 validate_brief_india_mc.py                 # sample 6, 1.5% tolerance
    python3 validate_brief_india_mc.py --sample 8 --json
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import time

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
MC_AUTOSUGGEST = "https://www.moneycontrol.com/mccode/common/autosuggestion_solr.php"
PRICE_TOL_PCT = 1.5
MIN_VERIFIED = 3
STALE_DAYS = 4


def _latest_scan() -> str:
    fs = sorted(glob.glob("indian_full_scan/indian_full_scan_*.xlsx"))
    return fs[-1] if fs else ""


def _mc_resolve(sym: str) -> str | None:
    """NSE symbol -> moneycontrol quote-page URL, matched EXACTLY against the
    NSE-symbol field in each candidate (not the first/best-ranked result —
    "Reliance" ranks Reliance Industries and Reliance Power similarly)."""
    try:
        r = requests.get(MC_AUTOSUGGEST, params={
            "classic": "true", "query": sym, "type": "1", "format": "json",
        }, headers=UA, timeout=15)
        results = r.json()
    except Exception:
        return None
    for res in results:
        codes = re.search(r"<span>([^<]+)</span>", res.get("pdt_dis_nm", ""))
        if not codes:
            continue
        parts = [c.strip().upper() for c in codes.group(1).split(",")]
        if sym.upper() in parts:
            return res.get("link_src")
    return None


def _fetch_moneycontrol(sym: str) -> dict:
    url = _mc_resolve(sym)
    if not url:
        return {"error": "no moneycontrol match"}
    try:
        r = requests.get(url, headers=UA, timeout=20)
    except Exception as e:
        return {"error": f"fetch: {str(e)[:60]}"}
    if r.status_code != 200:
        return {"error": f"http {r.status_code}"}
    txt = r.text
    price_m = re.search(r'id="nsecp"[^>]*>([\d,]+\.?\d*)<', txt) or \
              re.search(r'id="bsecp"[^>]*>([\d,]+\.?\d*)<', txt)
    date_m = re.search(r'As on ([A-Za-z0-9, ]+?)\s*\|', txt)
    if not price_m:
        return {"error": "no price marker on page"}
    return {
        "price": float(price_m.group(1).replace(",", "")),
        "date": date_m.group(1).strip() if date_m else None,
        "source": "moneycontrol",
    }


def _fetch_yfinance(sym: str) -> dict:
    try:
        import yfinance as yf
        h = yf.Ticker(f"{sym}.NS").history(period="5d")
    except Exception as e:
        return {"error": f"yfinance: {str(e)[:60]}"}
    if h is None or h.empty:
        return {"error": "yfinance: no data"}
    last = h.iloc[-1]
    return {
        "price": float(last["Close"]),
        "date": h.index[-1].strftime("%Y-%m-%d"),
        "source": "yfinance",
    }


def _fetch(sym: str) -> dict:
    got = _fetch_moneycontrol(sym)
    if not got.get("error"):
        return got
    mc_err = got["error"]
    got2 = _fetch_yfinance(sym)
    if not got2.get("error"):
        return got2
    return {"error": f"moneycontrol: {mc_err}; yfinance: {got2['error']}"}


def _parse_mc_date(s: str):
    """moneycontrol: 'DD Mon, YYYY'. yfinance already returns ISO."""
    if not s:
        return None
    try:
        return pd.Timestamp(s)
    except Exception:
        try:
            return pd.to_datetime(s, format="%d %b, %Y")
        except Exception:
            return None


def validate(sample: int, tol: float) -> dict:
    f = _latest_scan()
    if not f:
        return {"ok": False, "reason": "no India scan workbook found", "checks": []}
    d = pd.read_excel(f, "All_Stocks")
    if "Median_Turnover" in d.columns:
        d = d.sort_values("Median_Turnover", ascending=False)
    picks = d.head(sample * 2)

    today = pd.Timestamp.today().normalize()
    checks, verified = [], 0
    for r in picks.to_dict("records"):
        if verified >= sample:
            break
        sym = str(r["Symbol"])
        got = _fetch(sym)
        time.sleep(0.6)
        if got.get("error"):
            checks.append({"symbol": sym, "status": "skip", "why": got["error"]})
            continue
        ours, theirs = float(r["LTP"]), got["price"]
        diff = abs(ours - theirs) / theirs * 100 if theirs else 999
        ok = diff <= tol
        verified += 1
        checks.append({"symbol": sym, "status": "ok" if ok else "MISMATCH",
                       "ours": ours, "theirs": theirs, "diff_pct": round(diff, 2),
                       "date": got.get("date"), "source": got.get("source")})

    bad = [c for c in checks if c["status"] == "MISMATCH"]
    stale = []
    for c in checks:
        dt = _parse_mc_date(c.get("date"))
        if dt is None:
            continue
        age = (today - dt.normalize()).days
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

    print(f"  validating {r.get('scan','?')} against moneycontrol (+ yfinance fallback), "
          f"tolerance {a.tolerance}%")
    for c in r["checks"]:
        if c["status"] == "skip":
            print(f"    -  {c['symbol']:12s} skipped ({c['why']})")
        else:
            mark = "ok" if c["status"] == "ok" else "!!"
            print(f"    {mark} {c['symbol']:12s} ours={c['ours']:<10} "
                  f"theirs={c['theirs']:<10} diff={c['diff_pct']}%  "
                  f"{c.get('date')}  [{c.get('source')}]")
    if r["ok"]:
        print(f"  ✓ validated: {r['verified']} names agree")
        return 0
    bar = "=" * 72
    print(f"\n{bar}\n  ❌  INDIA BRIEF FAILED EXTERNAL VALIDATION — DO NOT SEND\n  {r['reason']}\n{bar}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
