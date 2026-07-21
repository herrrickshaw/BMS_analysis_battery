#!/usr/bin/env python3
"""
fundamentals_store_reader.py — serve the off-hours store to the scan, in the
exact DataFrame shape yfinance returns, so the scan's screeners run unchanged.

WHY A SHIM AND NOT AN EDIT TO EACH SCREENER
-------------------------------------------
The scan reads statements through stock_utils.row(df, label, col): it does
df.loc[label].iloc[col], needing an EXACT label match and columns ordered
most-recent-first. Reproducing that shape here means the four screeners in
fundamental_scan() do not change at all — they cannot tell a store-sourced
statement from a live yfinance one. Anything subtler risks a screener silently
scoring differently depending on the source, which is worse than no store.

WHAT IT CANNOT SERVE
--------------------
The store holds ANNUAL statements only. BullCartel needs QUARTERLY data
(quarterly_income_stmt), which yfinance provides and this does not. So a
store-sourced ticker can run Piotroski, Coffee Can and Magic Formula (annual)
but NOT BullCartel. That is a deliberate, stated trade: the store fixes the
alphabet bias for three of the four fundamental screeners across the whole
universe; BullCartel stays live-only and therefore alphabet-limited until the
collector also gathers quarterly data. Three-of-four for everyone beats
four-of-four for the A's.

    from fundamentals_store_reader import statements
    inc, bal, cf = statements("ZYDUSLIFE")   # or (None, None, None) if absent
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
try:
    import data_registry as _R
    STORE = _R.FUND_DIR / "IN_current.parquet"
except Exception:
    STORE = HERE / "cache_seed" / "fundamentals_current" / "IN_current.parquet"

# Our field -> (statement, yfinance row-label the scan queries). The label must
# be EXACTLY what stock_utils.row() looks up; the scan tries some aliases, and
# the first one it lists is used here.
FIELD_TO_LABEL = {
    "net_income":          ("inc", "Net Income"),
    "revenue":             ("inc", "Total Revenue"),
    "gross_profit":        ("inc", "Gross Profit"),
    "total_assets":        ("bal", "Total Assets"),
    "borrowings":          ("bal", "Long Term Debt"),   # scan reads Long Term Debt
    "current_assets":      ("bal", "Current Assets"),
    "current_liabilities": ("bal", "Current Liabilities"),
    "shares":              ("bal", "Share Issued"),
    "cfo":                 ("cf",  "Operating Cash Flow"),
}

_CACHE = {"mtime": None, "by_ticker": {}}


def _load():
    """Load the store once, grouped by ticker, refreshing if the file changed."""
    if not STORE.exists():
        return {}
    m = STORE.stat().st_mtime
    if _CACHE["mtime"] == m:
        return _CACHE["by_ticker"]
    d = pd.read_parquet(STORE)
    d = d[d["source"] == "yfinance"] if "source" in d.columns else d
    by = {t: g for t, g in d.groupby(d["ticker"].astype(str).str.upper())}
    _CACHE.update(mtime=m, by_ticker=by)
    return by


def statements(symbol: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame],
                                     Optional[pd.DataFrame]]:
    """(inc, bal, cf) for `symbol` from the store, yfinance-shaped, or all None.

    Columns are fiscal years DESCENDING, so column 0 is the most recent year —
    exactly the ordering stock_utils.row(col=0) assumes. Returns None for a
    statement that has no populated rows, matching what first_df() would do.
    """
    g = _load().get(str(symbol).upper())
    if g is None or g.empty:
        return None, None, None

    # Most-recent fiscal year first.
    g = g.sort_values("fy_end", ascending=False)
    cols = list(g["fy_end"])

    frames = {"inc": {}, "bal": {}, "cf": {}}
    for field, (stmt, label) in FIELD_TO_LABEL.items():
        if field not in g.columns:
            continue
        vals = pd.to_numeric(g[field], errors="coerce").tolist()
        if all(v != v for v in vals):        # all NaN -> the row is genuinely absent
            continue
        frames[stmt][label] = vals

    def _mk(rows):
        if not rows:
            return None
        return pd.DataFrame(rows, index=cols).T   # index=label, columns=fy_end desc

    return _mk(frames["inc"]), _mk(frames["bal"]), _mk(frames["cf"])


def has(symbol: str) -> bool:
    """True if the store can serve annual statements for this symbol."""
    inc, bal, cf = statements(symbol)
    return inc is not None and bal is not None


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or ["ZYDUSLIFE", "TATASTEEL"]:
        inc, bal, cf = statements(s)
        print(f"{s}: inc={None if inc is None else inc.shape} "
              f"bal={None if bal is None else bal.shape} "
              f"cf={None if cf is None else cf.shape}")
        if bal is not None:
            print("   labels:", list(bal.index))
