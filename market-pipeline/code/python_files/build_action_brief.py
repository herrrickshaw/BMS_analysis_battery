#!/usr/bin/env python3
# build_action_brief.py
# ======================
# Action-oriented companion to build_mailer.py's brief_today.html.
#
# brief_today.html answers "what happened / what does the data say" — one
# block per market with screener tables, sentiment, correlation clusters,
# a 5-year scoreboard. This answers a narrower question: "what, if
# anything, is worth ACTING on today" — a short, prioritized list of
# triggers (buy watchlist, breakout entries, earnings to review before the
# print, positions to reassess), each with an explicit one-line reason, not
# a data dump to interpret yourself.
#
# Reuses build_mailer.py's data loaders (combined JSON, Darvas breakout
# dataframes, PEAD-leader/dividend-history flags, liquidity annotation) —
# does NOT re-implement or duplicate that data access. Sections with no
# underlying live-price/breakout signal (Europe/Japan/Korea, which only
# have a fundamentals sheet, no combined JSON) are labeled as a research
# shortlist, not a trigger — this stays honest about what the data can and
# can't support rather than manufacturing an action where none exists.
#
# Same visual template as build_mailer.py (fonts, freshness banner,
# liquidity-floor note, colour conventions) so the two briefs read as a
# matched pair, not two different products.
#
#   from build_action_brief import build; subj, text, html = build()

from __future__ import annotations

import datetime as _dt
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

from build_mailer import (
    _COL,
    _as_of_html,
    _earnings_news_lookup,
    _eu_picks_rows,
    _jp_picks_rows,
    _kr_picks_rows,
    _load_combined,
    _load_dividend_history_in,
    _load_pead_leaders,
    _warehouse_ltp_map,
    dbrk,
    liq,
)

_MKT_LABEL = {"IN": "🇮🇳 India", "US": "🇺🇸 US"}


# ── index regime: one fetch feeds both the numeric table and the action line ──

def _index_regime_data() -> list[dict]:
    idx = [("^NSEI", "Nifty 50"), ("^GSPC", "S&P 500"), ("^STOXX50E", "Euro Stoxx 50")]
    try:
        import yfinance as yf
    except Exception:
        yf = None
    out = []
    for tkr, name in idx:
        rec = {"name": name, "last": None, "dma50": None, "dma200": None,
               "stance200": "n/a", "cross": "n/a"}
        if yf is not None:
            try:
                h = yf.download(tkr, period="1y", progress=False, auto_adjust=True)
                closes = pd.to_numeric(h["Close"].squeeze(), errors="coerce").dropna()
                if len(closes):
                    rec["last"] = float(closes.iloc[-1])
                    if len(closes) >= 50:
                        rec["dma50"] = float(closes.rolling(50).mean().iloc[-1])
                    if len(closes) >= 200:
                        rec["dma200"] = float(closes.rolling(200).mean().iloc[-1])
                    if rec["dma200"] is not None:
                        rec["stance200"] = "above" if rec["last"] > rec["dma200"] else "below"
                    if rec["dma50"] is not None and rec["dma200"] is not None:
                        rec["cross"] = "golden" if rec["dma50"] > rec["dma200"] else "death"
            except Exception:
                pass
        out.append(rec)
    return out


def _index_snapshot_html(regime: list[dict]) -> str:
    cells = []
    for r in regime:
        col200 = "#2e7d32" if r["stance200"] == "above" else "#c62828" if r["stance200"] == "below" else "#888"
        cross_note = f" · {'Golden' if r['cross']=='golden' else 'Death'} Cross" if r["cross"] != "n/a" else ""
        last_disp = "n/a" if r["last"] is None else f"{r['last']:,.0f}"
        stance_disp = "n/a" if r["stance200"] == "n/a" else r["stance200"] + " 200-DMA"
        cells.append(
            f"<td style='padding:8px 12px;vertical-align:top'>"
            f"<div style='font-size:12px;color:#888'>{r['name']}</div>"
            f"<div style='font-size:17px;font-weight:700'>{last_disp}</div>"
            f"<div style='font-size:11px;color:{col200}'>"
            f"{stance_disp}{cross_note}</div></td>")
    return f"<table style='border-collapse:collapse;width:100%'><tr>{''.join(cells)}</tr></table>"


