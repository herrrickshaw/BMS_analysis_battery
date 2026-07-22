#!/usr/bin/env python3
"""
Minimal email assembler for the daily market report.

Replaces the (wiped) build_email.py. Loads the latest combined_IN / combined_US
JSONs produced by daily_combined_report.py, adds a market-snapshot banner and a
lightweight Darvas-breakouts section extracted directly from the freshest scan
xlsx (replacing the wiped darvas_breakouts.py), and emits:
  * <repo>/reports/daily_market_report_<date>.html   (email body)
  * <repo>/reports/daily_market_report_artifact.html (artifact page)
"""
import glob, json, os, sys
from datetime import datetime
from pathlib import Path

import data_registry as _R

# PF is this script's OWN directory. It used to be ~/Downloads/code/python_files
# — a stale pre-migration copy of this same repo — so the "latest" scan it found
# was combined_US_20260714 while the live tree had 20260721. Seven days out, no
# error, because both trees exist and both look plausible. Deriving from
# __file__ makes reading someone else's copy impossible rather than merely
# unlikely.
PF = Path(__file__).resolve().parent

# Outputs go to the repo, not ~/Downloads: macOS TCC denies launchd all access
# there, so a scheduled run would fail at write time. The old scratchpad mirror
# pointed at a session UUID that no longer exists — a dead path that silently
# wrote nowhere useful — so it is gone; the repo copy is the durable one.
OUT_DIR = _R.REPO / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DATE = datetime.now().strftime("%Y-%m-%d")
DATE_H = datetime.now().strftime("%d %b %Y")
NOW = datetime.now().strftime("%d %b %Y %H:%M")

DISCLAIMER = ("Educational / research only — NOT investment advice. These are "
              "mechanical quantitative screeners plus noisy news sentiment; they "
              "do not account for your objectives or risk. Past results do not "
              "guarantee future returns. Consult a SEBI-registered adviser before "
              "acting. Convergence is explicitly NOT a buy signal.")

CUR = {"IN": "₹", "US": "$"}


def latest_json(market):
    files = sorted(glob.glob(str(PF / "combined_report_results" /
                                 f"combined_{market}_*.json")))
    if not files:
        return None
    return json.loads(Path(files[-1]).read_text())


def latest_scan_xlsx(market):
    d = "indian_full_scan" if market == "IN" else "us_full_scan"
    files = sorted(glob.glob(str(PF / d / f"*_full_scan_*.xlsx")))
    return files[-1] if files else None


# ---------------------------------------------------------------- market snapshot
def market_snapshot():
    """Nifty vs 200DMA + regime, India VIX, S&P 500 regime. Best-effort."""
    out = {}
    try:
        import yfinance as yf
        import pandas as pd
        def regime(ticker, label):
            try:
                h = yf.Ticker(ticker).history(period="1y")
                if h.empty:
                    return None
                last = float(h["Close"].iloc[-1])
                dma200 = float(h["Close"].tail(200).mean())
                reg = "above 200-DMA (bullish)" if last > dma200 else "below 200-DMA (bearish)"
                return {"label": label, "last": last, "dma200": dma200, "regime": reg}
            except Exception:
                return None
        out["nifty"] = regime("^NSEI", "Nifty 50")
        out["sp500"] = regime("^GSPC", "S&P 500")
        try:
            vh = yf.Ticker("^INDIAVIX").history(period="5d")
            out["vix"] = float(vh["Close"].iloc[-1]) if not vh.empty else None
        except Exception:
            out["vix"] = None
    except Exception as e:
        out["error"] = str(e)
    return out


def snapshot_html(snap):
    parts = []
    n = snap.get("nifty")
    if n:
        parts.append(f"Nifty 50 <b>{n['last']:,.0f}</b> vs 200-DMA {n['dma200']:,.0f} "
                     f"&mdash; {n['regime']}")
    if snap.get("vix") is not None:
        parts.append(f"India VIX <b>{snap['vix']:.2f}</b>")
    s = snap.get("sp500")
    if s:
        parts.append(f"S&amp;P 500 <b>{s['last']:,.0f}</b> &mdash; {s['regime']}")
    if not parts:
        return "<p style='color:#777'>Market snapshot unavailable this run.</p>"
    return "<p>" + " &nbsp;|&nbsp; ".join(parts) + "</p>"


