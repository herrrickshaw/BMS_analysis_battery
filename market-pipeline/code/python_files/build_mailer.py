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
import os
import re
import warnings
from pathlib import Path

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


def _pct(x):
    if pd.isna(x):
        return "—"
    color = "#1b7f37" if x >= 0 else "#b00"
    return f"<span style='color:{color};font-weight:600'>{x:+.2f}%</span>"


_PG_DSN = "dbname=market_data host=/tmp user=umashankar"
_BHAVCOPY_DB = "/Users/umashankar/data/bhavcopy.duckdb"

# Sanity bounds on 1-day Change%, keyed to each market's actual circuit-breaker
# regime rather than one arbitrary flat number — see _warehouse_ltp_map's
# docstring for the incident (XAIR +1273.8%) that motivated a bound at all.
#   IN — NSE/BSE assign every non-F&O stock a STATIC daily price band of 2%,
#        5%, 10% or 20% (exchange-published, symmetric). The ~200 F&O-eligible
#        names trade on a wider DYNAMIC band instead of a fixed one, so they
#        can rarely print slightly past 20% intraday — but a print beyond 20%
#        is still overwhelmingly more likely to be a bad Prev_Close than a
#        genuine move, so 20% is used as the "flag, don't display" gate for
#        all India symbols alike (no per-stock band table is loaded here).
#   US  — there is NO daily price CAP for US equities. LULD (Limit Up-Limit
#        Down) only PAUSES trading when price exits a 5-20% band around a
#        rolling reference price; the band re-centers after each pause, so a
#        stock can legitimately move >50% in a session (biotech catalysts,
#        low-float squeezes). 100% stays a pure data-sanity heuristic, not a
#        regulatory bound — genuine large moves under it must pass through.
# Public-source citations + India's index-level (not stock-level) MWCB
# structure + why these two numbers are NOT the same mechanism as India's
# 20% market-wide halt threshold: see DECISION_REGISTER.md, decisions D-05
# and D-05a. Korea (30%, exact) and Japan (50%, heuristic) bounds for the
# same purpose live in regime_price_model.py's CIRCUIT_BOUND_PCT — not
# duplicated here because those two markets don't have a Change% column in
# this mailer yet.
_CIRCUIT_BREAKER_PCT = {"IN": 20.0, "US": 100.0}


def _sanity_bound(market: str) -> float:
    return _CIRCUIT_BREAKER_PCT.get(market, 100.0)


