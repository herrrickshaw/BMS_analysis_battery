#!/usr/bin/env python3
# watchlist_repair.py
# ===================
# Fix the three standing data gaps at their ROOT (user, 2026-07-23) instead of
# re-reporting them every morning:
#
#   1. RENAMED TICKERS — the largest "no price data" bucket was names NSE
#      renamed out from under the watchlist (AMARAJABAT→ARE&M 2023,
#      ATFL→SUNDROP 2025, TATAMOTORS→TMPV 2025). Authoritative source: NSE's
#      own symbolchange.csv (nsearchives.nseindia.com), chain-resolved
#      (ITCAGRO→ATFL→SUNDROP). Rows are REWRITTEN to the current symbol with
#      the old one preserved in the note.
#   2. INSTRUMENT-TYPE MISMATCH — ETFs (NIFTYBEES…) in an equity watchlist.
#      Standing user rule (the golden-cross-ETF incident): funds are not
#      equity picks. Tracking-tier ETF rows move to the purged archive with
#      reason "instrument-type: ETF"; held rows are NEVER touched.
#   3. DELISTED / STALE — after renames, an IN tracking row still absent from
#      the CURRENT NSE equity list (data/nse_equity_list.csv, refreshed daily
#      by run_app.sh) is no longer listed — archived with reason. US tracking
#      rows are checked against SEC EDGAR's company_tickers.json the same way.
#
# Everything it removes goes to watchlist_purged.csv with a reason — repair
# deletes from the LIVE list, never from history. Held/sold rows are exempt
# from all removal (portfolio is not this tool's to prune).
#
#   watchlist_repair.py            # apply
#   watchlist_repair.py --dry-run  # report only

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
WATCHLIST = HERE / "watchlist.csv"
PURGED = HERE / "watchlist_purged.csv"
CACHE = HERE / "data"
SYMCHANGE = CACHE / "nse_symbolchange.csv"
NSE_LIST = CACHE / "nse_equity_list.csv"
EDGAR = HERE / "market_cache" / "fundamentals" / "company_tickers.json"
EDGAR_ALT = Path("/Users/umashankar/market-pipeline/market_cache/fundamentals/company_tickers.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
MAX_AGE_S = 7 * 86400

ETF_PAT = re.compile(r"(BEES$|ETF|^LIQUID|IETF|NIFTY(?!.*LTD)|GOLDCASE|SILVERCASE)", re.I)


def _fetch(url: str, dest: Path) -> bool:
    if dest.exists() and time.time() - dest.stat().st_mtime < MAX_AGE_S:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-sL", "--max-time", "30", "-A", UA, url,
                        "-o", str(dest)], capture_output=True)
    return r.returncode == 0 and dest.exists() and dest.stat().st_size > 500


def rename_map() -> dict:
    """old NSE symbol -> CURRENT symbol, chains resolved."""
    if not _fetch("https://nsearchives.nseindia.com/content/equities/symbolchange.csv",
                  SYMCHANGE):
        print("  ⚠ symbolchange.csv unavailable and no cache — rename pass skipped")
        return {}
    df = pd.read_csv(SYMCHANGE, header=None,
                     names=["company", "old", "new", "date"], skipinitialspace=True)
    df["old"] = df.old.astype(str).str.strip().str.upper()
    df["new"] = df.new.astype(str).str.strip().str.upper()
    m = dict(zip(df.old, df.new))
    # chain: ITCAGRO -> ATFL -> SUNDROP (bounded — NSE data has no cycles, but
    # never trust a file not to)
    out = {}
    for old in m:
        cur, hops = old, 0
        while cur in m and hops < 6:
            cur = m[cur]
            hops += 1
        out[old] = cur
    return out


def nse_current() -> set:
    p = NSE_LIST if NSE_LIST.exists() else HERE / "data" / "nse_equity_list.csv"
    try:
        df = pd.read_csv(p)
        col = "SYMBOL" if "SYMBOL" in df.columns else df.columns[0]
        return set(df[col].astype(str).str.strip().str.upper())
    except Exception:
        return set()


