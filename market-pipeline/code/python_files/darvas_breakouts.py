# darvas_breakouts.py
# ====================
# Fresh-breakout extractor from the latest full-market scan's Darvas_Signals sheet.
#
# WHY THIS EXISTS
# ---------------
# The raw scans tag EVERY stock trading above its Darvas box as `BREAKOUT_BUY`
# (US ~2,800, India ~1,100, Europe ~400).  That is far too many to act on — most
# have run miles past the box and are no longer "fresh".  This script distils each
# market's BREAKOUT_BUY set down to genuinely fresh, tradable breakouts and emits:
#   • a ready-to-embed HTML fragment (used by build_email.py), and
#   • a ranked CSV  →  ~/Downloads/{in,us,eu}_darvas_breakouts_<date>.csv
#
# FRESHNESS TIERS
#   Tier 1  Golden Cross + Darvas breakout, box position <= 130%   (strongest)
#   Tier 2  box position 100–120%, above 200-DMA, positive day,
#           >= 250 daily bars of history                            (fresh)
# When a market has no Tier-1/Tier-2 names (e.g. Europe, whose box-position scale
# runs very hot) we fall back to the *least-extended* breakouts so the section is
# never empty.
#
# COLUMN ENCODINGS DIVERGE BY MARKET — everything below is read defensively:
#   US  Darvas_Signals : Symbol, LTP, Change%, Darvas_Signal, Box_Top, Box_Bottom,
#                        Upside_to_Top%, Position_in_Box%, Data_Points, GC_Signal,
#                        DMA50, DMA200, DMA_Gap%                        (no Suffix/Name)
#   IN  Darvas_Signals : + Suffix (.BO = BSE, else NSE).  Some scan builds instead
#                        expose an uptrend as a boolean col DMA50_above_200 and omit
#                        DMA_Gap% — both are handled.
#   EU  Darvas_Signals : Symbol, Name, Sector, LTP, Change%, 200_Day_MA,
#                        Distance_to_200MA%, Trend_Signal, Darvas_Signal, Box_Top,
#                        Box_Bottom, Upside_to_Top%, Position_in_Box%   (NO GC_Signal,
#                        NO DMA_Gap% — uptrend read from Distance_to_200MA%/Trend_Signal)
#
# Usage:
#   python darvas_breakouts.py --market IN
#   python darvas_breakouts.py --market US
#   python darvas_breakouts.py --market EU
#   python darvas_breakouts.py --market US --html-only   # print HTML fragment only
#
# ⚠️ Educational/research only. A mechanical breakout filter, NOT investment advice.

from __future__ import annotations

import argparse
import glob
import os
from datetime import date
from pathlib import Path

import pandas as pd

# ── Where scans live and where CSVs go ────────────────────────────────────────
HERE = Path(__file__).resolve().parent
HOME = Path(os.path.expanduser("~"))
DOWNLOADS = HOME / "Downloads"

# Latest-scan glob patterns, most-specific first. Both the local (code/python_files)
# and the mirrored ~/Downloads/data locations are searched.
SCAN_GLOBS = {
    "IN": [
        str(HERE / "indian_full_scan" / "indian_full_scan_*.xlsx"),
        str(DOWNLOADS / "data" / "indian_full_scan" / "indian_full_scan_*.xlsx"),
        str(HERE / "indian_full_scan_*.xlsx"),
    ],
    "US": [
        str(HERE / "us_full_scan" / "us_full_scan_*.xlsx"),
        str(DOWNLOADS / "data" / "us_full_scan" / "us_full_scan_*.xlsx"),
        str(DOWNLOADS / "us_full_scan" / "us_full_scan_*.xlsx"),
        str(HERE / "us_full_scan_*.xlsx"),
    ],
    "EU": [
        str(HERE / "european_scan" / "european_market_scan_*.xlsx"),
        str(DOWNLOADS / "data" / "european_scan" / "european_market_scan_*.xlsx"),
        str(HERE / "european_market_scan_*.xlsx"),
    ],
}

CUR = {"IN": "₹", "US": "$", "EU": "€"}
CSV_TAG = {"IN": "in", "US": "us", "EU": "eu"}

