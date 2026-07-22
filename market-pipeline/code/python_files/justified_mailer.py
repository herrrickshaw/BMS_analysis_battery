#!/usr/bin/env python3
"""
justified_mailer.py — the evidence-first brief: only screens that earned their
place in a backtest, each section headed by the numbers that justify it.

WHY THIS EXISTS
---------------
The daily brief runs every screener everywhere. This mailer inverts that: it
starts from the repo's measured evidence and shows ONLY the best-backtested
screen per market, with the backtest result, sample size and test window printed
above the picks. What didn't survive testing is listed too — an exclusion with a
reason is information; a silent omission is not.

EVIDENCE SOURCES (all in-repo, cited in the email):
  * BACKTEST_FINDINGS.md (global-stock-screener) — point-in-time technical
    screens, 10y (2016→2026), 21-day forward horizon, 5 markets, equal-weight
    market benchmark. THE primary evidence.
  * reports/factor_combo_{india,us}_252d.csv — fundamental factor combos,
    252-day forward, with explicit n / years / t-stat.
  * Piotroski PIT (SEC EDGAR) finding — US high-F INVERTED; and the
    cost/capacity result: the Piotroski edge is an ILLIQUIDITY premium,
    retail-scale only (survives ~$100k, dead by ~$10M).

RULES
  * A market's section runs its backtest-best screen on TODAY's data.
  * Golden Cross appears nowhere (worst screen in every tested market).
  * Europe gets no picks — untested there is untested, and saying so beats
    borrowing another market's evidence.
  * Liquidity: picks come from the gated universes (India workbook is
    pre-gated; US/JP/KR joined to Liquidity_Tier, T1–T3 only).

Usage:
    justified_mailer.py            # build + print summary + save HTML draft
    justified_mailer.py --send     # also email it (env_loader creds)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BHAV = Path("/Users/umashankar/market-pipeline/data/bhavcopy_cache")
OUT_HTML = HERE / "reports" / "justified_brief.html"

PANELS = {
    "US": BHAV / "ohlcv_US.parquet",
    "JP": BHAV / "ohlcv_JAPAN.parquet",
    "KR": BHAV / "ohlcv_KOREA.parquet",
    # cleaned_long, NOT ohlcv_NSE: the scan cache holds ~126 bars, which is
    # exactly too short for 126-day momentum (shift lands off the edge — first
    # run produced 2 non-NaN momenta out of 2,069 symbols). cleaned_long holds
    # ~273 trading days with NSE precedence pre-resolved.
    "IN": BHAV / "cleaned_long.parquet",
}
WORKBOOKS = {
    "US": ("us_full_scan/us_full_scan_*.xlsx", "Symbol"),
    "JP": ("japan_scan/japan_market_scan_*.xlsx", "YF_Ticker"),
    "KR": ("korea_scan/korea_market_scan_*.xlsx", "YF_Ticker"),
}
GOOD_TIERS = {"T1_MOST_LIQUID", "T2_LIQUID", "T3_MID"}
TOP_N = 10

# The evidence block per section — shown in the email verbatim. Numbers are
# from BACKTEST_FINDINGS.md; keep in sync with that file, not with hope.
EVIDENCE = {
    "IN": dict(screen="near-52w-high + momentum", edge="+1.33pp (near_high) / +1.18pp (momentum)",
               win="0.456", window="2016→2026 (10y), 21-day fwd, point-in-time",
               universe="6,573 NSE/BSE symbols (deep LTM panel)",
               note="India is the momentum exception — these screens are NEGATIVE in US/KR/CN."),
    "US": dict(screen="RSI-14 oversold (&lt;30)", edge="+1.85pp", win="0.463",
               window="2016→2026 (10y), 21-day fwd, point-in-time",
               universe="9,278 US symbols (deep LTM panel)",
               note="Mean-reversion beat the market here; breakout screens were negative."),
    "KR": dict(screen="RSI-14 oversold (&lt;30)", edge="+2.04pp", win="0.481",
               window="2016→2026 (10y), 21-day fwd, point-in-time",
               universe="KOSPI+KOSDAQ deep panel",
               note="Strongest oversold edge of the five tested markets."),
    "JP": dict(screen="RSI-14 oversold (&lt;30)", edge="+0.93pp", win="0.513",
               window="2016→2026 (10y), 21-day fwd, point-in-time",
               universe="TSE deep panel",
               note="Highest win-rate of any screen/market pair tested (0.513)."),
}

EXCLUDED = [
    ("Golden Cross (all markets)", "worst screen in every tested market "
     "(US −0.46, KR −0.58, CN −0.89, IN −0.07 pp); adds no out-of-sample value"),
    ("Europe picks", "no backtest covers Europe — untested is untested; "
     "borrowing US evidence for EU names would be dressing, not justification"),
    ("india_factor_panel fundamental signals", "documented alphabetical sample "
     "(98% A-names, 2026-07-21 CHANGELOG) — its recurrences measure the bias"),
    ("near_high / momentum outside India", "negative edge in US (−0.90), "
     "KR (+0.22 near_high but −0.50 momentum), CN (−0.32/−0.69)"),
]

CAVEATS = ("Edges are small (0.2–2.0pp per 21 days), before transaction costs. "
           "Survivorship: the LTM panel is currently-listed-heavy. 21-day horizon "
           "only. Educational/research only — NOT investment advice.")


def rsi14(close: pd.Series) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _tiers(market: str) -> pd.Series:
    glob, scol = WORKBOOKS[market]
    files = sorted(HERE.glob(glob))
    if not files:
        return pd.Series(dtype=str)
    df = pd.read_excel(files[-1], sheet_name="All_Stocks")
    name = df["Name"] if "Name" in df.columns else pd.Series("", index=df.index)
    out = pd.DataFrame({"sym": df[scol].astype(str), "tier": df.get("Liquidity_Tier", ""),
                        "name": name})
    return out.drop_duplicates("sym").set_index("sym")


def oversold_picks(market: str) -> pd.DataFrame:
    """Today's RSI-14 < 30 names in the liquid tiers, most-oversold first.

    Guards: >=100 bars of history (a 20-bar listing can print RSI ~0 on noise)
    and, for the US, the scan's own $2 price floor — without these the top of
    the list is delisting-bound zombies with 14 straight red days."""
    px = pd.read_parquet(PANELS[market], columns=["Date", "Symbol", "Close"])
    px = px.sort_values(["Symbol", "Date"])
    bars = px.groupby("Symbol")["Close"].transform("size")
    px = px[bars >= 100]
    g = px.groupby("Symbol")["Close"]
    rsi = g.transform(rsi14)
    last = px.assign(rsi=rsi).groupby("Symbol").tail(1)
    if market == "US":
        last = last[last["Close"] >= 2.0]
    meta = _tiers(market)
    last = last.join(meta, on="Symbol")
    last = last[last["tier"].isin(GOOD_TIERS)]
    picks = last[(last["rsi"] > 2) & (last["rsi"] < 30)].nsmallest(TOP_N, "rsi")
    return pd.DataFrame({"symbol": picks["Symbol"], "name": picks["name"].fillna(""),
                         "metric": picks["rsi"].round(1).astype(str) + " RSI",
                         "close": picks["Close"]})


def _india_equity_names() -> pd.DataFrame:
    """Equity-only allowlist from the raw NSE archive, keyed by ISIN prefix.

    The ISIN prefix is the instrument-type key (INE=corporate equity,
    INF=fund/ETF, IN0-3=G-Secs) — series/instrument-type columns do NOT filter
    funds, which is exactly how LIQUIDSBI (an ETF) once shipped as a
    golden-cross pick. Without this, sector ETFs dominate any momentum list:
    first run of this mailer surfaced PHARMABEES/HEALTHIETF/MOMNC as 'stocks'."""
    raw = pd.read_parquet(BHAV / "nse.parquet",
                          columns=["TckrSymb", "ISIN", "SctySrs", "FinInstrmNm"])
    eq = raw[raw["ISIN"].astype(str).str.startswith("INE")
             & (raw["SctySrs"] == "EQ")]
    return (eq.drop_duplicates("TckrSymb")
              .set_index("TckrSymb")["FinInstrmNm"])


def india_momentum_picks() -> pd.DataFrame:
    """Near-52w-high AND positive 6m momentum, ranked by momentum. The NSE
    cache is the already-liquidity-gated universe (~2,400 names); filtered to
    real equities via ISIN before ranking."""
    px = pd.read_parquet(PANELS["IN"], columns=["Date", "Symbol", "Close"])
    names = _india_equity_names()
    px = px[px["Symbol"].isin(names.index)]
    # Liquidity gate: cleaned_long is the FULL ~5,200-symbol universe; without
    # this, penny movers (VIJIFIN @ ₹9) top the momentum list. The scan
    # workbook's All_Stocks already cleared the ₹1cr median-turnover floor.
    wb = sorted(HERE.glob("indian_full_scan/indian_full_scan_*.xlsx"))
    if wb:
        gated = set(pd.read_excel(wb[-1], sheet_name="All_Stocks")["Symbol"].astype(str))
        px = px[px["Symbol"].isin(gated)]
    px = px.sort_values(["Symbol", "Date"])
    g = px.groupby("Symbol")["Close"]
    hi252 = g.transform(lambda s: s.rolling(252, min_periods=120).max())
    mom126 = g.transform(lambda s: s / s.shift(126) - 1)
    last = px.assign(hi=hi252, mom=mom126).groupby("Symbol").tail(1)
    # The backtest tested near_high and momentum as SEPARATE screens (both
    # positive in India); intersecting them is stricter than the evidence and
    # left one name on first run. Show each screen's top half instead.
    nh = last[last["Close"] >= 0.95 * last["hi"]].nlargest(TOP_N // 2, "mom")
    mo = last[last["mom"] > 0].nlargest(TOP_N, "mom")
    mo = mo[~mo["Symbol"].isin(nh["Symbol"])].head(TOP_N // 2)
    picks = pd.concat([
        nh.assign(metric=(nh["Close"] / nh["hi"] * 100).round(1).astype(str) + "% of 52w-hi"),
        mo.assign(metric=(mo["mom"] * 100).round(1).astype(str) + "% 6m mom"),
    ])
    return pd.DataFrame({"symbol": picks["Symbol"],
                         "name": picks["Symbol"].map(names).fillna(""),
                         "metric": picks["metric"],
                         "close": picks["Close"]})


def fundamentals_overlay() -> str:
    """The factor-combo evidence table, numbers straight from the CSVs."""
    rows = []
    for mkt, f in (("India", "reports/factor_combo_india_252d.csv"),
                   ("US", "reports/factor_combo_us_252d.csv")):
        try:
            df = pd.read_csv(HERE / f)
        except Exception:
            continue
        for _, r in df.iterrows():
            if r["combo"] in ("piotroski", "roce_plus", "piotroski + roce_plus") \
                    and bool(r.get("testable", False)):
                rows.append(f"<tr><td>{mkt}</td><td>{r['combo']}</td>"
                            f"<td>{int(r['n']):,}</td><td>{r['n_years']:.0f}y</td>"
                            f"<td>{r['edge']:+.1f}pp</td><td>{r['t']:.2f}</td>"
                            f"<td>{int(r['years_positive'])}/{int(r['n_years'])}</td></tr>")
    if not rows:
        return ""
    return (
        '<h3 style="margin:18px 0 4px">Fundamental overlay — factor combos (252-day fwd)</h3>'
        '<table style="border-collapse:collapse;font-size:12px;width:100%">'
        '<tr style="text-align:left;border-bottom:1px solid #ccc">'
        '<th style="padding:3px 6px">Mkt</th><th>Combo</th><th>n</th><th>Span</th>'
        '<th>Edge</th><th>t-stat</th><th>Yrs +</th></tr>' + "".join(rows) + "</table>"
        '<p style="font-size:11px;color:#875c00;background:#fff8e6;padding:6px 8px;margin:6px 0">'
        "Read honestly: edges are directionally positive but t-stats are weak "
        "(&lt;1) — suggestive, not significant. Two further checks temper the US row: "
        "the point-in-time SEC-EDGAR backtest found US high-F <b>inverted</b> "
        "(high scores underperformed), and the cost model shows the Piotroski edge "
        "is an <b>illiquidity premium</b> — intact at ~$100k deployed, gone by ~$10M. "
        "Treat the overlay as a quality tag on technical picks, not a standalone signal.</p>")


def section(market: str, label: str, picks: pd.DataFrame) -> str:
    ev = EVIDENCE[market]
    head = (
        f'<h3 style="margin:18px 0 2px">{label} — {ev["screen"]}</h3>'
        f'<p style="font-size:11px;color:#555;background:#eef4fb;padding:6px 8px;margin:2px 0 6px">'
        f'<b>Why this screen:</b> edge <b>{ev["edge"]}</b> vs equal-weight market, '
        f'win rate {ev["win"]} · tested {ev["window"]} · universe {ev["universe"]}. '
        f'{ev["note"]}</p>')
    if picks.empty:
        return head + '<p style="font-size:12px;color:#888">No qualifying names today.</p>'
    rows = "".join(
        f'<tr><td style="padding:3px 6px"><b>{r.symbol}</b></td>'
        f'<td style="color:#666">{(r.name_ or "")[:34]}</td>'
        f'<td>{r.metric}</td><td>{r.close:,.2f}</td></tr>'
        for r in picks.rename(columns={"name": "name_"}).itertuples())
    return head + (
        '<table style="border-collapse:collapse;font-size:12px;width:100%">'
        '<tr style="text-align:left;border-bottom:1px solid #ccc">'
        '<th style="padding:3px 6px">Symbol</th><th>Name</th><th>Signal</th><th>Close</th></tr>'
        + rows + "</table>")


def build(picks: dict) -> str:
    today = date.today().strftime("%d %b %Y")
    parts = [
        '<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:680px">',
        f'<h2 style="margin:0 0 2px">🧪 Justified Brief — {today}</h2>',
        '<p style="color:#666;font-size:12px;margin:0 0 10px">Every section below '
        'exists because a backtest says it should. The evidence (result, sample, '
        'test window) is printed above each list; what failed testing is listed at '
        'the bottom with reasons.</p>',
    ]
    parts.append(section("IN", "🇮🇳 India", picks["IN"]))
    for mkt, label in (("US", "🇺🇸 US"), ("KR", "🇰🇷 Korea"), ("JP", "🇯🇵 Japan")):
        parts.append(section(mkt, label, picks[mkt]))
    parts.append(fundamentals_overlay())
    parts.append(
        '<h3 style="margin:18px 0 4px">Excluded by evidence</h3><ul style="font-size:12px;color:#555">'
        + "".join(f"<li><b>{k}</b> — {v}</li>" for k, v in EXCLUDED) + "</ul>")
    parts.append(f'<p style="font-size:10px;color:#999;border-top:1px solid #eee;'
                 f'padding-top:8px">{CAVEATS} Sources: BACKTEST_FINDINGS.md, '
                 f'factor_combo_*_252d.csv, piotroski PIT/cost studies — all in-repo.</p></div>')
    return "\n".join(parts)


def send(html: str) -> bool:
    import smtplib
    from email.mime.text import MIMEText
    sys.path.insert(0, str(HERE))
    import env_loader as env
    user, pw = env.get("GMAIL_USER"), env.get("GMAIL_APP_PASSWORD")
    to = env.get("MAIL_TO") or user
    if not (user and pw):
        print("  no creds — not sent"); return False
    msg = MIMEText(html, "html")
    msg["Subject"] = f"🧪 Justified Brief — {date.today():%d %b %Y}"
    msg["From"], msg["To"] = user, to
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw); s.send_message(msg)
    print(f"  sent → {to}")
    return True


def sync_watchlist(picks_by_market: dict) -> int:
    """Track today's justified picks in watchlist.csv under their own
    `justified` status — rendered as a SEPARATE table in the digest, never
    mixed into held/watch/sold. Existing rows are never touched (same
    contract as signal_tracker / recurring_movers)."""
    wl_path = HERE / "watchlist.csv"
    if not wl_path.exists():
        return 0
    wl = pd.read_csv(wl_path)
    have = {(str(r["symbol"]).upper(), str(r["market"]).upper())
            for _, r in wl.iterrows()}
    rows = []
    for mkt, picks in picks_by_market.items():
        for r in picks.itertuples():
            k = (str(r.symbol).upper(), mkt)
            if k in have:
                continue
            rows.append({"symbol": r.symbol, "market": mkt, "status": "justified",
                         "note": f"{r.metric} @ {date.today():%Y-%m-%d}"})
            have.add(k)
    if rows:
        pd.concat([wl, pd.DataFrame(rows)], ignore_index=True).to_csv(
            wl_path, index=False)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--sync-watchlist", action="store_true",
                    help="add today's picks to watchlist.csv as `justified` tier")
    a = ap.parse_args()
    picks = {"IN": india_momentum_picks(),
             "US": oversold_picks("US"),
             "KR": oversold_picks("KR"),
             "JP": oversold_picks("JP")}
    html = build(picks)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html)
    print(f"  draft → {OUT_HTML}")
    if a.sync_watchlist:
        n = sync_watchlist(picks)
        print(f"  watchlist.csv: +{n} `justified` rows (existing untouched)")
    if a.send:
        send(html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