# ---------------------------------------------------------------- Darvas extract
def darvas_section(market, top=15):
    """Lightweight fresh-breakout extraction from the scan's Darvas_Signals sheet."""
    xlsx = latest_scan_xlsx(market)
    tag = {"IN": "India", "US": "US"}[market]
    if not xlsx:
        return f"<p><i>{tag}: scan xlsx unavailable &mdash; Darvas section skipped.</i></p>"
    try:
        import pandas as pd
        xl = pd.ExcelFile(xlsx)
        if "Darvas_Signals" not in xl.sheet_names:
            return f"<p><i>{tag}: no Darvas_Signals sheet.</i></p>"
        df = pd.read_excel(xlsx, sheet_name="Darvas_Signals")
        buys = df[df.get("Darvas_Signal", "").astype(str).str.upper() == "BREAKOUT_BUY"].copy()
        # "fresh" = box position 100-120% if available, else keep all buys
        poscol = next((c for c in df.columns if "position" in c.lower() or "box_pos" in c.lower()), None)
        if poscol:
            buys = buys[(pd.to_numeric(buys[poscol], errors="coerce") >= 100) &
                        (pd.to_numeric(buys[poscol], errors="coerce") <= 120)]
        buys = buys.head(top)
        if buys.empty:
            return f"<p><i>{tag}: no fresh box breakouts today.</i></p>"
        cur = CUR[market]
        rows = []
        for _, r in buys.iterrows():
            sym = r.get("Symbol", "")
            ltp = r.get("LTP", "")
            suf = r.get("Suffix", "")
            exch = f" &middot; {suf}" if suf else ""
            ltp_s = f"{cur}{float(ltp):,.2f}" if str(ltp) not in ("", "nan") else "&mdash;"
            rows.append(f"<tr><td><b>{sym}</b>{exch}</td><td>{ltp_s}</td></tr>")
        return (f"<h3>{tag} &mdash; fresh box breakouts (top {len(buys)})</h3>"
                f"<table><tr><th>Symbol</th><th>LTP</th></tr>{''.join(rows)}</table>")
    except Exception as e:
        return f"<p><i>{tag}: Darvas extraction failed ({e}).</i></p>"


# ---------------------------------------------------------------- news picks
def news_picks_block(markets=("IN", "US"), top=12):
    """Stocks the street is actively talking about — reverse-matched from the
    live news pool, ranked by headline mentions + sentiment. Independent of the
    screeners, so it delivers value even when the picks have no coverage."""
    try:
        import sys
        sys.path.insert(0, str(PF))
        from news_picks import news_picks
    except Exception as e:
        return f"<p style='color:#777'>News picks unavailable ({e}).</p>"
    cur = CUR
    h = ['<p style="font-size:12px;color:#555">Most-covered names in today\'s '
         'market news, with headline sentiment. This is <b>news buzz, not a '
         'recommendation</b> — coverage volume ≠ quality, and sentiment is '
         'mechanical (VADER on headlines).</p>']
    any_rows = False
    for mk in markets:
        try:
            rows = news_picks(mk, top=top)
        except Exception as e:
            h.append(f"<p style='color:#777'>{mk}: news picks failed ({e}).</p>")
            continue
        label = {"IN": "India (NSE/BSE)", "US": "US (NASDAQ/NYSE)"}[mk]
        if not rows:
            h.append(f"<h3>{label}</h3><p style='color:#777'>No clearly-named "
                     f"stocks in today's headlines.</p>")
            continue
        any_rows = True
        tr = []
        for p in rows:
            col = {"POSITIVE": "#2e7d32", "NEGATIVE": "#c62828"}.get(p["label"], "#f57f17")
            tr.append(
                f"<tr><td><b>{p['symbol']}</b> &middot; {p['exchange']}</td>"
                f"<td>{p['name'][:32]}</td><td align='center'>{p['mentions']}</td>"
                f"<td style='color:{col}'>{p['label']}</td>"
                f"<td>{p['score']:+.2f}</td>"
                f"<td style='font-size:12px'>{p['headline']}</td></tr>")
        h.append(f"<h3>{label} &mdash; top {len(rows)} in the news</h3>"
                 "<table><tr><th>Symbol</th><th>Name</th><th>Headlines</th>"
                 "<th>Sentiment</th><th>Score</th><th>Top headline</th></tr>"
                 + "".join(tr) + "</table>")
    if not any_rows:
        h.append("<p>No clearly-named stocks in today's headlines across markets.</p>")
    return "\n".join(h)