def _regime_action_html(regime: list[dict]) -> str:
    """The action synthesis _market_snapshot_html() never made explicit:
    what should today's entry sizing/selectivity actually be, given the
    trend regime."""
    lines = []
    for r in regime:
        if r["last"] is None:
            lines.append(f"<li><b>{r['name']}</b>: data unavailable — treat as regime-unknown, size down.</li>")
            continue
        risk_on = r["stance200"] == "above" and r["cross"] == "golden"
        risk_off = r["stance200"] == "below" and r["cross"] == "death"
        risk = "RISK-ON" if risk_on else "RISK-OFF" if risk_off else "MIXED"
        col = {"RISK-ON": "#2e7d32", "RISK-OFF": "#c62828", "MIXED": "#b8860b"}[risk]
        advice = {
            "RISK-ON": "act on BUY WATCHLIST / breakout entries below at normal size.",
            "RISK-OFF": "require BOTH a Tier-1 breakout AND a Triple-Hit fundamentals match before adding any new name; no forced exits on existing positions.",
            "MIXED": "act only on double-confirmed names (Triple-Hit + Tier-1 breakout together); skip single-signal entries.",
        }[risk]
        lines.append(
            f"<li><b>{r['name']}</b> — <span style='color:{col};font-weight:700'>{risk}</span>: {advice}</li>"
        )
    return "<ul style='font-size:13px;margin:4px 0 8px 18px'>" + "".join(lines) + "</ul>"


# ── per-market action sections ────────────────────────────────────────────────

def _buy_watchlist_rows(data: dict, market: str, darvas_df: pd.DataFrame | None, cap: int = 5):
    """Triple-Hit fundamentals picks, liquidity-gated, ranked up by any same-
    day Tier-1 Darvas breakout or bullish news convergence -- the two-out-
    of-three-signals-agree case is exactly what's worth acting on first."""
    picks = data.get("picks") or []
    triple = [p for p in picks if p.get("Tier") == "Triple Hit"]
    if not triple:
        return []

    conv = data.get("convergence") or []
    bullish_syms = {c["Symbol"] for c in conv if "BOTH BULLISH" in str(c.get("Convergence", ""))}
    t1_syms = set(darvas_df[darvas_df["Tier"] == 1]["Symbol"]) if darvas_df is not None and not darvas_df.empty else set()

    p = pd.DataFrame(triple)
    p["Market"] = market
    p = liq.annotate(p)
    p = p[p["Liquidity"].isin(["High", "Medium"])].copy()
    if p.empty:
        return []
    wh = _warehouse_ltp_map(market)
    p["LTP"] = p["Symbol"].map(lambda s: wh.get(s, (None, None))[0])
    p["Change_Pct"] = p["Symbol"].map(lambda s: wh.get(s, (None, None))[1])
    p["_t1"] = p["Symbol"].isin(t1_syms)
    p["_bull"] = p["Symbol"].isin(bullish_syms)
    p["_score"] = p["_t1"].astype(int) * 2 + p["_bull"].astype(int)
    p["_l"] = p["Liquidity"].map({"High": 0, "Medium": 1})
    p = p.sort_values(["_score", "_l"], ascending=[False, True]).head(cap)

    rows = []
    for _, r in p.iterrows():
        tags = []
        if r["_t1"]:
            tags.append("✅ Tier-1 breakout today")
        if r["_bull"]:
            tags.append("✅ positive news convergence")
        tag_html = " · ".join(tags) if tags else "Triple-Hit fundamentals only"
        ltp = r.get("LTP")
        ltp_disp = f"{ltp:,.2f}" if pd.notna(ltp) else "—"
        chg = r.get("Change_Pct")
        chg_disp = f"{chg:+.2f}%" if pd.notna(chg) else "—"
        rows.append(
            f"<tr><td style='padding:4px 8px'><b>{r['Symbol']}</b></td>"
            f"<td style='text-align:right'>{ltp_disp}</td>"
            f"<td style='text-align:right'>{chg_disp}</td>"
            f"<td style='color:{_COL.get(r['Liquidity'],'#777')};font-weight:600'>{r['Liquidity']}</td>"
            f"<td style='font-size:11.5px;color:#333'>{tag_html}</td></tr>"
        )
    return rows


