#!/usr/bin/env python3
# watchlist_digest.py
# ===================
# Per-name morning digest for the stocks YOU track — 🟢/🔴/⚪ + move + context.
#
# WHY THIS EXISTS (and why it is not the daily brief)
# ───────────────────────────────────────────────────
# The brief scans ~20,000 stocks and reports what the SCREENERS liked. It never
# answers "how did my names do", because your names are not a screener output.
# Those are different questions and the brief cannot answer the second one
# without becoming a worse version of itself.
#
# Shape borrowed from Kevin Meneses' n8n stock-digest writeup (schedule → read a
# watchlist → fetch quotes → classify 🟢/🔴/⚪ → email). Two deliberate departures:
#
#   * DATA SOURCE. The article calls EODHD, a paid API. Everything needed is
#     already on this machine and already refreshed nightly by ingest.sh —
#     market_cache/ohlc/*.parquet for US/global, the bhavcopy LMDB for India.
#     Paying an external provider for data we already hold, and adding a network
#     dependency to a step that currently has none, would be a downgrade.
#   * WATCHLIST SOURCE. The article reads Google Sheets. A CSV needs no OAuth and
#     works today; --watchlist points anywhere, so swapping in a Sheets export
#     later changes nothing else.
#
# Reads (via data_registry — never hardcode these):
#     cache.ohlc      market_cache/ohlc/<TICKER>.parquet
#     bhavcopy.lmdb   India EOD
#
#   watchlist_digest.py                          # HTML to stdout
#   watchlist_digest.py --out digest.html
#   watchlist_digest.py --watchlist my.csv
#
# Watchlist CSV: a `symbol` column; optional `market` (US/IN) and `note`.
#
# 2026-07-23 additions (user request):
#   * ORDER — 🟢 movers first, then flat, then 🔴, misses last; status tier
#     (held > watch > signal > sold) breaks ties within a colour.
#   * LIQUIDITY — every row gets a "Liq" tier (T1..T4, same absolute USD bands
#     as the scan workbooks, FX via liquidity.py's cached rates); names below
#     their market's floor (India ₹1cr/day policy gate, $10k structural
#     elsewhere) drop into a muted strip at the bottom instead of competing
#     with tradeable names. Unmeasurable liquidity fails OPEN ("?"), never
#     drops a row.
#   * WHY — the Note column is now "Why on the list": status + machine-written
#     note expanded to a readable reason ("screener signal: grade-A breakout
#     (breakout_quality) on 2026-07-21", "recurring mover x3 +5.2% since ...").

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_registry as R  # noqa: E402
import env_loader as _env  # noqa: E402

# Classification thresholds. ⚪ is a genuine band, not a rounding artifact: a
# ±0.75% day on most equities is noise, and colouring it green or red invents a
# signal. The article's binary up/down colouring makes every flat day look like
# a move.
FLAT_BAND_PCT = 0.75


# The per-symbol OHLC cache (market_cache/ohlc/) is US-only — 7,657 bare
# tickers, zero suffixed names. KR/JP/EU watchlist rows therefore ALWAYS
# reported "not in cache" (all 125 KR rows on 2026-07-23). Their prices do
# exist locally: the year-partitioned warehouse signal_tracker already reads
# (global-market-data/warehouse/ohlcv/<MKT>/year=*.parquet, fresh through
# today). Fall back to it, loading each market ONCE per run — a filtered
# per-symbol read costs ~0.4s and 190 of them would take minutes.
WAREHOUSE = Path("/Users/umashankar/repos/global-market-data/warehouse/ohlcv")
_WH_FRAMES: dict = {}


def _warehouse_frames(market: str) -> dict:
    """symbol -> OHLC frame for one market from the warehouse. Last TWO year
    partitions, not one: in early January the current partition alone holds
    fewer than the 10 bars the turnover median needs, and every row would read
    'liquidity unmeasurable' for two weeks."""
    mkt = market.upper()[:2]
    if mkt in _WH_FRAMES:
        return _WH_FRAMES[mkt]
    frames: dict = {}
    try:
        years = sorted((WAREHOUSE / mkt).glob("year=*.parquet"))[-2:]
        if years:
            df = pd.concat([pd.read_parquet(p) for p in years],
                           ignore_index=True).sort_values("Date")
            frames = {s: g for s, g in df.groupby("Symbol")}
    except Exception:
        frames = {}
    _WH_FRAMES[mkt] = frames
    return frames


