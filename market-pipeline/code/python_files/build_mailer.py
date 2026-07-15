#!/usr/bin/env python3
# build_mailer.py
# ===============
# Assemble the Daily Market Brief HTML (+ plain-text summary) — the ONE
# assembler for the live daily_pipeline.sh -> send_mailer.py path.
#
# Merged 2026-07-13 with the previously-separate, unused-on-this-branch
# build_email.py to avoid two overlapping report builders. This file now
# covers everything build_email.py did, plus what build_mailer.py already
# had:
#   1. Market snapshot (India/US/Europe vs 200-DMA)
#   2. India / US / Europe / Japan / Korea — fundamentals screener picks
#   3. India Cash Conversion Cycle (screener.in 228040)
#   4. Convergence (fundamentals + positive/negative news agree)
#   5. Share Market News Picks — India + US (headline-driven, screener-independent)
#   6. Talk on the Street — per-ticker sentiment for the fundamental picks
#   7. Darvas Breakouts — India / US / Europe fresh-breakout fragments
#      (Japan/Korea skipped: darvas_breakouts.py has no scan-glob support for
#      those markets yet)
#   8. Global momentum top-15 + "other markets" world tour
#   9. 20-market 5-year scoreboard
#   10. Market Correlation Highlights — top clusters per market from
#       market_correlation_scan.py (NSE/US/Europe/Japan/Korea)
#   + educational-only / NOT-investment-advice disclaimer.
#
# Every section degrades gracefully to "n/a" / an empty-state message when
# its source data (a scan xlsx / combined JSON / darvas_breakouts.py /
# correlation_scan/*.txt) hasn't been generated yet — nothing here is fatal
# to the rest of the report.
#
#   from build_mailer import build; subj, text, html = build()

from __future__ import annotations

import ast
import datetime as _dt
import glob
import json
import re
import warnings

import pandas as pd

warnings.filterwarnings("ignore")

import liquidity as liq
import run_global_analysis as rga
import market_performance as mp
import news_picks as npk

try:
    import darvas_breakouts as dbrk
except Exception:
    dbrk = None

_COL = {"High": "#1b7f37", "Medium": "#b8860b", "Low": "#b00"}
_SENT_COL = {"POSITIVE": "#1b7f37", "NEGATIVE": "#b00", "NEUTRAL": "#777"}


def _tv(x):
    return f"${x/1e6:.1f}M" if pd.notna(x) else "—"


def _table(headers, rows):
    h = "".join(f"<th align='left' style='padding:5px 8px'>{x}</th>" for x in headers)
    return (f"<table style='border-collapse:collapse;width:100%;font-size:13px'>"
            f"<tr style='background:#eef'>{h}</tr>{''.join(rows)}</table>")


def _load_combined(market: str) -> dict:
    files = sorted(glob.glob(f"combined_report_results/combined_{market}_*.json"))
    if not files:
        return {}
    try:
        return json.load(open(files[-1]))
    except Exception:
        return {}


def _news_rows(market: str, top: int = 8):
    try:
        picks = npk.news_picks(market, top=top)
    except Exception:
        return []
    rows = []
    for p in picks:
        rows.append(
            f"<tr><td style='padding:4px 8px'><b>{p['symbol']}</b></td>"
            f"<td>{p['name']}</td>"
            f"<td style='color:{_SENT_COL.get(p['label'], '#777')};font-weight:600'>{p['label']} ({p['score']:+.2f})</td>"
            f"<td>{p['mentions']}</td>"
            f"<td style='color:#555'>{p['headline']}</td></tr>"
        )
    return rows