def _warehouse_ltp_map(market: str) -> dict:
    """Symbol -> (ltp, change_pct), sourced from PERSISTED warehouse history —
    NOT a fresh scan-file read. US reads the last known as_of_date per symbol
    from Postgres market_daily.snapshots (the daily-ingest warehouse); India has
    no equivalent snapshots table (it lives separately — see market_ingest.py's
    own docstring on why India is OHLCV time series, not point-in-time
    snapshots) so this computes change_pct itself from the last two trade_dates
    in DuckDB bhavcopy.duckdb's cleaned_ohlcv.

    Querying the warehouse rather than the latest scan file also closes a real
    coverage gap: the warehouse accumulates every day's ingest, so a symbol
    missing from TODAY's single scan file (confirmed live: 53/486 India picks,
    11%) can still resolve from its last known snapshot.

    SANITY BOUND, not optional: live-tested and found the SOURCE scan's own
    Prev_Close is sometimes wrong for thinly-traded names — XAIR showed
    Prev_Close=$0.42 against LTP=$5.77, a mathematically consistent but
    implausible +1273.8% single-day move, and this pattern repeated across
    several other penny names in the same scan. That number was already being
    stored (it round-trips into this same warehouse via market_ingest.py) but
    never DISPLAYED before — Change% wasn't a mailer column until now, so
    nothing surfaced it. A single US equity essentially never moves >100% in
    one day; treat anything beyond that as evidence of a bad prev-close, not a
    real move, and show "flagged" rather than the raw number.
    """
    import duckdb as _dd

    if market == "US":
        try:
            con = _dd.connect()
            con.execute(f"ATTACH '{_PG_DSN}' AS pg (TYPE postgres)")
            df = con.execute("""
                SELECT symbol, ltp, change_pct FROM (
                    SELECT symbol, ltp, change_pct,
                           row_number() OVER (PARTITION BY symbol ORDER BY as_of_date DESC) rn
                    FROM pg.market_daily.snapshots WHERE market='us'
                ) WHERE rn = 1
            """).df()
        except Exception:
            return {}
        out = {}
        bound = _sanity_bound("US")
        for r in df.itertuples():
            cp = r.change_pct
            if cp is not None and abs(cp) > bound:
                cp = None   # flagged, not displayed as a real move
            out[r.symbol] = (r.ltp, cp)
        return out

    if market == "IN":
        try:
            con = _dd.connect(_BHAVCOPY_DB, read_only=True)
            df = con.execute("""
                WITH ranked AS (
                    SELECT symbol, trade_date, close,
                           row_number() OVER (PARTITION BY symbol ORDER BY trade_date DESC) rn
                    FROM cleaned_ohlcv
                )
                SELECT a.symbol, a.close ltp, b.close prev_close,
                       (a.close / b.close - 1) * 100 change_pct
                FROM ranked a JOIN ranked b ON a.symbol = b.symbol AND b.rn = 2
                WHERE a.rn = 1 AND b.close > 0
            """).df()
        except Exception:
            return {}
        out = {}
        bound = _sanity_bound("IN")
        for r in df.itertuples():
            cp = r.change_pct
            if cp is not None and abs(cp) > bound:
                cp = None
            out[r.symbol] = (r.ltp, cp)
        return out

    return {}


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
    """Fundamentals-screener picks rows for India/US, liquidity-annotated.

    Shows LTP + 1-day Change% rather than Turnover — Turnover matters for
    deciding whether a pick is TRADEABLE (that's what the Liquidity column,
    kept alongside, already answers), but once a pick clears the liquidity
    gate the reader's next question is "what is it doing right now", which
    turnover doesn't answer and price/change does.

    LTP and Change% both come from the WAREHOUSE (_warehouse_ltp_map), not a
    fresh scan-file read or the picks JSON's own (possibly stale) LTP — see
    that function's docstring for why: better coverage (accumulates across
    days, not just today's file) and a sanity bound the raw scan data needs.
    """
    picks = data.get("picks") or []
    if not picks:
        return []
    p = pd.DataFrame(picks)
    p["Market"] = market
    p = liq.annotate(p)
    wh = _warehouse_ltp_map(market)
    p["LTP"] = p["Symbol"].map(lambda s: wh.get(s, (None, None))[0])
    p["Change_Pct"] = p["Symbol"].map(lambda s: wh.get(s, (None, None))[1])
    rank = {"Triple Hit": 0, "Multi-Screen": 1, "Single-Screen": 2}
    lr = {"High": 0, "Medium": 1, "Low": 2, "Unknown": 3}
    p["_o"] = p["Tier"].map(rank).fillna(3)
    p["_l"] = p["Liquidity"].map(lr).fillna(3)
    rows = []
    for _, r in p.sort_values(["_o", "_l"]).head(cap).iterrows():
        ltp = r.get("LTP")
        ltp_disp = f"{ltp:,.2f}" if pd.notna(ltp) else "—"
        rows.append(f"<tr><td style='padding:4px 8px'><b>{r.Symbol}</b></td>"
                    f"<td>{r.Tier}</td><td>{r.Screens}</td>"
                    f"<td style='text-align:right'>{ltp_disp}</td>"
                    f"<td style='text-align:right'>{_pct(r.get('Change_Pct'))}</td>"
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


def _load_pead_leaders(market: str) -> set:
    """FDR-significant sector-spillover leaders from the latest
    pead_sector_spillover_v4.py run -- the ONLY tickers this session's
    validation confirmed a real (not merely nominally-significant) same-
    sector spillover effect for, after full-sample re-runs, four confound
    checks, and a walk-forward train/test split (see DECISION_REGISTER.md's
    PEAD & Sector-Spillover section, D-16/D-17). As of this session that's
    just MCHP (US, Technology) -- ANET/WDAY looked promising early on but
    were downgraded once a quarter_key dedup bug was fixed, so this
    deliberately reads ONLY the fdr_significant flag, not the full
    candidate list, to avoid resurfacing a result that already failed
    multiple-testing correction. Missing/unavailable file degrades to an
    empty set, matching every other section's graceful-degradation
    contract, never an error."""
    try:
        data = json.load(open("cache_seed/pead_sector_spillover_v4_results.json"))
    except Exception:
        return set()
    for r in data:
        if r.get("market") == market:
            return {l["ticker"] for l in r.get("top_sector_leaders", []) if l.get("fdr_significant")}
    return set()


def _load_dividend_history_in() -> set:
    """India only -- no equivalent source exists for US/JP/KR this
    session. Flags symbols that have EVER mentioned "Dividend" in an NSE
    board-meeting description (cache_seed/earnings_dates_nse/IN.parquet).
    This is a coarse "this company is a known dividend payer" signal, NOT
    a prediction that the upcoming board meeting specifically will declare
    one -- NSE's own board-meeting notice is a generic "financial results"
    intimation ahead of the meeting; the description only confirms
    dividend intent once the company itself files it, which usually
    happens closer to (or at) the meeting date, not a week ahead."""
    try:
        df = pd.read_parquet("cache_seed/earnings_dates_nse/IN.parquet")
    except FileNotFoundError:
        return set()
    bm = df[df["event_type"] == "board_meeting"]
    return set(bm[bm["description"].str.contains("Dividend", case=False, na=False)]["symbol"])


def _earnings_news_lookup(market: str, symbols: set) -> dict:
    """Cross-checks the SAME news-sentiment fetch _news_rows()/_talk_rows()
    already run (news_picks.news_picks) for headlines that actually
    mention earnings/results terms, restricted to tickers with earnings
    due in the next 7 days -- reuses the existing fetch rather than adding
    a second network call the mailer would need to also degrade
    gracefully for."""
    keywords = ("earning", "result", "profit", "quarter", " q1", " q2", " q3", " q4",
                "beat", "miss", "guidance", "revenue", "dividend")
    try:
        picks = npk.news_picks(market, top=60, min_mentions=1)
    except Exception:
        return {}
    out = {}
    for p in picks:
        if p["symbol"] not in symbols:
            continue
        headline = p.get("headline") or ""
        if any(k in headline.lower() for k in keywords):
            out[p["symbol"]] = f"{p['label']}: {headline[:70]}"
    return out


def _upcoming_earnings_section(market: str, symbols: list, cap: int = 12) -> str:
    """NEW section for the stock-recommendation picks: which of THIS
    market's picks report earnings within the next 7 days, cross-
    referenced against a dividend-history flag, confirmed PEAD sector-
    leader status, and any earnings-related news already surfaced for that
    ticker.

    DELIBERATELY NOT a prediction of which way any of these stocks will
    move after their NEXT earnings call -- nobody knows the surprise sign
    yet. What IS shown is validated, backward-looking evidence: (a) has
    this company mentioned dividends at a past board meeting, (b) has this
    exact ticker's own earnings, historically and across a walk-forward
    holdout, shown a statistically significant tendency to move its
    sector peers (Foster 1981; Thomas & Zhang 2008), and (c) does its
    recent news already reference the upcoming/last result. See
    DECISION_REGISTER.md's PEAD & Sector-Spillover section for the full
    literature basis and this session's validation methodology.
    """
    kd_path = Path(f"cache_seed/earnings_key_dates/{market}.parquet")
    if not kd_path.exists() or not symbols:
        return "<p style='color:#777'>Upcoming-earnings data unavailable (run earnings_key_dates.py).</p>"
    try:
        kd = pd.read_parquet(kd_path)
    except Exception:
        return "<p style='color:#777'>Upcoming-earnings data unavailable.</p>"
    kd = kd[kd["symbol"].isin(symbols)].copy()
    if kd.empty:
        return "<p style='color:#777'>None of today's picks report earnings in the next 7 days.</p>"
    now = pd.Timestamp.now()
    kd["days_until"] = (kd["next_date_start"] - now).dt.total_seconds() / 86400
    kd = kd[(kd["days_until"] >= 0) & (kd["days_until"] <= 7)]
    if kd.empty:
        return "<p style='color:#777'>None of today's picks report earnings in the next 7 days.</p>"

    leaders = _load_pead_leaders(market)
    div_syms = _load_dividend_history_in() if market == "IN" else set()
    news_lookup = _earnings_news_lookup(market, set(kd["symbol"]))

    rows = []
    for _, r in kd.sort_values("days_until").head(cap).iterrows():
        sym = r["symbol"]
        when = r["next_date_start"].strftime("%d %b")
        range_note = f"–{r['next_date_end'].strftime('%d %b')}" if r["is_range"] else ""
        div_flag = "💰 dividend history" if sym in div_syms else "—"
        pead_flag = ("📊 <b>confirmed PEAD leader</b>" if sym in leaders else "—")
        news_flag = news_lookup.get(sym, "—")
        rows.append(
            f"<tr><td style='padding:4px 8px'><b>{sym}</b></td>"
            f"<td>{when}{range_note}</td><td style='text-align:right'>{int(round(r['days_until']))}d</td>"
            f"<td>{div_flag}</td><td>{pead_flag}</td>"
            f"<td style='color:#555;font-size:11px'>{news_flag}</td></tr>")
    if not rows:
        return "<p style='color:#777'>None of today's picks report earnings in the next 7 days.</p>"
    return _table(["Symbol", "Date", "In", "Dividend history", "PEAD", "Earnings-related news"], rows)


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


def _as_of_html() -> str:
    """State the data vintage explicitly: what closed when, and when we looked.

    Every price here is a LAST OFFICIAL CLOSE, not a live quote — but the brief is
    read hours later, often with the market already open. Measured 2026-07-15 at
    09:15 IST, live quotes had already drifted from the closes in that morning's
    brief: HDFCBANK 809.4 -> 812.0, ICICIBANK 1407.7 -> 1417.0, INFY 1092.9 ->
    1077.0 (1.5%). "Data as of last close" doesn't convey that. This does.
    """
    import datetime as _d
    gen = _d.datetime.now()
    rows = []

    # India: authoritative — the bhavcopy cache's own max trade date
    try:
        import os as _os
        import duckdb as _dd
        p = Path(_os.environ.get("BHAV_CACHE",
                                 Path.home() / "Downloads" / "data" / "bhavcopy_cache")) / "cleaned_long.parquet"
        if p.exists():
            d = _dd.connect().execute(
                f"SELECT max(Date) FROM read_parquet('{p}')").fetchone()[0]
            rows.append(("🇮🇳 India (NSE/BSE)", f"{d:%d %b %Y} close", "official bhavcopy"))
    except Exception:
        pass

    # Other markets: report when their scan ran; the prices in it are that run's
    # last available close.
    for label, pat in (("🇺🇸 US", "us_full_scan/us_full_scan_*.xlsx"),
                       ("🇪🇺 Europe", "european_scan/european_market_scan*.xlsx"),
                       ("🇯🇵 Japan", "japan_scan/japan_market_scan_*.xlsx"),
                       ("🇰🇷 Korea", "korea_scan/korea_market_scan_*.xlsx")):
        try:
            fs = sorted(glob.glob(pat))
            if fs:
                m = _dt.datetime.fromtimestamp(os.path.getmtime(fs[-1]))
                rows.append((label, "last close at scan time", f"scanned {m:%d %b %H:%M}"))
        except Exception:
            continue

    if not rows:
        return ""
    body = "".join(
        f"<tr><td style='padding:2px 10px 2px 0'>{a}</td>"
        f"<td style='padding:2px 10px 2px 0'><b>{b}</b></td>"
        f"<td style='padding:2px 0;color:#777'>{c}</td></tr>" for a, b, c in rows)
    return (
        "<div style='background:#fffbe6;border-left:3px solid #f9a825;padding:8px 11px;"
        "margin:0 0 14px;font-size:11.5px;color:#444'>"
        f"<b>⏱ Prices are last official closes — not live.</b> This brief was generated "
        f"<b>{gen:%d %b %Y, %H:%M}</b> and the figures below were accurate as of that moment. "
        f"Markets move: once trading reopens, live quotes will differ from every price here "
        f"(on 15 Jul, quotes had already moved up to ~1.5% from the morning's closes by 09:15). "
        f"Nothing here reflects intraday activity after the close shown."
        f"<table style='margin-top:6px;font-size:11px;border-collapse:collapse'>{body}</table>"
        "</div>")


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
    # Carry FX: a funding-currency (JPY/CHF) spike unwinds leveraged carry and
    # the selling lands on exactly the equities this brief covers — the 2024-08-05
    # yen-carry unwind took the Nikkei -12.4% in a session and the KOSPI -8.8%.
    # Best-effort: never let an FX hiccup break the brief.
    try:
        from carry_fx import carry_html as _carry_html
        carry_html_ = _carry_html()
    except Exception as _e:
        carry_html_ = f"<p style='color:#777;font-size:12px'>carry FX unavailable ({str(_e)[:40]})</p>"
    as_of_html = _as_of_html()
    snapshot_html = _market_snapshot_html()

    # 1. India / US / Europe / Japan / Korea fundamentals screener picks
    ind_picks_rows = _market_picks_rows(ind_data, "IN")
    us_picks_rows = _market_picks_rows(us_data, "US")
    ind_symbols = [p["Symbol"] for p in (ind_data.get("picks") or [])]
    us_symbols = [p["Symbol"] for p in (us_data.get("picks") or [])]
    try:
        ind_earnings_html = _upcoming_earnings_section("IN", ind_symbols)
    except Exception as e:
        ind_earnings_html = f"<p style='color:#777'>Upcoming-earnings section unavailable ({str(e)[:60]}).</p>"
    try:
        us_earnings_html = _upcoming_earnings_section("US", us_symbols)
    except Exception as e:
        us_earnings_html = f"<p style='color:#777'>Upcoming-earnings section unavailable ({str(e)[:60]}).</p>"
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
    # split per market: each geography's block owns its own convergence, so
    # "what about India?" is answerable in one place instead of six
    conv_in = _convergence_html("🇮🇳 India", ind_data)
    conv_us = _convergence_html("🇺🇸 US", us_data)
    convergence_html = conv_in + conv_us          # kept for any external caller

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
<p style="color:#666;font-size:13px;margin:0 0 10px">One block per market — screener, fundamentals, news and breakouts together · then global context</p>
{as_of_html}
<p style="font-size:11px;color:#555;margin:0 0 14px;background:#f6f8fc;border-left:3px solid #1a73e8;padding:6px 9px"><b>Liquidity floor</b>: India ~₹1cr/day (an explicit policy choice); other markets ~$10k/day (a structural floor — below it a listing is not transacted anywhere). The old single ~$120k bar was India's rupee gate applied everywhere: measured, it cut at India's 47th percentile but Korea's 23rd — one constant, four different filters. <b>Tier</b> is now a PERCENTILE within each market's own tradeable universe (~20% per tier), so "illiquid" means the same thing in Mumbai and New York. Bonds, G-secs and T-bills are excluded structurally, not by value — a bond trading 90 units/day at ₹1 lakh face clears a value gate.</p>
<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px">🌍 Market Snapshot</h2>
{snapshot_html}

<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:26px">🇮🇳 India <span style="font-weight:400;color:#666;font-size:13px">— mood {mood['mood']} ({mood['score']:+.2f}) from {mood.get('n_articles',0)} articles</span></h2>
<h3 style="font-size:13px;margin:12px 0 4px;color:#333">Screener — most tradable</h3>
{_table(["Symbol","Tier","Screens","LTP","Chg%","Liquidity"], ind_picks_rows) if ind_picks_rows else "<p>no picks</p>"}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">📅 Upcoming earnings <span style="font-weight:400;color:#777">— next 7 days, dividend history &amp; PEAD context</span></h3>
<p style="font-size:11px;color:#666;margin:2px 0">Not a directional call — the surprise hasn't happened yet. "Confirmed PEAD leader" means THIS ticker's own earnings have historically moved its sector peers, validated with a walk-forward holdout (see DECISION_REGISTER.md).</p>
{ind_earnings_html}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">Cash Conversion Cycle <span style="font-weight:400;color:#777">(screener.in 228040)</span></h3>
<p style="font-size:11px;color:#666;margin:2px 0">Lowest/negative CCC = collects from customers before paying suppliers.</p>
{_table(["Symbol","Name","CCC days","ROCE","Liquidity"], ccc_rows) if ccc_rows else "<p>n/a</p>"}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">⭐ Convergence <span style="font-weight:400;color:#777">— fundamentals &amp; the street agree</span></h3>
{conv_in}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">🔥 News picks <span style="font-weight:400;color:#777">— buzz, NOT a recommendation</span></h3>
{_table(["Symbol","Name","Sentiment","Mentions","Headline"], in_news_rows) if in_news_rows else "<p>n/a</p>"}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">🗞️ Talk on the Street <span style="font-weight:400;color:#777">— per-ticker sentiment</span></h3>
{_table(["Symbol","Sentiment","Score","Articles"], in_talk_rows) if in_talk_rows else "<p style='color:#777'>No per-ticker news matches today.</p>"}
{darvas_in}

<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:26px">🇺🇸 US <span style="font-weight:400;color:#666;font-size:13px">— mood {us_mood['mood']} ({us_mood['score']:+.2f}) from {us_mood.get('n_articles',0)} articles</span></h2>
<h3 style="font-size:13px;margin:12px 0 4px;color:#333">Screener — most tradable</h3>
{_table(["Symbol","Tier","Screens","LTP","Chg%","Liquidity"], us_picks_rows) if us_picks_rows else "<p>no picks (run daily_combined_report.py --market US)</p>"}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">📅 Upcoming earnings <span style="font-weight:400;color:#777">— next 7 days, dividend history &amp; PEAD context</span></h3>
<p style="font-size:11px;color:#666;margin:2px 0">Not a directional call — the surprise hasn't happened yet. "Confirmed PEAD leader" means THIS ticker's own earnings have historically moved its sector peers, validated with a walk-forward holdout (see DECISION_REGISTER.md).</p>
{us_earnings_html}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">⭐ Convergence</h3>
{conv_us}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">🔥 News picks <span style="font-weight:400;color:#777">— buzz, NOT a recommendation</span></h3>
{_table(["Symbol","Name","Sentiment","Mentions","Headline"], us_news_rows) if us_news_rows else "<p>n/a</p>"}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">🗞️ Talk on the Street</h3>
{_table(["Symbol","Sentiment","Score","Articles"], us_talk_rows) if us_talk_rows else "<p style='color:#777'>No per-ticker news matches today.</p>"}
{darvas_us}

<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:26px">🇪🇺 Europe</h2>
<h3 style="font-size:13px;margin:12px 0 4px;color:#333">Fundamentals picks</h3>
{_table(["Symbol","Name","Tier","Screens","Piotroski"], eu_picks_rows) if eu_picks_rows else "<p>no European scan available today</p>"}
{darvas_eu}

<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:26px">🇯🇵 Japan</h2>
<h3 style="font-size:13px;margin:12px 0 4px;color:#333">Fundamentals picks</h3>
{_table(["Code","Name","Tier","Screens","Piotroski"], jp_picks_rows) if jp_picks_rows else "<p>no Japan scan available today</p>"}

<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:26px">🇰🇷 Korea</h2>
<h3 style="font-size:13px;margin:12px 0 4px;color:#333">Fundamentals picks</h3>
{_table(["Code","Name","Tier","Screens","Piotroski"], kr_picks_rows) if kr_picks_rows else "<p>no Korea scan available today</p>"}

<h2 style="font-size:16px;border-bottom:2px solid #1a73e8;padding-bottom:3px;margin-top:26px">🌍 Global context</h2>
<h3 style="font-size:13px;margin:12px 0 4px;color:#333">Momentum — top 15 across 20 markets</h3>
{_table(["Mkt","Symbol","6mo %","RSI"], g_rows)}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">Other markets — top tradable mover each <span style="font-weight:400;color:#777">(≥$1M/day)</span></h3>
{_table(["Market","Symbol","6mo %","Liquidity"], other_rows) if other_rows else "<p>n/a</p>"}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">20-market 5-year scoreboard</h3>
{_table(["Mkt","Index","5y CAGR%","1y %","Sharpe"], p_rows)}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">💱 Carry-trade FX <span style="font-weight:400;color:#777">— the cross-asset channel into JP/KR/IN equities</span></h3>
{carry_html_}
<h3 style="font-size:13px;margin:14px 0 4px;color:#333">🔗 Correlation highlights</h3>
<p style="font-size:11px;color:#666;margin:2px 0">Top correlated-stock clusters per market, 1y returns. Statistical (not causal) groupings; they break down in stressed markets.</p>
{corr_html}
<p style="font-size:11px;color:#bf360c;border-top:1px solid #eee;padding-top:10px;margin-top:18px">⚠️ Educational/research only. NOT investment advice. Screener/Darvas/Convergence results are mechanical filters, not buy/sell signals. Liquidity/CCC are estimates; index figures price-only, local currency. Correlation clusters are statistical (not causal) groupings and can break down in stressed markets. Past performance does not guarantee future returns. Consult a SEBI-registered investment advisor.</p>
</div>"""

    text = (f"Daily Market Brief — {today}\n"
            f"Prices are last official closes, accurate as of generation "
            f"({_dt.datetime.now():%d %b %Y %H:%M}). Live quotes will differ.\n"
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