def edgar_current() -> set:
    p = EDGAR if EDGAR.exists() else EDGAR_ALT
    try:
        d = json.loads(p.read_text())
        return {v["ticker"].upper().replace(".", "-") for v in d.values()}
    except Exception:
        return set()


def main() -> int:
    dry = "--dry-run" in sys.argv
    wl = pd.read_csv(WATCHLIST)
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    renames = rename_map()
    nse = nse_current()
    edgar = edgar_current()
    print(f"  sources: {len(renames)} NSE renames, {len(nse)} current NSE "
          f"equities, {len(edgar)} EDGAR tickers")

    renamed, to_purge = [], []
    for i, r in wl.iterrows():
        sym = str(r["symbol"]).strip().upper()
        mkt = str(r.get("market", "")).upper()
        status = str(r.get("status", "held")).lower()
        protected = status in ("held", "sold")
        if mkt == "IN":
            # 1. rename first — a renamed name is not delisted
            if sym in renames and renames[sym] != sym:
                new = renames[sym]
                wl.at[i, "symbol"] = new
                wl.at[i, "note"] = (f"{r.get('note', '')} | renamed from {sym} "
                                    f"({today})").strip(" |")
                renamed.append(f"{sym}→{new}")
                sym = new
            # 1b. WRONG-SYMBOL entries: watchlist "GMDC" vs NSE "GMDCLTD".
            # Conservative: only when the symbol is absent from the current
            # list AND exactly ONE current symbol extends it (or vice versa)
            # with ≥4 shared leading chars — ambiguity means no touch.
            if nse and sym not in nse and len(sym) >= 4:
                cands = [c for c in nse
                         if (c.startswith(sym) or sym.startswith(c))
                         and min(len(c), len(sym)) >= 4 and c != sym]
                if len(cands) == 1:
                    new = cands[0]
                    wl.at[i, "symbol"] = new
                    wl.at[i, "note"] = (f"{wl.at[i, 'note']} | symbol corrected "
                                        f"from {sym} ({today})").strip(" |")
                    renamed.append(f"{sym}→{new} (corrected)")
                    sym = new
            if protected:
                continue
            # 2. instrument type: ETFs out of the equity watchlist
            if ETF_PAT.search(sym) and sym not in nse:
                to_purge.append((i, "instrument-type: ETF/fund — excluded by design"))
                continue
            # 3. delisted: not on the CURRENT NSE equity list
            if nse and sym not in nse:
                to_purge.append((i, "not on current NSE EQ/BE/BZ list (delisted, merged, or non-equity instrument)"))
        elif mkt == "US" and not protected:
            if edgar and sym not in edgar and "-" not in sym:
                to_purge.append((i, "not in SEC EDGAR ticker registry (delisted/renamed)"))

    print(f"  renames applied: {len(renamed)}"
          + (f" — {', '.join(renamed[:10])}" + ("…" if len(renamed) > 10 else "")
             if renamed else ""))
    print(f"  rows to archive: {len(to_purge)}")
    for i, reason in to_purge[:15]:
        print(f"    {wl.at[i, 'symbol']:14s} {reason}")
    if len(to_purge) > 15:
        print(f"    … +{len(to_purge) - 15} more")

    if dry:
        print("  (dry run — nothing written)")
        return 0

    if to_purge:
        idx = [i for i, _ in to_purge]
        arch = wl.loc[idx].copy()
        arch["purged_date"] = today
        arch["reason"] = [rsn for _, rsn in to_purge]
        old = pd.read_csv(PURGED) if PURGED.exists() else pd.DataFrame()
        pd.concat([old, arch], ignore_index=True).to_csv(PURGED, index=False)
        wl = wl.drop(index=idx).reset_index(drop=True)
    if to_purge or renamed:
        wl.to_csv(WATCHLIST, index=False)
        print(f"  watchlist.csv: {len(wl)} rows "
              f"({len(renamed)} renamed, {len(to_purge)} archived)")
    else:
        print("  nothing to repair")
    return 0


if __name__ == "__main__":
    sys.exit(main())