def _market_picks_rows(data: dict, market: str, cap: int = 12):
    """Fundamentals-screener picks rows for India/US, liquidity-annotated."""
    picks = data.get("picks") or []
    if not picks:
        return []
    p = pd.DataFrame(picks)
    p["Market"] = market
    p = liq.annotate(p)
    rank = {"Triple Hit": 0, "Multi-Screen": 1, "Single-Screen": 2}
    lr = {"High": 0, "Medium": 1, "Low": 2, "Unknown": 3}
    p["_o"] = p["Tier"].map(rank).fillna(3)
    p["_l"] = p["Liquidity"].map(lr).fillna(3)
    rows = []
    for _, r in p.sort_values(["_o", "_l"]).head(cap).iterrows():
        rows.append(f"<tr><td style='padding:4px 8px'><b>{r.Symbol}</b></td>"
                    f"<td>{r.Tier}</td><td>{r.Screens}</td><td>{_tv(r.get('Turnover_USD'))}</td>"
                    f"<td style='color:{_COL.get(r.Liquidity,'#777')};font-weight:600'>{r.Liquidity}</td></tr>")
    return rows


def _eu_picks_rows(top: int = 15):
    """Europe has no combined JSON — read the EU scan's Fundamentals sheet directly."""
    files = sorted(glob.glob("european_scan/european_market_scan*.xlsx"))
    if not files:
        return []
    try:
        xl = pd.ExcelFile(files[-1])
        if "Fundamentals" not in xl.sheet_names:
            return []
        fd = pd.read_excel(files[-1], sheet_name="Fundamentals")
    except Exception:
        return []

    def _pio(v):
        try:
            return int(float(v))
        except Exception:
            return None

    cands = []
    for _, r in fd.iterrows():
        pio = _pio(r.get("Piotroski_Score"))
        cc = str(r.get("CoffeeCan_Class", "")).upper() == "PASS"
        if not ((pio is not None and pio >= 7) or cc):
            continue
        cands.append((pio, cc, r))
    cands.sort(key=lambda x: -(x[0] if x[0] is not None else -1))

    rows = []
    for pio, cc, r in cands[:top]:
        sym = str(r.get("Symbol", "")).strip()
        name = str(r.get("Name", "") or sym).split(",")[0]
        tier = "Triple Hit" if (pio is not None and pio >= 7 and cc) else "Multi-Screen"
        screens = "+".join(s for s, ok in (("Piotroski", pio is not None and pio >= 7),
                                            ("CoffeeCan", cc)) if ok) or "—"
        rows.append(f"<tr><td style='padding:4px 8px'><b>{sym}</b></td><td>{name}</td>"
                    f"<td>{tier}</td><td>{screens}</td>"
                    f"<td>{'n/a' if pio is None else pio}</td></tr>")
    return rows


def _jp_picks_rows(top: int = 15):
    """Japan has no combined JSON — read the JP scan's Fundamentals sheet directly.
    Mirrors _eu_picks_rows(); Japan's sheet uses Piotroski_Strong (YES/NO) and a
    plain CoffeeCan (PASS/FAIL) column rather than EU's *_Class columns."""
    files = sorted(glob.glob("japan_scan/japan_market_scan*.xlsx"))
    if not files:
        return []
    try:
        xl = pd.ExcelFile(files[-1])
        if "Fundamentals" not in xl.sheet_names:
            return []
        fd = pd.read_excel(files[-1], sheet_name="Fundamentals")
    except Exception:
        return []

    def _pio(v):
        try:
            return int(float(v))
        except Exception:
            return None

    cands = []
    for _, r in fd.iterrows():
        pio = _pio(r.get("Piotroski_Score"))
        strong = str(r.get("Piotroski_Strong", "")).upper() == "YES"
        cc = str(r.get("CoffeeCan", "")).upper() == "PASS"
        if not (strong or cc or (pio is not None and pio >= 7)):
            continue
        cands.append((pio, strong, cc, r))
    cands.sort(key=lambda x: -(x[0] if x[0] is not None else -1))

    rows = []
    for pio, strong, cc, r in cands[:top]:
        code = str(r.get("Code", "") or r.get("YF_Ticker", "") or "").strip()
        name = str(r.get("Name", "") or code).split(",")[0]
        pio_ok = strong or (pio is not None and pio >= 7)
        tier = "Triple Hit" if (pio_ok and cc) else "Multi-Screen"
        screens = "+".join(s for s, ok in (("Piotroski", pio_ok), ("CoffeeCan", cc)) if ok) or "—"
        rows.append(f"<tr><td style='padding:4px 8px'><b>{code}</b></td><td>{name}</td>"
                    f"<td>{tier}</td><td>{screens}</td>"
                    f"<td>{'n/a' if pio is None else pio}</td></tr>")
    return rows