def _breakout_only_rows(darvas_df: pd.DataFrame | None, exclude_syms: set, cap: int = 5):
    """Tier-1 Darvas breakouts that aren't already in the buy watchlist --
    pure momentum trigger, no fundamentals screen behind it, flagged as such
    rather than blended into the fundamentals-backed list above."""
    if darvas_df is None or darvas_df.empty:
        return []
    t1 = darvas_df[darvas_df["Tier"] == 1]
    t1 = t1[~t1["Symbol"].isin(exclude_syms)].head(cap)
    if t1.empty:
        return []
    rows = []
    for _, r in t1.iterrows():
        rows.append(
            f"<tr><td style='padding:4px 8px'><b>{r['Symbol']}</b></td>"
            f"<td>{r.get('Name','')}</td>"
            f"<td style='text-align:right'>{(r.get('Change%') or 0):+.2f}%</td>"
            f"<td style='text-align:right'>{r.get('Position_in_Box%','—')}%</td>"
            f"<td style='font-size:11.5px;color:#333'>Momentum only — no fundamentals screen behind this one</td></tr>"
        )
    return rows


def _earnings_watch_rows(market: str, symbols: list, max_days: int = 4, cap: int = 5):
    """Same source as build_mailer's upcoming-earnings section, but cut down
    to what's actually worth a pre-print decision: reporting within
    max_days AND carrying a differentiated signal (confirmed PEAD-leader
    status or dividend history) -- a bare "reports in 6 days, nothing else
    known" row isn't an action item, it's noise."""
    kd_path = Path(f"cache_seed/earnings_key_dates/{market}.parquet")
    if not kd_path.exists() or not symbols:
        return []
    try:
        kd = pd.read_parquet(kd_path)
    except Exception:
        return []
    kd = kd[kd["symbol"].isin(symbols)].copy()
    if kd.empty:
        return []
    now = pd.Timestamp.now()
    kd["days_until"] = (kd["next_date_start"] - now).dt.total_seconds() / 86400
    kd = kd[(kd["days_until"] >= 0) & (kd["days_until"] <= max_days)]
    if kd.empty:
        return []

    leaders = _load_pead_leaders(market)
    div_syms = _load_dividend_history_in() if market == "IN" else set()
    kd = kd[kd["symbol"].isin(leaders) | kd["symbol"].isin(div_syms)]
    if kd.empty:
        return []
    news_lookup = _earnings_news_lookup(market, set(kd["symbol"]))

    rows = []
    for _, r in kd.sort_values("days_until").head(cap).iterrows():
        sym = r["symbol"]
        when = r["next_date_start"].strftime("%d %b")
        signal = []
        if sym in leaders:
            signal.append("📊 confirmed PEAD leader")
        if sym in div_syms:
            signal.append("💰 dividend history")
        news_flag = news_lookup.get(sym, "")
        rows.append(
            f"<tr><td style='padding:4px 8px'><b>{sym}</b></td>"
            f"<td>{when}</td><td style='text-align:right'>{int(round(r['days_until']))}d</td>"
            f"<td style='font-size:11.5px'>{' · '.join(signal)}</td>"
            f"<td style='font-size:11px;color:#555'>{news_flag}</td>"
            f"<td style='font-size:11.5px;color:#333'>Decide entry/exit stance before the print — not a directional call</td></tr>"
        )
    return rows


