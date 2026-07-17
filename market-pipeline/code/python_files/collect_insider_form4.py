#!/usr/bin/env python3
"""
collect_insider_form4.py -- v8: genuinely NEW data collection, per
explicit user request ("add ... insider Form 4 data").

Source: SEC's bulk quarterly "Insider Transactions Data Sets"
(sec.gov/data-research/sec-markets-data/insider-transactions-data-sets),
verified live (2026-07-17): {year}q{quarter}_form345.zip, one file per
quarter back to 2006q1, each containing NONDERIV_TRANS.tsv (individual
Form 3/4/5 transactions) and SUBMISSION.tsv (filing-level metadata
including the genuine point-in-time FILING_DATE and the issuer's
trading symbol) joined on ACCESSION_NUMBER.

SCOPE (stated up front): S&P 500 pool only (484 symbols, same as
collect_short_interest.py), quarters 2017q1-2025q4 to match this
account's factorial panel's test window. Full-universe, full-history
collection is a real follow-up, not attempted here -- SEC's bulk files
aren't filterable server-side, so every quarter's full ~7-14MB zip must
be downloaded and filtered locally regardless of scope, but S&P-500
filtering keeps the LOCAL processing (parsing 100k+ rows/quarter) and
resulting dataset size manageable.

TRANSACTION CODE FILTER: only TRANS_CODE 'P' (open-market purchase) and
'S' (open-market sale) are kept -- these are the two codes that reflect
genuine insider CONVICTION (spending/receiving real cash at a market
price they chose), unlike 'A' (grants/awards, routine compensation),
'M' (option exercise, often mechanical/pre-scheduled per a 10b5-1 plan),
'G' (gifts), or 'F' (tax withholding). Conflating these would dilute a
genuine signal with routine compensation noise.

POINT-IN-TIME: aggregated on SUBMISSION.tsv's FILING_DATE (when the
transaction became public, required within 2 business days of the
trade under Section 16(a)) -- NOT the transaction date, which an
observer at the time could not have known.
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd
import requests

SP500_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/sp500_constituents.csv"
OUT_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/insider_transactions_us.parquet"
BASE_URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip"
HEADERS = {"User-Agent": "market-pipeline research umashankartd1991@gmail.com"}
QUARTERS = [f"{y}q{q}" for y in range(2017, 2026) for q in range(1, 5)]
KEEP_CODES = {"P", "S"}


def fetch_quarter(q: str, sp500_syms: set) -> pd.DataFrame:
    url = BASE_URL.format(q=q)
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
    except requests.RequestException as e:
        print(f"  {q}: request failed ({e})")
        return pd.DataFrame()
    if r.status_code != 200:
        print(f"  {q}: HTTP {r.status_code} -- skipping (likely not yet published)")
        return pd.DataFrame()

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open("SUBMISSION.tsv") as f:
            sub = pd.read_csv(f, sep="\t", usecols=[
                "ACCESSION_NUMBER", "FILING_DATE", "ISSUERTRADINGSYMBOL"], dtype=str)
        sub = sub[sub["ISSUERTRADINGSYMBOL"].isin(sp500_syms)]
        if sub.empty:
            return pd.DataFrame()
        with z.open("NONDERIV_TRANS.tsv") as f:
            trans = pd.read_csv(f, sep="\t", usecols=[
                "ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE",
                "TRANS_SHARES", "TRANS_PRICEPERSHARE"], dtype=str)
        trans = trans[trans["TRANS_CODE"].isin(KEEP_CODES)]

    merged = trans.merge(sub, on="ACCESSION_NUMBER", how="inner")
    merged["quarter"] = q
    return merged


def main():
    sp500 = pd.read_csv(SP500_PATH)
    sp500_syms = set(sp500["Symbol"])
    print(f"Fetching SEC Form 4 insider transactions for {len(sp500_syms)} S&P 500 symbols, "
          f"{len(QUARTERS)} quarters ({QUARTERS[0]} to {QUARTERS[-1]})...")

    frames = []
    for i, q in enumerate(QUARTERS):
        df = fetch_quarter(q, sp500_syms)
        if not df.empty:
            frames.append(df)
            print(f"  {q}: {len(df):,} P/S transactions across {df['ISSUERTRADINGSYMBOL'].nunique()} S&P 500 symbols")
        else:
            print(f"  {q}: 0 matching rows")

    if not frames:
        print("No data fetched -- aborting.")
        return
    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={"ISSUERTRADINGSYMBOL": "symbol"})
    out["FILING_DATE"] = pd.to_datetime(out["FILING_DATE"], format="%d-%b-%Y", errors="coerce")
    out["TRANS_DATE"] = pd.to_datetime(out["TRANS_DATE"], format="%d-%b-%Y", errors="coerce")
    out["TRANS_SHARES"] = pd.to_numeric(out["TRANS_SHARES"], errors="coerce")
    out["TRANS_PRICEPERSHARE"] = pd.to_numeric(out["TRANS_PRICEPERSHARE"], errors="coerce")
    out = out.dropna(subset=["FILING_DATE", "TRANS_SHARES"])
    out = out.sort_values(["symbol", "FILING_DATE"]).reset_index(drop=True)

    print(f"\nTotal: {len(out):,} open-market P/S transactions, {out['symbol'].nunique()} symbols, "
          f"{out['FILING_DATE'].min().date()} to {out['FILING_DATE'].max().date()}")
    print(out["TRANS_CODE"].value_counts())
    out.to_parquet(OUT_PATH, index=False)
    print(f"Saved -> cache_seed/insider_transactions_us.parquet")


if __name__ == "__main__":
    main()
