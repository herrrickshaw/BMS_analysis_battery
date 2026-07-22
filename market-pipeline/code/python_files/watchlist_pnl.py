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
# Warehouse dirs (year-partitioned parquet) — pd.read_parquet reads a directory
# natively. Replaces the monolithic ltm panels and the per-market folklore of
# which repo held the good copy (the other US.parquet is the broken
# alphabetical collection).
PANELS = {
    "IN": Path("/Users/umashankar/repos/global-market-data/warehouse/ohlcv/IN"),
    "US": Path("/Users/umashankar/repos/global-market-data/warehouse/ohlcv/US"),
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


def _cap(s: pd.Series, asof: Optional[pd.Timestamp]) -> pd.Series:
    """Drop bars after `asof`. A no-op when asof is None."""
    if asof is None or not len(s):
        return s
    try:
        return s[pd.to_datetime(s.index) <= asof]
    except Exception:
        return s


def _current_prices(market: str, asof: Optional[pd.Timestamp] = None):
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

    `asof` caps every series at a date. Today's bar is an unsettled intraday
    tick until the close prints — the 2026-07-21 brief failed validation for
    exactly that reason, screener.in serving live quotes mid-session — so a mark
    dated today is not comparable to an entry dated on a close. Passing an asof
    makes "priced to yesterday" a property of the run rather than an accident of
    when the stores last happened to update.
    """
    px, dates = {}, {}
    if market == "US":
        try:
            import data_registry as R
            for f in R.OHLC_DIR.glob("*.parquet"):
                try:
                    d = pd.read_parquet(f, columns=["Close"]).dropna()
                except Exception:
                    continue
                c = _cap(d["Close"], asof)
                if not len(c):
                    continue
                px[f.stem.upper()] = float(c.iloc[-1])
                dates[f.stem.upper()] = pd.to_datetime(c.index[-1])
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
                c = _cap(pd.to_numeric(df["Close"], errors="coerce").dropna(), asof)
                if not len(c):
                    continue
                k = str(sym).upper()
                px[k] = float(c.iloc[-1])
                dates[k] = pd.to_datetime(c.index[-1])
        except Exception:
            pass
    return pd.Series(px, dtype=float), pd.Series(dates)


def _yf_candidates(market: str, symbol: str) -> list:
    """Local watchlist symbol -> yfinance ticker candidates.

    Korea stores bare codes that have LOST their leading zeros (38880 is really
    038880), so the code must be re-padded to six digits before a suffix is
    added; .KS is KOSPI and .KQ is KOSDAQ, and only trying one silently drops
    every listing on the other board.
    """
    s = str(symbol).strip().upper()
    if market == "JP":
        return [f"{s}.T"]
    if market == "KR":
        try:
            p = f"{int(s):06d}"
        except ValueError:
            p = s
        return [f"{p}.KS", f"{p}.KQ"]
    return [s]          # EU symbols already carry their exchange suffix


def _fetch_missing(d: pd.DataFrame, asof: Optional[pd.Timestamp]) -> pd.DataFrame:
    """Fill prices for markets with no local store (EU/JP/KR) from yfinance.

    OHLC_DIR holds US names only and bhavcopy holds India, so EU/JP/KR names sit
    in the watchlist with no mark at all — 50 of 651 rows. Their scans fetch
    live at scan time and retain nothing, so there is no history to read.

    Opt-in (--fetch-missing) because this reaches the network from what is
    otherwise a pure reporting tool. Bars after `asof` are dropped, so a name
    whose market was shut on the as-of date reports its last real session rather
    than being silently forward-filled — Japan was closed 2026-07-20 for Marine
    Day, so JP legitimately marks to 07-17.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("  --fetch-missing: yfinance unavailable, skipping")
        return d

    need = d[d["ltp"].isna()] if "ltp" in d.columns else d.iloc[0:0]
    if need.empty:
        return d
    print(f"  --fetch-missing: {len(need)} unpriced names from yfinance …")

    start = (pd.to_datetime(need["date_added"]).min() - pd.Timedelta(days=7))
    if pd.isna(start):
        start = (asof or pd.Timestamp.today()) - pd.Timedelta(days=400)
    end = ((asof or pd.Timestamp.today()) + pd.Timedelta(days=1))

    ok = 0
    for i, r in need.iterrows():
        for t in _yf_candidates(str(r["market"]), str(r["symbol"])):
            try:
                h = yf.Ticker(t).history(start=start.strftime("%Y-%m-%d"),
                                         end=end.strftime("%Y-%m-%d"),
                                         auto_adjust=False)
            except Exception:
                continue
            if h is None or h.empty or "Close" not in h.columns:
                continue
            c = _cap(pd.to_numeric(h["Close"], errors="coerce").dropna(), asof)
            if not len(c):
                continue
            idx = pd.to_datetime(c.index).tz_localize(None)
            last_dt = idx[-1]
            d.at[i, "ltp"] = float(c.iloc[-1])
            d.at[i, "as_of"] = last_dt
            d0 = r.get("date_added")
            if pd.notna(d0):
                prior = c[idx <= pd.Timestamp(d0)]
                if len(prior):
                    e = float(prior.iloc[-1])
                    d.at[i, "entry_price"] = e
                    d.at[i, "basis"] = "panel-close"
                    # Same guard build() applies, and for the same reason: a mark
                    # dated BEFORE the entry cannot measure a return. Japan was
                    # shut 2026-07-20 (Marine Day), so 15 JP names entered on the
                    # 20th resolved both entry and mark to the SAME 07-17 bar —
                    # differencing it against itself printed a confident +0.0%,
                    # indistinguishable from a stock that genuinely did not move.
                    if last_dt < pd.Timestamp(d0):
                        d.at[i, "pct_since"] = float("nan")
                    else:
                        d.at[i, "pct_since"] = (float(c.iloc[-1]) / e - 1) * 100
                    d.at[i, "held_days"] = (last_dt - pd.Timestamp(d0)).days
            ok += 1
            break
    print(f"  --fetch-missing: priced {ok}/{len(need)}")
    return d


def build(market: Optional[str], status: Optional[str],
          asof: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    wl = pd.read_csv(WATCHLIST)
    wl["symbol"] = wl["symbol"].astype(str).str.upper()
    wl["market"] = wl["market"].astype(str).str.upper()
    if market:
        wl = wl[wl["market"] == market.upper()]
    if status:
        wl = wl[wl["status"] == status]

    ed = entry_dates()
    # A name signalled AFTER the as-of date has not entered the book yet as of
    # that date. Keeping it would show a position that did not exist, or one
    # whose entry postdates its own mark.
    if asof is not None and not ed.empty:
        ed = ed[pd.to_datetime(ed["date_added"]) <= asof]
    wl = wl.merge(ed, on=["symbol", "market"], how="left")

    # A date embedded in the note is a fallback for rows the ledger missed.
    note_dt = wl["note"].astype(str).str.extract(DATE_RE)[0]
    wl["date_added"] = wl["date_added"].fillna(pd.to_datetime(note_dt, errors="coerce"))

    # Apply the as-of cap AFTER the note fallback, not only to the ledger.
    # Filtering the ledger alone let five KR names stamped 2026-07-21 through,
    # because their date came from the note regex instead — a second entry
    # path around the same guard.
    if asof is not None:
        wl = wl[wl["date_added"].isna() | (pd.to_datetime(wl["date_added"]) <= asof)]

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
        if asof is not None:
            wide = wide[wide.index <= asof]
        b = BENCH.get(mkt)
        bench = wide[b] if b in wide.columns else wide.median(axis=1)

        fresh, fresh_asof = _current_prices(mkt, asof)   # LFS panel is days behind
        mkt_latest = fresh_asof.max() if len(fresh_asof) else pd.NaT
        # NB: not `asof` — that is the as-of CAP parameter. Reusing the name
        # rebound it to a list on the second market iteration and the panel cap
        # then compared an index against a list ("Lengths must match").
        ltp, entry, pct, xpct, basis, asof_col, stale = [], [], [], [], [], [], []
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
            ltp.append(cur); asof_col.append(ao)
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
        g["as_of"], g["stale_days"] = asof_col, stale
        out.append(g)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def main() -> int:
    ap = argparse.ArgumentParser(description="Watchlist P&L since entry")
    ap.add_argument("--market")
    ap.add_argument("--status", choices=["held", "sold", "watch", "signal"])
    ap.add_argument("--sort", choices=["default", "pct", "date"], default="default")
    ap.add_argument("--top", type=int, default=0, help="limit rows printed per market")
    ap.add_argument("--out")
    ap.add_argument("--asof", help="cap all prices at this date (YYYY-MM-DD), "
                                   "e.g. yesterday's close; 'yesterday' accepted")
    ap.add_argument("--fetch-missing", action="store_true",
                    help="fetch EU/JP/KR prices from yfinance (no local store)")
    a = ap.parse_args()

    asof = None
    if a.asof:
        if a.asof == "yesterday":
            asof = pd.Timestamp.today().normalize() - pd.Timedelta(days=1)
        else:
            asof = pd.Timestamp(a.asof)
        print(f"  as-of cap: {asof:%Y-%m-%d} — bars after this date are excluded")

    d = build(a.market, a.status, asof)
    if d.empty:
        print("  nothing to show"); return 1
    if a.fetch_missing:
        d = _fetch_missing(d, asof)

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
        # A row whose mark falls on its entry date has a zero-day holding
        # period: its 0.0% is arithmetic, not performance. Folding those into
        # the median makes a list that has barely been held look like a list
        # that went nowhere. Report the held subset separately rather than
        # publishing one number that means two different things.
        held = g[(g["as_of"].notna()) & (g["date_added"].notna())
                 & (pd.to_datetime(g["as_of"]) > pd.to_datetime(g["date_added"]))]
        hv = held["pct_since"].dropna()
        zero_day = len(v) - len(hv)
        med_h = f"{hv.median():+7.1f}%" if len(hv) else "     n/a"
        print(f"    {mkt} {st:<7} n={len(v):>3}  med {v.median():>+7.1f}%   "
              f"vs mkt {x.median() if len(x) else float('nan'):>+7.1f}   "
              f"win {(x > 0).mean()*100 if len(x) else float('nan'):>3.0f}%"
              f"   held>0d n={len(hv):>3} med {med_h}"
              + (f"  [{zero_day} zero-day]" if zero_day else ""))
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