def _kr_picks_rows(top: int = 15):
    """Korea has no combined JSON — read the KR scan's Fundamentals sheet directly.
    Same shape as _jp_picks_rows() (Piotroski_Strong YES/NO + CoffeeCan PASS/FAIL)."""
    files = sorted(glob.glob("korea_scan/korea_market_scan*.xlsx"))
    if not files:
        return []
    try:
        xl = pd.ExcelFile(files[-1])
        if "Fundamentals" not in xl.sheet_names:
            return []
        fd = pd.read_excel(files[-1], sheet_name="Fundamentals")
    except Exception:
        return []

    def _pio(v):
        try:
            return int(float(v))
        except Exception:
            return None

    cands = []
    for _, r in fd.iterrows():
        pio = _pio(r.get("Piotroski_Score"))
        strong = str(r.get("Piotroski_Strong", "")).upper() == "YES"
        cc = str(r.get("CoffeeCan", "")).upper() == "PASS"
        if not (strong or cc or (pio is not None and pio >= 7)):
            continue
        cands.append((pio, strong, cc, r))
    cands.sort(key=lambda x: -(x[0] if x[0] is not None else -1))

    rows = []
    for pio, strong, cc, r in cands[:top]:
        code = str(r.get("Code", "") or r.get("YF_Ticker", "") or "").strip()
        name = str(r.get("Name", "") or code).split(",")[0]
        pio_ok = strong or (pio is not None and pio >= 7)
        tier = "Triple Hit" if (pio_ok and cc) else "Multi-Screen"
        screens = "+".join(s for s, ok in (("Piotroski", pio_ok), ("CoffeeCan", cc)) if ok) or "—"
        rows.append(f"<tr><td style='padding:4px 8px'><b>{code}</b></td><td>{name}</td>"
                    f"<td>{tier}</td><td>{screens}</td>"
                    f"<td>{'n/a' if pio is None else pio}</td></tr>")
    return rows


def _convergence_html(label: str, data: dict) -> str:
    conv = data.get("convergence") or []
    both = [c for c in conv if "BOTH BULLISH" in str(c.get("Convergence", ""))]
    caut = [c for c in conv if "NEGATIVE" in str(c.get("Convergence", ""))]
    if not both and not caut:
        return f"<p style='color:#777;font-size:13px'>{label}: no fundamental picks had matching news coverage today.</p>"
    parts = []
    if both:
        parts.append(f"<p style='font-size:13px'><b>🎯 {label} high-conviction</b> "
                     "(strong fundamentals AND positive news):</p><ul style='font-size:13px;margin:4px 0 8px 18px'>")
        for c in both:
            parts.append(f"<li><b>{c.get('Symbol')}</b> [{c.get('Tier')}] — news "
                        f"{float(c.get('News_Score', 0)):+.2f} ({c.get('N_Articles', 0)} articles): "
                        f"{c.get('Top_Headline', '')}</li>")
        parts.append("</ul>")
    if caut:
        parts.append(f"<p style='font-size:13px'><b>⚠️ {label} caution</b> "
                     "(strong fundamentals BUT negative news):</p><ul style='font-size:13px;margin:4px 0 8px 18px'>")
        for c in caut:
            parts.append(f"<li><b>{c.get('Symbol')}</b> — news {float(c.get('News_Score', 0)):+.2f}: "
                        f"{c.get('Top_Headline', '')}</li>")
        parts.append("</ul>")
    return "".join(parts)