# ---------------------------------------------------------------- convergence
def convergence_block(reports):
    high, caution = [], []
    for mk, rep in reports.items():
        if not rep:
            continue
        for c in rep.get("convergence", []):
            conv = c.get("Convergence", "")
            row = (mk, c)
            if "BOTH BULLISH" in conv:
                high.append(row)
            elif "NEGATIVE" in conv:
                caution.append(row)
    h = ['<h2>⭐ CONVERGENCE &mdash; where fundamentals &amp; the street agree</h2>',
         '<p style="font-size:12px;color:#555">Convergence is NOT a buy signal &mdash; '
         'it flags names two independent, noisy signals happen to agree on.</p>']
    if not high and not caution:
        h.append("<p>No fundamental picks had matching news coverage today.</p>")
        return "\n".join(h)
    if high:
        h.append('<p><b>\U0001f3af High-conviction (strong fundamentals AND positive news):</b></p><ul>')
        for mk, c in high:
            h.append(f"<li style='background:#e8f5e9'><b>{c['Symbol']}</b> "
                     f"[{c.get('Tier','')} &middot; {mk}] &mdash; news {c['News_Score']:+.2f} "
                     f"({c['N_Articles']} art): {c.get('Top_Headline','')}</li>")
        h.append("</ul>")
    if caution:
        h.append('<p><b>⚠️ Caution (strong fundamentals BUT negative news):</b></p><ul>')
        for mk, c in caution:
            h.append(f"<li><b>{c['Symbol']}</b> [{mk}] &mdash; news {c['News_Score']:+.2f}: "
                     f"{c.get('Top_Headline','')}</li>")
        h.append("</ul>")
    return "\n".join(h)


# ---------------------------------------------------------------- component 1
def picks_table(rep):
    mk = rep["market"]; cur = CUR[mk]
    picks = rep.get("picks", [])
    if not picks:
        return f"<p>No fundamental picks for {mk} today.</p>"
    triple = [p for p in picks if p["Tier"] == "Triple Hit"]
    multi = [p for p in picks if p["Tier"] == "Multi-Screen"]
    single = [p for p in picks if p["Tier"] == "Single-Screen"]
    def rows(lst, n):
        out = []
        for p in lst[:n]:
            ltp = p.get("LTP")
            ltp_s = f"{cur}{float(ltp):,.2f}" if ltp not in (None, "", "nan") else "&mdash;"
            pio = p.get("Piotroski")
            pio_s = "&mdash;" if pio in (None, "", "nan") else pio
            out.append(f"<tr><td><b>{p['Symbol']}</b></td><td>{ltp_s}</td>"
                       f"<td>{p['Tier']}</td><td>{p['Screens']}</td><td>{pio_s}</td></tr>")
        return "".join(out)
    head = ("<tr><th>Symbol</th><th>LTP</th><th>Tier</th><th>Screens</th>"
            "<th>Piotroski</th></tr>")
    body = rows(triple, 15) + rows(multi, 15) + rows(single, 10)
    note = ""
    if mk == "IN" and not triple and not multi:
        note = ("<p style='font-size:12px;color:#777'>India's full scan carried no "
                "fundamentals this run &mdash; showing top single-screen (Darvas) names.</p>")
    return (f"<h3>{ {'IN':'India (NSE/BSE)','US':'US (NASDAQ/NYSE)'}[mk] } &mdash; "
            f"{len(triple)} triple, {len(multi)} multi-screen</h3>{note}"
            f"<table>{head}{body}</table>")