def _wh_candidates(symbol: str, market: str) -> list:
    """Cache-key spellings for a watchlist symbol in the warehouse.

    The watchlist stores KR codes the way brokers print them — '5360', with the
    leading zeros dropped — while the warehouse keys the full six digits plus
    venue suffix ('005360.KS'). KOSPI vs KOSDAQ is not recorded in the
    watchlist, so try both suffixes. JP is four digits + '.T'; EU rows are
    already stored suffixed.
    """
    if market == "KR" and symbol.isdigit():
        code = symbol.zfill(6)
        return [f"{code}.KS", f"{code}.KQ"]
    if market == "JP" and symbol.isdigit():
        return [f"{symbol}.T"]
    return [symbol, symbol.replace(".", "-")]


def _load_ohlc(symbol: str, market: str) -> Optional[pd.DataFrame]:
    """Recent OHLC for one symbol from the local cache. None if not cached."""
    if market.upper() in ("IN", "INDIA", "NS"):
        # bhavcopy_store.get(), NOT load_symbol() — the latter does not exist and
        # the broad `except` here swallowed the ImportError, so every India name
        # reported as "not in cache" while the data was present all along.
        try:
            from bhavcopy_store import get as _bhav_get  # type: ignore
            return _bhav_get(symbol)
        except Exception:
            return None
    # Class shares: filings write BRK.B, yfinance and the cache write BRK-B. The
    # dot form is what a broker statement gives you, so normalise rather than
    # asking the watchlist to know the cache's convention — otherwise a position
    # you definitely hold reports as "not in cache" purely on punctuation.
    for cand in (symbol, symbol.replace(".", "-")):
        p = R.OHLC_DIR / f"{cand}.parquet"
        if p.exists():
            try:
                return pd.read_parquet(p)
            except Exception:
                return None
    frames = _warehouse_frames(market)
    for cand in _wh_candidates(symbol, market.upper()[:2]):
        df = frames.get(cand)
        if df is not None and not df.empty:
            return df
    return None


def _pct_change(df: pd.DataFrame, bars: int = 1) -> Optional[float]:
    try:
        c = pd.to_numeric(df["Close"], errors="coerce").dropna()
        if len(c) < bars + 1:
            return None
        return float((c.iloc[-1] / c.iloc[-1 - bars] - 1.0) * 100.0)
    except Exception:
        return None


# ── liquidity ────────────────────────────────────────────────────────────────
# The scans gate on liquidity; the digest historically did not, so an untradeable
# micro-cap could sit at the top of the email looking like an opportunity. Reuse
# the pipeline's own machinery (liquidity.py FX + adaptive_liquidity floors)
# rather than inventing a digest-local standard: floor = structural $10k/day
# everywhere plus India's chosen Rs 1 crore policy gate; tiers = the same
# absolute T1_MEGA..T4_SMALL bands the scan workbooks print, so the labels mean
# the same thing here as there.
#
# scan_gate() itself is NOT reusable here: it derives currency from the ticker
# suffix only, and the watchlist stores IN/KR/JP names BARE — 'RELIANCE' would
# be priced in USD, inflating its turnover ~83x. Currency therefore comes from
# the suffix when there is one (EU rows are pre-suffixed) and from the market
# column otherwise.
TIER_SHORT = {"T1_MEGA": "T1", "T2_LARGE": "T2", "T3_MID": "T3", "T4_SMALL": "T4"}


def _fx_map() -> dict:
    """currency -> units per USD, cached on disk by liquidity.py. {} on failure
    — every name then reads 'liquidity unmeasurable', which fails OPEN (no row
    is dropped because an FX provider had a bad morning)."""
    try:
        import liquidity as L
        return L.scan_fx()
    except Exception:
        return {}


