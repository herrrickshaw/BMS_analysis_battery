#!/usr/bin/env python3
"""
valuation_reversion_backtest.py — does the over/under-priced signal CORRECT over
time? PIT test for the US (India already validated in backtest_pe_anomalies.py:
sector-relative cheap−rich = +5.3%/6M, t 2.5).

Two questions, monthly formations 2017→2026:
  1. FORWARD RETURN — do cheap-vs-market names (low PE quintile) out-return rich-vs-
     market names (high PE quintile) over the next 3M/6M?
  2. CONVERGENCE — does a rich stock's PE actually FALL toward the market median,
     and a cheap stock's PE RISE toward it? (the literal "correct to the average").

Data: US fundamentals_history (SEC EDGAR annual, `filed` date = PIT) → EPS = NI/shares;
warehouse/ohlcv/US adjusted closes. PE winsorised [1,200]; survivorship-biased
universe so read SPREADS not levels; 3M/6M windows overlap → de-overlapped t-stats.
Market-relative (not sector-relative — no historical US sectors); India's result IS
sector-relative.

Output: reports/valuation_reversion_{}.md".format(MKT.lower())
"""
from __future__ import annotations
import glob, sys
from pathlib import Path
import numpy as np, pandas as pd
from obs import get_logger

HERE = Path(__file__).resolve().parent
LOG = get_logger("valuation_reversion")
FH = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history"
WH = "/Users/umashankar/repos/global-market-data/warehouse/ohlcv"
# per-market: (fundamentals file, price dir, formation start). US/KR/JP warehouse
# prices are split-adjusted (price_adjuster_global.py); fundamentals histories:
# US 2017→, KR/JP 2021→ (shorter window → fewer non-overlap obs → weaker t).
CFG = {
 "US": (f"{FH}/US.parquet", f"{WH}/US", "2017-01-01"),
 "KR": (f"{FH}/KR.parquet", f"{WH}/KR", "2022-01-01"),
 "JP": (f"{FH}/JP.parquet", f"{WH}/JP", "2022-01-01"),
}
MKT = sys.argv[1] if len(sys.argv) > 1 else "US"
FUND, PX_DIR, START = CFG[MKT]


def load_prices() -> pd.DataFrame:
    parts = sorted(glob.glob(f"{PX_DIR}/year=*.parquet"))
    px = pd.concat((pd.read_parquet(p, columns=["Date", "Symbol", "Close"]) for p in parts),
                   ignore_index=True)
    px["Date"] = pd.to_datetime(px["Date"])
    w = px.pivot_table(index="Date", columns="Symbol", values="Close", aggfunc="last").sort_index()
    return w.resample("ME").last()                       # month-end closes


def pit_eps(dates) -> pd.DataFrame:
    f = pd.read_parquet(FUND)
    f["eff"] = pd.to_datetime(f.get("filed"), errors="coerce")
    f["eff"] = f["eff"].fillna(pd.to_datetime(f["fy_end"], errors="coerce") + pd.Timedelta(days=90))
    f["eps"] = pd.to_numeric(f.net_income, errors="coerce") / pd.to_numeric(f.shares, errors="coerce")
    f = f[np.isfinite(f.eps) & f.eff.notna()].sort_values("eff")
    # PIT: at each month-end, the latest EPS whose eff <= that date, per ticker
    panel = {}
    for tk, g in f.groupby("ticker"):
        s = pd.Series(g.eps.values, index=g.eff.values)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        panel[tk] = s.reindex(s.index.union(dates)).ffill().reindex(dates)
    return pd.DataFrame(panel)


def nonoverlap_t(sp: pd.Series, step: int) -> float:
    d = sp.iloc[::step].dropna()
    return float(d.mean() / d.std() * np.sqrt(len(d))) if len(d) > 2 and d.std() else float("nan")


