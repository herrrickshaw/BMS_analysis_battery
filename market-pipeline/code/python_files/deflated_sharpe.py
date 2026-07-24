#!/usr/bin/env python3
"""
deflated_sharpe.py — the overfitting guard the methodology (López de Prado, "The
Deflated Sharpe Ratio", 2014) requires when a strategy is SELECTED as the best of
many trials.

profitability_optimizer.py picked, per (market, regime), the best of 10 factors by
information ratio. Selecting the max of N noisy trials inflates the winner's Sharpe
even if none has real edge. This computes:

  E[max SR]  the Sharpe you'd EXPECT from the best of N random trials (given the
             spread of the trial Sharpes) — the selection-bias benchmark.
  DSR        P(true SR > that benchmark) for the chosen factor. DSR > 0.95 ⇒ the
             winner survives the multiple-testing correction; below ⇒ likely a fluke.

Uses the trial info ratios in reports/profitability_optimizer.csv (annualised;
un-annualised to per-2wk for the test). Near-normal returns assumed (skew≈0),
noted as a caveat.

Output: reports/deflated_sharpe.md + reports/deflated_sharpe.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
from math import e
try:
    from scipy.stats import norm
    Zinv, Phi = norm.ppf, norm.cdf
except Exception:                                   # scipy-free fallback
    from statistics import NormalDist
    _N = NormalDist()
    Zinv, Phi = _N.inv_cdf, _N.cdf

import strategy_regime_survival as S
from obs import get_logger, DecisionLog

HERE = Path(__file__).resolve().parent
LOG = get_logger("deflated_sharpe")
GAMMA = 0.5772156649015329                          # Euler-Mascheroni


def expected_max_sr(trial_srs) -> float:
    """López de Prado E[max SR] from N independent trials given their dispersion."""
    trials = np.asarray([s for s in trial_srs if np.isfinite(s)])
    N = len(trials)
    if N < 2:
        return float("nan")
    v = trials.std(ddof=1)
    return v * ((1 - GAMMA) * Zinv(1 - 1.0 / N) + GAMMA * Zinv(1 - 1.0 / (N * e)))


def dsr(sr_best, trial_srs, T, skew=0.0, kurt=3.0) -> float:
    """Deflated Sharpe: P(true SR > E[max SR]) for the selected strategy."""
    emax = expected_max_sr(trial_srs)
    if not np.isfinite(emax) or T < 3:
        return float("nan")
    denom = np.sqrt(1 - skew * sr_best + (kurt - 1) / 4.0 * sr_best ** 2)
    return float(Phi((sr_best - emax) * np.sqrt(T - 1) / denom))


def main() -> int:
    dl = DecisionLog()
    csv = HERE / "reports" / "profitability_optimizer.csv"
    if not csv.exists():
        LOG.error("run profitability_optimizer.py first"); return 1
    df = pd.read_csv(csv)
    A = np.sqrt(S.ANN)                              # annualise factor (IR = SR·√26)
    rows = []
    for mkt in S.MARKETS:
        for regime in ("bull", "bear"):
            m = df[(df.market == mkt) & (df.regime == regime)].dropna(subset=["info_ratio"])
            if len(m) < 2:
                continue
            trials_sr = (m.info_ratio / A).values              # per-2wk Sharpe of each trial
            best = m.loc[m.info_ratio.idxmax()]
            sr_best = best.info_ratio / A
            T = float(best["n"])                               # formation weeks
            emax = expected_max_sr(trials_sr)
            d = dsr(sr_best, trials_sr, T)
            survives = np.isfinite(d) and d >= 0.95
            rows.append({"market": mkt, "regime": regime, "chosen": best.factor,
                         "n_trials": len(m), "T_weeks": int(T),
                         "IR_chosen": round(best.info_ratio, 2),
                         "IR_exp_max": round(emax * A, 2),
                         "DSR": round(d, 3), "survives_0.95": survives})
            LOG.info(f"{mkt} {regime}: chose {best.factor} IR {best.info_ratio:.2f} vs "
                     f"E[max] {emax*A:.2f} of {len(m)} trials -> DSR {d:.2f} "
                     f"{'PASS' if survives else 'FAIL'}")
            dl.record("deflated_sharpe", market=mkt, regime=regime, chosen=best.factor,
                      ir_chosen=round(best.info_ratio, 2), ir_exp_max=round(emax * A, 2),
                      dsr=round(d, 3), survives=bool(survives))
    out = pd.DataFrame(rows)
    out.to_csv(HERE / "reports" / "deflated_sharpe.csv", index=False)

    npass = int(out["survives_0.95"].sum())
    L = ["# Deflated Sharpe — multiple-testing correction on the factor optimiser", "",
         "Each desk×regime picks the best of 10 factors → selection bias. `IR_exp_max` "
         "is the info ratio you'd expect from the best of that many random trials; `DSR` "
         "is P(the chosen factor's true edge beats that benchmark). **DSR ≥ 0.95 passes.**",
         "", f"**{npass} of {len(out)} selected factors survive the correction.**", "",
         "| market | regime | chosen | trials | IR chosen | IR exp-max | DSR | verdict |",
         "|---|---|---|--:|--:|--:|--:|---|"]
    for _, r in out.iterrows():
        L.append(f"| {r.market} | {r.regime} | {r.chosen} | {r.n_trials} | {r['IR_chosen']} | "
                 f"{r['IR_exp_max']} | {r.DSR} | {'✅ real' if r['survives_0.95'] else '⚠️ fragile'} |")
    L += ["", "> DSR near 1 ⇒ the winner clears the bar set by trying 10 factors — a real "
          "edge, not the luckiest draw. Fragile cells (DSR < 0.95) should be treated as "
          "unproven and defaulted to the incumbent rule, or re-tested out-of-sample. "
          "Near-normal returns assumed (skew≈0); the AWS run can plug in realised "
          "skew/kurtosis per factor. Not investment advice."]
    (HERE / "reports" / "deflated_sharpe.md").write_text("\n".join(L))
    print("\n".join(L))
    print("\nwrote reports/deflated_sharpe.{md,csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
