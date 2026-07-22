#!/usr/bin/env python3
"""
nse_xbrl_results.py — point-in-time India fundamentals from NSE's XBRL filings.

THE GAP THIS CLOSES (the last big one)
--------------------------------------
Every India fundamentals source so far fails point-in-time:

  yfinance      figures but NO filing dates -> backtests guess a +90d lag
  screener.in   10y dated-ish history but rate-limited (~150 req/session), which
                is what made every panel an alphabetical-prefix sample

NSE's corporate-filings API is the actual record: every listed company's
quarterly result WITH the filing timestamp, plus a link to the XBRL file
containing the full P&L. Verified 2026-07-22 by plain curl — no cookies:

  index:  nseindia.com/api/corporates-financial-results
          ?index=equities&period=Quarterly&from_date=DD-MM-YYYY&to_date=...
          -> ~3,500 records/quarter: symbol, fromDate/toDate (fiscal period),
             filingDate/broadCastDate (WHEN THE MARKET LEARNED IT), audited,
             consolidated, xbrl file URL. 3,796 of 3,814 carried real links.
  files:  nsearchives.nseindia.com/corporate/xbrl/INDAS_*.xml (~20KB each)
          -> in-bse-fin taxonomy, 85 numeric elements: RevenueFromOperations,
             FinanceCosts, Depreciation, ProfitBeforeTax, TaxExpense,
             ProfitLossForPeriod, EPS ...

A backtest built on this uses visible_from = filingDate — the real date, not a
proxy. That removes the single biggest honesty caveat on the factor work.

DESIGN (each rule earned this session)
--------------------------------------
* THE INDEX IS COLLECTED PER QUARTER-WINDOW and stored whole. It is one request
  per window and is the map of what exists; files can always be re-fetched, the
  map of filings cannot be reconstructed from files alone.
* FILES DOWNLOAD IN HASH ORDER, politely, idempotent. An interrupted run leaves
  a representative sample, never an alphabetical prefix (the A-bias, twice).
* RAW XML IS KEPT verbatim; the parquet is derived. A parser bug must never
  cost source data.
* THE PARSER BINDS NUMBERS TO THE FILING'S OWN PERIOD: it only takes elements
  whose contextRef period matches the index record's fromDate/toDate. XBRL
  files carry multiple contexts (quarter, YTD, prior year); grabbing "the
  first" silently mixes periods.
* Consecutive-failure circuit breaker; a throttle must stop the run, not burn
  the window fetching nothing.

    nse_xbrl_results.py --index --quarters 4      # fetch/refresh the index
    nse_xbrl_results.py --files --limit 500       # download XBRLs (resumable)
    nse_xbrl_results.py --parse                   # XMLs -> pit parquet
    nse_xbrl_results.py --status
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

try:
    import data_registry as _R
    ROOT = _R.MARKET_CACHE / "nse_xbrl"
except Exception:
    ROOT = Path(__file__).resolve().parent / "cache_seed" / "nse_xbrl"

XML_DIR = ROOT / "xml"
INDEX_PQ = ROOT / "results_index.parquet"
PANEL_PQ = ROOT / "pit_quarterly.parquet"

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
API = ("https://www.nseindia.com/api/corporates-financial-results"
       "?index=equities&period=Quarterly&from_date={f}&to_date={t}")
RATE = 0.8
BREAKER = 40          # consecutive file failures = a block, stop

# in-bse-fin elements -> our columns. The taxonomy is BSE's even on NSE filings.
# Alias lists: taxonomy versions differ across years. The 2018 "WEB" files
# carry only ProfitLossForPeriodFromContinuingOperations, never the plain
# element; banks report InterestEarned-based income. First alias that matches
# the filing's period wins.
FIELDS = {
    "revenue":        ["RevenueFromOperations", "IncomeFromOperations",
                       "InterestEarned"],
    "other_income":   ["OtherIncome"],
    "total_income":   ["Income", "TotalIncome"],
    "finance_costs":  ["FinanceCosts", "InterestExpended"],
    "depreciation":   ["DepreciationDepletionAndAmortisationExpense"],
    "total_expenses": ["Expenses", "TotalExpenditure"],
    "pbt":            ["ProfitBeforeTax", "ProfitLossBeforeTax"],
    "tax":            ["TaxExpense"],
    "pat":            ["ProfitLossForPeriod",
                       "ProfitLossForPeriodFromContinuingOperations",
                       "NetProfitLossForThePeriod"],
    "eps_basic":      ["BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                       "BasicEarningsLossPerShareFromContinuingOperations",
                       "BasicEPSBeforeExtraordinaryItems"],
}


# ── index ─────────────────────────────────────────────────────────────────────
def _windows(quarters: int):
    """EXACT calendar-quarter windows (Jan-Mar, Apr-Jun, ...), newest first.

    The API filters on FILING date and behaves oddly for long/ragged windows —
    a 4.7-month window returned 8 filings where the exact quarters inside it
    held thousands. Quarter boundaries are also the natural unit: Indian results
    seasons cluster in the first ~45 days of each calendar quarter.
    """
    today = _dt.date.today()
    q_start_month = 3 * ((today.month - 1) // 3) + 1
    start = _dt.date(today.year, q_start_month, 1)
    end = today
    for _ in range(quarters):
        yield start, end
        end = start - _dt.timedelta(days=1)
        start = _dt.date(end.year, 3 * ((end.month - 1) // 3) + 1, 1)


def fetch_index(quarters: int) -> pd.DataFrame:
    old = pd.read_parquet(INDEX_PQ) if INDEX_PQ.exists() else pd.DataFrame()
    frames = [old] if not old.empty else []
    s = requests.Session(); s.headers.update(UA)
    for f, t in _windows(quarters):
        u = API.format(f=f.strftime("%d-%m-%Y"), t=t.strftime("%d-%m-%Y"))
        try:
            r = s.get(u, timeout=45)
            r.raise_for_status()
            d = pd.DataFrame(r.json())
        except Exception as e:
            print(f"  window {f}..{t}: FAILED {type(e).__name__}: {str(e)[:60]}")
            time.sleep(3)
            continue
        print(f"  window {f}..{t}: {len(d)} filings")
        if not d.empty:
            frames.append(d)
        time.sleep(2)
    if not frames:
        return old
    allf = pd.concat(frames, ignore_index=True)
    # seqNumber is NSE's own filing id — the natural dedup key.
    allf = allf.drop_duplicates(subset=["seqNumber"], keep="first")
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = INDEX_PQ.with_suffix(".parquet.tmp")
    allf.to_parquet(tmp, index=False); tmp.replace(INDEX_PQ)
    print(f"  index: {len(allf)} filings, {allf['symbol'].nunique()} symbols -> {INDEX_PQ.name}")
    return allf


# ── files ─────────────────────────────────────────────────────────────────────
def fetch_files(limit: int) -> None:
    if not INDEX_PQ.exists():
        print("  no index — run --index first"); return
    idx = pd.read_parquet(INDEX_PQ)
    idx = idx[idx["xbrl"].astype(str).str.endswith(".xml")]
    XML_DIR.mkdir(parents=True, exist_ok=True)
    have = {p.name for p in XML_DIR.glob("*.xml")}
    todo = [(r["seqNumber"], r["xbrl"]) for _, r in idx.iterrows()
            if r["xbrl"].rsplit("/", 1)[-1] not in have]
    # Hash order: an interrupted run leaves a REPRESENTATIVE sample. Twice this
    # week an alphabetical walk + a rate limit produced an all-A dataset.
    todo.sort(key=lambda x: hashlib.md5(str(x[0]).encode()).hexdigest())
    if limit:
        todo = todo[:limit]
    print(f"  {len(idx)} indexed | {len(have)} on disk | fetching {len(todo)}")
    s = requests.Session(); s.headers.update(UA)
    ok = fail = streak = 0
    for i, (_, url) in enumerate(todo, 1):
        name = url.rsplit("/", 1)[-1]
        try:
            r = s.get(url, timeout=30)
            r.raise_for_status()
            if len(r.content) < 500 or b"<html" in r.content[:200].lower():
                raise ValueError("not an XBRL document")
            (XML_DIR / name).write_bytes(r.content)
            ok += 1; streak = 0
        except Exception:
            fail += 1; streak += 1
            if streak >= BREAKER:
                print(f"  ⚠️  {streak} consecutive failures — blocked, stopping "
                      f"(resume later; {ok} fetched this run)")
                break
        if i % 200 == 0:
            print(f"  [{i}/{len(todo)}] ok {ok} fail {fail}")
        time.sleep(RATE)
    print(f"  files: +{ok} fetched, {fail} failed")


# ── parse ─────────────────────────────────────────────────────────────────────
def _parse_one(path: Path, want_start: str = None, want_end: str = None) -> dict:
    """One filing -> {field: value}, bound to the filing's OWN fiscal period.

    The index record says which quarter this filing is about (fromDate/toDate) —
    that is the authority. For each element, take the value whose contextRef's
    period equals that quarter, preferring PLAIN contexts over dimensional ones.

    The first version voted for the most-referenced context instead; dimensional
    filings (typedMember contexts like ...ItemsThatWillNotBeReclassified...01D)
    won the vote with contexts the P&L never references, and 172 of 299 files
    "failed to parse" while containing every number in plain sight.
    """
    x = path.read_text(errors="ignore")

    # context id -> (start, end); parse each block individually so one context's
    # regex cannot bleed into the next.
    ctx = {}
    for blk in re.finditer(r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', x, re.S):
        cid, body = blk.groups()
        ms = re.search(r"<xbrli:startDate>([^<]+)</xbrli:startDate>", body)
        me = re.search(r"<xbrli:endDate>([^<]+)</xbrli:endDate>", body)
        if ms and me:
            dimensional = "Member" in body or "typedMember" in body or "explicitMember" in body
            ctx[cid] = (ms.group(1).strip(), me.group(1).strip(), dimensional)

    if not ctx:
        return {}

    def _period_ok(cid):
        s, e, _ = ctx[cid]
        if want_start and want_end:
            return s == want_start and e == want_end
        return True

    # NSE "WEB"-format files reference contextRef="OneD" (the filing's own
    # quarter, by NSE's stable naming convention) WITHOUT defining it — invalid
    # XBRL, but consistent. When the index has told us the quarter, synthesize
    # the conventional ids so those files parse instead of "failing" with every
    # number in plain sight. 172 of the first 299 files were this.
    if want_start and want_end:
        for conv in ("OneD", "OneI"):
            ctx.setdefault(conv, (want_start, want_end, False))

    out = {}
    chosen_period = None
    for col, els in FIELDS.items():
        best = None
        for el in els:
            for m in re.finditer(
                    rf'<in-bse-fin:{el}\b[^>]*contextRef="([^"]+)"[^>]*>(-?[\d.]+)</', x):
                cid, val = m.groups()
                if cid not in ctx or not _period_ok(cid):
                    continue
                dim = ctx[cid][2]
                if best is None or (best[1] and not dim):   # plain beats dimensional
                    best = (float(val), dim, cid)
            if best is not None:
                break                    # first alias with a period-matched value
        if best is not None:
            out[col] = best[0]
            chosen_period = chosen_period or ctx[best[2]][:2]
        else:
            out[col] = None

    if chosen_period:
        out["period_start"], out["period_end"] = chosen_period
    elif want_start:
        out["period_start"], out["period_end"] = want_start, want_end
    return out


def parse_all() -> None:
    if not INDEX_PQ.exists():
        print("  no index"); return
    idx = pd.read_parquet(INDEX_PQ)
    by_file = {str(r["xbrl"]).rsplit("/", 1)[-1]: r for _, r in idx.iterrows()}
    rows, bad = [], 0
    files = sorted(XML_DIR.glob("*.xml"))
    for p in files:
        rec = by_file.get(p.name)
        if rec is None:
            continue
        # normalise the index's '01-Oct-2024' to the XBRL's ISO '2024-10-01'
        def _iso(s):
            try:
                return _dt.datetime.strptime(str(s), "%d-%b-%Y").date().isoformat()
            except Exception:
                return None
        try:
            d = _parse_one(p, _iso(rec.get("fromDate")), _iso(rec.get("toDate")))
        except Exception:
            bad += 1
            continue
        if not d or d.get("pat") is None and d.get("revenue") is None:
            bad += 1
            continue
        rows.append({
            "symbol": str(rec["symbol"]).upper(),
            "filing_date": rec.get("filingDate"),
            "audited": rec.get("audited"),
            "consolidated": rec.get("consolidated"),
            "relating_to": rec.get("relatingTo"),
            **d,
            "xml_file": p.name,
        })
    if not rows:
        print(f"  parsed 0 filings ({bad} unparseable)"); return
    d = pd.DataFrame(rows)
    tmp = PANEL_PQ.with_suffix(".parquet.tmp")
    d.to_parquet(tmp, index=False); tmp.replace(PANEL_PQ)
    print(f"  panel: {len(d)} filings, {d['symbol'].nunique()} symbols "
          f"({bad} unparseable) -> {PANEL_PQ.name}")


def status() -> None:
    if INDEX_PQ.exists():
        i = pd.read_parquet(INDEX_PQ)
        print(f"  index : {len(i)} filings, {i['symbol'].nunique()} symbols")
    else:
        print("  index : none")
    n = len(list(XML_DIR.glob('*.xml'))) if XML_DIR.exists() else 0
    print(f"  files : {n} XMLs on disk")
    if PANEL_PQ.exists():
        p = pd.read_parquet(PANEL_PQ)
        import collections
        c = collections.Counter(str(s)[0] for s in p["symbol"].unique())
        print(f"  panel : {len(p)} filings, {p['symbol'].nunique()} symbols, "
              f"{len(c)} first-letters, A {c.get('A',0)/max(p['symbol'].nunique(),1)*100:.0f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description="NSE XBRL point-in-time results")
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--quarters", type=int, default=4)
    ap.add_argument("--files", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--parse", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.index:
        fetch_index(a.quarters)
    if a.files:
        fetch_files(a.limit)
    if a.parse:
        parse_all()
    if a.status or not (a.index or a.files or a.parse):
        status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
