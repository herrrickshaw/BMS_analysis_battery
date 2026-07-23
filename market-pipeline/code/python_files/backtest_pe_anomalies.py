#!/usr/bin/env python3
# backtest_pe_anomalies.py
# ========================
# Two PE-pattern backtests on India (user, 2026-07-23):
#
#   A. SECTOR PE ANOMALIES GETTING CORRECTED
#      Within-industry PE quintiles each month-end: does a stock priced cheap
#      RELATIVE TO ITS OWN SECTOR out-earn one priced rich vs sector over the
#      next 1/3/6 months? Plus the sector-level version: when a whole sector's
#      median PE stretches vs its own 3-year history (z-score), does the
#      stretch correct?
#
#   B. PE TRENDS vs COMPANY PERFORMANCE
#      Decompose 12-month multiple change: Δln(PE) = Δln(price) − Δln(EPS).
#      2×2 buckets (PE expanding/compressing × EPS growing/shrinking) →
#      forward returns. Does multiple expansion continue or revert, and does
#      delivery (EPS growth) change the answer? Plus: do high-PE names "earn"
#      their multiple with faster subsequent EPS growth?
#
# DATA (all local, nothing fetched):
#   fundamentals  global-stock-screener/cache_seed/fundamentals_history/IN.parquet
#                 (annual, fy_end 2012→2026, `filed` = point-in-time availability;
#                  where filed is missing, fy_end + 90d is assumed — Indian annual
#                  results deadline is ~60d, +30d buffer)
#   prices        global-market-data/warehouse/ohlcv_adj/IN (2016→2026, Close is
#                 ALREADY adjusted — verified vs RELIANCE's 2024 1:1 bonus)
#
# HONESTY NOTES (printed with results):
#   * Survivorship: fundamentals were collected for names alive at collection
#     time; dead companies are under-represented → level results are biased
#     UP. Spreads (Q1−Q5, bucket differences) are the trustworthy statistic.
#   * 3M/6M forward windows overlap across monthly formation dates; t-stats
#     are computed on non-overlapping subsets for those horizons.
#   * Annual EPS only — a stock can look cheap for up to a year after a blowup
#     quarter. This biases AGAINST the value result, not for it.

from __future__ import annotations

import glob
import sys

import numpy as np
import pandas as pd

# IN_screener_only_backup, NOT IN.parquet: the merged file mixes screener_in
# rows (₹ crore, annual) with yfinance rows that carry QUARTERLY magnitudes
# mislabelled as annual (TCS "FY26" = ₹13.7k cr ≈ one quarter) — a 4x EPS
# error. The backup is pure screener.in: 10y annual, NI in crore, shares =
# CURRENT count applied historically — which pairs correctly with the
# split-ADJUSTED price panel (validated: TCS FY24-26 EPS 120/133/136 ✓).
FUND = ("/Users/umashankar/repos/global-stock-screener/cache_seed/"
        "fundamentals_history/IN_screener_only_backup.parquet")
PX_DIR = "/Users/umashankar/repos/global-market-data/warehouse/ohlcv_adj/IN"
OUT_MD = "reports/pe_anomaly_backtest.md"

START, END = "2017-01-31", "2026-06-30"
PE_MIN, PE_MAX = 1.0, 200.0          # winsorize: negative/absurd PEs excluded
MIN_IND = 8                          # names an industry needs in a month
FILING_LAG_DAYS = 90                 # assumed when `filed` is missing


def month_ends(px: pd.DataFrame) -> pd.DataFrame:
    """symbol × month-end adjusted close, long → wide."""
    px = px.assign(me=px["Date"] + pd.offsets.MonthEnd(0))
    last = px.sort_values("Date").groupby(["Symbol", "me"]).Close.last()
    return last.unstack("Symbol")


def load_prices() -> pd.DataFrame:
    parts = sorted(glob.glob(f"{PX_DIR}/year=*.parquet"))
    px = pd.concat((pd.read_parquet(p, columns=["Date", "Symbol", "Close"])
                    for p in parts), ignore_index=True)
    px["Date"] = pd.to_datetime(px["Date"])
    return month_ends(px)