# Fallback ticker→name map (scan All_Fundamentals Name/Sector are often blank).
# EU names are pulled live from full_european_market_scan.EURO_STOXX_50_META when
# available; this covers the most common US/IN large-caps so the fragment reads well.
NAME_MAP = {
    # US
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet", "GOOG": "Alphabet",
    "AMZN": "Amazon", "NVDA": "NVIDIA", "META": "Meta Platforms", "TSLA": "Tesla",
    "ADBE": "Adobe", "INTU": "Intuit", "ADSK": "Autodesk", "AVGO": "Broadcom",
    "AMD": "AMD", "CRM": "Salesforce", "ORCL": "Oracle", "NFLX": "Netflix",
    "RYAAY": "Ryanair", "DKNG": "DraftKings",
    # IN
    "RELIANCE": "Reliance Industries", "TCS": "Tata Consultancy Services",
    "INFY": "Infosys", "HDFCBANK": "HDFC Bank", "ICICIBANK": "ICICI Bank",
    "INDHOTEL": "Indian Hotels", "JSWSTEEL": "JSW Steel", "VARROC": "Varroc Engineering",
    "KARURVYSYA": "Karur Vysya Bank", "VBL": "Varun Beverages", "MASTEK": "Mastek",
}


def _eu_meta():
    """Pull the EU ticker→(name, sector) map from the scan module if importable."""
    try:
        from full_european_market_scan import EURO_STOXX_50_META
        return EURO_STOXX_50_META
    except Exception:
        return {}


