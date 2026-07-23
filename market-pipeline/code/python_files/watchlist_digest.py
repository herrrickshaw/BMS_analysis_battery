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
#   * DASHBOARD — the email now opens with aggregate views over every priced
#     row: market pulse (per-market medians + 1d return-distribution bars),
#     sector clusters (hottest first; labels from market_cache/sector_map.json,
#     JP via TSE 33-industry codes, others via capped incremental yfinance —
#     `--build-sectors` backfills in one sitting), and liquidity × returns
#     (is the strength in names you can actually buy?).
#   * ZONE-FIRST LAYOUT — 🟩 Buy zone (all countries, one table) → 🟨 Hold →
#     🟥 Sell (with eviction-clock Streak column) → ❔ Unmeasured; exited
#     positions in a muted strip; "🆕 joined / 🪦 left" churn line up top.
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


# ── sector classification ────────────────────────────────────────────────────
# The dashboard clusters by sector, so every priced row wants a label. No single
# local source covers all five markets:
#   * JP  — free: the japan scan workbook carries the TSE 33-industry CODE for
#           every name; the code→name map below is the stable public JPX one.
#   * IN/US/KR/EU — yfinance .info['sector'], fetched INCREMENTALLY into
#           market_cache/sector_map.json: at most SECTOR_FETCH_CAP misses per
#           scheduled run (the 07:00 mailer must not hang on a slow API), with
#           --build-sectors to backfill everything in one sitting. A name that
#           never resolves shows as "Unclassified" rather than being dropped.
SECTOR_CACHE = R.MARKET_CACHE / "sector_map.json"
SECTOR_FETCH_CAP = 40

# JPX 33-industry codes (data_j.xls "33業種コード") → English sector names.
JP_SECTORS = {
    "0050": "Fishery/Agri", "1050": "Mining", "2050": "Construction",
    "3050": "Foods", "3100": "Textiles", "3150": "Pulp & Paper",
    "3200": "Chemicals", "3250": "Pharmaceutical", "3300": "Oil & Coal",
    "3350": "Rubber", "3400": "Glass & Ceramics", "3450": "Iron & Steel",
    "3500": "Nonferrous Metals", "3550": "Metal Products", "3600": "Machinery",
    "3650": "Electric Appliances", "3700": "Transport Equipment",
    "3750": "Precision Instruments", "3800": "Other Products",
    "4050": "Utilities", "5050": "Land Transport", "5100": "Marine Transport",
    "5150": "Air Transport", "5200": "Warehousing", "5250": "Info & Comm",
    "6050": "Wholesale", "6100": "Retail", "7050": "Banks",
    "7100": "Securities", "7150": "Insurance", "7200": "Other Financing",
    "8050": "Real Estate", "9050": "Services",
}


def _yf_ticker(symbol: str, market: str) -> str:
    """Watchlist spelling → the yfinance spelling, per market convention."""
    if market == "IN":
        return f"{symbol}.NS"
    if market == "KR" and symbol.isdigit():
        return f"{symbol.zfill(6)}.KS"
    if market == "JP" and symbol.isdigit():
        return f"{symbol}.T"
    return symbol


def _load_sector_cache() -> dict:
    import json
    try:
        return json.loads(SECTOR_CACHE.read_text())
    except Exception:
        return {}


def _save_sector_cache(m: dict) -> None:
    import json
    try:
        SECTOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SECTOR_CACHE.write_text(json.dumps(m, indent=0, sort_keys=True))
    except Exception:
        pass


def _jp_sectors_from_workbook() -> dict:
    """code(str) -> sector name, from the latest japan scan workbook. Local, free."""
    try:
        import glob
        fs = sorted(glob.glob(str(Path(__file__).parent / "japan_scan" / "japan_market_scan_*.xlsx")))
        if not fs:
            return {}
        df = pd.read_excel(fs[-1], "All_Stocks", usecols=["Code", "Sector"])
        return {str(int(c)): JP_SECTORS.get(str(int(s)).zfill(4), None)
                for c, s in zip(df["Code"], df["Sector"])
                if pd.notna(c) and pd.notna(s)}
    except Exception:
        return {}


