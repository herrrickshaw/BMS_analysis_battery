#!/usr/bin/env python3
"""
value_quality_ls_backtest.py — the strategy the whole analysis points to, tested PIT.

LONG  = cheap (low PE) AND high ROE  — cheap-for-quality (the reversion tailwind + the
        earnings to back it: Vedanta/IOC/National-Aluminium type)
SHORT = expensive (high PE) AND low ROE — the "hollow overpriced" that history shows
        corrects down (Westlife/Adani-Green/MTAR type)

Dollar-neutral book, monthly formations, forward 3M/6M. Run across India/US/Korea —
the markets where valuation reversion tested significant (Japan skipped: directional
but not significant). India uses screener.in fundamentals + adjusted prices and can go
sector-relative; US/KR use SEC-EDGAR / yfinance history, market-relative.

PE winsorised [1,200]; survivorship-biased universes → read the SPREAD; overlapping
fwd windows → de-overlapped t. Descriptive backtest, not investment advice.

Output: reports/value_quality_ls.md
"""
from __future__ import annotations
import glob
from pathlib import Path
import numpy as np, pandas as pd
from obs import get_logger

HERE = Path(__file__).resolve().parent
LOG = get_logger("value_quality_ls")
FH = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history"
WH = "/Users/umashankar/repos/global-market-data/warehouse"
CFG = {                         # mkt: (fund file, price dir, start)
 "IN": (f"{FH}/IN_screener_only_backup.parquet", f"{WH}/ohlcv_adj/IN", "2017-01-01"),
 "US": (f"{FH}/US.parquet",                      f"{WH}/ohlcv/US",     "2017-01-01"),
 "KR": (f"{FH}/KR.parquet",                      f"{WH}/ohlcv/KR",     "2022-01-01"),
}


def load_px(px_dir):
    parts = sorted(glob.glob(f"{px_dir}/year=*.parquet"))
    px = pd.concat((pd.read_parquet(p, columns=["Date", "Symbol", "Close"]) for p in parts),
                   ignore_index=True)
    px["Date"] = pd.to_datetime(px["Date"])
    return px.pivot_table(index="Date", columns="Symbol", values="Close",
                          aggfunc="last").sort_index().resample("ME").last()


def fund_records(mkt, fund):
    f = pd.read_parquet(fund)
    f["eps"] = pd.to_numeric(f.net_income, errors="coerce") / pd.to_numeric(f.shares, errors="coerce")
    if mkt == "IN":
        eq = pd.to_numeric(f.equity_capital, errors="coerce") + pd.to_numeric(f.reserves, errors="coerce")
        f["eff"] = pd.to_datetime(f.fy_end, errors="coerce") + pd.Timedelta(days=90)
    else:
        eq = pd.to_numeric(f.equity, errors="coerce")
        f["eff"] = pd.to_datetime(f.get("filed"), errors="coerce").fillna(
                   pd.to_datetime(f.fy_end, errors="coerce") + pd.Timedelta(days=90))
    f["roe"] = pd.to_numeric(f.net_income, errors="coerce") / eq.where(eq > 0)
    return f[np.isfinite(f.eps) & f.eff.notna()][["ticker", "eff", "eps", "roe"]]


def pit_panel(rec, dates, col):
    out = {}
    for tk, g in rec.sort_values("eff").groupby("ticker"):
        s = pd.Series(g[col].values, index=g.eff.values)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        out[tk] = s.reindex(s.index.union(dates)).ffill().reindex(dates)
    return pd.DataFrame(out)


def nonoverlap_t(sp, step):
    d = sp.iloc[::step].dropna()
    return float(d.mean() / d.std() * np.sqrt(len(d))) if len(d) > 2 and d.std() else float("nan")


def run(mkt):
    fund, px_dir, start = CFG[mkt]
    px = load_px(px_dir); dates = px.index[px.index >= start]
    rec = fund_records(mkt, fund)
    eps = pit_panel(rec, dates, "eps"); roe = pit_panel(rec, dates, "roe")
    common = px.columns.intersection(eps.columns)
    px, eps, roe = px[common].reindex(dates), eps[common], roe[common]
    pe = (px / eps).where(eps > 0).clip(1, 200)
    fwd = {h: px.shift(-h) / px - 1 for h in (3, 6)}
    books = {3: [], 6: []}
    for t in dates:
        p, r = pe.loc[t], roe.loc[t]
        u = p.dropna().index.intersection(r.dropna().index)
        if len(u) < 60:
            continue
        p, r = p.reindex(u), r.reindex(u)
        cheap = p <= p.quantile(1/3); rich = p >= p.quantile(2/3)
        hiroe = r >= r.quantile(0.5); loroe = r <= r.quantile(0.5)
        longs = u[cheap & hiroe]; shorts = u[rich & loroe]
        if len(longs) < 5 or len(shorts) < 5:
            continue
        for h in (3, 6):
            fr = fwd[h].loc[t]
            lm, sm = fr.reindex(longs).mean(), fr.reindex(shorts).mean()
            if np.isfinite(lm) and np.isfinite(sm):
                books[h].append({"date": t, "long": lm, "short": sm, "ls": lm - sm,
                                 "n_long": len(longs), "n_short": len(shorts)})
    return {h: pd.DataFrame(v) for h, v in books.items()}


def main() -> int:
    res = {}
    for mkt in ("IN", "US", "KR"):
        with_ = run(mkt); res[mkt] = with_
        r6 = with_[6]
        LOG.info(f"{mkt}: {len(r6)} formations, avg {r6.n_long.mean():.0f} long / "
                 f"{r6.n_short.mean():.0f} short")
    L = ["# Value + quality long/short — cheap∩high-ROE vs expensive∩low-ROE (PIT)", "",
         "LONG cheap (bottom-tercile PE) ∩ high-ROE (top half); SHORT expensive (top-tercile "
         "PE) ∩ low-ROE (bottom half). Dollar-neutral, monthly formations. Markets where "
         "valuation reversion tested significant (Japan excluded). Survivorship-biased → "
         "read the L/S spread; de-overlapped t.", "",
         "| market | horizon | long | short | **L/S** | t | n L/S |",
         "|---|---|--:|--:|--:|--:|--:|"]
    combined = {3: [], 6: []}
    for mkt in ("IN", "US", "KR"):
        for h in (3, 6):
            d = res[mkt][h]
            if d.empty: continue
            t = nonoverlap_t(d["ls"], h)
            L.append(f"| {mkt} | {h}M | {d['long'].mean()*100:+.2f}% | {d['short'].mean()*100:+.2f}% | "
                     f"**{d['ls'].mean()*100:+.2f}%** | {t:.2f} | {d.n_long.mean():.0f}/{d.n_short.mean():.0f} |")
            combined[h].append(d.set_index("date")["ls"])
    L += ["", "## Combined (equal-weight across IN/US/KR)", "",
          "| horizon | avg L/S | t |", "|---|--:|--:|"]
    for h in (3, 6):
        c = pd.concat(combined[h], axis=1).mean(axis=1).dropna()
        L.append(f"| {h}M | **{c.mean()*100:+.2f}%** | {nonoverlap_t(c, h):.2f} |")
    L += ["", "> L/S > 0 with t≳2 ⇒ cheap-for-quality out-returns hollow-overpriced — the "
          "strategy the clustering + reversion tests both point to. Gross of costs/borrow; "
          "the short leg needs a locate and pays borrow (thin small-caps especially). "
          "Not investment advice."]
    (HERE / "reports" / "value_quality_ls.md").write_text("\n".join(L))
    print("\n".join(L))
    print("\nwrote reports/value_quality_ls.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