def _turnover_usd(df: pd.DataFrame, symbol: str, market: str,
                  fx: dict) -> Optional[float]:
    """Median daily Close×Volume over the last 60 bars, in USD. None = unmeasurable."""
    if df is None or "Close" not in df.columns or "Volume" not in df.columns:
        return None
    try:
        import liquidity as L
        t = (pd.to_numeric(df["Close"], errors="coerce")
             * pd.to_numeric(df["Volume"], errors="coerce")).dropna().tail(60)
        if len(t) < 10:
            return None
        tv = float(t.median())
        ccy = (L.currency_for(symbol) if "." in str(symbol)
               else L.CCY.get(market.upper()[:2], "USD"))
        if ccy in L.SUBUNIT:                       # London pence etc.
            base, div = L.SUBUNIT[ccy]
            tv, ccy = tv / div, base
        rate = fx.get(ccy)
        return tv / rate if rate else None
    except Exception:
        return None


def _liq_label(tv: Optional[float], market: str) -> tuple:
    """(short tier label, below_floor). Unmeasurable -> ('?', False): unknown
    liquidity is not the same claim as 'too illiquid to trade'."""
    if tv is None:
        return "?", False
    try:
        from adaptive_liquidity import scan_floor
        floor = scan_floor(market)
    except Exception:
        floor = 120_000.0 if market.upper().startswith("IN") else 10_000.0
    if tv < floor:
        return "—", True
    try:
        from liquidity import SCAN_TIERS_USD
        for lo, name in SCAN_TIERS_USD:
            if tv >= lo:
                return TIER_SHORT.get(name, name), False
    except Exception:
        pass
    return "T4", False


# ── why is this name on the list ─────────────────────────────────────────────
# The status column says WHAT a row is; the note says (for signal rows) which
# filter promoted it, in the terse form the writers use. Expand both into one
# human-readable remark so the email answers "why am I looking at this?"
# without a trip back to signal_tracker's ledger.
_FILTER_DESC = {
    "technical": "grade-A breakout (breakout_quality)",
    "triple": "triple screener confluence",
    "piotroski+debt": "Piotroski F-score + debt reduction",
    "piotroski+roce": "Piotroski F-score + ROCE quality",
}


def why_listed(status: str, note: str) -> str:
    n = note.strip()
    if status == "held":
        return "portfolio holding" + (f" — {n}" if n else "")
    if status == "sold":
        return "exited position" + (f" — {n}" if n else "")
    if status == "watch":
        return "manually watched" + (f" — {n}" if n else "")
    if status == "justified":
        return f"justified pick — {n}" if n else "justified pick (evidence-backed screen)"
    # signal tier: notes are machine-written; parse the known shapes.
    if n.startswith("recurring"):
        # "recurring x3 +5.2% since 2026-07-18" (recurring_movers)
        return n.replace("recurring", "recurring mover", 1)
    m = re.match(r"([a-z+]+)\s+(\d{4}-\d{2}-\d{2})$", n)
    if m and m.group(1) in _FILTER_DESC:
        return f"screener signal: {_FILTER_DESC[m.group(1)]} on {m.group(2)}"
    if n:
        # pre-ledger rows carry a company name, not a source — say so rather
        # than presenting the name as if it were a reason.
        return f"screener signal (source not recorded) — {n}"
    return "screener signal (source not recorded)"


def classify(pct: Optional[float]) -> str:
    if pct is None:
        return "⚪"
    if pct > FLAT_BAND_PCT:
        return "🟢"
    if pct < -FLAT_BAND_PCT:
        return "🔴"
    return "⚪"