def _talk_rows(data: dict, cap: int = 10):
    talk = data.get("talk") or {}
    scored = [(s, t) for s, t in talk.items()
              if isinstance(t, dict) and t.get("label") not in (None, "NO_DATA")]
    scored.sort(key=lambda kv: -float(kv[1].get("score", 0)))
    rows = []
    for sym, t in scored[:cap]:
        col = _SENT_COL.get(t.get("label"), "#777")
        rows.append(f"<tr><td style='padding:4px 8px'><b>{sym}</b></td>"
                    f"<td style='color:{col};font-weight:600'>{t.get('label')}</td>"
                    f"<td>{float(t.get('score', 0)):+.2f}</td><td>{t.get('n_articles', 0)}</td></tr>")
    return rows


_DARVAS_LABEL = {"IN": "🇮🇳 India", "US": "🇺🇸 US", "EU": "🇪🇺 Europe"}


def _ccc_rows(top: int = 12):
    """India Cash Conversion Cycle screen — screener.in/screens/228040. Lowest/
    negative CCC = collects from customers before paying suppliers (strong
    working-capital efficiency). Live-scrapes each run (refreshing the local
    cache); falls back to the cached parquet if the live fetch fails."""
    cdf = pd.DataFrame()
    try:
        import screener_in as sin
        cdf = sin.ccc_screen()
        if not cdf.empty:
            cdf.to_parquet("cache_seed/india_ccc_screen.parquet", index=False)
    except Exception:
        pass
    if cdf.empty:
        try:
            cdf = pd.read_parquet("cache_seed/india_ccc_screen.parquet")
        except Exception:
            return []
    if cdf.empty or "Cash_Cycle" not in cdf.columns:
        return []
    cdf = cdf.copy()
    cdf["Cash_Cycle"] = pd.to_numeric(cdf["Cash_Cycle"], errors="coerce")
    cdf = cdf.dropna(subset=["Cash_Cycle"])
    cdf["Market"] = "IN"
    cdf = liq.annotate(cdf)
    cdf = cdf[cdf["Liquidity"].isin(["High", "Medium"])].sort_values("Cash_Cycle").head(top)
    rows = []
    for _, r in cdf.iterrows():
        rows.append(f"<tr><td style='padding:4px 8px'><b>{r.Symbol}</b></td>"
                    f"<td>{r.get('Name','')}</td><td>{r.Cash_Cycle:.1f}</td>"
                    f"<td>{r.get('ROCE','')}</td>"
                    f"<td style='color:{_COL.get(r.Liquidity,'#777')};font-weight:600'>{r.Liquidity}</td></tr>")
    return rows


def _darvas_section(market: str, cap: int = 15) -> str:
    """Fresh Darvas breakouts for one market, capped to `cap` rows for readability
    (a full-universe scan can surface 100+ "fresh" breakouts — the header still
    reports the true Tier-1/Tier-2 totals, only the table is truncated)."""
    if dbrk is None:
        return "<p style='color:#777'>Darvas fragment unavailable (darvas_breakouts.py not importable).</p>"
    label = _DARVAS_LABEL.get(market, market)
    try:
        _, df = dbrk.build(market, write_csv=False)
    except Exception as e:
        return f"<p style='color:#777'>Darvas fragment for {market} unavailable ({e}).</p>"
    if df.empty:
        return (f'<h3>📈 {label} — Darvas Breakouts</h3>'
                f'<p style="color:#777">No fresh breakouts in the latest scan.</p>')
    n1 = int((df["Tier"] == 1).sum())
    n2 = int((df["Tier"] == 2).sum())
    shown_note = f", top {cap} of {len(df)} shown" if len(df) > cap else ""
    head = ("<tr><th>Tier</th><th>Symbol</th><th>Name</th><th>Exch</th>"
            "<th>LTP</th><th>Day</th><th>Box Pos</th><th>Upside</th>"
            "<th>50/200</th><th>GC</th></tr>")
    body = dbrk.rows_html(df.head(cap), market)
    return (
        f'<h3>📈 {label} — Darvas Breakouts '
        f'<span style="font-weight:400;color:#777">({n1} Tier-1 · {n2} Tier-2{shown_note})</span></h3>'
        f'<div class="trail" style="overflow-x:auto">'
        f'<table style="border-collapse:collapse;width:100%;font-size:12.5px">'
        f'{head}{body}</table></div>'
        f'<p style="font-size:11px;color:#888;margin-top:4px">Tier 1 = Golden Cross + '
        f'Darvas breakout, box position ≤130%. Tier 2 = box position 100–120%, above '
        f'200-DMA, up day, ≥250 daily bars. "Box Pos" &gt;100% = trading above the box.</p>')