def assign_sectors(rows: list, fetch_cap: int = SECTOR_FETCH_CAP) -> None:
    """Fill r['sector'] for every row, from cache → JP workbook → capped yfinance."""
    cache = _load_sector_cache()
    dirty = False
    jp_map = None
    fetched = 0
    for r in rows:
        key = f"{r['market']}:{r['symbol']}"
        if key in cache:
            r["sector"] = cache[key] or "Unclassified"
            continue
        sector = None
        if r["market"] == "JP" and r["symbol"].isdigit():
            if jp_map is None:
                jp_map = _jp_sectors_from_workbook()
            sector = jp_map.get(r["symbol"])
        if sector is None and not r["missing"] and fetched < fetch_cap:
            try:
                import yfinance as yf
                sector = yf.Ticker(_yf_ticker(r["symbol"], r["market"])).info.get("sector")
                fetched += 1
                # checkpoint during long --build-sectors runs: a crash at name
                # 600 of 700 must not throw away 599 answers.
                if fetched % 25 == 0:
                    _save_sector_cache(cache)
            except Exception:
                sector = None
        if sector is not None or r["market"] == "JP":
            # cache resolved names AND JP misses (a code absent from the JPX map
            # will not appear tomorrow either); leave yf failures uncached so
            # the next run retries them.
            cache[key] = sector
            dirty = True
        r["sector"] = sector or "Unclassified"
    if dirty:
        _save_sector_cache(cache)


# ── dashboard ────────────────────────────────────────────────────────────────
# Aggregate view over every PRICED row: how each market did, which sectors and
# liquidity tiers the moves clustered in. All tiers count — a sold or signal
# name is still a market observation; the per-name table below is where status
# matters.
_BUCKETS = ((-5.0, "#8b0000"), (-2.0, "#d9534f"), (-0.75, "#f0b8b8"),
            (0.75, "#d8d8d8"), (2.0, "#b8e0b8"), (5.0, "#4cae4c"),
            (float("inf"), "#0a7a0a"))


def _median(vals):
    import statistics
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def _dist_bar(d1s, width=180) -> str:
    """Email-safe stacked bar of the 1d return distribution (nested table)."""
    d1s = [d for d in d1s if d is not None]
    if not d1s:
        return ""
    counts, lo = [], float("-inf")
    for hi, colour in _BUCKETS:
        counts.append((sum(1 for d in d1s if lo < d <= hi), colour))
        lo = hi
    total = sum(c for c, _ in counts) or 1
    cells = "".join(
        f'<td style="background:{colour};width:{max(1, round(c / total * width))}px;'
        f'height:10px;font-size:0;line-height:0">&nbsp;</td>'
        for c, colour in counts if c)
    return (f'<table cellspacing="0" cellpadding="0" style="border-collapse:collapse">'
            f'<tr>{cells}</tr></table>')


def _pctfmt(v, bold=False) -> str:
    if v is None:
        return "—"
    colour = "#0a0" if v > 0 else ("#c00" if v < 0 else "#666")
    w = "font-weight:600;" if bold else ""
    return f'<span style="{w}color:{colour}">{v:+.2f}%</span>'


