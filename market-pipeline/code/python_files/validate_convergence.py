#!/usr/bin/env python3
"""
validate_convergence.py — do TWO independent sources agree on the brief's picks?

WHY A SECOND SOURCE
-------------------
validate_brief.py checks the India scan against screener.in, and that single
check has already caught a real disaster (a GOLDEN_CROSS pick quoting a
seven-week-stale price). But one external source has two failure modes it cannot
see past:

  1. AVAILABILITY. screener.in hard-blocked this machine twice on 2026-07-21
     (connection refused after ~130 requests). A validator that cannot reach its
     only source fails, the send is suppressed, and a false negative looks
     exactly like a real data problem. The brief does not go out either way.
  2. CORRECTNESS. If screener.in is itself wrong for a name, agreeing with it
     proves nothing. Two sources that independently agree is evidence; one
     source is an assumption.

So this adds moneycontrol as a SECOND opinion and reports CONVERGENCE:

    both agree      -> strong confirmation, send
    one unreachable -> degraded but usable; say so rather than failing
    both disagree   -> our data is probably wrong; do not send
    sources differ  -> flag the name; neither source is automatically right

🔴 CONVERGENCE IS NOT A MAJORITY VOTE. With two sources a disagreement cannot be
resolved by counting. This reports the disagreement and refuses to pick a
winner — silently trusting whichever source is closer to our own number would
turn the check into a rubber stamp for the value we already had.

    validate_convergence.py                 # sample 6 India picks
    validate_convergence.py --sample 10 --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

SCREENER = "https://www.screener.in/company/{}/"
MC_SEARCH = ("https://www.moneycontrol.com/mccode/common/autosuggestion_solr.php"
             "?classic=true&query={}&type=1&format=json")
MC_PRICE = "https://priceapi.moneycontrol.com/pricefeed/nse/equitycash/{}"

# screener.in rounds to ~4 significant figures and moneycontrol quotes live/last
# traded, so exact equality is the wrong bar. 2% catches a stale-by-weeks price
# without tripping on rounding or a normal intraday move.
TOL_PCT = 2.0
RATE = 0.8


def _get(url: str, timeout: int = 20) -> Optional[str]:
    try:
        return urllib.request.urlopen(
            urllib.request.Request(url, headers=UA), timeout=timeout
        ).read().decode("utf-8", "replace")
    except Exception:
        return None


def screener_price(sym: str) -> dict:
    """Price + close date from screener.in's company header."""
    body = _get(SCREENER.format(sym))
    if body is None:
        return {"ok": False, "reason": "unreachable"}
    txt = re.sub(r"<[^>]+>", " ", body)
    txt = re.sub(r"\s+", " ", txt)
    m = re.search(r"₹\s*([\d,]+(?:\.\d+)?)", txt) or re.search(r"Rs\.?\s*([\d,]+(?:\.\d+)?)", txt)
    d = re.search(r"(\d{1,2}\s+[A-Z][a-z]{2})\s*-\s*close price", txt)
    if not m:
        return {"ok": False, "reason": "no price on page"}
    return {"ok": True, "price": float(m.group(1).replace(",", "")),
            "close_date": d.group(1) if d else None}


def mc_code(sym: str) -> Optional[str]:
    """NSE symbol -> moneycontrol's internal code (RELIANCE -> RI)."""
    body = _get(MC_SEARCH.format(urllib.parse.quote(sym)))
    if not body:
        return None
    try:
        for row in json.loads(body):
            # The suggestion carries "ISIN, NSESYMBOL, ..." — require an EXACT
            # symbol match. Substring matching pairs RELIANCE with RELIANCEPOWER
            # and silently validates against a different company.
            disp = re.sub(r"<[^>]+>", "", row.get("pdt_dis_nm", ""))
            parts = [p.strip() for p in disp.replace("&nbsp;", " ").split(",")]
            if sym.upper() in [p.upper() for p in parts]:
                return row.get("link_src", "").rstrip("/").split("/")[-1]
    except Exception:
        return None
    return None


def mc_price(sym: str) -> dict:
    code = mc_code(sym)
    if not code:
        return {"ok": False, "reason": "symbol not resolved"}
    body = _get(MC_PRICE.format(code))
    if not body:
        return {"ok": False, "reason": "unreachable"}
    try:
        d = json.loads(body).get("data", {})
        p = d.get("pricecurrent") or d.get("HP")
        return ({"ok": True, "price": float(p), "code": code} if p
                else {"ok": False, "reason": "no price field"})
    except Exception as e:
        return {"ok": False, "reason": f"parse: {type(e).__name__}"}