_CORR_MARKETS = [
    ("nse", "🇮🇳 India (NSE)"),
    ("us", "🇺🇸 US"),
    ("europe", "🇪🇺 Europe"),
    ("japan", "🇯🇵 Japan"),
    ("korea", "🇰🇷 Korea"),
]


def _corr_section(top_n: int = 3) -> str:
    """🔗 Market Correlation Highlights — top clusters per market, read from
    market_correlation_scan.py's plain-text cluster report
    (correlation_scan/<market>_correlation_clusters.txt). Each market is parsed
    independently; a missing/malformed file for one market degrades to an
    'n/a' line for that market only, never raises."""
    blocks = []
    for key, label in _CORR_MARKETS:
        try:
            files = sorted(glob.glob(f"correlation_scan/{key}_correlation_clusters.txt"))
            if not files:
                blocks.append(f"<p style='font-size:12px;margin:6px 0'><b>{label}</b>: "
                              f"n/a (no correlation scan yet)</p>")
                continue
            text = open(files[-1]).read()
            header = next((l for l in text.splitlines() if "symbols" in l and "period=" in l), "")
            m = re.search(r"([\d,]+)\s+symbols", header)
            n_sym = m.group(1) if m else "?"
            cl_lines = [l.strip() for l in text.splitlines() if l.strip().startswith("(")]
            items = []
            for l in cl_lines[:top_n]:
                mm = re.match(r"\((\d+)\)\s+(\[.*\])", l)
                if not mm:
                    continue
                size = mm.group(1)
                try:
                    members = ast.literal_eval(mm.group(2))
                except Exception:
                    members = []
                shown = ", ".join(str(x) for x in members[:8]) + (" …" if len(members) > 8 else "")
                items.append(f"<li>({size}) {shown}</li>")
            if not items:
                blocks.append(f"<p style='font-size:12px;margin:6px 0'><b>{label}</b>: "
                              f"{n_sym} symbols scanned, no clusters &gt;1 found</p>")
            else:
                blocks.append(
                    f"<p style='font-size:12px;margin:8px 0 2px'><b>{label}</b> "
                    f"({n_sym} symbols, {len(cl_lines)} clusters found)</p>"
                    f"<ul style='font-size:12px;margin:2px 0 6px 18px'>{''.join(items)}</ul>")
        except Exception:
            blocks.append(f"<p style='font-size:12px;margin:6px 0'><b>{label}</b>: "
                          f"n/a (error reading correlation scan)</p>")
    return "".join(blocks)