def render_dashboard(rows: list) -> str:
    priced = [r for r in rows if not r["missing"] and r["d1"] is not None]
    if not priced:
        return ""
    th = ('<tr style="text-align:left;border-bottom:2px solid #ddd;'
          'font-size:12px;color:#555">')
    td = 'style="padding:5px 4px;border-bottom:1px solid #f0f0f0"'
    out = ['<h3 style="margin:16px 0 4px">🌍 Market pulse</h3>',
           '<table style="border-collapse:collapse;width:100%;font-size:13px">',
           th + '<th style="padding:5px 4px">Market</th><th>n</th><th>🟢/⚪/🔴</th>'
                '<th>med 1d</th><th>med 5d</th><th>1d distribution</th>'
                '<th>best</th><th>worst</th></tr>']
    order = ["IN", "US", "JP", "KR", "EU"]
    for mkt in sorted({r["market"] for r in priced},
                      key=lambda m: order.index(m) if m in order else 9):
        g = [r for r in priced if r["market"] == mkt]
        up = sum(1 for r in g if r["mark"] == "🟢")
        dn = sum(1 for r in g if r["mark"] == "🔴")
        best = max(g, key=lambda r: r["d1"]); worst = min(g, key=lambda r: r["d1"])
        out.append(
            f'<tr><td {td}><b>{mkt}</b></td><td {td}>{len(g)}</td>'
            f'<td {td} style="font-size:12px">{up}/{len(g) - up - dn}/{dn}</td>'
            f'<td {td}>{_pctfmt(_median([r["d1"] for r in g]), True)}</td>'
            f'<td {td}>{_pctfmt(_median([r["d5"] for r in g]))}</td>'
            f'<td {td}>{_dist_bar([r["d1"] for r in g])}</td>'
            f'<td {td} style="font-size:12px">{best["symbol"]} {_pctfmt(best["d1"])}</td>'
            f'<td {td} style="font-size:12px">{worst["symbol"]} {_pctfmt(worst["d1"])}</td></tr>')
    out.append('</table>')

    # sector clusters, hottest first; Unclassified pinned last
    sectors = {}
    for r in priced:
        sectors.setdefault(r.get("sector", "Unclassified"), []).append(r)
    ranked = sorted(sectors.items(),
                    key=lambda kv: (kv[0] == "Unclassified",
                                    -(_median([r["d1"] for r in kv[1]]) or 0)))
    out += ['<h3 style="margin:16px 0 4px">🏭 Sector clusters '
            '<span style="font-weight:400;color:#777;font-size:12px">'
            '(across all markets, hottest median 1d first)</span></h3>',
            '<table style="border-collapse:collapse;width:100%;font-size:13px">',
            th + '<th style="padding:5px 4px">Sector</th><th>n</th><th>med 1d</th>'
                 '<th>med 5d</th><th>🟢%</th><th>leaders</th></tr>']
    for sec, g in ranked:
        if len(g) < 2 and sec != "Unclassified":
            continue                      # a 1-name "cluster" is just the name
        up_pct = 100.0 * sum(1 for r in g if r["mark"] == "🟢") / len(g)
        leaders = sorted(g, key=lambda r: -r["d1"])[:2]
        lead = " · ".join(f'{r["symbol"]}<span style="color:#999;font-size:10px">'
                          f' {r["market"]}</span> {_pctfmt(r["d1"])}' for r in leaders)
        out.append(
            f'<tr><td {td}>{sec}</td><td {td}>{len(g)}</td>'
            f'<td {td}>{_pctfmt(_median([r["d1"] for r in g]), True)}</td>'
            f'<td {td}>{_pctfmt(_median([r["d5"] for r in g]))}</td>'
            f'<td {td}>{up_pct:.0f}%</td>'
            f'<td {td} style="font-size:12px">{lead}</td></tr>')
    out.append('</table>')

    # liquidity × returns — is the strength in names you can actually buy?
    out += ['<h3 style="margin:16px 0 4px">💧 Liquidity × returns</h3>',
            '<table style="border-collapse:collapse;width:100%;font-size:13px">',
            th + '<th style="padding:5px 4px">Tier</th><th>n</th><th>med 1d</th>'
                 '<th>med 5d</th><th>🟢%</th><th>1d distribution</th></tr>']
    tier_label = {"T1": "T1 most liquid (≥$12M/d)", "T2": "T2 (≥$3M/d)",
                  "T3": "T3 (≥$600k/d)", "T4": "T4 above floor",
                  "—": "below floor", "?": "unmeasured"}
    for tkey in ("T1", "T2", "T3", "T4", "—", "?"):
        g = [r for r in priced if r.get("liq") == tkey]
        if not g:
            continue
        up_pct = 100.0 * sum(1 for r in g if r["mark"] == "🟢") / len(g)
        out.append(
            f'<tr><td {td}>{tier_label[tkey]}</td><td {td}>{len(g)}</td>'
            f'<td {td}>{_pctfmt(_median([r["d1"] for r in g]), True)}</td>'
            f'<td {td}>{_pctfmt(_median([r["d5"] for r in g]))}</td>'
            f'<td {td}>{up_pct:.0f}%</td>'
            f'<td {td}>{_dist_bar([r["d1"] for r in g])}</td></tr>')
    out.append('</table>')
    return "\n".join(out)


