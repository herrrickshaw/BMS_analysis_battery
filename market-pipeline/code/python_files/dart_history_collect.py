#!/usr/bin/env python3
"""
dart_history_collect.py — deepen Korea fundamentals history via DART (2015→2021),
so valuation_reversion / value_quality_ls can use a 10y window for KR instead of the
5y yfinance one (KR is where the strategy tested strongest — more history = more power).

Reuses dart_fundamentals.py (corp_map + cached fnlttSinglAcntAll). Pulls annual
net_income (ifrs-full_ProfitLoss) and equity (ifrs-full_Equity) per KR stock per year;
one DART call returns current + prior term, so 2015-2021 = ~3 calls/stock. Shares come
from the existing KR.parquet (proxy — ROE is exact; PE ranking ~robust to shares drift).

Cached per corp_code_year on disk, so it's resumable — re-running skips what's done.
Output: fundamentals_history/KR_dart_history.parquet (append-merged with KR.parquet later).
"""
from __future__ import annotations
import sys, glob
from pathlib import Path
import numpy as np, pandas as pd
import dart_fundamentals as DF
from obs import get_logger, timed

LOG = get_logger("dart_history")
WH_KR = "/Users/umashankar/repos/global-market-data/warehouse/ohlcv/KR"
OUT = Path("/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/KR_dart_history.parquet")
YEARS = ["2015", "2016", "2017", "2018", "2019", "2020", "2021"]
NI_TAG = ("ifrs-full_ProfitLoss",)
EQ_TAG = ("ifrs-full_Equity", "ifrs-full_EquityAttributableToOwnersOfParent")


def kr_universe() -> list:
    parts = sorted(glob.glob(f"{WH_KR}/year=2024.parquet") + glob.glob(f"{WH_KR}/year=2025.parquet"))
    syms = set()
    for p in parts:
        syms |= set(pd.read_parquet(p, columns=["Symbol"]).Symbol.unique())
    # warehouse KR symbols are like '005930.KS' → DART wants bare 6-digit
    return sorted({str(s).split(".")[0] for s in syms if str(s).split(".")[0].isdigit()})


def year_amounts(code, year):
    """(net_income, equity) for a company-year via cached DART statements."""
    rows = DF._statements(code, year)
    if not rows:
        return None, None
    ni = DF._amount(rows, NI_TAG, "thstrm_amount")
    eq = DF._amount(rows, EQ_TAG, "thstrm_amount")
    return ni, eq


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0    # 0 = full universe
    cmap = DF.corp_map()
    uni = kr_universe()
    if limit:
        uni = uni[:limit]
    LOG.info(f"DART history: {len(uni)} KR stocks × {len(YEARS)} years")
    recs, hits, miss = [], 0, 0
    for i, code in enumerate(uni, 1):
        cc = cmap.get(code)
        if not cc:
            miss += 1; continue
        for y in YEARS:
            try:
                ni, eq = year_amounts(cc, y)
            except Exception:
                ni = eq = None
            if ni is not None:
                recs.append({"ticker": f"{code}.KS", "fy_end": f"{y}-12-31",
                             "net_income": ni, "equity": eq})
                hits += 1
        if i % 100 == 0:
            LOG.info(f"  {i}/{len(uni)} stocks, {hits} statements, {miss} no-corp-code")
    df = pd.DataFrame(recs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    LOG.info(f"wrote {OUT}: {len(df)} rows, {df.ticker.nunique()} tickers, "
             f"years {df.fy_end.str[:4].min()}-{df.fy_end.str[:4].max()}")
    print(f"DART history collected: {len(df)} statements, {df.ticker.nunique()} KR tickers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