# ---------------------------------------------------------------- talk
def talk_block(rep):
    mk = rep["market"]
    mood = rep.get("mood") or {}
    talk = rep.get("talk") or {}
    src = ("CNBC · MarketWatch" if mk == "US"
           else "Moneycontrol · ET · BusinessLine · LiveMint")
    col = {"POSITIVE": "#2e7d32", "NEGATIVE": "#c62828"}.get(mood.get("mood"), "#f57f17")
    h = [f"<h3>{ {'IN':'India','US':'US'}[mk] } market mood</h3>"]
    if mood:
        h.append(f"<p>Mood: <b style='color:{col}'>{mood.get('mood')} "
                 f"({mood.get('score',0):+.2f})</b> from {mood.get('n_articles','?')} live "
                 f"articles ({src})</p>")
    rows = []
    for sym, t in sorted(talk.items(), key=lambda x: -x[1].get("score", 0)):
        if t.get("label") in (None, "NO_DATA"):
            continue
        c = {"POSITIVE": "#2e7d32", "NEGATIVE": "#c62828"}.get(t["label"], "#f57f17")
        head = ""
        hl = t.get("headlines") or []
        if hl and isinstance(hl[0], dict):
            head = hl[0].get("title", "")[:70]
        rows.append(f"<tr><td><b>{sym}</b></td><td style='color:{c}'>{t['label']}</td>"
                    f"<td>{t['score']:+.2f}</td><td>{t.get('n_articles',0)}</td>"
                    f"<td style='font-size:12px'>{head}</td></tr>")
    if rows:
        h.append("<table><tr><th>Symbol</th><th>Sentiment</th><th>Score</th>"
                 "<th>Articles</th><th>Top headline</th></tr>" + "".join(rows) + "</table>")
    else:
        h.append("<p style='color:#777'>No per-ticker coverage today.</p>")
    return "\n".join(h)


