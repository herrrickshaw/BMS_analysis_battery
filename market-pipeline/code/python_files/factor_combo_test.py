#!/usr/bin/env python3
"""
factor_combo_test.py — does Piotroski work, and do combinations work BETTER?

THE QUESTION
------------
Three things, in order:
  1. Does the Piotroski filter earn a benchmark-adjusted excess return at all?
  2. Does Piotroski + ROCE beat Piotroski alone?
  3. Does adding a debt-cycle condition beat that?

WHAT THIS CAN AND CANNOT ESTABLISH — read before believing any number
---------------------------------------------------------------------
1. INTERSECTIONS COLLAPSE THE SAMPLE. Over 68,003 US symbol-years, `piotroski`
   fires 1,590 times and `roce_plus` 693. Their intersection is necessarily
   smaller than either, and the triple smaller still. A combination that "wins"
   on 30 observations has told you nothing. Every result below is printed with
   its n, and anything under MIN_N is refused rather than reported.

2. STOCK-YEARS ARE NOT INDEPENDENT. Everything co-moves within a year, so 1,590
   stock-years is nowhere near 1,590 independent draws. A naive t-test on pooled
   rows would overstate significance by roughly sqrt(stocks-per-year). This
   clusters by year: the year means are the observations, and there are only 9.
   Nine. That is the real sample size, and it is why nothing here can be
   "significant" in a way worth trading on.

3. SURVIVORSHIP. The fundamentals come from filers that still exist. Companies
   that went bust have prices but no statements and silently leave the scored
   universe — exactly the names a quality screen should have avoided. This
   flatters every filter, and flatters the WEAK ones most.

4. THE PRIOR IS THAT THIS FAILS. This repo has already recorded that US
   Piotroski is INVERTED (high-F underperforms) and that a "Piotroski dominates
   all 7 markets" claim was a variance artefact on 272 stocks. A result here
   agreeing with those should be believed more readily than one overturning them.

So: this can REJECT a filter that fails badly. It cannot ENDORSE one that wins.

    python factor_combo_test.py                 # US, 252d horizon
    python factor_combo_test.py --horizon 63
    python factor_combo_test.py --panel cache_seed/factorial_symbol_year_table_IN_full.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_PANEL = HERE / "cache_seed" / "factorial_symbol_year_table_us.parquet"

# Below this, a cell is reported as UNTESTABLE rather than given a number. An
# average over a handful of stock-years is an anecdote with a decimal point.
MIN_N = 40
MIN_YEARS = 4

# The combinations the question actually asks about, plus controls.
COMBOS = [
    ("ALL (baseline)",                       []),
    ("piotroski",                            ["piotroski"]),
    ("roce_plus",                            ["roce_plus"]),
    ("piotroski + roce_plus",                ["piotroski", "roce_plus"]),
    ("debt_reduction",                       ["debt_reduction"]),
    ("piotroski + debt_reduction",           ["piotroski", "debt_reduction"]),
    ("roce_plus + debt_reduction",           ["roce_plus", "debt_reduction"]),
    ("piotroski + roce_plus + debt_reduction", ["piotroski", "roce_plus", "debt_reduction"]),
    # Controls: if an unrelated filter scores like the quality ones, the quality
    # result is measuring the universe, not quality.
    ("not_distress (control)",               ["not_distress"]),
    ("low_asset_growth (control)",           ["low_asset_growth"]),
]


def year_clustered(df: pd.DataFrame, col: str) -> dict:
    """Mean excess return with the YEAR as the unit of observation.

    Pooling stock-years and running a t-test treats co-moving stocks as
    independent draws and inflates t by roughly sqrt(stocks per year). Averaging
    within year first, then testing across years, is the cheap honest fix — and
    it makes the true sample size (the year count) impossible to hide.
    """
    if df.empty or col not in df:
        return {}
    # MEDIAN within year, not mean. xret is right-skewed to an extreme degree
    # (median -9.4pp, mean -3.6pp, max +7,564pp — a single 75-bagger). On a cell
    # of 59 observations one such name IS the result. The median asks "what
    # happened to a typical pick", which is the question a screen is making a
    # claim about.
    per_year = df.groupby("year")[col].median().dropna()
    n_years = len(per_year)
    if n_years < 2:
        return {"n_years": n_years}
    m = float(per_year.mean())
    sd = float(per_year.std(ddof=1))
    se = sd / np.sqrt(n_years) if sd > 0 else np.nan
    t = m / se if se and se == se and se != 0 else np.nan
    return {"mean": m, "n_years": n_years, "se": se, "t": t,
            "years_positive": int((per_year > 0).sum()),
            "pooled_mean": float(df[col].mean()),
            "pooled_median": float(df[col].median()),
            "top1_share": _top1_share(df[col])}


def _top1_share(s: pd.Series) -> float:
    """How much of the cell's total excess return comes from its single best name.

    A cell where one stock supplies most of the aggregate is not evidence of a
    repeatable filter, however large the mean. Reported so that cannot hide.
    """
    v = s.dropna()
    if len(v) < 2:
        return float("nan")
    tot = v.sum()
    return float(v.max() / tot) if tot > 0 else float("nan")


def run(panel: Path, horizon: int, min_liq: Optional[float]) -> int:
    if not panel.exists():
        print(f"panel not found: {panel}", file=sys.stderr)
        return 1
    d = pd.read_parquet(panel)
    xcol = f"xret_T+{horizon}d"
    if xcol not in d.columns:
        print(f"no column {xcol}; have {[c for c in d.columns if c.startswith('xret')]}")
        return 1

    d = d[d[xcol].notna()].copy()
    if min_liq is not None and "log_liquidity" in d.columns:
        before = len(d)
        d = d[d["log_liquidity"] >= min_liq]
        print(f"  liquidity gate: log_liquidity >= {min_liq} kept {len(d):,}/{before:,}")

    print("=" * 78)
    print(f"  FACTOR COMBINATION TEST — {panel.name}")
    print(f"  horizon {horizon}d, benchmark-adjusted excess return (xret)")
    print("=" * 78)
    base = year_clustered(d, xcol)
    print(f"  universe: {len(d):,} symbol-years across {d['year'].nunique()} years "
          f"({int(d['year'].min())}-{int(d['year'].max())})")
    print(f"  baseline median xret: {base.get('mean', float('nan')):+.2f}pp "
          f"(all figures are PERCENTAGE POINTS vs benchmark)\n")

    print(f"  {'combination':<40} {'n':>7} {'yrs':>4} {'med xret':>9} "
          f"{'vs base':>8} {'t':>6} {'yrs+':>6} {'top1':>7}")
    print("  " + "-" * 76)

    results = []
    for name, flags in COMBOS:
        sub = d
        for f in flags:
            if f not in d.columns:
                sub = d.iloc[0:0]
                break
            sub = sub[sub[f].fillna(False).astype(bool)]
        n = len(sub)
        st = year_clustered(sub, xcol)
        if n < MIN_N or st.get("n_years", 0) < MIN_YEARS:
            print(f"  {name:<40} {n:>7} {st.get('n_years', 0):>4} "
                  f"{'UNTESTABLE — below MIN_N/MIN_YEARS':>36}")
            results.append({"combo": name, "n": n, "testable": False})
            continue
        edge = st["mean"] - base["mean"]
        print(f"  {name:<40} {n:>7} {st['n_years']:>4} {st['mean']:>+9.2f} "
              f"{edge:>+8.2f} {st['t']:>6.2f} {st['years_positive']:>3}/{st['n_years']} "
              f"{st['top1_share']*100 if st['top1_share']==st['top1_share'] else float('nan'):>6.0f}%")
        results.append({"combo": name, "n": n, "n_years": st["n_years"],
                        "mean": st["mean"], "edge": edge, "t": st["t"],
                        "years_positive": st["years_positive"], "testable": True})

    print()
    print("  READING THIS TABLE")
    print("  ------------------")
    print("  'yrs' is the REAL sample size — the number of annual observations, not n.")
    print("  |t| < 2 on ~9 years is indistinguishable from noise. Treat 'yrs+' (how many")
    print("  years the edge was positive) as more informative than t: a filter that wins")
    print("  in 8 of 9 years is more credible than one with a big mean from one year.")
    print("  Survivorship inflates every row; the baseline is inflated too, so the")
    print("  'vs base' column is the more trustworthy comparison.")
    print("  'top1' is the share of the cell's total excess return contributed by its")
    print("  single best name. Above ~30% the cell is one lucky stock, not a filter.")
    return 0, pd.DataFrame(results)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", default=str(DEFAULT_PANEL))
    ap.add_argument("--horizon", type=int, default=252,
                    choices=[5, 21, 63, 126, 252])
    ap.add_argument("--min-liquidity", type=float, default=None,
                    help="log_liquidity floor; the repo's edge is illiquidity-linked, "
                         "so results move a lot with this")
    ap.add_argument("--out", help="write the result table to CSV")
    a = ap.parse_args()
    rc, tbl = run(Path(a.panel), a.horizon, a.min_liquidity)
    if a.out and tbl is not None:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        tbl.to_csv(a.out, index=False)
        print(f"\n  → {a.out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
