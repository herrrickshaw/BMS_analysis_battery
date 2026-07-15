#!/usr/bin/env python3
"""
carry_fx.py — track the FX pairs whose carry-trade unwinds move THIS brief's equities.

WHY THIS BELONGS IN AN EQUITY BRIEF
-----------------------------------
The carry trade borrows a low-yield funding currency (JPY, CHF) and buys a
high-yield target (AUD, NZD, BRL, MXN, ZAR, TRY, INR). It is a leveraged position
on FX *stability*, so when the funding currency rallies sharply the trade unwinds,
leverage is cut, and the selling lands on equities — the ones this brief scans.

That is not theoretical. On 2024-08-05 a yen-carry unwind (BoJ hike + soft US
payrolls) drove USDJPY down ~12% over three weeks and the Nikkei fell 12.4% in a
single session — its worst day since 1987 — dragging Korea (KOSPI -8.8%) and
global equities with it. An equity brief covering Japan, Korea and India that
ignores JPY strength is blind to the single most common cross-asset transmission
channel into exactly those markets.

WHAT IT TRACKS
--------------
Funding legs (a RALLY here is the danger — it makes the borrowed leg expensive):
    JPY, CHF
Canonical carry crosses (the cleanest unwind signal):
    AUDJPY, NZDJPY
Target legs (a SELLOFF here is the danger — the invested leg loses value):
    AUD, NZD, BRL, MXN, ZAR, TRY, INR

Signal: 1d / 5d / 20d moves in the funding currency vs USD and in the carry
crosses. Sharp funding-currency strength + carry-cross weakness = unwind pressure.
Thresholds are deliberately blunt (a 2%+ single-day JPY move is rare and was the
Aug-2024 tell); this is a heads-up, not a model.

Usage:
    python3 carry_fx.py                 # table
    python3 carry_fx.py --json
    from carry_fx import carry_status, carry_html
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

# yfinance FX convention: "JPY=X" is USD/JPY (yen per USD), so a RISING quote =
# a WEAKER yen. Crosses like "AUDJPY=X" are quoted directly.
FUNDING = {"JPY": "JPY=X", "CHF": "CHF=X"}
CROSSES = {"AUDJPY": "AUDJPY=X", "NZDJPY": "NZDJPY=X"}
TARGETS = {"AUD": "AUDUSD=X", "NZD": "NZDUSD=X", "BRL": "BRL=X",
           "MXN": "MXN=X", "ZAR": "ZAR=X", "TRY": "TRY=X", "INR": "INR=X"}

# A 1-day move beyond this in the funding leg is the "pay attention" line.
# Aug-2024: USDJPY fell ~3% in a day at the peak of the unwind.
FUND_1D_ALERT = 1.5
CROSS_1D_ALERT = 2.0


def _pct(s: pd.Series, n: int):
    s = s.dropna()
    if len(s) <= n:
        return None
    return round((float(s.iloc[-1]) / float(s.iloc[-1 - n]) - 1) * 100, 2)


def _fetch(symbols: list) -> pd.DataFrame:
    import yfinance as yf
    d = yf.download(symbols, period="3mo", progress=False, auto_adjust=True)
    return d["Close"] if "Close" in d else d


def carry_status() -> dict:
    syms = list(FUNDING.values()) + list(CROSSES.values()) + list(TARGETS.values())
    try:
        px = _fetch(syms)
    except Exception as e:
        return {"error": str(e)[:80], "rows": [], "alerts": []}
    if px is None or px.empty:
        return {"error": "no FX data", "rows": [], "alerts": []}

    rows, alerts = [], []

    for name, sym in FUNDING.items():
        s = px[sym] if sym in px.columns else None
        if s is None:
            continue
        d1, d5, d20 = _pct(s, 1), _pct(s, 5), _pct(s, 20)
        # USD/JPY falling => JPY STRENGTHENING => funding leg getting expensive
        strengthen_1d = -d1 if d1 is not None else None
        rows.append({"leg": "funding", "name": f"USD/{name}", "last": round(float(s.dropna().iloc[-1]), 3),
                     "d1": d1, "d5": d5, "d20": d20,
                     "note": f"{name} {'strengthening' if (strengthen_1d or 0) > 0 else 'weakening'}"})
        if strengthen_1d is not None and strengthen_1d >= FUND_1D_ALERT:
            alerts.append(f"{name} strengthened {strengthen_1d:.2f}% in 1d — carry funding leg "
                          f"getting expensive; unwind pressure on AUD/NZD/EM and on JP/KR equities")

    for name, sym in CROSSES.items():
        s = px[sym] if sym in px.columns else None
        if s is None:
            continue
        d1, d5, d20 = _pct(s, 1), _pct(s, 5), _pct(s, 20)
        rows.append({"leg": "carry cross", "name": name, "last": round(float(s.dropna().iloc[-1]), 3),
                     "d1": d1, "d5": d5, "d20": d20,
                     "note": "canonical carry proxy"})
        if d1 is not None and d1 <= -CROSS_1D_ALERT:
            alerts.append(f"{name} fell {d1:.2f}% in 1d — the canonical carry cross unwinding")

    for name, sym in TARGETS.items():
        s = px[sym] if sym in px.columns else None
        if s is None:
            continue
        d1, d5, d20 = _pct(s, 1), _pct(s, 5), _pct(s, 20)
        inverted = sym.endswith("USD=X")          # AUDUSD/NZDUSD quoted as target/USD
        rows.append({"leg": "target", "name": name if inverted else f"USD/{name}",
                     "last": round(float(s.dropna().iloc[-1]), 4),
                     "d1": d1, "d5": d5, "d20": d20,
                     "note": "high-yield leg"})

    return {"rows": rows, "alerts": alerts,
            "as_of": str(px.dropna(how="all").index[-1].date())}


def carry_html() -> str:
    st = carry_status()
    if st.get("error") or not st["rows"]:
        return "<p style='color:#777;font-size:12px'>carry FX unavailable today</p>"
    def f(v):
        if v is None:
            return "—"
        c = "#1b7f37" if v > 0 else "#b00" if v < 0 else "#777"
        return f"<span style='color:{c}'>{v:+.2f}%</span>"
    body = "".join(
        f"<tr><td style='padding:4px 8px'><b>{r['name']}</b></td>"
        f"<td style='color:#777'>{r['leg']}</td><td>{r['last']}</td>"
        f"<td>{f(r['d1'])}</td><td>{f(r['d5'])}</td><td>{f(r['d20'])}</td></tr>"
        for r in st["rows"])
    al = ""
    if st["alerts"]:
        items = "".join(f"<li>{a}</li>" for a in st["alerts"])
        al = ("<div style='background:#fdecea;border-left:3px solid #b00;padding:7px 10px;"
              f"margin:6px 0;font-size:12px'><b>⚠️ Carry-unwind pressure</b><ul style='margin:4px 0'>{items}</ul></div>")
    return (al + "<table style='border-collapse:collapse;width:100%;font-size:12.5px'>"
            "<tr style='background:#eef'><th align='left' style='padding:5px 8px'>Pair</th>"
            "<th align='left'>Leg</th><th align='left'>Last</th><th align='left'>1d</th>"
            f"<th align='left'>5d</th><th align='left'>20d</th></tr>{body}</table>"
            "<p style='font-size:11px;color:#666;margin:3px 0'>Carry unwinds transmit FX stress "
            "into equities: a sharp funding-currency (JPY/CHF) rally forces de-leveraging that "
            "sells the high-yield leg and the equities financed against it. On 2024-08-05 a "
            "yen-carry unwind took the Nikkei -12.4% in one session and the KOSPI -8.8%.</p>")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    st = carry_status()
    if a.json:
        print(json.dumps(st, indent=1)); sys.exit(0)
    if st.get("error"):
        print(f"  error: {st['error']}"); sys.exit(1)
    print(f"\n  === CARRY-TRADE FX (as of {st['as_of']}) ===")
    print(f"  {'PAIR':10s} {'LEG':12s} {'LAST':>10s} {'1d':>8s} {'5d':>8s} {'20d':>8s}")
    for r in st["rows"]:
        g = lambda v: f"{v:+.2f}%" if v is not None else "—"
        print(f"  {r['name']:10s} {r['leg']:12s} {r['last']:>10} "
              f"{g(r['d1']):>8} {g(r['d5']):>8} {g(r['d20']):>8}")
    if st["alerts"]:
        print("\n  ⚠️  UNWIND PRESSURE:")
        for x in st["alerts"]:
            print(f"    - {x}")
    else:
        print("\n  no carry-unwind alerts today")