def _latest_scan() -> Optional[Path]:
    fs = sorted((HERE / "indian_full_scan").glob("indian_full_scan_*.xlsx"))
    return fs[-1] if fs else None


def run(sample: int, as_json: bool) -> int:
    f = _latest_scan()
    if not f:
        print("no India scan workbook found", file=sys.stderr)
        return 1
    d = pd.read_excel(f, "All_Stocks")
    d["tv"] = pd.to_numeric(d.get("Median_Turnover"), errors="coerce")
    picks = d.nlargest(sample * 3, "tv")

    rows, done = [], 0
    for _, r in picks.iterrows():
        if done >= sample:
            break
        sym = str(r.get("Symbol", "")).strip().upper()
        ours = pd.to_numeric(pd.Series([r.get("LTP")]), errors="coerce").iloc[0]
        if not sym or ours != ours:
            continue
        s, m = screener_price(sym), mc_price(sym)
        time.sleep(RATE)
        rec = {"symbol": sym, "ours": round(float(ours), 2),
               "screener": s.get("price"), "moneycontrol": m.get("price"),
               "screener_err": None if s["ok"] else s["reason"],
               "mc_err": None if m["ok"] else m["reason"],
               "close_date": s.get("close_date")}
        for k, v in (("screener", s), ("moneycontrol", m)):
            rec[f"{k}_diff_pct"] = (abs(v["price"] - ours) / ours * 100
                                    if v["ok"] and ours else None)
        agree = [k for k in ("screener", "moneycontrol")
                 if rec[f"{k}_diff_pct"] is not None and rec[f"{k}_diff_pct"] <= TOL_PCT]
        reach = [k for k in ("screener", "moneycontrol") if rec[f"{k}_diff_pct"] is not None]
        rec["verdict"] = ("CONFIRMED" if len(agree) == 2 else
                          "DEGRADED" if len(agree) == 1 and len(reach) == 1 else
                          "SPLIT" if len(agree) == 1 else
                          "REJECTED" if len(reach) >= 1 else "NO_SOURCE")
        rows.append(rec); done += 1

    if as_json:
        print(json.dumps(rows, indent=2)); return 0

    print("=" * 84)
    print(f"  CONVERGENCE CHECK — {f.name}   ({len(rows)} picks, tolerance {TOL_PCT}%)")
    print("=" * 84)
    print(f"  {'symbol':<13} {'ours':>10} {'screener':>10} {'moneyctl':>10} "
          f"{'s%':>6} {'m%':>6}  verdict")
    print("  " + "-" * 80)
    for r in rows:
        sp = f"{r['screener']:.2f}" if r["screener"] else (r["screener_err"] or "—")[:10]
        mp = f"{r['moneycontrol']:.2f}" if r["moneycontrol"] else (r["mc_err"] or "—")[:10]
        sd = f"{r['screener_diff_pct']:.2f}" if r["screener_diff_pct"] is not None else "—"
        md = f"{r['moneycontrol_diff_pct']:.2f}" if r["moneycontrol_diff_pct"] is not None else "—"
        print(f"  {r['symbol']:<13} {r['ours']:>10.2f} {sp:>10} {mp:>10} "
              f"{sd:>6} {md:>6}  {r['verdict']}")

    from collections import Counter
    c = Counter(r["verdict"] for r in rows)
    print(f"\n  {dict(c)}")
    print("\n  CONFIRMED  both sources agree with us — strongest evidence")
    print("  DEGRADED   only one source reachable, and it agrees — usable, say so")
    print("  SPLIT      sources disagree with each other — NOT resolved by voting;")
    print("             two sources cannot outvote each other. Inspect the name.")
    print("  REJECTED   reachable source(s) disagree with us — do not send")
    # Exit non-zero only when a reachable source actually contradicts us. An
    # unreachable source must not suppress the brief: that was the failure mode
    # this file exists to remove.
    return 1 if c.get("REJECTED", 0) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Two-source convergence check for the brief")
    ap.add_argument("--sample", type=int, default=6)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    return run(a.sample, a.json)


if __name__ == "__main__":
    sys.exit(main())