def _caution_rows(data: dict, cap: int = 5):
    """Convergence NEGATIVE: fundamentals still screen well but news has
    turned -- the "don't add blindly, reassess first" list."""
    conv = data.get("convergence") or []
    caut = [c for c in conv if "NEGATIVE" in str(c.get("Convergence", ""))][:cap]
    rows = []
    for c in caut:
        rows.append(
            f"<tr><td style='padding:4px 8px'><b>{c.get('Symbol')}</b></td>"
            f"<td style='text-align:right'>{float(c.get('News_Score',0)):+.2f}</td>"
            f"<td style='font-size:11.5px;color:#555'>{c.get('Top_Headline','')}</td>"
            f"<td style='font-size:11.5px;color:#333'>Reassess before adding — don't average down on the fundamentals screen alone</td></tr>"
        )
    return rows


def _table(headers, rows):
    h = "".join(f"<th align='left' style='padding:5px 8px'>{x}</th>" for x in headers)
    return (f"<table style='border-collapse:collapse;width:100%;font-size:13px'>"
            f"<tr style='background:#eef'>{h}</tr>{''.join(rows)}</table>")


def _market_action_block(market: str) -> tuple[str, dict]:
    """Returns (html, counts) -- counts feeds build()'s subject line so the
    email is scannable from an inbox list without opening it."""
    label = _MKT_LABEL[market]
    zero_counts = {"buy": 0, "breakout": 0, "earnings": 0, "caution": 0}
    data = _load_combined(market)
    if not data:
        return f"<p style='color:#777'>{label}: no combined scan available today.</p>", zero_counts

    darvas_df = None
    if dbrk is not None:
        try:
            _, darvas_df = dbrk.build(market if market == "US" else "IN", write_csv=False)
        except Exception:
            darvas_df = None

    symbols = [p["Symbol"] for p in (data.get("picks") or [])]

    buy_rows = _buy_watchlist_rows(data, market, darvas_df, cap=5)
    buy_syms = set()
    for row_html in buy_rows:
        # symbol is the first <b>…</b> in the row
        start = row_html.find("<b>") + 3
        buy_syms.add(row_html[start:row_html.find("</b>", start)])
    breakout_rows = _breakout_only_rows(darvas_df, buy_syms, cap=5)
    earnings_rows = _earnings_watch_rows(market, symbols, cap=5)
    caution_rows = _caution_rows(data, cap=5)
    counts = {"buy": len(buy_rows), "breakout": len(breakout_rows),
              "earnings": len(earnings_rows), "caution": len(caution_rows)}

    n_actions = sum(bool(x) for x in (buy_rows, breakout_rows, earnings_rows, caution_rows))
    parts = [f"<h2 style=\"font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:26px\">{label}</h2>"]

    if n_actions == 0:
        parts.append("<p style='color:#777;font-size:13px'>No high-confidence triggers today — nothing here clears the double-confirmation bar.</p>")
        return "".join(parts), counts

    if buy_rows:
        parts.append("<h3 style=\"font-size:13px;margin:12px 0 4px;color:#1b7f37\">🟢 BUY WATCHLIST — Triple-Hit + liquid</h3>")
        parts.append(_table(["Symbol", "LTP", "Chg%", "Liquidity", "Why"], buy_rows))
    if breakout_rows:
        parts.append("<h3 style=\"font-size:13px;margin:14px 0 4px;color:#1a73e8\">🚀 BREAKOUT ENTRIES — Tier-1 Darvas, momentum only</h3>")
        parts.append(_table(["Symbol", "Name", "Chg%", "Box Pos", "Note"], breakout_rows))
    if earnings_rows:
        parts.append(f"<h3 style=\"font-size:13px;margin:14px 0 4px;color:#333\">📅 EARNINGS WATCH — next {4}d, decide before the print</h3>")
        parts.append(_table(["Symbol", "Date", "In", "Signal", "News", "Action"], earnings_rows))
    if caution_rows:
        parts.append("<h3 style=\"font-size:13px;margin:14px 0 4px;color:#c62828\">⚠️ CAUTION / REASSESS — fundamentals OK, news turned</h3>")
        parts.append(_table(["Symbol", "News", "Headline", "Action"], caution_rows))

    return "".join(parts), counts


