#!/usr/bin/env python3
"""
Convert tracked data/*.csv files into DuckDB tables (one table per file, schema
preserved as-is), then optionally mirror those tables into a Postgres database
via DuckDB's postgres extension.

This is the standard path for any new small/medium reference CSV added to
data/: load it once with this script instead of leaving it as a loose file.

Usage:
    python3 scripts/csv_to_db.py                    # (re)build data/market_data.duckdb from data/*.csv
    python3 scripts/csv_to_db.py --verify            # compare DuckDB table row/col counts against source CSVs
    python3 scripts/csv_to_db.py --to-postgres DSN   # also copy every table into a Postgres database
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
DUCKDB_PATH = DATA / 'market_data.duckdb'

# CSVs intentionally left out of the DB migration: these are refreshed daily
# from external sources (NSE/NASDAQ/JPX/FinanceDataReader/Wikipedia/akshare)
# by run_app.sh and are gitignored — they're a runtime cache, not tracked data.
EXCLUDE_NAMES = {
    'nse_equity_list.csv', 'us_list.csv', 'japan_list.csv', 'korea_list.csv',
    'china_list.csv', 'hk_list.csv', 'canada_list.csv', 'sp500_list.csv',
    'europe_list.csv',
}


def _table_name(csv_path: Path) -> str:
    return csv_path.stem.replace('-', '_')


def discover_csvs() -> list[Path]:
    return sorted(
        p for p in DATA.rglob('*.csv')
        if p.name not in EXCLUDE_NAMES
    )


def build(con: duckdb.DuckDBPyConnection, csvs: list[Path]) -> None:
    for csv_path in csvs:
        table = _table_name(csv_path)
        rel = csv_path.relative_to(DATA)
        print(f"  {rel} -> table '{table}'")
        con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(
            f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto(?, header=true, all_varchar=false)",
            [str(csv_path)],
        )


def verify(con: duckdb.DuckDBPyConnection, csvs: list[Path]) -> bool:
    import csv as csv_mod

    ok = True
    for csv_path in csvs:
        table = _table_name(csv_path)
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv_mod.reader(f)
            header = next(reader)
            csv_rows = sum(1 for _ in reader)

        db_row = con.execute(f"SELECT count(*) FROM {table}").fetchone()
        db_rows = db_row[0] if db_row else -1
        db_cols = [c[0] for c in con.execute(f"DESCRIBE {table}").fetchall()]

        row_match = csv_rows == db_rows
        col_match = header == db_cols
        status = 'OK' if row_match and col_match else 'MISMATCH'
        if status == 'MISMATCH':
            ok = False
        print(f"  [{status}] {table}: csv_rows={csv_rows} db_rows={db_rows} "
              f"csv_cols={header} db_cols={db_cols}")
    return ok


def to_postgres(con: duckdb.DuckDBPyConnection, csvs: list[Path], dsn: str) -> None:
    con.execute("INSTALL postgres")
    con.execute("LOAD postgres")
    con.execute(f"ATTACH '{dsn}' AS pg (TYPE POSTGRES)")
    for csv_path in csvs:
        table = _table_name(csv_path)
        print(f"  duckdb.{table} -> postgres.{table}")
        con.execute(f"DROP TABLE IF EXISTS pg.{table}")
        con.execute(f"CREATE TABLE pg.{table} AS SELECT * FROM {table}")
    con.execute("DETACH pg")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify', action='store_true', help='verify DuckDB tables match source CSVs, build nothing')
    ap.add_argument('--to-postgres', metavar='DSN', help="Postgres DSN, e.g. 'dbname=repo_csv_archive'")
    args = ap.parse_args()

    csvs = discover_csvs()
    if not csvs:
        print("No CSVs found under data/ (outside the excluded runtime-cache list).")
        return 1

    con = duckdb.connect(str(DUCKDB_PATH))

    if args.verify:
        print(f"Verifying {len(csvs)} tables in {DUCKDB_PATH} against source CSVs:")
        ok = verify(con, csvs)
        return 0 if ok else 1

    print(f"Building {DUCKDB_PATH} from {len(csvs)} CSVs under {DATA}:")
    build(con, csvs)

    print("\nVerifying row/column parity:")
    ok = verify(con, csvs)
    if not ok:
        print("Parity check FAILED — not safe to delete source CSVs.")
        return 1

    if args.to_postgres:
        print(f"\nMirroring tables into Postgres ({args.to_postgres}):")
        to_postgres(con, csvs, args.to_postgres)

    print("\nDone.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
