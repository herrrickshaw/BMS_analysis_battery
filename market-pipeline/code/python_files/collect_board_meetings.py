#!/usr/bin/env python3
"""
collect_board_meetings.py — NSE board-meeting intimations for bonus/split
announcement dating (the caBroadcastDate field NSE never populates).

Why: corp_actions_history has ex-dates but its caBroadcastDate column is null
in every row (verified against the live API too, 2026-07-23). The earliest
public, timestamped signal of a bonus/split is the BOARD-MEETING INTIMATION
("meeting on <date> to consider ... bonus/split") — `bm_timestamp` on
api/corporate-board-meetings. That is the honest announcement anchor for the
"how much of the pre-ex run-up was tradeable" study.

Collects quarterly windows 2016 -> today, keeps rows whose purpose mentions
bonus / split / sub-division, writes
market_cache/exchange_extras/board_meetings_bonus_split.parquet (idempotent
re-runs: dedup on symbol+bm_date+purpose).
"""
from __future__ import annotations

import datetime as dt
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path("/Users/umashankar/market-pipeline/market_cache/exchange_extras/"
           "board_meetings_bonus_split.parquet")
API = ("https://www.nseindia.com/api/corporate-board-meetings"
       "?index=equities&from_date={f}&to_date={t}")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
PURPOSE = re.compile(r"bonus|split|sub-?division", re.I)


def windows(start=dt.date(2016, 1, 1)):
    end = dt.date.today()
    cur = start
    while cur < end:
        nxt = (pd.Timestamp(cur) + pd.offsets.QuarterEnd()).date()
        yield cur, min(nxt, end)
        cur = nxt + dt.timedelta(days=1)


def main() -> int:
    s = requests.Session()
    s.headers.update(UA)
    s.get("https://www.nseindia.com/companies-listing/corporate-filings-board-meetings",
          timeout=45)
    frames = []
    for f, t in windows():
        try:
            r = s.get(API.format(f=f.strftime("%d-%m-%Y"),
                                 t=t.strftime("%d-%m-%Y")), timeout=60)
            r.raise_for_status()
            d = pd.DataFrame(r.json())
        except Exception as e:
            print(f"  {f}..{t}: FAILED {type(e).__name__}: {str(e)[:60]}")
            time.sleep(4)
            continue
        if not d.empty and "bm_purpose" in d:
            hit = d[d["bm_purpose"].astype(str).str.contains(PURPOSE)]
            frames.append(hit)
            print(f"  {f}..{t}: {len(d)} meetings, {len(hit)} bonus/split")
        else:
            print(f"  {f}..{t}: 0 rows")
        time.sleep(2)
    new = pd.concat(frames, ignore_index=True)
    if OUT.exists():
        new = pd.concat([pd.read_parquet(OUT), new], ignore_index=True)
    new = new.drop_duplicates(subset=["bm_symbol", "bm_date", "bm_purpose"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".parquet.tmp")
    new.to_parquet(tmp, index=False)
    tmp.replace(OUT)
    print(f"wrote {OUT.name}: {len(new)} bonus/split intimations, "
          f"{new['bm_symbol'].nunique()} symbols")
    return 0


if __name__ == "__main__":
    sys.exit(main())