def _research_shortlist_block(label: str, rows_fn) -> str:
    """Europe/Japan/Korea have no combined JSON (no live price, no
    convergence, no Darvas breakout scan for those markets) -- only a
    Piotroski fundamentals sheet. Labeled explicitly as research material,
    not a trigger, rather than dressing a fundamentals-only list up as an
    action the data can't actually support."""
    try:
        rows = rows_fn(top=8)
    except Exception:
        rows = []
    parts = [f"<h2 style=\"font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:26px\">{label}</h2>"]
    if not rows:
        parts.append("<p style='color:#777;font-size:13px'>No scan available today.</p>")
        return "".join(parts)
    parts.append(
        "<p style='font-size:11px;color:#666;margin:2px 0 6px'>No live price/breakout signal available for "
        "this market — fundamentals-only research shortlist, not a trade trigger.</p>"
    )
    parts.append(_table(["Symbol", "Name", "Tier", "Screens", "Piotroski"], rows))
    return "".join(parts)


def build():
    today = _dt.date.today().strftime("%d %b %Y")
    as_of_html = _as_of_html()
    regime = _index_regime_data()
    snapshot_html = _index_snapshot_html(regime)
    regime_action_html = _regime_action_html(regime)

    ind_block, ind_counts = _market_action_block("IN")
    us_block, us_counts = _market_action_block("US")
    eu_block = _research_shortlist_block("🇪🇺 Europe", _eu_picks_rows)
    jp_block = _research_shortlist_block("🇯🇵 Japan", _jp_picks_rows)
    kr_block = _research_shortlist_block("🇰🇷 Korea", _kr_picks_rows)

    totals = {k: ind_counts[k] + us_counts[k] for k in ind_counts}
    count_str = f"{totals['buy']} BUY · {totals['breakout']} breakout · {totals['earnings']} earnings · {totals['caution']} caution"

    html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:820px;color:#1a1a1a">
<style>
h3{{font-size:14px;margin:14px 0 6px;color:#333}}
.trail{{overflow-x:auto;margin:6px 0}}
.trail table{{border-collapse:collapse;width:100%;font-size:12.5px}}
.trail th{{background:#eef;text-align:left;padding:5px 8px}}
.trail td{{padding:4px 8px;border-bottom:1px solid #f0f0f0}}
</style>
<h1 style="font-size:21px;margin:0 0 2px">🎯 Daily Action Brief — {today}</h1>
<p style="color:#666;font-size:13px;margin:0 0 10px">Prioritized triggers only — buy watchlist, breakout entries, earnings to decide before the print, positions to reassess. Full analysis: brief_today.html</p>
{as_of_html}
<p style="font-size:11px;color:#555;margin:0 0 14px;background:#f6f8fc;border-left:3px solid #1a73e8;padding:6px 9px"><b>Liquidity floor</b>: India ~₹1cr/day, other markets ~$10k/day — see brief_today.html for the full rationale. Every list below is already filtered to this floor.</p>
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px">🌍 Regime — how much conviction today's entries need</h2>
{snapshot_html}
{regime_action_html}
{ind_block}
{us_block}
{eu_block}
{jp_block}
{kr_block}
<p style="font-size:11px;color:#bf360c;border-top:1px solid #eee;padding-top:10px;margin-top:18px">⚠️ Educational/research only. NOT investment advice. Every item above is a mechanical filter match (screener + breakout + news-sentiment agreement), not a buy/sell signal — verify price and liquidity live before acting, and consult a SEBI-registered investment advisor. "BUY WATCHLIST" names a candidate for further review, not a standing order.</p>
</div>"""

    text = (f"Daily Action Brief — {today} ({count_str})\n"
            f"Prioritized triggers only: buy watchlist, breakout entries, earnings to decide "
            f"before the print, positions to reassess. Full analysis in brief_today.html.\n"
            f"Educational/research only. NOT investment advice.")
    subject = f"🎯 Daily Action Brief — {today} ({count_str})"
    return subject, text, html


if __name__ == "__main__":
    s, t, h = build()
    open("action_brief_today.html", "w").write(h)
    print(s, "\n", t, "\nhtml bytes:", len(h))