# EU exchange from ticker suffix (used to tag the market for the CSV).
EU_EXCH = {
    "L": "London", "F": "Frankfurt", "DE": "XETRA", "PA": "Euronext Paris",
    "AS": "Amsterdam", "BR": "Brussels", "LS": "Lisbon", "IR": "Dublin",
    "MI": "Borsa Italiana", "MC": "Madrid", "ST": "Stockholm", "HE": "Helsinki",
    "CO": "Copenhagen", "OL": "Oslo", "SW": "SIX Swiss", "VI": "Vienna",
    "WA": "Warsaw", "AT": "Athens", "IS": "Istanbul", "PR": "Prague",
    "BD": "Budapest", "TL": "Tallinn", "RG": "Riga", "VS": "Vilnius", "IC": "Iceland",
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _latest_scan(market: str) -> str | None:
    for pat in SCAN_GLOBS[market]:
        files = sorted(glob.glob(pat))
        if files:
            return files[-1]
    return None


def _num(v, default=None):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return float(v)
    except Exception:
        return default


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def _exchange_for(market: str, row: dict) -> str:
    if market == "IN":
        suf = str(row.get("Suffix", "") or "").upper()
        return "BSE" if suf in (".BO", "BO", ".BSE") else "NSE"
    if market == "EU":
        tkr = str(row.get("Symbol", ""))
        suf = tkr.rsplit(".", 1)[-1].upper() if "." in tkr else ""
        return EU_EXCH.get(suf, "Europe")
    return "US"


def _name_for(market: str, sym: str, row: dict) -> str:
    nm = str(row.get("Name", "") or "").strip()
    if nm and nm.lower() not in ("nan", "none"):
        # Yahoo sometimes returns "NAME,ISIN,..." — keep text before first comma.
        return nm.split(",")[0].strip()
    if market == "EU":
        meta = _eu_meta()
        if sym in meta:
            return meta[sym][0]
    return NAME_MAP.get(sym, sym)


# ── Core extraction ───────────────────────────────────────────────────────────
def extract(market: str) -> pd.DataFrame:
    """Return a ranked DataFrame of fresh breakouts for the market, or empty."""
    scan = _latest_scan(market)
    if not scan:
        print(f"  [darvas:{market}] no scan workbook found under {SCAN_GLOBS[market][0]}")
        return pd.DataFrame()

    xl = pd.ExcelFile(scan)
    if "Darvas_Signals" not in xl.sheet_names:
        print(f"  [darvas:{market}] {Path(scan).name} has no Darvas_Signals sheet")
        return pd.DataFrame()
    df = pd.read_excel(scan, sheet_name="Darvas_Signals")
    if df.empty or "Darvas_Signal" not in df.columns:
        return pd.DataFrame()

    has_gc = "GC_Signal" in df.columns
    has_gap = "DMA_Gap%" in df.columns
    has_dma50flag = "DMA50_above_200" in df.columns
    has_dist = "Distance_to_200MA%" in df.columns
    has_trend = "Trend_Signal" in df.columns
    has_dp = "Data_Points" in df.columns

    rows = []
    for _, r in df.iterrows():
        rr = r.to_dict()
        if str(rr.get("Darvas_Signal", "")).upper() != "BREAKOUT_BUY":
            continue
        sym = str(rr.get("Symbol", "") or "").strip()
        if not sym:
            continue

        pos = _num(rr.get("Position_in_Box%"))          # >100 = above box
        upside = _num(rr.get("Upside_to_Top%"), 0.0)
        chg = _num(rr.get("Change%"), 0.0)
        dp = _num(rr.get("Data_Points"), 9999) if has_dp else 9999
        gap = _num(rr.get("DMA_Gap%")) if has_gap else (
            _num(rr.get("Distance_to_200MA%")) if has_dist else None)

        gc = str(rr.get("GC_Signal", "")).upper() if has_gc else ""
        golden = gc == "GOLDEN_CROSS"
        # Uptrend / above-200-DMA, read from whichever encoding this scan uses.
        uptrend = (
            (has_gc and gc in ("GOLDEN_CROSS", "ABOVE_200DMA"))
            or (has_dma50flag and _truthy(rr.get("DMA50_above_200")))
            or (has_dist and (_num(rr.get("Distance_to_200MA%"), -1) or -1) > 0)
            or (has_trend and any(k in str(rr.get("Trend_Signal", "")).lower()
                                  for k in ("uptrend", "above")))
        )

        # Freshness tiers (guard on box position being present).
        p = pos if pos is not None else 999
        if golden and p <= 130:
            tier = 1
        elif 100 <= p <= 120 and uptrend and chg > 0 and dp >= 250:
            tier = 2
        else:
            tier = 3  # extended / not-fresh — kept only for the fallback pool

        # Ranking score: prefer tight (just above box), in uptrend, positive day.
        # Lower position (closer to 100) is fresher; reward DMA gap & change.
        prox = max(0.0, 100.0 - abs(p - 105))           # peaks near +5% above box
        score = prox + (chg or 0) + (0.5 * (gap or 0)) + (8 if golden else 0) \
            + (4 if uptrend else 0)

        rows.append({
            "Tier": tier,
            "Symbol": sym,
            "Name": _name_for(market, sym, rr),
            "Exchange": _exchange_for(market, rr),
            "LTP": _num(rr.get("LTP")),
            "Change%": chg,
            "Box_Top": _num(rr.get("Box_Top")),
            "Box_Bottom": _num(rr.get("Box_Bottom")),
            "Position_in_Box%": pos,
            "Upside_to_Top%": upside,
            "50/200_Gap%": gap,
            "Golden_Cross": "YES" if golden else "",
            "Uptrend": "YES" if uptrend else "",
            "_score": score,
        })

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    fresh = out[out["Tier"].isin([1, 2])].copy()
    if fresh.empty:
        # Fallback: least-extended breakouts (closest box position to 100 that are
        # still above the box), so the section is never empty (EU commonly hits this).
        pool = out.copy()
        pool["_ext"] = (pool["Position_in_Box%"].fillna(9999) - 100).abs()
        fresh = pool.sort_values("_ext").head(12).drop(columns="_ext")
        fresh["Tier"] = fresh["Tier"].where(fresh["Tier"] < 3, 3)
    fresh = fresh.sort_values(["Tier", "_score"], ascending=[True, False])
    return fresh.reset_index(drop=True)


# ── HTML fragment ─────────────────────────────────────────────────────────────
def _fmt(v, nd=2):
    return "n/a" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v:,.{nd}f}"