def _market_snapshot_html() -> str:
    idx = [("^NSEI", "Nifty 50"), ("^GSPC", "S&P 500"), ("^STOXX50E", "Euro Stoxx 50")]
    try:
        import yfinance as yf
    except Exception:
        yf = None
    cells = []
    for tkr, name in idx:
        last = dma50 = dma200 = None
        stance200, col200 = "n/a", "#888"
        stance50, col50 = "n/a", "#888"
        cross_note = ""
        if yf is not None:
            try:
                h = yf.download(tkr, period="1y", progress=False, auto_adjust=True)
                closes = pd.to_numeric(h["Close"].squeeze(), errors="coerce").dropna()
                if len(closes):
                    last = float(closes.iloc[-1])
                    if len(closes) >= 50:
                        dma50 = float(closes.rolling(50).mean().iloc[-1])
                        stance50 = "above 50-DMA" if last > dma50 else "below 50-DMA"
                        col50 = "#2e7d32" if last > dma50 else "#c62828"
                    if len(closes) >= 200:
                        dma200 = float(closes.rolling(200).mean().iloc[-1])
                        stance200 = "above 200-DMA (bullish)" if last > dma200 else "below 200-DMA (cautious)"
                        col200 = "#2e7d32" if last > dma200 else "#c62828"
                    if dma50 is not None and dma200 is not None:
                        cross_note = " · Golden Cross" if dma50 > dma200 else " · Death Cross"
            except Exception:
                pass
        cells.append(
            f"<td style='padding:8px 12px;vertical-align:top'>"
            f"<div style='font-size:12px;color:#888'>{name}</div>"
            f"<div style='font-size:17px;font-weight:700'>{'n/a' if last is None else f'{last:,.0f}'}</div>"
            f"<div style='font-size:11px;color:{col200}'>{stance200} · 200-DMA "
            f"{'n/a' if dma200 is None else f'{dma200:,.0f}'}</div>"
            f"<div style='font-size:11px;color:{col50}'>{stance50} · 50-DMA "
            f"{'n/a' if dma50 is None else f'{dma50:,.0f}'}{cross_note}</div></td>")
    return f"<table style='border-collapse:collapse;width:100%'><tr>{''.join(cells)}</tr></table>"


def build():
    today = _dt.date.today().strftime("%d %b %Y")

    ind_data = _load_combined("IN")
    us_data = _load_combined("US")
    mood = ind_data.get("mood") or {"mood": "n/a", "score": 0, "n_articles": 0}
    us_mood = us_data.get("mood") or {"mood": "n/a", "score": 0, "n_articles": 0}

    # 0. Market snapshot
    snapshot_html = _market_snapshot_html()

    # 1. India / US / Europe / Japan / Korea fundamentals screener picks
    ind_picks_rows = _market_picks_rows(ind_data, "IN")
    us_picks_rows = _market_picks_rows(us_data, "US")
    try:
        eu_picks_rows = _eu_picks_rows()
    except Exception:
        eu_picks_rows = []
    try:
        jp_picks_rows = _jp_picks_rows()
    except Exception:
        jp_picks_rows = []
    try:
        kr_picks_rows = _kr_picks_rows()
    except Exception:
        kr_picks_rows = []

    # 2. India CCC screen (screener.in 228040)
    ccc_rows = _ccc_rows()

    # 3. Convergence (fundamentals + street agree)
    convergence_html = _convergence_html("🇮🇳 India", ind_data) + _convergence_html("🇺🇸 US", us_data)

    # 4. Share Market News Picks — India + US
    in_news_rows = _news_rows("IN")
    us_news_rows = _news_rows("US")

    # 5. Talk on the Street — per-ticker sentiment for the fundamental picks
    in_talk_rows = _talk_rows(ind_data)
    us_talk_rows = _talk_rows(us_data)

    # 6. Darvas Breakouts — India / US / Europe
    darvas_in = _darvas_section("IN")
    darvas_us = _darvas_section("US")
    darvas_eu = _darvas_section("EU")

    # 7. Global momentum (top 15 overall)
    allh = rga.load_highlights()
    g = allh.head(15)
    g_rows = [f"<tr><td style='padding:4px 8px'>{r.Market}</td><td>{r.Symbol}</td>"
              f"<td>{r.ret_126:+.0f}</td><td>{r.rsi14}</td></tr>" for _, r in g.iterrows()]

    # 7b. Other markets — top tradable mover per market (world tour, ex-IN/US)
    other_rows = []
    try:
        h = liq.annotate(allh.copy())
        names = {"TW": "Taiwan", "KR": "Korea", "JP": "Japan", "CN": "China", "HK": "Hong Kong",
                 "CA": "Canada", "AU": "Australia", "UK": "UK", "DE": "Germany", "CH": "Switzerland",
                 "SE": "Sweden", "FI": "Finland", "DK": "Denmark", "SG": "Singapore", "EU": "Euronext",
                 "BR": "Brazil", "SA": "Saudi", "ZA": "S.Africa"}
        for m in [x for x in names if x in set(h.Market)]:
            sub = h[h.Market == m].sort_values("ret_126", ascending=False).head(1)
            if sub.empty:
                continue
            r = sub.iloc[0]
            other_rows.append(f"<tr><td style='padding:4px 8px'>{names[m]}</td>"
                              f"<td><b>{r.Symbol}</b></td><td>{r.ret_126:+.0f}%</td>"
                              f"<td style='color:{_COL.get(r.Liquidity,'#777')};font-weight:600'>{r.Liquidity}</td></tr>")
    except Exception:
        pass

    # 8. 5y scoreboard
    p5 = mp.load()
    p_rows = [f"<tr><td style='padding:4px 8px'>{r.Market}</td><td>{r.Index}</td>"
              f"<td>{r['CAGR%']}</td><td>{r['Return_1y%']}</td><td>{r.Sharpe}</td></tr>"
              for _, r in p5.iterrows()]

    # 9. Market Correlation Highlights — top clusters per market (NSE/US/Europe/Japan/Korea)
    try:
        corr_html = _corr_section()
    except Exception:
        corr_html = "<p style='color:#777'>Correlation scan unavailable.</p>"

    html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:820px;color:#1a1a1a">
