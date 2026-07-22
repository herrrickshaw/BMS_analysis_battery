#!/usr/bin/env python3
"""
Consolidate the India bhavcopy cache into DuckDB, and optionally mirror to Postgres.

WHY: `~/Downloads/data/bhavcopy_cache` holds the same data twice — 538 raw day-CSVs
(486 MB) AND the parquets built from them (182 MB). Worse, every file there matches
an LFS rule in .gitattributes (`*.parquet`, `**/data/**/*.csv`) while being
regenerated on each run, so a single `git add -A` would push ~120 MB of churn into
LFS *permanently* (parquet is binary — no delta compression, a new blob every run).

DESIGN — "only new data moves" (for append-only sources):
  * DuckDB is the local analytical store. Gitignored: it is a full-file rewrite,
    which is the worst possible shape for LFS.
  * Postgres is the durable store. Append-only sources (nse_raw/bse_raw, and the
    static nse_deep_ohlcv) load only rows newer than the mirror's max date.
  * REGENERATED sources (see the set below) are instead re-created from source:
    bhavcopy_history.py rewrites them daily and may drop/replace historical rows,
    which appends can never reconcile (caused a permanent --verify FAIL by
    2026-07-22: cleaned_ohlcv carried a +17,571-row surplus of cleaned-away rows).

Verified before use (2026-07-15): nse.parquet/bse.parquet reproduce the raw CSVs
losslessly — 34/34 cols and 269/269 dates each — so the day-CSVs are redundant.

Usage:
    python3 scripts/bhavcopy_to_db.py                      # (re)build ~/data/bhavcopy.duckdb
    python3 scripts/bhavcopy_to_db.py --verify             # row/col parity vs source parquets
    python3 scripts/bhavcopy_to_db.py --to-postgres DSN    # mirror/UPSERT into Postgres
    python3 scripts/bhavcopy_to_db.py --incremental        # only load dates newer than the DB max
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb

HOME = Path("/Users/umashankar")
# The pipeline (and its cache) migrated out of ~/Downloads on 2026-07-16; the
# launchd plist exports BHAV_CACHE pointing at the live location — honor it.
CACHE = Path(os.environ.get("BHAV_CACHE",
                            str(HOME / "market-pipeline" / "data" / "bhavcopy_cache")))
DB = HOME / "data" / "bhavcopy.duckdb"

# table -> (source parquet, date column, select body)
TABLES = {
    "bhavcopy_ohlcv": (
        "assembled_long.parquet", "trade_date",
        """SELECT CAST(Date AS DATE) trade_date, CAST(Symbol AS VARCHAR) symbol,
                  CAST(_exch AS VARCHAR) exch, CAST(Open AS DOUBLE) "open",
                  CAST(High AS DOUBLE) "high", CAST(Low AS DOUBLE) "low",
                  CAST(Close AS DOUBLE) "close", CAST(Volume AS BIGINT) "volume"
           FROM read_parquet('{src}')""",
    ),
    "cleaned_ohlcv": (
        "cleaned_long.parquet", "trade_date",
        """SELECT CAST(Date AS DATE) trade_date, CAST(Symbol AS VARCHAR) symbol,
                  CAST(Open AS DOUBLE) "open", CAST(High AS DOUBLE) "high",
                  CAST(Low AS DOUBLE) "low", CAST(Close AS DOUBLE) "close",
                  CAST(Volume AS BIGINT) "volume"
           FROM read_parquet('{src}')""",
    ),
    "nse_deep_ohlcv": (
        "nse_deep.parquet", "trade_date",
        """SELECT CAST(Date AS DATE) trade_date, CAST(Symbol AS VARCHAR) symbol,
                  CAST(Open AS DOUBLE) "open", CAST(High AS DOUBLE) "high",
                  CAST(Low AS DOUBLE) "low", CAST(Close AS DOUBLE) "close",
                  CAST(Volume AS BIGINT) "volume"
           FROM read_parquet('{src}')""",
    ),
    # raw 34-col bhavcopy — the lossless archive that makes the day-CSVs redundant
    "nse_raw": ("nse.parquet", "TradDt", "SELECT * FROM read_parquet('{src}')"),
    "bse_raw": ("bse.parquet", "TradDt", "SELECT * FROM read_parquet('{src}')"),
}

# Sorting by (symbol, date) lets DuckDB's run-length/delta encoders do real work.
SORTED = {"bhavcopy_ohlcv", "cleaned_ohlcv", "nse_deep_ohlcv"}

# Sources that bhavcopy_history.py REWRITES on every run, where historical rows
# can be dropped (clean_ohlcv filters) or replaced/backfilled (assembled dedup
# keep="last"). An append-only `WHERE date > max` load can never reconcile those,
# so --incremental drifted +17,571 rows on cleaned_ohlcv by 2026-07-22 and
# --verify FAILed permanently. These tables are re-created from source instead.
#   * nse_raw/bse_raw stay append-only: bhavcopy_raw_archive.py only ever
#     concatenates day-CSVs newer than the parquet's max TradDt.
#   * nse_deep_ohlcv stays append-only: static archive, no live writer.
REGENERATED = {"bhavcopy_ohlcv", "cleaned_ohlcv"}


def build(db_path: Path, incremental: bool) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    for tbl, (src, datecol, body) in TABLES.items():
        p = CACHE / src
        if not p.exists():
            print(f"  ! {src} missing — skipping {tbl}")
            continue
        sel = body.format(src=p)
        if tbl in SORTED:
            sel += " ORDER BY symbol, trade_date"
        exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name=?", [tbl]
        ).fetchone()[0]
        if incremental and exists and tbl not in REGENERATED:
            mx = con.execute(f'SELECT max("{datecol}") FROM "{tbl}"').fetchone()[0]
            n0 = con.execute(f'SELECT count(*) FROM "{tbl}"').fetchone()[0]
            con.execute(
                f'INSERT INTO "{tbl}" SELECT * FROM ({sel}) WHERE "{datecol}" > ?', [mx]
            )
            n1 = con.execute(f'SELECT count(*) FROM "{tbl}"').fetchone()[0]
            print(f"  {tbl:16s} +{n1-n0:>7,} new rows (was {n0:,}, max {datecol} {mx})")
        else:
            con.execute(f'CREATE OR REPLACE TABLE "{tbl}" AS {sel}')
            n = con.execute(f'SELECT count(*) FROM "{tbl}"').fetchone()[0]
            note = " (replaced: regenerated source)" if incremental and exists else ""
            print(f"  {tbl:16s} {n:>9,} rows{note}")
    con.close()


def verify(db_path: Path) -> int:
    """Prove the DB reproduces every source parquet, row-for-row and col-for-col."""
    con = duckdb.connect(str(db_path), read_only=True)
    bad = 0
    print(f"\n=== VERIFY {db_path.name} vs source parquets ===")
    for tbl, (src, _dc, _b) in TABLES.items():
        p = CACHE / src
        if not p.exists():
            continue
        want = con.execute(f"SELECT count(*) FROM read_parquet('{p}')").fetchone()[0]
        got = con.execute(f'SELECT count(*) FROM "{tbl}"').fetchone()[0]
        wcols = len(con.execute(f"DESCRIBE SELECT * FROM read_parquet('{p}')").fetchall())
        gcols = len(con.execute(f'DESCRIBE "{tbl}"').fetchall())
        ok = want == got
        # raw tables must also keep every column; OHLCV views are a deliberate subset
        colnote = f"cols {wcols}->{gcols}"
        if tbl.endswith("_raw") and wcols != gcols:
            ok = False
        print(f"  {'OK ' if ok else 'FAIL'} {tbl:16s} rows {want:>9,} -> {got:>9,}  {colnote}")
        bad += 0 if ok else 1
    con.close()
    print("  all tables reproduce their source" if not bad else f"  {bad} MISMATCH(ES)")
    return bad


def to_postgres(db_path: Path, dsn: str, schema: str = "bhavcopy") -> None:
    """Mirror into Postgres: append new dates (append-only sources) or rebuild
    on row-count divergence (REGENERATED sources).

    Targets a DEDICATED schema (default `bhavcopy`), never `public`. The
    market_data DB already carries a populated, normalized schema from the
    event-driven platform (public.ohlcv_history ~825k rows keyed by stock_id,
    public.stocks ~19k). Bhavcopy is denormalized by symbol and does NOT fit
    that model, so it is kept side-by-side rather than merged — merging would
    require a symbol->stock_id mapping and risks corrupting live data.
    """
    # NB: a read_only DuckDB connection forces ATTACHed databases read-only too,
    # so we must open read-write here even though we only READ the local tables.
    con = duckdb.connect(str(db_path))
    con.execute("INSTALL postgres"); con.execute("LOAD postgres")
    con.execute(f"ATTACH '{dsn}' AS pg (TYPE postgres)")
    con.execute(f'CREATE SCHEMA IF NOT EXISTS pg."{schema}"')
    for tbl in TABLES:
        exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name=?", [tbl]
        ).fetchone()[0]
        if not exists:
            continue
        tgt = f'pg."{schema}"."{tbl}"'
        con.execute(f'CREATE TABLE IF NOT EXISTS {tgt} AS SELECT * FROM "{tbl}" LIMIT 0')
        before = con.execute(f"SELECT count(*) FROM {tgt}").fetchone()[0]
        local_n = con.execute(f'SELECT count(*) FROM "{tbl}"').fetchone()[0]
        if before == 0:
            con.execute(f'INSERT INTO {tgt} SELECT * FROM "{tbl}"')
        elif tbl in REGENERATED:
            # regenerated sources drop/replace historical rows — an append can
            # never reconcile that, so rebuild whenever the mirror disagrees.
            # DELETE+INSERT, not DROP: market_daily.ticker_freshness (a view
            # built by market_ingest.py) depends on cleaned_ohlcv, and DROP
            # would require CASCADE-ing it away.
            if before != local_n:
                con.execute(f"DELETE FROM {tgt}")
                con.execute(f'INSERT INTO {tgt} SELECT * FROM "{tbl}"')
        else:
            # append only rows newer than what Postgres already has
            dc = TABLES[tbl][1]
            mx = con.execute(f'SELECT max("{dc}") FROM {tgt}').fetchone()[0]
            con.execute(
                f'INSERT INTO {tgt} SELECT * FROM "{tbl}" WHERE "{dc}" > ?', [mx]
            )
        after = con.execute(f"SELECT count(*) FROM {tgt}").fetchone()[0]
        note = " (rebuilt)" if tbl in REGENERATED and before not in (0, after) else ""
        print(f"  pg.{schema}.{tbl:16s} {before:>9,} -> {after:>9,} rows (+{after-before:,}){note}")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument("--to-postgres", metavar="DSN")
    a = ap.parse_args()
    dbp = Path(a.db)
    if a.verify:
        sys.exit(verify(dbp))
    if a.to_postgres:
        to_postgres(dbp, a.to_postgres)
        sys.exit(0)
    print(f"building {dbp} …")
    build(dbp, a.incremental)
    sys.exit(verify(dbp))