# ── buy / hold / sell zones + watchlist hygiene ──────────────────────────────
# Zone is a PURE FUNCTION of the price series — no state to persist, no state
# to corrupt, recomputable for any past session:
#     BUY   close > EMA20 and EMA20 > EMA50   (aligned uptrend)
#     SELL  close < EMA50                     (trend broken)
#     HOLD  anything between
# Eviction rule (user, 2026-07-23): a tracked name in the SELL zone for MORE
# THAN 5 consecutive sessions leaves the watchlist. Because zone is stateless,
# the streak is read straight off the tail of the series — no counter column
# that a missed run would corrupt. Only the TRACKING tiers (watch/signal/
# justified) are evicted: `held` is the user's portfolio and exiting it is not
# this tool's call; `sold` is already out. Evicted rows keep their line in the
# CSV (status → "evicted", note says when and why) — history is never deleted.
SELL_STREAK_LIMIT = 5      # strictly more than this → evicted
MIN_BARS_FOR_ZONE = 25     # below this EMA50 is noise; zone "?" and no eviction


def _close_series(df: pd.DataFrame) -> Optional[pd.Series]:
    """Date-ordered Close series with a datetime index, or None."""
    if df is None or "Close" not in df.columns:
        return None
    d = df
    for col in ("Date", "date", "price_date"):
        if col in d.columns:
            d = d.assign(_dt=pd.to_datetime(d[col], errors="coerce")) \
                 .dropna(subset=["_dt"]).sort_values("_dt").set_index("_dt")
            break
    c = pd.to_numeric(d["Close"], errors="coerce").dropna()
    return c if len(c) else None


def zone_series(df: pd.DataFrame) -> Optional[pd.Series]:
    """Per-bar BUY/HOLD/SELL labels aligned to the close series."""
    c = _close_series(df)
    if c is None or len(c) < MIN_BARS_FOR_ZONE:
        return None
    e20 = c.ewm(span=20, adjust=False).mean()
    e50 = c.ewm(span=50, adjust=False).mean()
    z = pd.Series("HOLD", index=c.index)
    z[c < e50] = "SELL"
    z[(c > e20) & (e20 > e50)] = "BUY"
    return z


def sell_streak(z: Optional[pd.Series]) -> int:
    """Trailing count of consecutive SELL sessions (0 if last bar isn't SELL)."""
    if z is None or z.empty:
        return 0
    n = 0
    for v in reversed(z.tolist()):
        if v != "SELL":
            break
        n += 1
    return n