def main() -> int:
    LOG.info("loading US prices…"); px = load_prices()
    dates = px.index[px.index >= START]
    LOG.info("building PIT EPS panel…"); eps = pit_eps(dates)
    common = px.columns.intersection(eps.columns)
    px, eps = px[common].reindex(dates), eps[common]
    pe = (px / eps).where(eps > 0).clip(1, 200)
    fwd3 = px.shift(-3) / px - 1
    fwd6 = px.shift(-6) / px - 1

    rows3, rows6, conv = [], [], []
    for t in dates:
        row = pe.loc[t].dropna()
        if row.size < 60:
            continue
        q = pd.qcut(row.rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        med = row.median()
        for h, fwd, store in [(3, fwd3, rows3), (6, fwd6, rows6)]:
            fr = fwd.loc[t]
            means = {int(k): fr.reindex(row.index[q == k]).mean() for k in [1, 2, 3, 4, 5]}
            if all(np.isfinite(v) for v in means.values()):
                store.append({"date": t, **means, "spread": means[1] - means[5]})
        # convergence: relative PE now vs 6M later, for Q1 (cheap) & Q5 (rich)
        for k, name in [(1, "cheap"), (5, "rich")]:
            names = row.index[q == k]
            rel_now = (row.reindex(names) / med)
            pe6 = pe.shift(-6).loc[t].reindex(names)
            med6 = pe.shift(-6).loc[t].median()
            rel_6m = pe6 / med6
            conv.append({"date": t, "bucket": name,
                         "rel_pe_now": rel_now.median(), "rel_pe_6m": rel_6m.median()})

    r3, r6, cv = pd.DataFrame(rows3), pd.DataFrame(rows6), pd.DataFrame(conv)
    def q(df, k): return df[k].mean() * 100
    L = [f"# Valuation reversion — does over/under-pricing correct? ({MKT}, PIT {START[:4]}→2026)", "",
         f"{len(r6)} monthly formations. Quintile 1 = cheapest vs market PE, 5 = richest. "
         "Market-relative (no historical sectors); India's sector-relative version is in "
         "`pe_anomaly_backtest.md` (+5.3%/6M, t 2.5). Survivorship-biased → read spreads.", "",
         "## 1. Forward return by PE quintile", "",
         "| horizon | Q1 cheap | Q2 | Q3 | Q4 | Q5 rich | Q1−Q5 | t |",
         "|---|--:|--:|--:|--:|--:|--:|--:|"]
    for h, df in [("3M", r3), ("6M", r6)]:
        t = nonoverlap_t(df["spread"], 3 if h == "3M" else 6)
        L.append(f"| {h} | {q(df,1):+.2f}% | {q(df,2):+.2f}% | {q(df,3):+.2f}% | {q(df,4):+.2f}% | "
                 f"{q(df,5):+.2f}% | **{q(df,'spread'):+.2f}%** | {t:.2f} |")
    # convergence
    cc = cv.groupby("bucket")[["rel_pe_now", "rel_pe_6m"]].mean()
    L += ["", "## 2. Convergence — does relative PE move toward the market median (1.0)?", "",
          "| bucket | rel-PE at formation | rel-PE +6M | moved toward 1.0? |",
          "|---|--:|--:|---|"]
    for b in ["cheap", "rich"]:
        n, s = cc.loc[b, "rel_pe_now"], cc.loc[b, "rel_pe_6m"]
        toward = "✅ yes" if abs(s - 1) < abs(n - 1) else "no"
        L.append(f"| {b} | {n:.2f}× | {s:.2f}× | {toward} |")
    L += ["", "> Read: if Q1−Q5 spread > 0 with t≳2, cheap-vs-market corrects UP / rich "
          "corrects DOWN in RETURNS. If rich rel-PE falls toward 1.0 and cheap rises toward "
          "1.0, the multiple itself converges. Both together = the mean-reversion the "
          "clustering screen bets on. Not investment advice."]
    (HERE / "reports" / f"valuation_reversion_{MKT.lower()}.md").write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nwrote reports/valuation_reversion_{MKT.lower()}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
