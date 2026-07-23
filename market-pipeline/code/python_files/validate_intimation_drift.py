#!/usr/bin/env python3
"""
validate_intimation_drift.py — the two remaining gates on the
india-ca-intimation-drift claim: a MATCHED benchmark and a family-wide FDR.

MATCHED BENCHMARK (kills the universe-level bias)
    Every event's drift CAR is re-benchmarked against symbols in the SAME
    monthly turnover decile over the SAME calendar window: excess =
    event CAR − median(matched control CAR). Whatever drift the filing/
    liquidity universe earns mechanically, the controls earn too.

INFERENCE
    Events overlap in calendar time (35-50td windows), so naive per-event t
    is anticonservative. Excess is aggregated to CALENDAR-QUARTER means and
    the t-stat runs across quarters.

FDR FAMILY
    The 6 event-study hypotheses tested today + the 12 factor-combo grid
    p-values parsed from MULTIPLE_TESTING.md = one 18-test family, BH at
    q=0.10 / 0.05. Per claims.yaml policy only q=0.10 survivors are citable.

OUTPUT reports/INTIMATION_VALIDATION.md
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

BASE = os.path.dirname(os.path.abspath(__file__))
ADJ = os.path.expanduser(
    "~/repos/global-market-data/warehouse/ohlcv_adj/IN/*.parquet")
EVENTS = os.path.join(BASE, "reports", "pit_event_studies.parquet")
GRID_MD = os.path.join(BASE, "reports", "MULTIPLE_TESTING.md")
OUT_MD = os.path.join(BASE, "reports", "INTIMATION_VALIDATION.md")


def bh_fdr(pvals: pd.Series, q: float) -> pd.Series:
    p = pvals.values
    n = len(p)
    order = np.argsort(p)
    thresh = q * (np.arange(1, n + 1)) / n
    passed = p[order] <= thresh
    k = np.max(np.where(passed)[0]) + 1 if passed.any() else 0
    out = np.zeros(n, dtype=bool)
    out[order[:k]] = True
    return pd.Series(out, index=pvals.index)


def quarter_t(df: pd.DataFrame, col: str, qcol: str = "quarter"):
    """One-sample t across calendar-quarter means."""
    qm = df.groupby(qcol)[col].mean().dropna()
    if len(qm) < 4:
        return np.nan, np.nan, len(qm)
    t, p = stats.ttest_1samp(qm, 0.0)
    return t, p, len(qm)


def main() -> int:
    ev = pd.read_parquet(EVENTS)
    con = duckdb.connect()
    con.sql(f"""
    CREATE TEMP TABLE px AS
    SELECT Symbol AS symbol, CAST(Date AS DATE) AS date, Close, Volume,
           row_number() OVER (PARTITION BY Symbol ORDER BY Date) AS rn,
           ln(Close / lag(Close) OVER (PARTITION BY Symbol ORDER BY Date)) AS lr
    FROM read_parquet('{ADJ}') WHERE Close > 0
    """)
    con.sql("""
    CREATE TEMP TABLE mkt AS
    SELECT date, median(lr) AS mlr FROM px WHERE lr IS NOT NULL GROUP BY date
    """)
    con.sql("""
    CREATE TEMP TABLE acum AS
    SELECT p.symbol, p.date, p.rn,
           sum(coalesce(p.lr,0) - coalesce(m.mlr,0))
             OVER (PARTITION BY p.symbol ORDER BY p.rn) AS acum
    FROM px p LEFT JOIN mkt m USING (date)
    """)
    # monthly turnover deciles (liquidity match universe)
    con.sql("""
    CREATE TEMP TABLE decile AS
    SELECT symbol, date_trunc('month', date) AS month,
           ntile(10) OVER (PARTITION BY date_trunc('month', date)
                           ORDER BY median(Close * Volume)) AS dec
    FROM px GROUP BY symbol, date_trunc('month', date)
    """)

    iv = ev[(ev["study"] == "post_ca_intimation")
            & ev["car_drift_ex"].notna()].copy()
    # window dates from the event symbol's own calendar
    con.register("iv", iv[["event_id", "symbol", "kind", "rn_ann", "rn_ex",
                           "car_drift_ex"]])
    win = con.sql("""
    SELECT e.event_id, s.date AS d0, x.date AS d1
    FROM iv e
    JOIN px s ON s.symbol = e.symbol AND s.rn = e.rn_ann + 1
    JOIN px x ON x.symbol = e.symbol AND x.rn = e.rn_ex - 1
    """).df()
    iv = iv.merge(win, on="event_id")
    iv["month"] = pd.to_datetime(iv["d0"]).dt.to_period("M").dt.to_timestamp()
    con.register("iv2", iv[["event_id", "symbol", "month", "d0", "d1"]])

    # matched control CARs: same month-decile symbols over the same dates
    ctl = con.sql("""
    WITH edec AS (
      SELECT e.*, d.dec FROM iv2 e
      JOIN decile d ON d.symbol = e.symbol AND d.month = e.month
    ),
    controls AS (
      SELECT e.event_id, e.d0, e.d1, c.symbol AS ctl_symbol
      FROM edec e
      JOIN decile c ON c.month = e.month AND c.dec = e.dec
                    AND c.symbol <> e.symbol
    ),
    car AS (
      SELECT ct.event_id,
             b.acum - a.acum AS ctl_car
      FROM controls ct
      JOIN acum a ON a.symbol = ct.ctl_symbol
        AND a.date = (SELECT max(date) FROM acum z
                      WHERE z.symbol = ct.ctl_symbol AND z.date <= ct.d0)
      JOIN acum b ON b.symbol = ct.ctl_symbol
        AND b.date = (SELECT max(date) FROM acum z
                      WHERE z.symbol = ct.ctl_symbol AND z.date <= ct.d1)
    )
    SELECT event_id, median(ctl_car) AS matched_car, count(*) AS n_ctl
    FROM car GROUP BY 1
    """).df()
    iv = iv.merge(ctl, on="event_id", how="inner")
    iv["excess"] = iv["car_drift_ex"] - iv["matched_car"]
    iv["quarter"] = pd.to_datetime(iv["d0"]).dt.to_period("Q").astype(str)
    print(f"{len(iv)} events with matched controls "
          f"(median controls/event: {iv.n_ctl.median():.0f})")

    hyps = []
    for kind, g in iv.groupby("kind"):
        t, p, nq = quarter_t(g, "excess")
        hyps.append({
            "hypothesis": f"intimation drift ({kind}) vs matched controls",
            "n": len(g), "clusters": nq,
            "effect": g["excess"].mean(), "med": g["excess"].median(),
            "t": t, "p": p})

    # PEAD Q5-Q1, quarter-clustered
    pe = ev[(ev["study"] == "pead_annret") & ev["car_2_63"].notna()].copy()
    pe["q5"] = pe.groupby("quarter")["ann_ret"].transform(
        lambda s: pd.qcut(s, 5, labels=False, duplicates="drop"))
    spread = (pe[pe.q5 == 4].groupby("quarter")["car_2_63"].mean()
              - pe[pe.q5 == 0].groupby("quarter")["car_2_63"].mean()).dropna()
    t, p = stats.ttest_1samp(spread, 0.0)
    hyps.append({"hypothesis": "PEAD ann-ret Q5-Q1 CAR63", "n": len(pe),
                 "clusters": len(spread), "effect": spread.mean(),
                 "med": spread.median(), "t": t, "p": p})

    # PEAD surprise T3-T1 (small n — naive t, flagged)
    sv = ev[(ev["study"] == "pead_surprise") & ev["car_2_63"].notna()].copy()
    if len(sv) >= 30:
        sv["t3"] = pd.qcut(sv["surprise"], 3, labels=False, duplicates="drop")
        a, b = sv[sv.t3 == 2]["car_2_63"], sv[sv.t3 == 0]["car_2_63"]
        t, p = stats.ttest_ind(a, b, equal_var=False)
        hyps.append({"hypothesis": "PEAD surprise T3-T1 CAR63 (naive t)",
                     "n": len(sv), "clusters": np.nan,
                     "effect": a.mean() - b.mean(),
                     "med": a.median() - b.median(), "t": t, "p": p})

    # post-ex drift per kind, quarter-clustered
    ca = ev[(ev["study"] == "post_ca") & ev["car_0_20"].notna()].copy()
    ca["quarter"] = pd.to_datetime(ca["signal_date"]
                                   if "signal_date" in ca else ca["eff_date"]) \
        .dt.to_period("Q").astype(str)
    for kind, g in ca.groupby("kind"):
        t, p, nq = quarter_t(g, "car_0_20")
        hyps.append({"hypothesis": f"post-ex drift 0..+20 ({kind})",
                     "n": len(g), "clusters": nq,
                     "effect": g["car_0_20"].mean(),
                     "med": g["car_0_20"].median(), "t": t, "p": p})

    new = pd.DataFrame(hyps)

    # fold in the stored factor-combo grid p-values
    grid_rows = []
    if os.path.exists(GRID_MD):
        for line in open(GRID_MD):
            m = re.match(r"\| (\S+) \| (.+?) \| \d+ \| \d+ \| [+\-\d.]+ "
                         r"\| [+\-\d.]+ \| ([\d.]+) \|", line)
            if m:
                grid_rows.append({
                    "hypothesis": f"grid: {m.group(1)} {m.group(2)}",
                    "n": np.nan, "clusters": np.nan, "effect": np.nan,
                    "med": np.nan, "t": np.nan, "p": float(m.group(3))})
    fam = pd.concat([new, pd.DataFrame(grid_rows)], ignore_index=True)
    fam = fam.dropna(subset=["p"]).reset_index(drop=True)
    fam["fdr10"] = bh_fdr(fam["p"], 0.10)
    fam["fdr05"] = bh_fdr(fam["p"], 0.05)
    fam = fam.sort_values("p")

    pct = lambda x: f"{x:+.2%}" if pd.notna(x) else "—"  # noqa: E731
    lines = [
        f"# Intimation-drift validation — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "Matched benchmark: each event vs the MEDIAN CAR of same-month,",
        "same-turnover-decile symbols over the identical calendar window",
        f"(median {iv.n_ctl.median():.0f} controls/event). Inference:",
        "calendar-quarter clustered t (events overlap in time).",
        f"FDR family: {len(fam)} hypotheses = {len(new)} event-study tests",
        "+ the factor-combo grid from MULTIPLE_TESTING.md. BH q=0.10/0.05.",
        "",
        "| hypothesis | n | qtrs | mean effect | median | t | p | q=.10 | q=.05 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in fam.iterrows():
        tcell = f"{r.t:+.2f}" if pd.notna(r.t) else "—"
        ncell = f"{int(r.n)}" if pd.notna(r.n) else "—"
        ccell = f"{int(r.clusters)}" if pd.notna(r.clusters) else "—"
        lines.append(
            f"| {r.hypothesis} | {ncell} | {ccell} | {pct(r.effect)} "
            f"| {pct(r.med)} | {tcell} | {r.p:.4f} "
            f"| {'✅' if r.fdr10 else '—'} | {'✅' if r.fdr05 else '—'} |")
    lines += [
        "",
        f"Survivors at q=0.10: {int(fam.fdr10.sum())} / {len(fam)}; "
        f"at q=0.05: {int(fam.fdr05.sum())}.",
        "",
        "claims.yaml policy: only q=0.10 survivors are citable as validated.",
    ]
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {OUT_MD}")
    print(fam[["hypothesis", "effect", "t", "p", "fdr10", "fdr05"]]
          .to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