def rows_html(df: pd.DataFrame, market: str) -> str:
    cur = CUR[market]
    body = []
    for _, r in df.iterrows():
        tier = int(r["Tier"])
        badge = ("🥇 T1" if tier == 1 else "🥈 T2" if tier == 2 else "•")
        gap = r.get("50/200_Gap%")
        body.append(
            f"<tr><td>{badge}</td>"
            f"<td><b>{r['Symbol']}</b></td>"
            f"<td>{r['Name']}</td>"
            f"<td>{r['Exchange']}</td>"
            f"<td style='text-align:right'>{cur}{_fmt(r['LTP'])}</td>"
            f"<td style='text-align:right;color:{'#2e7d32' if (r['Change%'] or 0) >= 0 else '#c62828'}'>"
            f"{(r['Change%'] or 0):+.2f}%</td>"
            f"<td style='text-align:right'>{_fmt(r['Position_in_Box%'], 0)}%</td>"
            f"<td style='text-align:right'>{_fmt(r['Upside_to_Top%'], 1)}%</td>"
            f"<td style='text-align:right'>{'n/a' if gap is None else f'{gap:+.1f}%'}</td>"
            f"<td>{r['Golden_Cross']}</td></tr>"
        )
    return "".join(body)


def to_html(df: pd.DataFrame, market: str) -> str:
    label = {"IN": "🇮🇳 India", "US": "🇺🇸 US", "EU": "🇪🇺 Europe"}[market]
    if df.empty:
        return (f'<h3>📈 {label} — Darvas Breakouts</h3>'
                f'<p style="color:#777">No fresh breakouts in the latest scan.</p>')
    n1 = int((df["Tier"] == 1).sum())
    n2 = int((df["Tier"] == 2).sum())
    head = ("<tr><th>Tier</th><th>Symbol</th><th>Name</th><th>Exch</th>"
            "<th>LTP</th><th>Day</th><th>Box Pos</th><th>Upside</th>"
            "<th>50/200</th><th>GC</th></tr>")
    return (
        f'<h3>📈 {label} — Darvas Breakouts '
        f'<span style="font-weight:400;color:#777">({n1} Tier-1 · {n2} Tier-2)</span></h3>'
        f'<div class="trail" style="overflow-x:auto">'
        f'<table style="border-collapse:collapse;width:100%;font-size:12.5px">'
        f'{head}{rows_html(df, market)}</table></div>'
        f'<p style="font-size:11px;color:#888;margin-top:4px">Tier 1 = Golden Cross + '
        f'Darvas breakout, box position ≤130%. Tier 2 = box position 100–120%, above '
        f'200-DMA, up day, ≥250 daily bars. "Box Pos" &gt;100% = trading above the box.</p>'
    )


# ── Public API for build_email.py ─────────────────────────────────────────────
def build(market: str, write_csv: bool = True) -> tuple[str, pd.DataFrame]:
    """Return (html_fragment, ranked_df) and optionally write the ranked CSV."""
    market = market.upper()
    df = extract(market)
    if write_csv and not df.empty:
        out = DOWNLOADS / f"{CSV_TAG[market]}_darvas_breakouts_{date.today():%Y%m%d}.csv"
        df.drop(columns=[c for c in ("_score",) if c in df.columns]).to_csv(out, index=False)
        print(f"  [darvas:{market}] {len(df)} fresh breakouts → {out}")
    return to_html(df, market), df


def main():
    ap = argparse.ArgumentParser(description="Fresh Darvas-breakout extractor per market")
    ap.add_argument("--market", choices=["IN", "US", "EU"], default="US")
    ap.add_argument("--html-only", action="store_true",
                    help="Print the HTML fragment only (no CSV, no summary)")
    a = ap.parse_args()

    html, df = build(a.market, write_csv=not a.html_only)
    if a.html_only:
        print(html)
        return
    print(f"\n{'='*66}\n  {a.market} DARVAS BREAKOUTS\n{'='*66}")
    if df.empty:
        print("  No fresh breakouts.")
    else:
        n1 = int((df["Tier"] == 1).sum())
        n2 = int((df["Tier"] == 2).sum())
        print(f"  {len(df)} fresh ({n1} Tier-1, {n2} Tier-2)\n")
        cols = ["Tier", "Symbol", "Name", "Exchange", "LTP", "Change%",
                "Position_in_Box%", "Upside_to_Top%", "Golden_Cross"]
        print(df[cols].to_string(index=False))


if __name__ == "__main__":
    main()