def _text(v) -> str:
    """Blank for NaN/None. A missing note is blank, not the string 'nan'."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


def build_rows(watchlist: pd.DataFrame) -> list:
    fx = _fx_map()
    rows = []
    for _, w in watchlist.iterrows():
        sym = str(w["symbol"]).strip().upper()
        mkt = (_text(w.get("market")) or "US").upper()
        status = (_text(w.get("status")) or "held").lower()
        note = _text(w.get("note"))
        df = _load_ohlc(sym, mkt)
        if df is None or df.empty:
            # Surfaced, not silently dropped. A name missing from the cache is a
            # coverage gap worth seeing — dropping it makes the digest look
            # complete while quietly omitting exactly what you asked about.
            rows.append({"symbol": sym, "market": mkt, "mark": "❔", "d1": None,
                         "d5": None, "close": None, "last": None,
                         "note": note, "status": status, "missing": True,
                         "liq": "?", "below_floor": False,
                         "why": why_listed(status, note)})
            continue
        close = pd.to_numeric(df["Close"], errors="coerce").dropna()
        last_date = None
        for col in ("Date", "date", "price_date"):
            if col in df.columns:
                last_date = str(pd.to_datetime(df[col], errors="coerce").max())[:10]
                break
        if last_date is None and isinstance(df.index, pd.DatetimeIndex):
            last_date = str(df.index.max())[:10]
        d1 = _pct_change(df, 1)
        liq, below = _liq_label(_turnover_usd(df, sym, mkt, fx), mkt)
        rows.append({"symbol": sym, "market": mkt, "mark": classify(d1), "d1": d1,
                     "d5": _pct_change(df, 5),
                     "close": float(close.iloc[-1]) if len(close) else None,
                     "last": last_date, "note": note, "status": status,
                     "missing": False, "liq": liq, "below_floor": below,
                     "why": why_listed(status, note)})
    # Green movers up front, everything else at the bottom (user's standing
    # ordering request, 2026-07-23) — colour is primary, then the old status
    # tiers (held > watch > signal > sold) break ties WITHIN a colour, then
    # move size. Names below their market's liquidity floor sink to the very
    # bottom regardless of colour: a move you cannot trade is trivia, not news.
    tier = {"held": 0, "watch": 1, "signal": 2, "justified": 4, "sold": 3}
    mark_rank = {"🟢": 0, "⚪": 1, "🔴": 2, "❔": 3}
    rows.sort(key=lambda r: (bool(r.get("below_floor")),
                             mark_rank.get(r["mark"], 3),
                             tier.get(r.get("status", "held"), 0),
                             r["d1"] is None, -(r["d1"] or 0)))
    return rows


def _fmt(p: Optional[float]) -> str:
    return "—" if p is None else f"{p:+.2f}%"


def render(rows: list, as_of: str) -> str:
    # Three tiers, not two. 'watch' names are neither owned nor exited — counting
    # them as held would overstate the portfolio nearly fourfold.
    live = [r for r in rows if r.get("status", "held") == "held"]
    exited = [r for r in rows if r.get("status", "held") == "sold"]
    watch = [r for r in rows if r.get("status", "held") == "watch"]
    signals = [r for r in rows if r.get("status", "held") == "signal"]
    # `justified` rows get their OWN table below the main one — they are picks
    # from the evidence-first mailer, not portfolio state, and mixing them into
    # the main table would bury both.
    justified = [r for r in rows if r.get("status", "held") == "justified"]
    rows = [r for r in rows if r.get("status", "held") != "justified"]
    # Below-floor names come OUT of the main table into their own strip at the
    # bottom: they stay visible (the liquidity call may age badly) but no longer
    # compete for attention with names that can actually be bought.
    illiquid = [r for r in rows if r.get("below_floor")]
    rows = [r for r in rows if not r.get("below_floor")]
    up = sum(1 for r in live if r["mark"] == "🟢")
    dn = sum(1 for r in live if r["mark"] == "🔴")
    flat = sum(1 for r in live if r["mark"] == "⚪")
    miss = sum(1 for r in rows if r["missing"])

    body = [
        '<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:680px">',
        f'<h2 style="margin:0 0 2px">📊 Watchlist Digest — {as_of}</h2>',
        f'<p style="color:#666;margin:0 0 14px;font-size:13px">'
        f'<b>{len(live)} held</b> — {up} up · {dn} down · {flat} flat (±{FLAT_BAND_PCT}%)'
        + (f' · {len(exited)} exited' if exited else '')
        + (f' · {len(watch)} watchlist' if watch else '')
        + (f' · {len(signals)} signals' if signals else '')
        + (f' · {len(justified)} justified' if justified else '')
        + (f' · {len(illiquid)} below liquidity floor' if illiquid else '')
        + (f' · <b style="color:#b00">{miss} not in cache</b>' if miss else '')
        + '</p>',
        '<table style="border-collapse:collapse;width:100%;font-size:14px">',
        '<tr style="text-align:left;border-bottom:2px solid #ddd">'
        '<th style="padding:6px 4px">Symbol</th><th>1d</th><th>5d</th>'
        '<th>Close</th><th>Liq</th><th>As of</th><th>Why on the list</th></tr>',
    ]
    for r in rows:
        st = r.get("status", "held")
        muted = st in ("sold", "watch")
        colour = "#999" if muted else {"🟢": "#0a0", "🔴": "#c00"}.get(r["mark"], "#666")
        tag = {"sold": '<span style="color:#aaa;font-size:10px"> exited</span>',
               "watch": '<span style="color:#7a9;font-size:10px"> watch</span>',
               "signal": '<span style="color:#c80;font-size:10px"> signal</span>'}.get(st, "")
        if r["missing"]:
            body.append(
                f'<tr style="border-bottom:1px solid #f0f0f0;color:#b00">'
                f'<td style="padding:6px 4px">❔ <b>{r["symbol"]}</b></td>'
                f'<td colspan="5">not in local cache — ingest.sh has never fetched it</td>'
                f'<td style="font-size:12px">{r["why"]}</td></tr>')
            continue
        body.append(
            f'<tr style="border-bottom:1px solid #f0f0f0">'
            f'<td style="padding:6px 4px">{r["mark"]} <b>{r["symbol"]}</b>'
            f'<span style="color:#999;font-size:11px"> {r["market"]}</span>{tag}</td>'
            f'<td style="color:{colour};font-weight:600">{_fmt(r["d1"])}</td>'
            f'<td style="color:#666">{_fmt(r["d5"])}</td>'
            f'<td>{r["close"]:,.2f}</td>'
            f'<td style="color:#999;font-size:11px">{r["liq"]}</td>'
            f'<td style="color:#999;font-size:12px">{r["last"] or "?"}</td>'
            f'<td style="color:#666;font-size:12px">{r["why"]}</td></tr>')
    body.append('</table>')

    if illiquid:
        body.append(
            '<h3 style="margin:18px 0 4px">🚱 Below liquidity floor '
            '<span style="font-weight:400;color:#777;font-size:12px">'
            '(median daily turnover under the market\'s gate — India ₹1cr/day, '
            'elsewhere $10k structural; moves here are hard to act on)</span></h3>'
            '<table style="border-collapse:collapse;width:100%;font-size:12px">')
        for r in illiquid:
            colour = {"🟢": "#0a0", "🔴": "#c00"}.get(r["mark"], "#666")
            body.append(
                f'<tr style="border-bottom:1px solid #f4f4f4;color:#888">'
                f'<td style="padding:4px">{r["mark"]} <b>{r["symbol"]}</b>'
                f'<span style="font-size:10px"> {r["market"]}</span></td>'
                f'<td style="color:{colour}">{_fmt(r["d1"])}</td>'
                f'<td>{r["close"]:,.2f}</td>'
                f'<td style="font-size:11px">{r["last"] or "?"}</td>'
                f'<td style="font-size:11px">{r["why"]}</td></tr>')
        body.append('</table>')

    if justified:
        body.append(
            '<h3 style="margin:18px 0 4px">🧪 Justified picks '
            '<span style="font-weight:400;color:#777;font-size:12px">'
            '(evidence-backed screens — see the Justified Brief for the backtest '
            'behind each)</span></h3>'
            '<table style="border-collapse:collapse;width:100%;font-size:13px">'
            '<tr style="text-align:left;border-bottom:2px solid #ddd">'
            '<th style="padding:5px 4px">Symbol</th><th>1d</th><th>5d</th>'
            '<th>Close</th><th>Liq</th><th>As of</th><th>Screen</th></tr>')
        for r in justified:
            if r["missing"]:
                body.append(
                    f'<tr style="border-bottom:1px solid #f0f0f0;color:#b58900">'
                    f'<td style="padding:5px 4px">❔ <b>{r["symbol"]}</b>'
                    f'<span style="color:#999;font-size:11px"> {r["market"]}</span></td>'
                    f'<td colspan="5" style="font-size:12px">not in local cache</td>'
                    f'<td style="color:#666;font-size:12px">{r["note"]}</td></tr>')
                continue
            colour = {"🟢": "#0a0", "🔴": "#c00"}.get(r["mark"], "#666")
            body.append(
                f'<tr style="border-bottom:1px solid #f0f0f0">'
                f'<td style="padding:5px 4px">{r["mark"]} <b>{r["symbol"]}</b>'
                f'<span style="color:#999;font-size:11px"> {r["market"]}</span></td>'
                f'<td style="color:{colour};font-weight:600">{_fmt(r["d1"])}</td>'
                f'<td style="color:#666">{_fmt(r["d5"])}</td>'
                f'<td>{r["close"]:,.2f}</td>'
                f'<td style="color:#999;font-size:11px">{r["liq"]}</td>'
                f'<td style="color:#999;font-size:12px">{r["last"] or "?"}</td>'
                f'<td style="color:#666;font-size:12px">{r["note"]}</td></tr>')
        body.append('</table>')

    body.append(
        '<p style="color:#999;font-size:11px;margin-top:14px">'
        'Prices from the local cache refreshed by ingest.sh — no external API. '
        '"As of" is the last bar actually held, so a stale row is visible rather '
        'than silently shown as current. Sorted 🟢 first, then flat, then 🔴; '
        'names below their market\'s liquidity floor sink to the bottom strip. '
        '"Liq" = median 60d USD turnover tier (T1 ≥$12M · T2 ≥$3M · T3 ≥$600k · '
        'T4 above floor · ? unmeasurable). Not investment advice.</p></div>')
    return "\n".join(body)


def main() -> int:
    ap = argparse.ArgumentParser(description="Watchlist digest from the local cache")
    ap.add_argument("--watchlist", default="watchlist.csv")
    ap.add_argument("--out", help="write HTML here (default: stdout)")
    ap.add_argument("--send", action="store_true",
                    help="email it via GMAIL_USER/GMAIL_APP_PASSWORD/MAIL_TO")
    args = ap.parse_args()

    wl_path = Path(args.watchlist)
    if not wl_path.is_absolute():
        wl_path = Path(__file__).resolve().parent / wl_path
    if not wl_path.exists():
        print(f"watchlist not found: {wl_path}", file=sys.stderr)
        return 1

    wl = pd.read_csv(wl_path)
    if "symbol" not in wl.columns:
        print("watchlist needs a 'symbol' column", file=sys.stderr)
        return 1

    rows = build_rows(wl)
    as_of = max([r["last"] for r in rows if r["last"]] or ["?"])
    html = render(rows, as_of)

    miss = sum(1 for r in rows if r["missing"])
    if args.out:
        Path(args.out).write_text(html)
        print(f"  digest: {len(rows)} names, {miss} missing → {args.out}")
    elif not args.send:
        print(html)

    if args.send:
        # Credentials come from env_loader, so there is ONE place they live
        # (.env, mode 600, gitignored). Using n8n's Gmail node instead would mean
        # a second credential store to keep in sync, editable only via the UI.
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        user, pw = _env.get("GMAIL_USER"), _env.get("GMAIL_APP_PASSWORD")
        to = _env.get("MAIL_TO")
        if not (user and pw and to):
            print("  ✗ cannot send: GMAIL_USER / GMAIL_APP_PASSWORD / MAIL_TO not set",
                  file=sys.stderr)
            return 1
        up = sum(1 for r in rows if r["mark"] == "🟢")
        dn = sum(1 for r in rows if r["mark"] == "🔴")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 Watchlist — {as_of} ({up}↑ {dn}↓)"
        msg["From"], msg["To"] = user, to
        msg.attach(MIMEText(html, "html"))
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
                s.login(user, pw)
                s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
            print(f"  sent '{msg['Subject']}' → {to}")
        except Exception as e:
            print(f"  ✗ send failed: {str(e)[:120]}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
