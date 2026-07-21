#!/usr/bin/env python3
"""
watchlist_pnl.py — watchlist sorted by market / date added / LTP, with % since entry.

WHERE EACH ENTRY DATE COMES FROM — and why that matters more than the number
---------------------------------------------------------------------------
"% profit since recommended" is only meaningful if the entry date is real. Three
different provenances feed this list, and they are NOT equally trustworthy:

  signal (forward)     signal_date stamped on the day the filter fired, with the
                       price as of that day. Genuinely out-of-sample.
  signal (backfilled)  reconstructed from dated scan workbooks. The DATE is real
                       (the workbook exists), but no entry price was recorded —
                       so the price is taken from the panel close on that date,
                       which is close to, but not identical to, what the brief
                       quoted.
  held / sold          acquisition date from the Schedule FA tax filing. Real
                       and audited, but the entry PRICE is the panel close on
                       that date, not your actual fill — no brokerage, no
                       slippage, and it ignores multiple tranches.

So the `basis` column is printed next to every % figure. A number whose basis is
`panel-close` is an estimate; one whose basis is `signal-price` is a record.
Collapsing them into one "% profit" column would present three different
qualities of evidence as if they were the same measurement.

    watchlist_pnl.py                     # all, grouped by market
    watchlist_pnl.py --market IN
    watchlist_pnl.py --status signal --sort pct
    watchlist_pnl.py --out reports/watchlist_pnl.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
WATCHLIST = HERE / "watchlist.csv"
LEDGER = HERE / "cache_seed" / "signal_ledger.parquet"
FA_SHEET = Path("/Users/umashankar/Downloads/Sheet for tax filing US stocks.xlsx")
PANELS = {
    "IN": Path("/Users/umashankar/repos/global-market-data/cache_seed/ltm/IN.parquet"),
    "US": Path("/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/US.parquet"),
}
BENCH = {"IN": "NIFTYBEES", "US": "SPY"}
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _bse_bridge() -> dict:
    try:
        xl = pd.read_excel("/Users/umashankar/Library/Mobile Documents/"
                           "com~apple~CloudDocs/Desktop/xlsx/Stock_List_NSE_BSE_1.xlsx",
                           sheet_name="Stock List")
        xl.columns = [str(c).strip() for c in xl.columns]
        return {str(int(r["BSE Code"])): str(r["NSE Symbol"]).strip().upper()
                for _, r in xl.iterrows()
                if pd.notna(r.get("BSE Code")) and pd.notna(r.get("NSE Symbol"))}
    except Exception:
        return {}


def entry_dates() -> pd.DataFrame:
    """(symbol, market) -> earliest known entry date + price + basis."""
    rows = []
    if LEDGER.exists():
        led = pd.read_parquet(LEDGER)
        led["signal_date"] = pd.to_datetime(led["signal_date"])
        for (sym, mkt), g in led.groupby(["symbol", "market"]):
            g = g.sort_values("signal_date")
            first = g.iloc[0]
            rows.append({"symbol": sym, "market": mkt,
                         "date_added": first["signal_date"],
                         "entry_price": first.get("price_at_signal"),
                         "basis": ("signal-price" if first.get("price_at_signal") ==
                                   first.get("price_at_signal") else "panel-close"),
                         "why": first["filter"]})
    if FA_SHEET.exists():
        try:
            fa = pd.read_excel(FA_SHEET, sheet_name="FA_SHEET")
            fa["sym"] = fa["Security"].astype(str).str.strip().str.upper()
            dcol = next((c for c in fa.columns if "acquiring" in str(c).lower()), None)
            if dcol:
                fa[dcol] = pd.to_datetime(fa[dcol], errors="coerce")
                g = fa.dropna(subset=[dcol]).groupby("sym")[dcol].min()
                for sym, dt in g.items():
                    rows.append({"symbol": sym, "market": "US", "date_added": dt,
                                 "entry_price": np.nan, "basis": "panel-close",
                                 "why": "acquired"})
        except Exception:
            pass
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows).sort_values("date_added")
    # Earliest known entry wins: the first time a name entered the book is the
    # date a "% since" should measure from.
    return d.drop_duplicates(subset=["symbol", "market"], keep="first")


def _current_prices(market: str):
    """(price, as_of_date) per symbol from the FRESHEST store, not the deepest.

    Returns the DATE alongside the price, always. A price without the date it
    belongs to is the defect this whole file keeps tripping over: a symbol that
    stopped trading three months ago sits in a "current" panel showing a stale
    close, and nothing distinguishes it from a live quote. Per-PANEL freshness
    cannot reveal that — only per-SYMBOL can.

    🔴 The LFS ltm panels are deep but STALE — IN ends 2026-07-13 (8d), US ends
    2026-07-02 (19d). The daily stores are the opposite: shallow but current
    (both at 2026-07-20). Reading both entry and current price from the LFS
    panel made entry == ltp for anything added in the last 8 days and printed
    "+0.0%", which reads as "went nowhere" rather than "no time has passed".

    So: history from the LFS panel, TODAY from the daily store. Neither source
    is right for both ends.
    """
    px, asof = {}, {}
    if market == "US":
        try:
            import data_registry as R
            for f in R.OHLC_DIR.glob("*.parquet"):
                try:
                    d = pd.read_parquet(f, columns=["Close"]).dropna()
                except Exception:
                    continue
                if not len(d):
                    continue
                px[f.stem.upper()] = float(d["Close"].iloc[-1])
                asof[f.stem.upper()] = pd.to_datetime(d.index[-1])
        except Exception:
            pass
    elif market == "IN":
        try:
            import bhavcopy_store as bs
            for sym in bs.symbols():
                try:
                    df = bs.get(sym)
                except Exception:
                    continue
                if df is None or df.empty or "Close" not in df.columns:
                    continue
                c = pd.to_numeric(df["Close"], errors="coerce").dropna()
                if not len(c):
                    continue
                k = str(sym).upper()
                px[k] = float(c.iloc[-1])
                idx = df.index[df.index.isin(c.index)] if hasattr(df.index, "isin") else df.index
                asof[k] = pd.to_datetime(idx[-1]) if len(idx) else pd.NaT
        except Exception:
            pass
    return pd.Series(px, dtype=float), pd.Series(asof)


def build(market: Optional[str], status: Optional[str]) -> pd.DataFrame:
    wl = pd.read_csv(WATCHLIST)
    wl["symbol"] = wl["symbol"].astype(str).str.upper()
    wl["market"] = wl["market"].astype(str).str.upper()
    if market:
        wl = wl[wl["market"] == market.upper()]
    if status:
        wl = wl[wl["status"] == status]

    ed = entry_dates()
    wl = wl.merge(ed, on=["symbol", "market"], how="left")

    # A date embedded in the note is a fallback for rows the ledger missed.
    note_dt = wl["note"].astype(str).str.extract(DATE_RE)[0]
    wl["date_added"] = wl["date_added"].fillna(pd.to_datetime(note_dt, errors="coerce"))

    bridge = _bse_bridge()
    out = []
    for mkt, grp in wl.groupby("market"):
        p = PANELS.get(mkt)
        if not p or not p.exists():
            out.append(grp); continue
        px = pd.read_parquet(p, columns=["Date", "Symbol", "Close"])
        px["Symbol"] = px["Symbol"].astype(str).str.upper()
        px["Date"] = pd.to_datetime(px["Date"])
        wide = px.pivot_table(index="Date", columns="Symbol", values="Close",
                              aggfunc="last").sort_index()
        b = BENCH.get(mkt)
        bench = wide[b] if b in wide.columns else wide.median(axis=1)

        fresh, fresh_asof = _current_prices(mkt)   # LFS panel is days behind
        mkt_latest = fresh_asof.max() if len(fresh_asof) else pd.NaT
        ltp, entry, pct, xpct, basis, asof, stale = [], [], [], [], [], [], []
        for _, r in grp.iterrows():
            key = bridge.get(r["symbol"], r["symbol"])
            if key not in wide.columns:
                key = key.replace(".", "-")
            s = wide[key].dropna() if key in wide.columns else pd.Series(dtype=float)
            # Current price from the fresh store, falling back to the panel's
            # last bar only when the symbol is absent there.
            cur = fresh.get(key, fresh.get(r["symbol"], np.nan))
            ao = fresh_asof.get(key, fresh_asof.get(r["symbol"], pd.NaT))
            if cur != cur and len(s):
                cur = float(s.iloc[-1]); ao = pd.to_datetime(s.index[-1])
            ltp.append(cur); asof.append(ao)
            # Days between this symbol's last bar and the freshest bar anywhere
            # in its market. 0 = traded on the most recent session; a large
            # number is a suspended, delisted or illiquid name whose "current"
            # price is nothing of the sort.
            stale.append((mkt_latest - ao).days
                         if (ao == ao and mkt_latest == mkt_latest) else np.nan)
            e, bs = r.get("entry_price"), r.get("basis")
            d0 = r.get("date_added")
            if (e != e or e is None) and d0 == d0 and len(s):
                prior = s[s.index <= d0]
                e = float(prior.iloc[-1]) if len(prior) else np.nan
                bs = "panel-close"
            entry.append(e); basis.append(bs if bs == bs else None)
            # 🔴 A "current" price dated BEFORE the entry cannot measure a return.
            # Caught the moment as_of was added: AARNAV was recorded 2026-07-21 at
            # 24.98 from the scan, while the freshest bhavcopy bar is 2026-07-20 at
            # 31.52 — differencing them printed +26.2% for a position held zero
            # days. The two numbers come from different stores and, for dual-listed
            # names, potentially different exchanges. Refuse rather than report.
            if (e == e and cur == cur and e and d0 == d0 and ao == ao
                    and pd.Timestamp(ao) < pd.Timestamp(d0)):
                pct.append(np.nan); xpct.append(np.nan)
            elif e == e and cur == cur and e:
                pc = (cur / e - 1) * 100
                pct.append(pc)
                bb = bench[bench.index >= d0].dropna() if d0 == d0 else pd.Series(dtype=float)
                xpct.append(pc - ((bb.iloc[-1] / bb.iloc[0] - 1) * 100) if len(bb) > 1 else np.nan)
            else:
                pct.append(np.nan); xpct.append(np.nan)
        g = grp.copy()
        g["ltp"], g["entry_price"], g["pct_since"], g["vs_mkt"], g["basis"] = \
            ltp, entry, pct, xpct, basis
        g["as_of"], g["stale_days"] = asof, stale
        out.append(g)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def main() -> int:
    ap = argparse.ArgumentParser(description="Watchlist P&L since entry")
    ap.add_argument("--market")
    ap.add_argument("--status", choices=["held", "sold", "watch", "signal"])
    ap.add_argument("--sort", choices=["default", "pct", "date"], default="default")
    ap.add_argument("--top", type=int, default=0, help="limit rows printed per market")
    ap.add_argument("--out")
    a = ap.parse_args()

    d = build(a.market, a.status)
    if d.empty:
        print("  nothing to show"); return 1

    # Requested ordering: market, then date added, then LTP.
    if a.sort == "pct":
        d = d.sort_values(["market", "pct_since"], ascending=[True, False])
    elif a.sort == "date":
        d = d.sort_values(["date_added", "market"], ascending=[False, True])
    else:
        d = d.sort_values(["market", "date_added", "ltp"],
                          ascending=[True, True, False],
                          na_position="last")

    print("=" * 96)
    print("  WATCHLIST — sorted by market, date added, LTP")
    print("=" * 96)
    for mkt, g in d.groupby("market", sort=True):
        priced = g["pct_since"].notna().sum()
        print(f"\n  ▌{mkt}   {len(g)} names, {priced} with an entry basis")
        print(f"    {'symbol':<12} {'status':<7} {'added':<11} {'entry':>10} "
              f"{'ltp':>10} {'as_of':<11} {'age':>4} {'% since':>9} {'vs mkt':>8}  basis")
        show = g.head(a.top) if a.top else g
        for _, r in show.iterrows():
            dt = f"{r['date_added']:%Y-%m-%d}" if pd.notna(r.get("date_added")) else "—"
            ep = f"{r['entry_price']:,.2f}" if pd.notna(r.get("entry_price")) else "—"
            lp = f"{r['ltp']:,.2f}" if pd.notna(r.get("ltp")) else "—"
            pc = f"{r['pct_since']:+.1f}%" if pd.notna(r.get("pct_since")) else "—"
            xp = f"{r['vs_mkt']:+.1f}" if pd.notna(r.get("vs_mkt")) else "—"
            ao = f"{r['as_of']:%Y-%m-%d}" if pd.notna(r.get("as_of")) else "—"
            sd = r.get("stale_days")
            # Flag anything more than a week behind its own market's last bar.
            age = ("—" if sd != sd else (f"{int(sd)}d" if sd <= 7 else f"⚠{int(sd)}d"))
            print(f"    {r['symbol']:<12} {str(r['status']):<7} {dt:<11} {ep:>10} "
                  f"{lp:>10} {ao:<11} {age:>4} {pc:>9} {xp:>8}  {r.get('basis') or '—'}")
        if a.top and len(g) > a.top:
            print(f"    … {len(g) - a.top} more")

    print("\n" + "=" * 96)
    print("  SUMMARY by market x status  (median % since entry / vs market)")
    for (mkt, st), g in d.groupby(["market", "status"]):
        v = g["pct_since"].dropna()
        if v.empty:
            continue
        x = g["vs_mkt"].dropna()
        print(f"    {mkt} {st:<7} n={len(v):>3}  med {v.median():>+7.1f}%   "
              f"vs mkt {x.median() if len(x) else float('nan'):>+7.1f}   "
              f"win {(x > 0).mean()*100 if len(x) else float('nan'):>3.0f}%")
    st = d["stale_days"].dropna() if "stale_days" in d.columns else pd.Series(dtype=float)
    if len(st):
        n_stale = int((st > 7).sum())
        print(f"\n  staleness: {len(st) - n_stale}/{len(st)} priced within 7d of their "
              f"market's last bar; {n_stale} older (⚠)")
        print("             a stale as_of means the SYMBOL stopped printing, not that")
        print("             the panel is behind — the panel is current to 2026-07-20.")
    print("\n  basis: signal-price = recorded when the filter fired (a record)")
    print("         panel-close  = panel close on the entry date (an estimate —")
    print("                        no fill price, no slippage, ignores tranches)")

    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        d.to_csv(a.out, index=False)
        print(f"\n  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
