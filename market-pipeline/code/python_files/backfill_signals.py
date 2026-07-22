#!/usr/bin/env python3
"""Backfill the signal ledger from rescued historical scan snapshots.

The 2026-07-22 LFS rescue recovered 25 dated full-scan workbooks
(2026-06-12 .. 06-26, five markets) that predate the signal ledger.
Their signals' +5d/+21d horizons have already elapsed — parsing them
multiplies the calibration dataset without waiting for new signals to age.

Writes to cache_seed/signal_ledger_backfill.parquet — a SEPARATE file from
the live ledger (which other automation appends to), so there is no
read-modify-write race. score_signals.py reads both.

Source of truth for the snapshots: dropbox:market-data-backup/history/
lfs-rescued-2026-07-22/ (local staging dir used when present).
"""
import glob
import os
import re
import sys

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "cache_seed", "signal_ledger_backfill.parquet")
STAGING = ("/private/tmp/claude-501/-Users-umashankar/"
           "f1dc3998-43b1-4d72-9d5a-7f0d73f31778/scratchpad/lfs-history")

MARKET_DIRS = {
    "indian_full_scan": "IN", "us_full_scan": "US", "japan_scan": "JP",
    "korea_scan": "KR", "european_scan": "EU",
}


def norm_symbol(sym, suffix, market):
    sym = str(sym).strip()
    sfx = "" if pd.isna(suffix) else str(suffix).strip()
    if market == "EU":
        return sym + sfx          # warehouse EU symbols are suffixed
    return sym                    # IN/US bare; JP/KR bare (scorer adds .T/.KS)


def parse_one(path, market):
    m = re.search(r"_(\d{8})_(\d{4})\.xlsx$", path)
    if not m:
        return None
    sig_date = pd.to_datetime(m.group(1), format="%Y%m%d")
    try:
        xl = pd.ExcelFile(path)
        sheet = ("Darvas_Signals" if "Darvas_Signals" in xl.sheet_names
                 else xl.sheet_names[0])
        df = xl.parse(sheet)
    except Exception as e:
        print(f"  SKIP {os.path.basename(path)}: {e}")
        return None
    need = {"Symbol", "Darvas_Signal", "LTP"}
    if not need.issubset(df.columns):
        print(f"  SKIP {os.path.basename(path)}: columns {list(df.columns)[:5]}")
        return None
    df = df.dropna(subset=["Symbol", "Darvas_Signal"])
    df = df[df["Darvas_Signal"].astype(str).str.contains("BUY|SELL", na=False)]
    out = pd.DataFrame({
        "symbol": [norm_symbol(s, x, market) for s, x in
                   zip(df["Symbol"], df.get("Suffix", pd.Series(index=df.index)))],
        "market": market,
        "filter": "darvas",
        "detail": df["Darvas_Signal"].astype(str).values,
        "score": pd.to_numeric(df.get("Position_in_Box%"), errors="coerce").values,
        "price_at_signal": pd.to_numeric(df["LTP"], errors="coerce").values,
        "source": "rescued:" + os.path.basename(path).split("__")[-1],
        "signal_date": sig_date,
        "provenance": "rescued-snapshot",
    })
    return out[out["price_at_signal"].notna() & (out["price_at_signal"] > 0)]


def main():
    root = STAGING if os.path.isdir(STAGING) else None
    if root is None:
        sys.exit("staging dir missing — rclone copy the Dropbox history tree "
                 "to a local dir and point STAGING at it")
    frames = []
    for key, market in MARKET_DIRS.items():
        for path in sorted(glob.glob(f"{root}/*{key}*/*.xlsx")):
            df = parse_one(path, market)
            if df is not None and len(df):
                frames.append(df)
                print(f"{os.path.basename(path)}: {len(df)} signals [{market}]")
    if not frames:
        sys.exit("no signals parsed")
    all_sig = pd.concat(frames, ignore_index=True)
    # dedupe: same symbol+market+direction+date (multiple intraday snapshots)
    all_sig = (all_sig.sort_values("source")
               .drop_duplicates(["symbol", "market", "detail", "signal_date"]))
    all_sig.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT}: {len(all_sig):,} backfilled signals "
          f"({all_sig.signal_date.min():%Y-%m-%d} → "
          f"{all_sig.signal_date.max():%Y-%m-%d})")
    print(all_sig.groupby(["market", "detail"]).size().to_string())


if __name__ == "__main__":
    main()