_NOTE_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def maintain(wl: pd.DataFrame) -> tuple:
    """Backfill entry_date/entry_price and evict stale SELL-zone names.

    Returns (wl, evicted_symbols, changed). Mutation lives HERE, once per run,
    before rendering — the mailer then shows the post-hygiene list, and a name
    never appears green in the email while already evicted underneath.
    """
    changed = False
    for col in ("entry_date", "entry_price"):
        if col not in wl.columns:
            wl[col] = None
            changed = True
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    evicted = []
    for i, w in wl.iterrows():
        status = (_text(w.get("status")) or "held").lower()
        if status in ("sold", "evicted"):
            continue
        sym = str(w["symbol"]).strip().upper()
        mkt = (_text(w.get("market")) or "US").upper()
        note = _text(w.get("note"))
        # entry_date: the note usually knows when the name arrived
        # ("technical 2026-07-21", "... since 2026-07-18", "... @ 2026-07-22").
        if not _text(w.get("entry_date")):
            m = _NOTE_DATE.search(note)
            if m:
                wl.at[i, "entry_date"] = m.group(1)
                changed = True
        df = _load_ohlc(sym, mkt)
        if df is None or getattr(df, "empty", True):
            continue
        c = _close_series(df)
        # entry_price: close on the first bar at/after entry_date
        ed = _text(wl.at[i, "entry_date"] if "entry_date" in wl.columns else "")
        if ed and not _text(w.get("entry_price")) and c is not None:
            after = c[c.index >= pd.Timestamp(ed)]
            if len(after):
                wl.at[i, "entry_price"] = round(float(after.iloc[0]), 4)
                changed = True
        # eviction — tracking tiers only
        if status in ("watch", "signal", "justified"):
            streak = sell_streak(zone_series(df))
            if streak > SELL_STREAK_LIMIT:
                wl.at[i, "status"] = "evicted"
                wl.at[i, "note"] = (f"{note} | evicted {today} after {streak} "
                                    f"sessions in sell zone").strip(" |")
                evicted.append(f"{sym} ({mkt}, {streak}d)")
                changed = True
    return wl, evicted, changed


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
    m = re.match(r"([a-z_+]+)\s+(\d{4}-\d{2}-\d{2})\b\s*(.*)$", n)
    if m:
        # any "<filter> <date>" note is a machine-written signal; describe the
        # filters we know, pass the rest through by name (golden_cross etc.).
        # Trailing annotations — "(backfilled)", "| evicted …" — ride along.
        extra = m.group(3).strip(" |")
        return (f"screener signal: {_FILTER_DESC.get(m.group(1), m.group(1))} "
                f"on {m.group(2)}" + (f" {extra}" if extra else ""))
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
                         "why": why_listed(status, note),
                         "zone": "?", "streak": 0,
                         "entry_date": _text(w.get("entry_date")),
                         "ret_entry": None, "days_in": None})
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
        z = zone_series(df)
        zone = z.iloc[-1] if z is not None else "?"
        last_close = float(close.iloc[-1]) if len(close) else None
        # return since the name entered the watchlist, off the recorded entry
        # price (backfilled by maintain() from the note's date)
        entry_date = _text(w.get("entry_date"))
        entry_px = pd.to_numeric(w.get("entry_price"), errors="coerce")
        ret_entry = (float((last_close / entry_px - 1.0) * 100.0)
                     if last_close and pd.notna(entry_px) and entry_px > 0 else None)
        days_in = None
        if entry_date:
            try:
                days_in = max(0, (pd.Timestamp.today() - pd.Timestamp(entry_date)).days)
            except Exception:
                pass
        rows.append({"symbol": sym, "market": mkt, "mark": classify(d1), "d1": d1,
                     "d5": _pct_change(df, 5), "close": last_close,
                     "last": last_date, "note": note, "status": status,
                     "missing": False, "liq": liq, "below_floor": below,
                     "why": why_listed(status, note),
                     "zone": zone, "streak": sell_streak(z),
                     "entry_date": entry_date, "ret_entry": ret_entry,
                     "days_in": days_in})
    # Green movers up front, everything else at the bottom (user's standing
    # ordering request, 2026-07-23) — colour is primary, then the old status
    # tiers (held > watch > signal > sold) break ties WITHIN a colour, then
    # move size. Names below their market's liquidity floor sink to the very
    # bottom regardless of colour: a move you cannot trade is trivia, not news.
    tier = {"held": 0, "watch": 1, "signal": 2, "justified": 4, "sold": 3,
            "evicted": 5}
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
    # Evicted rows are OUT of every live view — they exist only as a short
    # "recently evicted" strip so a disappearance is explained, never silent.
    evicted = [r for r in rows if r.get("status", "held") == "evicted"]
    rows = [r for r in rows if r.get("status", "held") != "evicted"]
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
        f'<h2 style="margin:0 0 2px">📊 Watchlist Dashboard — {as_of}</h2>',
        f'<p style="color:#666;margin:0 0 14px;font-size:13px">'
        f'<b>{len(live)} held</b> — {up} up · {dn} down · {flat} flat (±{FLAT_BAND_PCT}%)'
        + (f' · {len(exited)} exited' if exited else '')
        + (f' · {len(watch)} watchlist' if watch else '')
        + (f' · {len(signals)} signals' if signals else '')
        + (f' · {len(justified)} justified' if justified else '')
        + (f' · {len(illiquid)} below liquidity floor' if illiquid else '')
        + (f' · {len(evicted)} evicted' if evicted else '')
        + (f' · <b style="color:#b00">{miss} not in cache</b>' if miss else '')
        + '</p>',
        render_dashboard(rows + justified + illiquid),
    ]

    # ── zone-first organisation (user, 2026-07-23) ───────────────────────────
    # BUY recommendations first — ALL countries in one table — then HOLD, then
    # SELL at the bottom. Green-first ordering survives within each zone
    # (build_rows' global sort). Exited rows are not recommendations and drop
    # to a muted strip; ❔/insufficient-history names get their own short table
    # rather than polluting a zone they were never measured for.
    FLAG = {"IN": "🇮🇳", "US": "🇺🇸", "JP": "🇯🇵", "KR": "🇰🇷", "EU": "🇪🇺"}

    def _since_entry(r) -> str:
        if r.get("ret_entry") is not None:
            colour = "#0a0" if r["ret_entry"] >= 0 else "#c00"
            d = f' · {r["days_in"]}d' if r.get("days_in") is not None else ""
            return f'<span style="color:{colour}">{r["ret_entry"]:+.1f}%</span>' \
                   f'<span style="color:#999;font-size:11px">{d}</span>'
        if r.get("entry_date"):
            return f'<span style="color:#999;font-size:11px">{r["entry_date"]}</span>'
        return '<span style="color:#ccc">—</span>'

    def _sym_cell(r) -> str:
        st = r.get("status", "held")
        tag = {"watch": '<span style="color:#7a9;font-size:10px"> watch</span>',
               "signal": '<span style="color:#c80;font-size:10px"> signal</span>'}.get(st, "")
        # 🆕 marks the daily churn: names that entered within the last 2 days.
        new = ' <span style="font-size:10px">🆕</span>' \
            if (r.get("days_in") is not None and r["days_in"] <= 1) else ""
        return (f'{r["mark"]} <b>{r["symbol"]}</b> '
                f'{FLAG.get(r["market"], r["market"])}{tag}{new}')

    active = [r for r in rows if r.get("status") in ("held", "watch", "signal")]
    exited = [r for r in rows if r.get("status") == "sold"]
    joined = [r for r in active if r.get("days_in") is not None and r["days_in"] <= 1]

    # today's churn, up front — the watchlist is DYNAMIC and the mailer should
    # say so before the tables do.
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    left_today = [r for r in evicted if f"evicted {today}" in (r.get("note") or "")]
    if joined or left_today:
        churn = []
        if joined:
            churn.append('<span style="color:#0a0"><b>🆕 joined:</b> '
                         + ", ".join(f'{r["symbol"]} {FLAG.get(r["market"], r["market"])}'
                                     for r in joined[:20]) + '</span>')
        if left_today:
            churn.append('<span style="color:#c00"><b>🪦 left:</b> '
                         + ", ".join(f'{r["symbol"]} {FLAG.get(r["market"], r["market"])}'
                                     for r in left_today[:20]) + '</span>')
        body.append('<p style="font-size:12px;margin:10px 0 0">'
                    + ' &nbsp;·&nbsp; '.join(churn) + '</p>')

    ZONES = (("BUY", "🟩 Buy zone", "close > EMA20 > EMA50 — aligned uptrend"),
             ("HOLD", "🟨 Hold zone", "between the EMAs — no signal either way"),
             ("SELL", "🟥 Sell zone",
              f"close < EMA50 — evicted after {SELL_STREAK_LIMIT + 1} straight sessions"),
             ("?", "❔ Unmeasured", "not in cache or under 25 bars of history"))
    for zkey, ztitle, zdesc in ZONES:
        grp = [r for r in active if r.get("zone", "?") == zkey]
        if not grp:
            continue
        held_n = sum(1 for r in grp if r["status"] == "held")
        body.append(
            f'<h3 style="margin:18px 0 4px">{ztitle} '
            f'<span style="font-weight:400;color:#777;font-size:12px">'
            f'{len(grp)} names ({held_n} held) — {zdesc}</span></h3>')
        streak_th = '<th>Streak</th>' if zkey == "SELL" else ''
        body.append(
            '<table style="border-collapse:collapse;width:100%;font-size:13px">'
            '<tr style="text-align:left;border-bottom:2px solid #ddd;font-size:12px;color:#555">'
            '<th style="padding:5px 4px">Symbol</th><th>1d</th><th>5d</th>'
            f'<th>Since entry</th>{streak_th}<th>Close</th><th>Liq</th>'
            '<th>As of</th><th>Why on the list</th></tr>')
        for r in grp:
            if r["missing"]:
                body.append(
                    f'<tr style="border-bottom:1px solid #f0f0f0;color:#b00">'
                    f'<td style="padding:5px 4px">❔ <b>{r["symbol"]}</b> '
                    f'{FLAG.get(r["market"], r["market"])}</td>'
                    f'<td colspan="6" style="font-size:12px">not in local cache — '
                    f'ingest.sh has never fetched it</td>'
                    f'<td style="font-size:12px">{r["why"]}</td></tr>')
                continue
            colour = ("#999" if r["status"] == "watch"
                      else {"🟢": "#0a0", "🔴": "#c00"}.get(r["mark"], "#666"))
            streak_td = ""
            if zkey == "SELL":
                s = r.get("streak", 0)
                warn = "#c00" if s >= SELL_STREAK_LIMIT else "#b8860b"
                streak_td = (f'<td style="color:{warn};font-size:12px">'
                             f'{s}d/{SELL_STREAK_LIMIT + 1}</td>')
            body.append(
                f'<tr style="border-bottom:1px solid #f0f0f0">'
                f'<td style="padding:5px 4px">{_sym_cell(r)}</td>'
                f'<td style="color:{colour};font-weight:600">{_fmt(r["d1"])}</td>'
                f'<td style="color:#666">{_fmt(r["d5"])}</td>'
                f'<td style="font-size:12px">{_since_entry(r)}</td>'
                f'{streak_td}'
                f'<td>{r["close"]:,.2f}</td>'
                f'<td style="color:#999;font-size:11px">{r["liq"]}</td>'
                f'<td style="color:#999;font-size:11px">{r["last"] or "?"}</td>'
                f'<td style="color:#666;font-size:12px">{r["why"]}</td></tr>')
        body.append('</table>')

    if exited:
        body.append(
            '<h3 style="margin:18px 0 4px">💼 Exited positions '
            f'<span style="font-weight:400;color:#777;font-size:12px">'
            f'({len(exited)} — kept for the record, not recommendations)</span></h3>'
            '<table style="border-collapse:collapse;width:100%;font-size:12px">')
        for r in exited:
            cell = (f'{_fmt(r["d1"])} · close {r["close"]:,.2f}'
                    if not r["missing"] else "not in cache")
            body.append(
                f'<tr style="border-bottom:1px solid #f4f4f4;color:#888">'
                f'<td style="padding:4px"><b>{r["symbol"]}</b> '
                f'{FLAG.get(r["market"], r["market"])}</td>'
                f'<td style="font-size:11px">{cell}</td>'
                f'<td style="font-size:11px">{_since_entry(r)}</td>'
                f'<td style="font-size:11px">{r["note"]}</td></tr>')
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

    if evicted:
        # newest first; the note carries "evicted YYYY-MM-DD after Nd" so the
        # strip is self-explaining. Capped — the point is "what just left and
        # why", not a graveyard tour.
        recent = sorted(evicted, key=lambda r: r.get("note", ""), reverse=True)[:15]
        body.append(
            '<h3 style="margin:18px 0 4px">🪦 Evicted '
            '<span style="font-weight:400;color:#777;font-size:12px">'
            f'(sell zone &gt;{SELL_STREAK_LIMIT} consecutive sessions — '
            f'{len(evicted)} total, latest {len(recent)})</span></h3>'
            '<table style="border-collapse:collapse;width:100%;font-size:12px">')
        for r in recent:
            ev = r["note"].rsplit("evicted", 1)[-1].strip() if "evicted" in r["note"] else ""
            body.append(
                f'<tr style="border-bottom:1px solid #f4f4f4;color:#888">'
                f'<td style="padding:4px"><b>{r["symbol"]}</b>'
                f'<span style="font-size:10px"> {r["market"]}</span></td>'
                f'<td style="font-size:11px">{_since_entry(r)}</td>'
                f'<td style="font-size:11px">evicted {ev}</td></tr>')
        body.append('</table>')

    body.append(
        '<p style="color:#999;font-size:11px;margin-top:14px">'
        'Prices from the local cache refreshed by ingest.sh — no external API. '
        '"As of" is the last bar actually held, so a stale row is visible rather '
        'than silently shown as current. Sorted 🟢 first, then flat, then 🔴; '
        'names below their market\'s liquidity floor sink to the bottom strip. '
        '"Liq" = median 60d USD turnover tier (T1 ≥$12M · T2 ≥$3M · T3 ≥$600k · '
        'T4 above floor · ? unmeasurable). '
        'Zone: 🟩 close&gt;EMA20&gt;EMA50 · 🟥 close&lt;EMA50 · 🟨 between; a tracked '
        f'name (watch/signal/justified) in 🟥 for &gt;{SELL_STREAK_LIMIT} consecutive '
        'sessions is auto-evicted; held positions are never auto-exited. '
        'Not investment advice.</p></div>')
    return "\n".join(body)


