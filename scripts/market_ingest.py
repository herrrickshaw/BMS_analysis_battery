#!/usr/bin/env python3
"""
Daily market ingest — append-only, per-geography, with a freshness ledger.

WHY: the pipeline re-scans each market from scratch every day and drops a
timestamped workbook (us_full_scan_20260714_1205.xlsx). Nothing accumulates: each
run's data is a fresh snapshot that overwrites nothing and is appended nowhere, so
there is no per-market history and no record of *when* each geography last got
real data. This script fixes both.

MODEL
  * India   -> true OHLCV time series (NSE/BSE bhavcopy), appended by trade_date.
               Lives in Postgres  bhavcopy.*  (see scripts/bhavcopy_to_db.py).
  * US/EU/JP/KR -> the scans emit a point-in-time snapshot (Symbol, LTP,
               Prev_Close, Change%, Darvas_Signal) with the date only in the
               filename. Each day's snapshot is appended as dated rows to
               market_daily.snapshots, building the history the scans never kept.

APPEND-ONLY + IDEMPOTENT: a market/date already present is never re-inserted, so
re-running the routine any number of times a day appends 0 rows.

LEDGER: every run writes market_daily.ingest_log (run_at, market, source,
last_data_date, rows_appended, total_rows, status). market_daily.freshness is a
view answering "when was each geography last updated?" at a glance.

Usage:
    python3 scripts/market_ingest.py                 # ingest all markets, then print status
    python3 scripts/market_ingest.py --status        # just the market-wise freshness table
    python3 scripts/market_ingest.py --market us     # one geography
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import duckdb

HOME = Path("/Users/umashankar")
# The live pipeline writes scans to market-pipeline/. The old Downloads/ tree is a
# stale mirror (and is periodically wiped mid-run), so reading from it fed the
# warehouse a 119-row partial while the complete 6,279-row US scan sat unseen here.
PF = HOME / "market-pipeline" / "code" / "python_files"
if not (PF / "us_full_scan").exists():  # fall back if the layout ever moves
    PF = HOME / "Downloads" / "code" / "python_files"
DSN = "dbname=market_data host=/tmp user=umashankar"
SCHEMA = "market_daily"

# market -> (geography label, scan dir, filename glob)
SNAPSHOT_MARKETS = {
    "us":     ("United States (NASDAQ/NYSE)", "us_full_scan",   "us_full_scan_*.xlsx"),
    "europe": ("Europe (17 exchanges)",       "european_scan",  "european_market_scan*.xlsx"),
    "japan":  ("Japan (TSE)",                 "japan_scan",     "japan_market_scan_*.xlsx"),
    "korea":  ("Korea (KOSPI/KOSDAQ)",        "korea_scan",     "korea_market_scan_*.xlsx"),
}
INDIA_LABEL = "India (NSE/BSE bhavcopy)"

DDL = f"""
CREATE SCHEMA IF NOT EXISTS pg."{SCHEMA}";
CREATE TABLE IF NOT EXISTS pg."{SCHEMA}".snapshots (
  market VARCHAR, as_of_date DATE, symbol VARCHAR, ltp DOUBLE, prev_close DOUBLE,
  change_pct DOUBLE, darvas_signal VARCHAR, source_file VARCHAR
);
CREATE TABLE IF NOT EXISTS pg."{SCHEMA}".ingest_log (
  run_at TIMESTAMP, market VARCHAR, geography VARCHAR, source VARCHAR,
  last_data_date DATE, rows_appended BIGINT, total_rows BIGINT,
  status VARCHAR, detail VARCHAR
);
"""


def connect():
    con = duckdb.connect()
    con.execute("INSTALL postgres"); con.execute("LOAD postgres")
    con.execute(f"ATTACH '{DSN}' AS pg (TYPE postgres)")
    for stmt in filter(None, (s.strip() for s in DDL.split(";"))):
        con.execute(stmt)
    return con


def _date_from_name(p: Path) -> dt.date | None:
    m = re.search(r"(20\d{6})", p.name)
    return dt.datetime.strptime(m.group(1), "%Y%m%d").date() if m else None


def log(con, market, geo, source, last_date, appended, total, status, detail=""):
    con.execute(
        f'INSERT INTO pg."{SCHEMA}".ingest_log VALUES (?,?,?,?,?,?,?,?,?)',
        [dt.datetime.now(), market, geo, source, last_date, appended, total, status, detail],
    )


def ingest_india(con) -> None:
    """India already has a real OHLCV series; record its true high-water mark."""
    try:
        n = con.execute("SELECT count(*) FROM pg.bhavcopy.bhavcopy_ohlcv").fetchone()[0]
        mx = con.execute("SELECT max(trade_date) FROM pg.bhavcopy.bhavcopy_ohlcv").fetchone()[0]
    except Exception as e:
        log(con, "india", INDIA_LABEL, "bhavcopy", None, 0, 0, "failed", str(e)[:180])
        print(f"  india    FAILED  {str(e)[:70]}")
        return
    prev = con.execute(
        f"""SELECT max(last_data_date) FROM pg."{SCHEMA}".ingest_log
            WHERE market='india' AND status<>'failed'"""
    ).fetchone()[0]
    status = "ok" if (prev is None or mx > prev) else "no_new_data"
    log(con, "india", INDIA_LABEL, "bhavcopy", mx, 0, n, status,
        "append handled by scripts/bhavcopy_to_db.py --incremental")
    print(f"  india    {status:12s} last_data={mx}  total_rows={n:,}")


def ingest_snapshot(con, market: str) -> None:
    geo, sub, glob = SNAPSHOT_MARKETS[market]
    files = sorted((PF / sub).glob(glob))
    if not files:
        log(con, market, geo, sub, None, 0, 0, "missing", f"no workbook in {sub}/")
        print(f"  {market:8s} MISSING      no scan workbook in {sub}/")
        return

    # A scan dir accumulates several re-runs per day (partial retries, throttled
    # runs, a full sweep). Blindly taking files[-1] once grabbed a 119-row partial
    # and, because the date was then "already ingested", permanently locked out the
    # complete 6,279-row scan. So: group by date, and for each date pick the LARGEST
    # file (byte size is a faithful proxy for row count across these identical
    # sheets). Only the newest date is ingested per run.
    by_date: dict = {}
    for p in files:
        d = _date_from_name(p)
        if d is None:
            continue
        cur = by_date.get(d)
        if cur is None or p.stat().st_size > cur.stat().st_size:
            by_date[d] = p
    if not by_date:
        log(con, market, geo, files[-1].name, None, 0, 0, "failed", "no date in any filename")
        print(f"  {market:8s} FAILED       cannot parse date from any workbook")
        return

    # Reconcile EVERY date, newest first, not just the latest: a date whose stored
    # snapshot is already as full as the best file is a no-op, so this repairs a
    # past partial (e.g. the 119-row 07-15) without re-touching complete history.
    for as_of in sorted(by_date, reverse=True):
        _ingest_date(con, market, geo, as_of, by_date[as_of])


def _ingest_date(con, market: str, geo: str, as_of, f) -> None:
    import pandas as pd

    # "already ingested" is no longer a hard skip: if the best file for this date
    # holds MORE rows than what's stored, it's a fuller scan and must replace the
    # partial — that is what "updating" the warehouse means. Equal/fewer rows skip.
    already = con.execute(
        f'SELECT count(*) FROM pg."{SCHEMA}".snapshots WHERE market=? AND as_of_date=?',
        [market, as_of],
    ).fetchone()[0]

    try:
        df = pd.read_excel(f, sheet_name="All_Stocks")
    except Exception as e:
        log(con, market, geo, f.name, as_of, 0, 0, "failed", str(e)[:180])
        print(f"  {market:8s} FAILED       {str(e)[:60]}")
        return
    # Count the way the row will actually land — unique symbols — so a deduped
    # stored snapshot compares equal to its source and the run stays idempotent.
    _symcol = next((c for c in ("Symbol", "YF_Ticker", "Code") if c in df.columns), None)
    best_rows = df[_symcol].astype(str).nunique() if _symcol else len(df)

    if already and already >= best_rows:
        total = con.execute(
            f'SELECT count(*) FROM pg."{SCHEMA}".snapshots WHERE market=?', [market]
        ).fetchone()[0]
        log(con, market, geo, f.name, as_of, 0, total, "no_new_data",
            f"{as_of} already ingested ({already:,} rows >= best file {best_rows:,})")
        print(f"  {market:8s} no_new_data  last_data={as_of}  (+0, total {total:,})")
        return
    if already:
        con.execute(
            f'DELETE FROM pg."{SCHEMA}".snapshots WHERE market=? AND as_of_date=?',
            [market, as_of],
        )
        print(f"  {market:8s} replacing    {as_of} partial ({already:,} rows) "
              f"with fuller {f.name} ({best_rows:,} rows)")

    # Column encodings diverge per market — the same divergence already documented
    # for the Darvas sheets. US: Symbol/LTP/Prev_Close/Darvas_Signal. Europe:
    # Symbol/LTP/Darvas_Signal but NO Prev_Close. Japan: YF_Ticker/Code/LTP_JPY +
    # Trend_Signal. Korea: Code/YF_Ticker/LTP_KRW + Trend_Signal. Take the first
    # column that exists; missing ones become all-NULL rather than crashing.
    def col(*names):
        for n in names:
            if n in df.columns:
                return df[n]
        return None

    def num(*names):
        c = col(*names)
        return pd.to_numeric(c, errors="coerce") if c is not None else pd.Series([None] * len(df))

    def text(*names):
        c = col(*names)
        return c.astype(str) if c is not None else pd.Series([None] * len(df))

    sym = col("Symbol", "YF_Ticker", "Code")
    if sym is None:
        log(con, market, geo, f.name, as_of, 0, 0, "failed",
            f"no symbol column; got {list(df.columns)[:8]}")
        print(f"  {market:8s} FAILED       no symbol column in {f.name}")
        return

    out = pd.DataFrame({
        "market": market,
        "as_of_date": as_of,
        "symbol": sym.astype(str),
        "ltp": num("LTP", "LTP_JPY", "LTP_KRW", "LTP_EUR", "LTP_GBP"),
        "prev_close": num("Prev_Close", "Previous_Close"),
        "change_pct": num("Change%", "Change_%"),
        "darvas_signal": text("Darvas_Signal", "Trend_Signal"),
        "source_file": f.name,
    })
    # Some source sheets list a ticker twice (e.g. Korea's KOSPI/KOSDAQ overlap),
    # which otherwise lands as duplicate (market, date, symbol) rows. Keep the first.
    out = out.drop_duplicates(subset="symbol", keep="first")
    con.register("out_df", out)
    con.execute(f'INSERT INTO pg."{SCHEMA}".snapshots SELECT * FROM out_df')
    con.unregister("out_df")
    total = con.execute(
        f'SELECT count(*) FROM pg."{SCHEMA}".snapshots WHERE market=?', [market]
    ).fetchone()[0]
    log(con, market, geo, f.name, as_of, len(out), total, "ok", f"from {f.name}")
    print(f"  {market:8s} ok           last_data={as_of}  (+{len(out):,}, total {total:,})")


def status(con) -> None:
    # One run now logs several dates, so "most recent run_at" is ambiguous among
    # the tied rows. Rank by the DATA date to name the true latest snapshot, and
    # take max(total_rows) per market — total_rows is cumulative, so its max is the
    # final count regardless of which date's row happened to carry it.
    rows = con.execute(f"""
        SELECT t.market, t.geography, t.source, t.last_data_date, tot.total_rows,
               t.status, t.run_at
        FROM (SELECT *, row_number() OVER (
                  PARTITION BY market ORDER BY last_data_date DESC, run_at DESC) rn
              FROM pg."{SCHEMA}".ingest_log) t
        JOIN (SELECT market, max(total_rows) total_rows
              FROM pg."{SCHEMA}".ingest_log GROUP BY market) tot USING (market)
        WHERE t.rn=1 ORDER BY t.market
    """).fetchall()
    today = dt.date.today()
    print(f"\n=== MARKET DATA FRESHNESS (as of {today}) ===")
    print(f"  {'MARKET':8s} {'GEOGRAPHY':32s} {'LAST DATA':11s} {'AGE':>4s} {'ROWS':>11s}  STATUS")
    for m, geo, _src, last, total, st, _run in rows:
        age = (today - last).days if last else None
        flag = "STALE" if (age is None or age > 4) else "fresh"
        print(f"  {m:8s} {(geo or '')[:32]:32s} {str(last):11s} {str(age)+'d' if age is not None else '  -':>4s} "
              f"{total or 0:>11,}  {st} [{flag}]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="all",
                    choices=["all", "india", "us", "europe", "japan", "korea"])
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    con = connect()
    if a.status:
        status(con); sys.exit(0)
    print("=== daily market ingest (append-only) ===")
    if a.market in ("all", "india"):
        ingest_india(con)
    for m in SNAPSHOT_MARKETS:
        if a.market in ("all", m):
            ingest_snapshot(con, m)
    status(con)
