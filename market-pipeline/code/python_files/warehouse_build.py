#!/usr/bin/env python3
"""
warehouse_build.py — one canonical OHLCV warehouse: partitioned parquet + DuckDB.

WHAT THIS REPLACES, AND WHY
---------------------------
Two repos each carry monolithic per-market price panels, largely DUPLICATED:

    global-market-data/cache_seed/ltm/     CN 142MB, US 103MB, JP 73MB, KR 67MB
    global-stock-screener/cache_seed/ltm/  CN 184MB, JP 121MB, KR 87MB, IN 68MB

~900MB of LFS where ~450MB of canonical data exists — and the two copies of the
same market DIVERGE (the two-copies trap, again). Worse, the canonical copy
differs PER MARKET: global-market-data/IN is the real 10.5-year panel, while
global-market-data/US is the KNOWN-BROKEN interrupted alphabetical collection
(see reference_us_price_panel_broken) and the good US lives in the screener
repo. Every consumer had to know this folklore.

The monoliths also defeat LFS: warehouse_update rewrites the whole 68-184MB
file daily, and every push uploads a complete new LFS object — append-only data
re-uploaded in full, forever, server-side.

MEASURED before building (IN panel, 4.8M rows):
    zstd re-compression      68.9MB vs 68MB   -> no win, already compressed
    year-partitioned total   72.6MB (+7%)     -> small local cost
    current-year partition    8.3MB           -> the ONLY file a daily push
                                                re-uploads: ~10x less LFS growth

So: NOT re-compression. Deduplication + partitioning is the space fix.

LAYOUT
------
    <warehouse root>/ohlcv/<MARKET>/year=<YYYY>.parquet   zstd, one file/yr
    <warehouse root>/warehouse.duckdb                     VIEWS only (small)

Consumers can read either way:
    pd.read_parquet(root/"ohlcv"/"IN")                    # pyarrow reads the dir
    duckdb: SELECT * FROM ohlcv WHERE market='IN' AND ...

    warehouse_build.py            # build/refresh all markets from canonical sources
    warehouse_build.py --check    # verify counts vs sources, no writes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Canonical source per market — the folklore, written down ONCE.
# 🔴 US: global-market-data's copy is the interrupted alphabetical collection
#        (CME/CMI absent; most-covered symbols all B's) — NEVER canonical.
# 🔴 IN: global-market-data's copy is the deep 10.5y panel (to 2016);
#        the screener repo's is shallower.
GMD = Path("/Users/umashankar/repos/global-market-data/cache_seed/ltm")
GSS = Path("/Users/umashankar/repos/global-stock-screener/cache_seed/ltm")
CANONICAL = {
    "IN": GMD / "IN.parquet",       # deep 10.5y
    "US": GSS / "US.parquet",       # 9,278 symbols; the other US is broken
    "JP": GSS / "JP.parquet",
    "KR": GSS / "KR.parquet",
    "CN": GSS / "CN.parquet",
    "EU": GSS / "EU.parquet",
}

WAREHOUSE = Path("/Users/umashankar/repos/global-market-data/warehouse")
COLS = ["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]


def build_market(market: str, src: Path, check: bool) -> dict:
    if not src.exists():
        return {"market": market, "status": "source missing"}
    d = pd.read_parquet(src)
    d["Date"] = pd.to_datetime(d["Date"])
    d["Symbol"] = d["Symbol"].astype(str).str.upper()
    keep = [c for c in COLS if c in d.columns]
    d = d[keep]
    out_dir = WAREHOUSE / "ohlcv" / market
    years = sorted(d["Date"].dt.year.unique())

    if check:
        have = sum(len(pd.read_parquet(p)) for p in out_dir.glob("year=*.parquet")) \
            if out_dir.exists() else 0
        return {"market": market, "status": "ok" if have == len(d) else "MISMATCH",
                "source_rows": len(d), "warehouse_rows": have}

    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for y in years:
        g = d[d["Date"].dt.year == y]
        p = out_dir / f"year={y}.parquet"
        # Idempotent per partition: skip CLOSED years already written with the
        # same row count — only the current year legitimately changes, which is
        # exactly what keeps the daily LFS delta at one small file.
        if p.exists() and y < years[-1]:
            try:
                if len(pd.read_parquet(p, columns=["Symbol"])) == len(g):
                    continue
            except Exception:
                pass
        tmp = p.with_suffix(".parquet.tmp")
        g.to_parquet(tmp, compression="zstd", index=False)
        tmp.replace(p)
        written += 1
    return {"market": market, "status": "built", "rows": len(d),
            "years": f"{years[0]}-{years[-1]}", "partitions_written": written}


def build_duckdb() -> None:
    """A small .duckdb of VIEWS over the parquet — no data copied into it.

    Views keep the .duckdb file a few KB, so committing it costs nothing and a
    consumer gets SQL over every market with zero load step. duckdb is in
    /usr/bin/python3, not the venv (see project_market_data_warehouse).
    """
    import subprocess
    sql = ["CREATE OR REPLACE VIEW ohlcv AS SELECT market, Date, Symbol, Open, "
           "High, Low, Close, Volume FROM read_parquet("
           f"'{WAREHOUSE}/ohlcv/*/year=*.parquet', hive_partitioning=0, "
           "union_by_name=true, filename=1) "
           ", regexp_extract(filename, 'ohlcv/([A-Z]+)/', 1) AS market_check;"]
    # simpler + robust: one view per market, then a union
    stmts = []
    markets = sorted(p.name for p in (WAREHOUSE / "ohlcv").iterdir() if p.is_dir())
    for m in markets:
        stmts.append(
            f"CREATE OR REPLACE VIEW ohlcv_{m.lower()} AS "
            f"SELECT '{m}' AS market, * FROM read_parquet("
            f"'{WAREHOUSE}/ohlcv/{m}/year=*.parquet');")
    union = " UNION ALL ".join(f"SELECT * FROM ohlcv_{m.lower()}" for m in markets)
    stmts.append(f"CREATE OR REPLACE VIEW ohlcv AS {union};")
    script = "\n".join(stmts)
    db = WAREHOUSE / "warehouse.duckdb"
    r = subprocess.run(["/usr/bin/python3", "-c",
                        "import duckdb,sys; con=duckdb.connect(sys.argv[1]); "
                        "con.execute(sys.argv[2]); "
                        "print(con.execute('SELECT market, COUNT(*) FROM ohlcv "
                        "GROUP BY market ORDER BY market').fetchall()); con.close()",
                        str(db), script],
                       capture_output=True, text=True, timeout=600)
    if r.returncode == 0:
        print(f"  duckdb views: {r.stdout.strip()}")
        print(f"  -> {db} ({db.stat().st_size/1024:.0f} KB — views only)")
    else:
        print(f"  duckdb FAILED: {r.stderr[:200]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--market")
    a = ap.parse_args()
    targets = {a.market: CANONICAL[a.market]} if a.market else CANONICAL
    for m, src in targets.items():
        r = build_market(m, src, a.check)
        print(" ", r)
    if not a.check:
        build_duckdb()
    return 0


if __name__ == "__main__":
    sys.exit(main())