def load_eps() -> pd.DataFrame:
    f = pd.read_parquet(FUND)
    f = f[(f.net_income.notna()) & (f.shares.notna()) & (f.shares > 0)].copy()
    f["eps"] = f.net_income * 1e7 / f.shares          # NI ₹crore → ₹
    f["fy_end"] = pd.to_datetime(f.fy_end)
    # no filed column in this source: assume results available fy_end + 90d
    # (Indian annual-results deadline ~60d, +30d buffer — conservative PIT)
    f["avail"] = f.fy_end + pd.Timedelta(days=FILING_LAG_DAYS)
    f["ticker"] = f.ticker.astype(str).str.upper()
    ind = (f.dropna(subset=["industry"]).groupby("ticker").industry
           .agg(lambda s: s.mode().iloc[0]))
    return f[["ticker", "fy_end", "avail", "eps"]], ind


def pit_eps_panel(eps: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """date × ticker matrix of the latest ANNUAL eps available at each date."""
    eps = eps.sort_values("avail")
    out = {}
    for tkr, g in eps.groupby("ticker"):
        s = g.set_index("avail").eps
        s = s[~s.index.duplicated(keep="last")]
        out[tkr] = s.reindex(dates, method="ffill")
    return pd.DataFrame(out, index=dates)


def nonoverlap_t(spreads: pd.Series, step: int) -> float:
    """t-stat on a de-overlapped subsequence (every `step`-th month)."""
    x = spreads.dropna().iloc[::step]
    return float(x.mean() / x.std() * np.sqrt(len(x))) if len(x) > 2 else np.nan


def main() -> int:
    print("loading prices…")
    px = load_prices()                              # month-end close, wide
    px = px.loc[(px.index >= "2016-01-31") & (px.index <= END)]
    eps, industry = load_eps()
    dates = px.index
    print(f"  {px.shape[1]} symbols × {len(dates)} month-ends")
    print("building PIT EPS panel…")
    epsp = pit_eps_panel(eps, dates)
    common = [c for c in px.columns if c in epsp.columns]
    px, epsp = px[common], epsp[common]
    pe = (px / epsp).where(lambda d: (d >= PE_MIN) & (d <= PE_MAX))
    print(f"  {len(common)} symbols with both prices and EPS; "
          f"median names/month with valid PE: "
          f"{int(pe.notna().sum(axis=1).median())}")

    fwd = {h: px.shift(-h) / px - 1 for h in (1, 3, 6)}
    ind_of = industry.reindex(common)

    lines = ["# PE anomaly backtests — India", "",
             f"Universe: {len(common)} NSE names, monthly {START} → {END}. "
             f"Annual PIT EPS (filed date, else fy_end+90d); adjusted closes; "
             f"PE winsorized to [{PE_MIN}, {PE_MAX}]. Survivorship-biased "
             f"universe — read SPREADS, not levels.", ""]

    # ── A. within-industry PE quintiles ──────────────────────────────────────
    print("A: within-industry PE quintiles…")
    lines += ["## A. Sector-relative PE — do anomalies correct?", ""]
    qret = {h: {q: [] for q in range(1, 6)} for h in fwd}
    months_used = 0
    start_ts = pd.Timestamp(START)
    for t in dates[dates >= start_ts]:
        row = pe.loc[t].dropna()
        if len(row) < 100:
            continue
        grp = ind_of.reindex(row.index)
        ok_ind = grp.value_counts()
        ok_ind = ok_ind[ok_ind >= MIN_IND].index
        sel = grp.isin(ok_ind)
        if sel.sum() < 80:
            continue
        # percentile of PE WITHIN industry → quintile
        pct = row[sel].groupby(grp[sel]).rank(pct=True)
        quint = np.ceil(pct * 5).clip(1, 5)
        months_used += 1
        for h, f_ in fwd.items():
            fr = f_.loc[t].reindex(quint.index)
            for q in range(1, 6):
                qret[h][q].append(float(fr[quint == q].mean()))
    lines.append(f"{months_used} monthly formations; quintile 1 = CHEAPEST vs "
                 f"own industry.\n")
    lines.append("| horizon | Q1 cheap | Q2 | Q3 | Q4 | Q5 rich | Q1−Q5 | t (de-overlapped) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for h in (1, 3, 6):
        means = [np.nanmean(qret[h][q]) * 100 for q in range(1, 6)]
        spr = pd.Series(qret[h][1]) - pd.Series(qret[h][5])
        t = nonoverlap_t(spr, h)
        lines.append("| %dM | %s | **%+.2f%%** | %.2f |" % (
            h, " | ".join(f"{m:+.2f}%" for m in means), spr.mean() * 100, t))

    # sector-level stretch: median PE z vs own trailing 36M
    print("A2: sector-level PE stretch…")
    ind_pe = {}
    for t in dates:
        row = pe.loc[t].dropna()
        g = ind_of.reindex(row.index)
        m = row.groupby(g).median()
        ind_pe[t] = m[row.groupby(g).count() >= MIN_IND]
    ind_pe = pd.DataFrame(ind_pe).T.sort_index()
    z = (ind_pe - ind_pe.rolling(36, min_periods=24).mean()) / \
        ind_pe.rolling(36, min_periods=24).std()
    # forward 3M sector equal-weight return
    stretch = []
    for t in dates[dates >= start_ts]:
        if t not in z.index:
            continue
        zrow = z.loc[t].dropna()
        fr = fwd[3].loc[t]
        g = ind_of.reindex(fr.dropna().index)
        sret = fr.dropna().groupby(g).mean()
        both = pd.concat([zrow, sret], axis=1, keys=["z", "r"]).dropna()
        stretch.append(both)
    st = pd.concat(stretch)
    hot = st[st.z > 1.5].r
    cold = st[st.z < -1.5].r
    mid = st[st.z.abs() <= 0.5].r
    lines += ["", "**Sector-level stretch (median PE z vs own 36M history) → "
              "forward 3M sector return:**", "",
              f"- stretched rich (z > +1.5): {hot.mean()*100:+.2f}% "
              f"(n={len(hot)} sector-months)",
              f"- neutral (|z| ≤ 0.5): {mid.mean()*100:+.2f}% (n={len(mid)})",
              f"- stretched cheap (z < −1.5): {cold.mean()*100:+.2f}% "
              f"(n={len(cold)})", ""]

    # ── B. PE trend vs delivery ──────────────────────────────────────────────
    print("B: PE trend × EPS delivery…")
    lines += ["## B. PE trends vs company performance", ""]
    lnpe = np.log(pe)
    d_pe = lnpe - lnpe.shift(12)                 # 12M multiple change
    d_eps = np.log(epsp.where(epsp > 0)) - np.log(epsp.where(epsp > 0)).shift(12)
    buckets = {"PE↑ EPS↑ (earned re-rating)": (d_pe > 0) & (d_eps > 0),
               "PE↑ EPS↓ (hope rally)":       (d_pe > 0) & (d_eps <= 0),
               "PE↓ EPS↑ (cheapening on delivery)": (d_pe <= 0) & (d_eps > 0),
               "PE↓ EPS↓ (deserved de-rating)":     (d_pe <= 0) & (d_eps <= 0)}
    lines.append("12M multiple change × 12M EPS delivery → forward returns "
                 "(equal-weight, monthly formations):\n")
    lines.append("| bucket | n/mo | fwd 3M | fwd 6M |")
    lines.append("|---|---|---|---|")
    for name, mask in buckets.items():
        r3, r6, ns = [], [], []
        for t in dates[dates >= start_ts]:
            m = mask.loc[t]
            syms = m[m].index
            if len(syms) < 20:
                continue
            ns.append(len(syms))
            r3.append(float(fwd[3].loc[t].reindex(syms).mean()))
            r6.append(float(fwd[6].loc[t].reindex(syms).mean()))
        lines.append(f"| {name} | {int(np.mean(ns)) if ns else 0} | "
                     f"{np.nanmean(r3)*100:+.2f}% | {np.nanmean(r6)*100:+.2f}% |")

    # do high PEs earn their multiple? PE quintile → subsequent 12M EPS growth
    print("B2: PE level vs subsequent EPS growth…")
    rows_ = []
    for t in dates[dates >= start_ts]:
        if t + pd.offsets.MonthEnd(12) > dates[-1]:
            break
        row = pe.loc[t].dropna()
        if len(row) < 100:
            continue
        q = np.ceil(row.rank(pct=True) * 5).clip(1, 5)
        growth = d_eps.shift(-12).loc[t]        # EPS growth over the NEXT 12M
        for k in range(1, 6):
            rows_.append((k, float(growth.reindex(q[q == k].index).mean())))
    bq = pd.DataFrame(rows_, columns=["q", "g"]).groupby("q").g.mean()
    lines += ["", "**Do high-PE names deliver faster subsequent EPS growth "
              "(next 12M, log growth)?**", "",
              "| PE quintile (1=cheap) | " +
              " | ".join(str(q) for q in bq.index) + " |",
              "|---|" + "---|" * len(bq),
              "| subsequent EPS growth | " +
              " | ".join(f"{v*100:+.1f}%" for v in bq.values) + " |", ""]

    text = "\n".join(lines)
    with open(OUT_MD, "w") as fh:
        fh.write(text)
    print(f"\nwrote {OUT_MD}\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
