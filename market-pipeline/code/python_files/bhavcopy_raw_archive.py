#!/usr/bin/env python3
"""Rebuild the raw 34-column bhavcopy archives from the cached day-CSVs.

WHY THIS EXISTS: `nse.parquet` / `bse.parquet` are the lossless 34-col UDiFF
archives that feed `pg.bhavcopy.nse_raw` / `bse_raw` (via
~/scripts/bhavcopy_to_db.py). They were built once on 2026-07-15 by an ad-hoc
script that was never committed and was lost with the ~/Downloads tree — so
the archives (and the Postgres raw tables) froze at TradDt 2026-07-13 while
`bhavcopy_history.py` kept the day-CSVs in nse/ and bse/ current. This script
is the missing writer, recreated and wired into daily_pipeline.sh step [15].

Verified before recreating (2026-07-22): each parquet is a plain per-day
concat of its day-CSVs — row counts match CSV-for-CSV on sampled dates,
34/34 columns, no extra filtering (the EQ/STK equity filter is applied by
bhavcopy_history.py when it WRITES the day-CSVs, not here).

Schema is pinned (TradDt/BizDt as date32, prices double, ids int64, the
usually-empty UDiFF columns as string) so incremental appends can never
drift the file's arrow schema — a drifted schema would break the
`--incremental` date-comparison in bhavcopy_to_db.py downstream.

Usage:
    python3 bhavcopy_raw_archive.py              # append day-CSVs newer than each parquet's max TradDt
    python3 bhavcopy_raw_archive.py --rebuild    # full rebuild from all day-CSVs
Exit code 1 if any archive could not be brought current.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

try:
    import data_registry as _R
    CACHE = _R.BHAV_CACHE
except Exception:  # runnable standalone (e.g. from ~/scripts callers)
    CACHE = Path(os.environ.get(
        "BHAV_CACHE",
        str(Path.home() / "market-pipeline" / "data" / "bhavcopy_cache")))

# the 34 UDiFF bhavcopy columns, dtypes matching the 2026-07-15 archives exactly
_DATE_COLS = ["TradDt", "BizDt"]
_F64 = ["OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric",
        "PrvsClsgPric", "SttlmPric", "TtlTrfVal"]
_I64 = ["FinInstrmId", "TtlTradgVol", "TtlNbOfTxsExctd", "NewBrdLotQty"]
_STR = ["Sgmt", "Src", "FinInstrmTp", "ISIN", "TckrSymb", "SctySrs",
        "XpryDt", "FininstrmActlXpryDt", "StrkPric", "OptnTp", "FinInstrmNm",
        "UndrlygPric", "OpnIntrst", "ChngInOpnIntrst", "SsnId",
        "Rmks", "Rsvd1", "Rsvd2", "Rsvd3", "Rsvd4"]
_ORDER = ["TradDt", "BizDt", "Sgmt", "Src", "FinInstrmTp", "FinInstrmId",
          "ISIN", "TckrSymb", "SctySrs", "XpryDt", "FininstrmActlXpryDt",
          "StrkPric", "OptnTp", "FinInstrmNm", "OpnPric", "HghPric", "LwPric",
          "ClsPric", "LastPric", "PrvsClsgPric", "UndrlygPric", "SttlmPric",
          "OpnIntrst", "ChngInOpnIntrst", "TtlTradgVol", "TtlTrfVal",
          "TtlNbOfTxsExctd", "SsnId", "NewBrdLotQty", "Rmks",
          "Rsvd1", "Rsvd2", "Rsvd3", "Rsvd4"]
SCHEMA = pa.schema(
    [(c, pa.date32()) for c in _DATE_COLS]
    + [(c, pa.string()) for c in ["Sgmt", "Src", "FinInstrmTp"]]
    + [("FinInstrmId", pa.int64())]
    + [(c, pa.string()) for c in ["ISIN", "TckrSymb", "SctySrs", "XpryDt",
                                  "FininstrmActlXpryDt", "StrkPric", "OptnTp",
                                  "FinInstrmNm"]]
    + [(c, pa.float64()) for c in ["OpnPric", "HghPric", "LwPric", "ClsPric",
                                   "LastPric", "PrvsClsgPric"]]
    + [("UndrlygPric", pa.string()), ("SttlmPric", pa.float64())]
    + [(c, pa.string()) for c in ["OpnIntrst", "ChngInOpnIntrst"]]
    + [("TtlTradgVol", pa.int64()), ("TtlTrfVal", pa.float64()),
       ("TtlNbOfTxsExctd", pa.int64()), ("SsnId", pa.string()),
       ("NewBrdLotQty", pa.int64()), ("Rmks", pa.string()),
       ("Rsvd1", pa.string()), ("Rsvd2", pa.string()),
       ("Rsvd3", pa.string()), ("Rsvd4", pa.string())]
)
assert SCHEMA.names == _ORDER


def _day_table(csv_path: Path) -> pa.Table:
    """One day-CSV -> arrow table with the pinned schema."""
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in _ORDER if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path.name}: missing columns {missing}")
    df = df[_ORDER]
    for c in _DATE_COLS:
        df[c] = pd.to_datetime(df[c]).dt.date
    for c in _F64:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in _I64:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("int64")
    for c in _STR:
        # all-NaN columns come back float64 from read_csv; force string-or-null
        s = df[c]
        df[c] = s.where(s.notna(), None).map(
            lambda v: v if (v is None or isinstance(v, str)) else str(v))
    return pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)


def refresh(exch: str, rebuild: bool) -> bool:
    """Bring CACHE/<exch>.parquet current from CACHE/<exch>/ day-CSVs."""
    out = CACHE / f"{exch}.parquet"
    day_dir = CACHE / exch
    files = sorted(day_dir.glob("*.csv"))
    if not files:
        print(f"  ! {exch}: no day-CSVs in {day_dir} — nothing to do")
        return False

    have_max: Optional[_dt.date] = None
    base: Optional[pa.Table] = None
    if out.exists() and not rebuild:
        base = pq.read_table(out).cast(SCHEMA)
        col = base.column("TradDt")
        have_max = pa.compute.max(col).as_py() if base.num_rows else None

    todo = [f for f in files
            if have_max is None
            or _dt.datetime.strptime(f.stem, "%Y%m%d").date() > have_max]
    if not todo:
        print(f"  {exch}.parquet already current (max TradDt {have_max})")
        return True

    parts = ([base] if base is not None else []) + [_day_table(f) for f in todo]
    merged = pa.concat_tables(parts)
    tmp = out.with_suffix(".parquet.tmp")
    pq.write_table(merged, tmp, compression="snappy")
    tmp.replace(out)

    new_max = pa.compute.max(merged.column("TradDt")).as_py()
    print(f"  {exch}.parquet {'rebuilt' if rebuild or base is None else 'appended'}: "
          f"+{len(todo)} day(s) -> {merged.num_rows:,} rows, "
          f"max TradDt {have_max} -> {new_max}")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rebuild", action="store_true",
                    help="full rebuild from all day-CSVs (default: append new dates)")
    a = ap.parse_args()
    print(f"raw bhavcopy archive refresh ({CACHE}) …")
    ok = all([refresh("nse", a.rebuild), refresh("bse", a.rebuild)])
    sys.exit(0 if ok else 1)