def main() -> int:
    ap = argparse.ArgumentParser(description="Watchlist digest from the local cache")
    ap.add_argument("--watchlist", default="watchlist.csv")
    ap.add_argument("--out", help="write HTML here (default: stdout)")
    ap.add_argument("--send", action="store_true",
                    help="email it via GMAIL_USER/GMAIL_APP_PASSWORD/MAIL_TO")
    ap.add_argument("--build-sectors", action="store_true",
                    help="backfill the ENTIRE sector cache now (slow, yfinance) "
                         "instead of the per-run cap")
    ap.add_argument("--no-maintain", action="store_true",
                    help="render only: skip entry backfill and sell-zone eviction "
                         "(no write to the watchlist CSV)")
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

    if not args.no_maintain:
        # Hygiene BEFORE rendering, so the email always reflects the
        # post-eviction list. maintain() only touches entry_date/entry_price
        # and flips watch/signal/justified → evicted; nothing is deleted.
        wl, evicted, changed = maintain(wl)
        if changed:
            wl.to_csv(wl_path, index=False)
        if evicted:
            print(f"  evicted (> {SELL_STREAK_LIMIT} sessions in sell zone): "
                  + ", ".join(evicted))

    rows = build_rows(wl)
    assign_sectors(rows, fetch_cap=10_000 if args.build_sectors else SECTOR_FETCH_CAP)
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
        # Held-only, matching the body's headline count. Counting every tier
        # made the subject balloon once KR/JP/EU started pricing (195↑ 352↓ on
        # 2026-07-23) — a number about the whole tracking universe, not the
        # portfolio the subject line is glanced for.
        held = [r for r in rows if r.get("status", "held") == "held"]
        up = sum(1 for r in held if r["mark"] == "🟢")
        dn = sum(1 for r in held if r["mark"] == "🔴")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 Watchlist — {as_of} ({up}↑ {dn}↓ of {len(held)} held)"
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