<style>
h3{{font-size:14px;margin:14px 0 6px;color:#333}}
.trail{{overflow-x:auto;margin:6px 0}}
.trail table{{border-collapse:collapse;width:100%;font-size:12.5px}}
.trail th{{background:#eef;text-align:left;padding:5px 8px}}
.trail td{{padding:4px 8px;border-bottom:1px solid #f0f0f0}}
</style>
<h1 style="font-size:21px;margin:0 0 2px">📈 Daily Market Brief — {today}</h1>
<p style="color:#666;font-size:13px;margin:0 0 14px">India · US · Europe · Japan · Korea fundamentals + Darvas breakouts + convergence + news picks + global momentum + 5-year scoreboard + market correlation highlights · data as of last close</p>
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px">🌍 Market Snapshot</h2>
{snapshot_html}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🇮🇳 India — Daily Screener (most tradable)</h2>
{_table(["Symbol","Tier","Screens","Turnover","Liquidity"], ind_picks_rows) if ind_picks_rows else "<p>no picks</p>"}
<p style="font-size:11px;color:#666;margin:3px 0">Mood: <b style="color:#2e7d32">{mood['mood']} ({mood['score']:+.2f})</b> from {mood.get('n_articles',0)} articles. Liquidity: High ≥$5M/day · Medium $0.5–5M · Low &lt;$0.5M.</p>
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🇺🇸 US — Daily Screener (most tradable)</h2>
{_table(["Symbol","Tier","Screens","Turnover","Liquidity"], us_picks_rows) if us_picks_rows else "<p>no picks (run daily_combined_report.py --market US)</p>"}
<p style="font-size:11px;color:#666;margin:3px 0">Mood: <b style="color:#2e7d32">{us_mood['mood']} ({us_mood['score']:+.2f})</b> from {us_mood.get('n_articles',0)} articles.</p>
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🇪🇺 Europe — Fundamentals Picks</h2>
{_table(["Symbol","Name","Tier","Screens","Piotroski"], eu_picks_rows) if eu_picks_rows else "<p>no European scan available today</p>"}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🇯🇵 Japan — Fundamentals Picks</h2>
{_table(["Code","Name","Tier","Screens","Piotroski"], jp_picks_rows) if jp_picks_rows else "<p>no Japan scan available today</p>"}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🇰🇷 Korea — Fundamentals Picks</h2>
{_table(["Code","Name","Tier","Screens","Piotroski"], kr_picks_rows) if kr_picks_rows else "<p>no Korea scan available today</p>"}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">💵 India — Cash Conversion Cycle (screener.in 228040)</h2>
<p style="font-size:12px;color:#555">Lowest/negative CCC = collects from customers before paying suppliers. Tradable (High/Medium) only.</p>
{_table(["Symbol","Name","CCC days","ROCE","Liquidity"], ccc_rows) if ccc_rows else "<p>n/a</p>"}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">⭐ Convergence — Fundamentals &amp; The Street Agree</h2>
{convergence_html}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🔥 Share Market News Picks — India</h2>
<p style="font-size:12px;color:#555">Stocks the street is talking about today (headline mentions + sentiment), independent of the screeners. News buzz, NOT a recommendation.</p>
{_table(["Symbol","Name","Sentiment","Mentions","Headline"], in_news_rows) if in_news_rows else "<p>n/a</p>"}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🔥 Share Market News Picks — US</h2>
<p style="font-size:12px;color:#555">Stocks the street is talking about today (headline mentions + sentiment), independent of the screeners. News buzz, NOT a recommendation.</p>
{_table(["Symbol","Name","Sentiment","Mentions","Headline"], us_news_rows) if us_news_rows else "<p>n/a</p>"}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🗞️ Talk on the Street — per-ticker sentiment (fundamental picks)</h2>
<h3>🇮🇳 India</h3>
{_table(["Symbol","Sentiment","Score","Articles"], in_talk_rows) if in_talk_rows else "<p style='color:#777'>No per-ticker news matches today.</p>"}
<h3>🇺🇸 US</h3>
{_table(["Symbol","Sentiment","Score","Articles"], us_talk_rows) if us_talk_rows else "<p style='color:#777'>No per-ticker news matches today.</p>"}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">📈 Darvas Breakouts</h2>
{darvas_in}
{darvas_us}
{darvas_eu}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🌍 Global Momentum — Top 15 (20 markets)</h2>
{_table(["Mkt","Symbol","6mo %","RSI"], g_rows)}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🗺️ Other Markets — top tradable mover each</h2>
<p style="font-size:12px;color:#555">Best liquid (≥$1M/day) 6-month performer per market.</p>
{_table(["Market","Symbol","6mo %","Liquidity"], other_rows) if other_rows else "<p>n/a</p>"}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🗓️ 20-Market 5-Year Scoreboard</h2>
{_table(["Mkt","Index","5y CAGR%","1y %","Sharpe"], p_rows)}
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:22px">🔗 Market Correlation Highlights</h2>
<p style="font-size:12px;color:#555">Top correlated-stock clusters per market (market_correlation_scan.py), 1y returns, threshold-based clustering.</p>
{corr_html}
<p style="font-size:11px;color:#bf360c;border-top:1px solid #eee;padding-top:10px;margin-top:18px">⚠️ Educational/research only. NOT investment advice. Screener/Darvas/Convergence results are mechanical filters, not buy/sell signals. Liquidity/CCC are estimates; index figures price-only, local currency. Correlation clusters are statistical (not causal) groupings and can break down in stressed markets. Past performance does not guarantee future returns. Consult a SEBI-registered investment advisor.</p>
</div>"""

    text = (f"Daily Market Brief — {today}\n"
            f"India mood: {mood['mood']} ({mood['score']:+.2f}). US mood: {us_mood['mood']} ({us_mood['score']:+.2f}).\n"
            f"India/US/Europe/Japan/Korea screener picks + CCC + convergence + news picks + Darvas breakouts + "
            f"global momentum + 20-market 5y scoreboard + market correlation highlights.\n"
            f"Educational/research only. NOT investment advice.")
    subject = f"📈 Daily Market Brief — {today}"
    return subject, text, html


if __name__ == "__main__":
    s, t, h = build()
    open("brief_today.html", "w").write(h)
    print(s, "\n", t, "\nhtml bytes:", len(h))
