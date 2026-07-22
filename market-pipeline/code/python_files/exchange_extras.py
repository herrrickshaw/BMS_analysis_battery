#!/usr/bin/env python3
"""
exchange_extras.py — the NSE/BSE bulk files the pipeline never collected.

Evaluated 2026-07-22 by probing the exchanges' public endpoints directly: all of
these are cookie-free bulk downloads (the NSE *website* APIs need a cookie dance,
but archives.nseindia.com and these two JSON endpoints answered plain curl).

WHAT EACH FILE FILLS
--------------------
  index_closes     ind_close_all_DDMMYYYY.csv — 162 indices/day with OHLC AND
                   P/E, P/B, dividend yield.
                   -> Fixes the BENCHMARK gap: NIFTYBEES (an ETF) was filtered
                      out of the equity panel by the ISIN rule, so signal
                      tracking fell back to a panel-median "benchmark". This is
                      the actual Nifty 50 close. Index P/E history is also a
                      regime series the pipeline has never had.
  delivery         sec_bhavdata_full_DDMMYYYY.csv — per-stock DELIV_QTY and
                   DELIV_PER alongside OHLCV.
                   -> A conviction/quality signal never collected: high delivery
                      % = positions taken home, not intraday churn.
  bulk_deals /     bulk.csv, block.csv — FULL history in one file each, with
  block_deals      client names.
                   -> Smart-money prints; never collected.
  corp_actions     NSE corporate-actions JSON — ex-dates for dividends, splits,
                   bonuses.
                   -> The split-adjustment gap: the deep panels carry RAW closes,
                      and splits faked a +12.2% illiquid premium in one measured
                      backtest. This is the data needed to adjust, or at least to
                      FLAG affected symbols.
  fo_oi            fao_participant_oi_DDMMYYYY.csv — FII/DII/pro/client OI.
                   -> Futures positioning by participant type; put_call_parity
                      context.
  bse_results_cal  BSE Corpforthresults JSON — upcoming board-meeting dates.
                   -> Earnings calendar without scraping.

DESIGN
------
* RAW FILES ARE KEPT verbatim under MARKET_CACHE/exchange_extras/<kind>/ —
  parsing bugs must never destroy source data — plus one tidy parquet per kind
  for consumers.
* IDEMPOTENT per (kind, date): a file already on disk is not re-fetched, so the
  daily run costs six small downloads.
* FAIL-SOFT per kind: index closes arriving must not depend on bulk deals
  parsing. Each kind reports ok/skip/fail independently.
* Weekends/holidays 404 -> recorded as a skip, not an error. NSE publishes
  nothing on non-trading days; that is a fact, not a failure.

    exchange_extras.py                # today's files (yesterday's trade date)
    exchange_extras.py --date 21072026
    exchange_extras.py --backfill 30  # last 30 calendar days, idempotent
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

try:
    import data_registry as _R
    ROOT = _R.MARKET_CACHE / "exchange_extras"
except Exception:
    ROOT = Path(__file__).resolve().parent / "cache_seed" / "exchange_extras"

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
TIMEOUT = 30
PAUSE = 1.0          # between downloads — six files, no reason to hammer


def _get(url: str, referer: str = None) -> requests.Response:
    h = dict(UA)
    if referer:
        h["Referer"] = referer
    return requests.get(url, headers=h, timeout=TIMEOUT)


# ── per-kind fetchers ─────────────────────────────────────────────────────────
def fetch_index_closes(d: _dt.date) -> pd.DataFrame:
    u = f"https://archives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv"
    r = _get(u)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = [c.strip() for c in df.columns]
    return df


def fetch_delivery(d: _dt.date) -> pd.DataFrame:
    u = f"https://archives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
    r = _get(u)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = [c.strip() for c in df.columns]
    # DELIV_PER arrives as '  45.67' or ' -' for series with no delivery concept
    df["DELIV_PER"] = pd.to_numeric(df["DELIV_PER"], errors="coerce")
    return df


def fetch_bulk_deals(_: _dt.date) -> pd.DataFrame:
    r = _get("https://archives.nseindia.com/content/equities/bulk.csv")
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def fetch_block_deals(_: _dt.date) -> pd.DataFrame:
    r = _get("https://archives.nseindia.com/content/equities/block.csv")
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def fetch_corp_actions(_: _dt.date) -> pd.DataFrame:
    # Answered plain curl with full JSON on 2026-07-22 — no cookie handshake.
    # If NSE later fences it, this fails loudly (raise_for_status) rather than
    # silently storing a block page as data.
    r = _get("https://www.nseindia.com/api/corporates-corporateActions?index=equities",
             referer="https://www.nseindia.com/")
    r.raise_for_status()
    d = pd.DataFrame(r.json())
    if d.empty:
        raise ValueError("CA endpoint returned an empty list")
    return d


def backfill_corp_actions(quarters: int) -> None:
    """Historical corporate actions, walked in exact calendar-quarter windows.

    THE gap this closes: the price warehouse holds RAW closes, and splits/bonuses
    fake returns through every event (+12.2% measured on one backtest). The CA
    API serves history by date window (probed: Q1-2020 alone returned 466
    actions) — but, like the results API, behaves oddly on ragged windows, so
    exact quarters only. Ex-dates + subjects ("Face Value Split ... From Rs 10
    To Re 1") are what an adjuster needs.
    """
    out = ROOT / "corp_actions_history.parquet"
    old = pd.read_parquet(out) if out.exists() else pd.DataFrame()
    frames = [old] if not old.empty else []
    today = _dt.date.today()
    qsm = 3 * ((today.month - 1) // 3) + 1
    start, end = _dt.date(today.year, qsm, 1), today
    for _ in range(quarters):
        u = ("https://www.nseindia.com/api/corporates-corporateActions?index=equities"
             f"&from_date={start:%d-%m-%Y}&to_date={end:%d-%m-%Y}")
        try:
            r = _get(u, referer="https://www.nseindia.com/")
            r.raise_for_status()
            d = pd.DataFrame(r.json())
            print(f"  CA window {start}..{end}: {len(d)} actions")
            if not d.empty:
                frames.append(d)
        except Exception as e:
            print(f"  CA window {start}..{end}: FAILED {type(e).__name__}")
        end = start - _dt.timedelta(days=1)
        start = _dt.date(end.year, 3 * ((end.month - 1) // 3) + 1, 1)
        time.sleep(1.5)
    if not frames:
        return
    allf = pd.concat(frames, ignore_index=True).drop_duplicates()
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    allf.to_parquet(tmp, index=False); tmp.replace(out)
    print(f"  CA history: {len(allf)} actions -> {out.name}")


def fetch_fo_oi(d: _dt.date) -> pd.DataFrame:
    u = f"https://archives.nseindia.com/content/nsccl/fao_participant_oi_{d:%d%m%Y}.csv"
    r = _get(u)
    r.raise_for_status()
    # first line is a title row, real header on line 2
    return pd.read_csv(io.StringIO(r.text), skiprows=1)


def fetch_bse_results_cal(_: _dt.date) -> pd.DataFrame:
    r = _get("https://api.bseindia.com/BseIndiaAPI/api/Corpforthresults/w"
             "?scripcode=&fromdate=&todate=", referer="https://www.bseindia.com/")
    r.raise_for_status()
    d = pd.DataFrame(r.json())
    if d.empty:
        raise ValueError("BSE results calendar empty")
    return d


KINDS = {
    # kind: (fetcher, dated?)  — dated files exist per trade day; undated ones
    # (bulk/block/CA/calendar) are full-history or forward-looking snapshots.
    "index_closes":    (fetch_index_closes, True),
    "delivery":        (fetch_delivery, True),
    "bulk_deals":      (fetch_bulk_deals, False),
    "block_deals":     (fetch_block_deals, False),
    "corp_actions":    (fetch_corp_actions, False),
    "fo_oi":           (fetch_fo_oi, True),
    "bse_results_cal": (fetch_bse_results_cal, False),
}


def collect(d: _dt.date, verbose: bool = True) -> dict:
    """Fetch every kind for trade-date d. Returns {kind: 'ok'|'skip'|'fail:..'}"""
    out = {}
    for kind, (fn, dated) in KINDS.items():
        kdir = ROOT / kind
        kdir.mkdir(parents=True, exist_ok=True)
        stamp = f"{d:%Y%m%d}" if dated else f"{_dt.date.today():%Y%m%d}"
        raw = kdir / f"{kind}_{stamp}.parquet"
        if raw.exists():
            out[kind] = "skip"          # idempotent
            continue
        try:
            df = fn(d)
            if df is None or df.empty:
                raise ValueError("empty frame")
            df.to_parquet(raw, index=False)
            out[kind] = "ok"
            if verbose:
                print(f"  ok    {kind:16} {len(df):>6} rows -> {raw.name}")
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            # A 404 on a dated file is a holiday/weekend, not a failure.
            out[kind] = "skip" if (dated and code == 404) else f"fail:HTTP {code}"
            if verbose:
                tag = "holiday/none" if out[kind] == "skip" else out[kind]
                print(f"  --    {kind:16} {tag}")
        except Exception as e:
            out[kind] = f"fail:{type(e).__name__}"
            if verbose:
                print(f"  FAIL  {kind:16} {type(e).__name__}: {str(e)[:60]}")
        time.sleep(PAUSE)
    return out


def consolidate(verbose: bool = True) -> None:
    """One tidy parquet per kind, concatenated + deduped, for consumers.

    Consumers read these, never the daily raws:
      index_closes.parquet  (Index Name, Date, Close, PE, PB, DivYield, ...)
      delivery.parquet      (SYMBOL, DATE1, DELIV_PER, ...)
    """
    for kind in KINDS:
        kdir = ROOT / kind
        files = sorted(kdir.glob(f"{kind}_*.parquet"))
        if not files:
            continue
        frames = []
        for f in files:
            try:
                frames.append(pd.read_parquet(f))
            except Exception:
                continue
        if not frames:
            continue
        allf = pd.concat(frames, ignore_index=True).drop_duplicates()
        outp = ROOT / f"{kind}.parquet"
        tmp = outp.with_suffix(".parquet.tmp")
        allf.to_parquet(tmp, index=False)
        tmp.replace(outp)
        if verbose:
            print(f"  consolidated {kind:16} {len(allf):>7} rows ({len(files)} days)")


def main() -> int:
    ap = argparse.ArgumentParser(description="NSE/BSE bulk extras collector")
    ap.add_argument("--date", help="trade date DDMMYYYY (default: yesterday)")
    ap.add_argument("--backfill", type=int, default=0, help="also fetch N prior days")
    ap.add_argument("--ca-quarters", type=int, default=0,
                    help="backfill corporate-actions history N quarters")
    a = ap.parse_args()

    if a.date:
        d0 = _dt.datetime.strptime(a.date, "%d%m%Y").date()
    else:
        d0 = _dt.date.today() - _dt.timedelta(days=1)

    if a.ca_quarters:
        backfill_corp_actions(a.ca_quarters)
        return 0

    # Keep the CA HISTORY fresh, not just the forward snapshot: refresh the
    # current quarter every daily run (idempotent — dedup on all columns), so
    # new ex-dates flow into the adjuster without anyone remembering to backfill.
    try:
        backfill_corp_actions(1)
    except Exception as e:
        print(f"  CA current-quarter refresh failed: {type(e).__name__}")

    days = [d0 - _dt.timedelta(days=i) for i in range(a.backfill + 1)]
    summary = {"ok": 0, "skip": 0, "fail": 0}
    for d in days:
        if len(days) > 1:
            print(f"— {d}")
        res = collect(d)
        for v in res.values():
            summary["ok" if v == "ok" else "skip" if v == "skip" else "fail"] += 1

    consolidate()
    print(f"\n  ok {summary['ok']} · skip {summary['skip']} · fail {summary['fail']}")
    # Failures on UNDATED kinds are real (they exist every day); surface them.
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