# ---------------------------------------------------------------- assemble
def build(reports, snap, degraded_note):
    n_picks = sum(len(r.get("picks", [])) for r in reports.values() if r)
    n_conv = sum(len([c for c in (r.get("convergence") or [])
                      if "BOTH BULLISH" in c.get("Convergence", "")])
                 for r in reports.values() if r)
    moods = []
    for mk, r in reports.items():
        if r and r.get("mood"):
            moods.append(f"{mk} {r['mood'].get('mood')}")
    mood_s = " / ".join(moods) or "n/a"

    css = """
    <style>
      body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
           color:#1a1a1a;line-height:1.5;max-width:960px;margin:0 auto;padding:16px}
      h1{font-size:22px;margin:0 0 4px} h2{font-size:18px;border-bottom:2px solid #ddd;
           padding-bottom:4px;margin-top:28px} h3{font-size:15px;margin:18px 0 6px}
      table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px}
      th,td{border:1px solid #e0e0e0;padding:6px 8px;text-align:left}
      th{background:#f5f5f5} .banner{background:#0d47a1;color:#fff;padding:14px 16px;
           border-radius:8px} .banner .disc{font-size:11px;color:#cfd8dc;margin-top:6px}
      .foot{font-size:11px;color:#555;border-top:1px solid #ddd;margin-top:28px;padding-top:12px}
      .warn{background:#fff3e0;border-left:4px solid #fb8c00;padding:8px 12px;font-size:12px;margin:12px 0}
    </style>"""

    ref = """
    <h2>\U0001f4d0 Screener reference</h2>
    <ul style="font-size:12px;color:#444">
      <li><b>Darvas Box</b> &mdash; momentum: price breaking above a consolidation box top (higher reward, higher risk).</li>
      <li><b>Piotroski F-Score</b> &mdash; 9-point fundamental health (profitability, leverage, efficiency); ≥7 = strong.</li>
      <li><b>Coffee Can</b> &mdash; buy-and-hold quality (consistent ROE / revenue growth, low debt).</li>
      <li><b>Magic Formula</b> &mdash; Greenblatt: high earnings yield + high return on capital.</li>
      <li><b>Bull Cartel</b> &mdash; composite momentum + fundamental confluence.</li>
      <li><b>Golden Cross</b> &mdash; 50-DMA crossing above 200-DMA (trend confirmation, lagging).</li>
    </ul>"""

    parts = [css]
    parts.append(f"""<div class="banner">
      <h1>\U0001f4c8 Daily Market Report &mdash; {DATE_H}</h1>
      <div>Generated {NOW} &nbsp;|&nbsp; Fundamentals: {n_picks} picks &nbsp;|&nbsp;
           Street mood: {mood_s} &nbsp;|&nbsp; Convergence: {n_conv}</div>
      <div class="disc">{DISCLAIMER}</div></div>""")
    parts.append("<h2>Market snapshot</h2>" + snapshot_html(snap))
    if degraded_note:
        parts.append(f'<div class="warn">{degraded_note}</div>')

    # Convergence leads
    parts.append(convergence_block(reports))

    # Share-market news picks (news-driven, independent of screeners)
    parts.append("<h2>\U0001f525 Share Market News Picks &mdash; what the street is "
                 "talking about</h2>")
    parts.append(news_picks_block(("IN", "US"), top=12))

    # Component 1
    parts.append("<h2>\U0001f4ca COMPONENT 1 &mdash; Stock picks based on fundamentals</h2>")
    for mk in ("US", "IN"):
        if reports.get(mk):
            parts.append(picks_table(reports[mk]))

    # Darvas
    parts.append("<h2>\U0001f4c8 Darvas breakouts (momentum &mdash; NOT buy recommendations)</h2>")
    parts.append(darvas_section("IN"))
    parts.append(darvas_section("US"))

    # Component 2
    parts.append("<h2>\U0001f5de️ COMPONENT 2 &mdash; Talk on the street</h2>")
    for mk in ("US", "IN"):
        if reports.get(mk):
            parts.append(talk_block(reports[mk]))

    parts.append(ref)
    parts.append(f'<div class="foot">{DISCLAIMER}</div>')
    return "\n".join(parts)


def main():
    reports = {"IN": latest_json("IN"), "US": latest_json("US")}
    degraded = []
    if not reports["IN"]:
        degraded.append("India combined report JSON missing this run.")
    if not reports["US"]:
        degraded.append("US combined report JSON missing this run.")
    degraded.append("Europe scan, and the dedicated Darvas/build-email scripts, were "
                    "lost in a Downloads-tree wipe; Europe is omitted and Darvas is a "
                    "lightweight fallback extraction this run.")
    snap = market_snapshot()
    html = build(reports, snap, " ".join(degraded))

    email_path = OUT_DIR / f"daily_market_report_{DATE}.html"
    art_path = OUT_DIR / "daily_market_report_artifact.html"
    for p in (email_path, art_path):
        try:
            p.write_text(html)
        except OSError as e:
            # Narrow: a write failure here is a real filesystem problem
            # (permissions, full disk) and must be visible. The previous broad
            # except also swallowed the dead-scratchpad writes, which is why
            # nobody noticed two of the four targets never existed.
            print(f"  write {p} failed: {e}")
    print(f"EMAIL_HTML={email_path}")
    print(f"ARTIFACT_HTML={art_path}")
    print(f"PICKS_IN={len(reports['IN'].get('picks', [])) if reports['IN'] else 0}")
    print(f"PICKS_US={len(reports['US'].get('picks', [])) if reports['US'] else 0}")


if __name__ == "__main__":
    main()
