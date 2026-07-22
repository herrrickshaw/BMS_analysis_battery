#!/usr/bin/env python3
"""Multiple-testing control for the strategy x market grid.

The estate has tested ~11 strategies across 7 markets — 100+ implicit
hypotheses — and historically headlined raw t-stats ("Piotroski dominates
all 7 markets" was a 272-stock variance claim later refuted). This module
makes survival-under-FDR the citable standard:

  * Benjamini-Hochberg FDR across the ENTIRE grid (all combos, all
    markets pooled — not per-file, which would understate the search).
  * Deflated Sharpe ratio (Bailey & Lopez de Prado 2014) helper for any
    analysis that has a returns series.

Run:  python3 multiple_testing.py          # scans reports/factor_combo_*.csv
Out:  reports/MULTIPLE_TESTING.md

Claims policy (claims.yaml in global-market-data): a grid result is
citable as 'validated' only if it survives BH-FDR at q=0.10 here.
"""
import glob
import math
import os
import re
from datetime import datetime

import pandas as pd
from scipy import stats

BASE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.join(BASE, "reports")
OUT_MD = os.path.join(REPORTS, "MULTIPLE_TESTING.md")


def bh_fdr(pvals, q=0.10):
    """Benjamini-Hochberg: returns boolean survivors for FDR level q."""
    s = pd.Series(pvals).dropna().sort_values()
    m = len(s)
    thresh = pd.Series([(i + 1) / m * q for i in range(m)], index=s.index)
    passed = s <= thresh
    if not passed.any():
        return pd.Series(False, index=pd.Series(pvals).index)
    cutoff = s[passed].max()
    return pd.Series(pvals).le(cutoff)


def deflated_sharpe(sr, n_trials, n_obs, skew=0.0, kurt=3.0, sr_var=None):
    """Probability the observed Sharpe exceeds the max expected from
    n_trials of noise (Bailey & Lopez de Prado 2014). Returns DSR in [0,1];
    cite only DSR > 0.95."""
    if sr_var is None:
        sr_var = (1 - skew * sr + (kurt - 1) / 4 * sr**2) / (n_obs - 1)
    emc = 0.5772156649
    max_z = (1 - emc) * stats.norm.ppf(1 - 1.0 / n_trials) \
        + emc * stats.norm.ppf(1 - 1.0 / (n_trials * math.e))
    sr0 = math.sqrt(sr_var) * max_z
    return stats.norm.cdf((sr - sr0) * math.sqrt(n_obs - 1)
                          / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr**2))


def main():
    rows = []
    for path in sorted(glob.glob(os.path.join(REPORTS, "factor_combo_*.csv"))):
        market = re.search(r"factor_combo_(\w+?)_", os.path.basename(path))
        market = market.group(1).upper() if market else "?"
        df = pd.read_csv(path)
        if not {"combo", "t", "n_years"}.issubset(df.columns):
            continue
        df = df[df.get("testable", True) == True]  # noqa: E712
        for _, r in df.iterrows():
            if r["combo"].startswith("ALL"):
                continue  # baseline, not a hypothesis
            dof = max(int(r["n_years"]) - 1, 1)
            p = 2 * stats.t.sf(abs(r["t"]), dof)
            rows.append({"market": market, "combo": r["combo"],
                         "n": int(r["n"]), "years": r["n_years"],
                         "edge": r.get("edge"), "t": r["t"], "p": p})
    grid = pd.DataFrame(rows)
    if grid.empty:
        print("no factor_combo files with t-stats found")
        return
    grid["fdr10"] = bh_fdr(grid["p"], q=0.10)
    grid["fdr05"] = bh_fdr(grid["p"], q=0.05)
    grid = grid.sort_values("p")

    surv = grid[grid.fdr10]
    lines = [
        f"# Multiple-testing control — generated {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Grid: {len(grid)} strategy-market hypotheses pooled from "
        f"factor_combo_*.csv. Family-wide BH-FDR. **Only q=0.10 survivors "
        "are citable** (claims.yaml policy). t-stats use n_years-1 dof "
        "(annual observations — conservative).",
        "",
        f"Survivors: **{int(grid.fdr10.sum())} at q=0.10**, "
        f"{int(grid.fdr05.sum())} at q=0.05, of {len(grid)} tested.",
        "",
        "| market | combo | n | yrs | edge | t | p | FDR q=.10 | q=.05 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in grid.iterrows():
        lines.append(
            f"| {r.market} | {r.combo} | {r.n} | {r.years:.0f} "
            f"| {r.edge:+.1f} | {r.t:+.2f} | {r.p:.4f} "
            f"| {'✅' if r.fdr10 else '—'} | {'✅' if r.fdr05 else '—'} |")
    lines += ["",
              "Interpretation: a — in the FDR column does not mean the effect "
              "is zero; it means this grid, searched this widely, cannot "
              "distinguish it from selection noise. Deflated-Sharpe helper "
              "(`deflated_sharpe`) is available for analyses with full "
              "return series."]
    with open(OUT_MD, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {OUT_MD}: {int(grid.fdr10.sum())}/{len(grid)} survive q=0.10")
    print(surv[["market", "combo", "edge", "t", "p"]].to_string(index=False))


if __name__ == "__main__":
    main()
