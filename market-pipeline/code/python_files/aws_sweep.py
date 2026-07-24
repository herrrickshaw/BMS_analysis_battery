#!/usr/bin/env python3
"""
aws_sweep.py — the heavy joint hyperparameter sweep worth running on AWS.

Grid: Lasso α × online learning-rate η × portfolio vol-target, per market, each
cell a walk-forward out-of-sample evaluation of the online learned model + risk
overlay. ~5 markets × 4 α × 3 η × 3 vol-target = 180 cells, each a full walk-
forward — parallelised across cores (multiprocessing). Finds the OOS-Sharpe-max
hyperparameters per market.

Env: MARKET_WH (data path), MARKET_LOGDIR (logs), SWEEP_OUT (results parquet).
Runs headless; writes SWEEP_OUT and prints the per-market winners.
"""
from __future__ import annotations
import os, json, itertools, warnings
from pathlib import Path
import numpy as np, pandas as pd
from multiprocessing import Pool, cpu_count
from sklearn.linear_model import SGDRegressor
from sklearn.exceptions import ConvergenceWarning
warnings.simplefilter("ignore", ConvergenceWarning)

import strategy_regime_survival as S
from factor_learning import build_xy, ls_book_ir
from obs import get_logger

LOG = get_logger("aws_sweep")
ALPHAS = [2e-4, 5e-4, 1e-3, 2e-3]
ETAS = [1e-4, 1e-3, 1e-2]
VOLTGT = [0.08, 0.10, 0.15]
OUT = Path(os.environ.get("SWEEP_OUT", Path(__file__).resolve().parent / "reports" / "aws_sweep.parquet"))

_CACHE: dict = {}          # market -> (X, y, wk)  built once, reused across cells


def data(mkt):
    if mkt not in _CACHE:
        _CACHE[mkt] = build_xy(mkt)
    return _CACHE[mkt]


def eval_cell(args):
    mkt, alpha, eta, vt = args
    X, y, wk = data(mkt)
    weeks = wk.unique().sort_values()
    cut = weeks[int(len(weeks) * 0.6)]
    te = wk > cut
    sgd = SGDRegressor(penalty="l1", alpha=alpha, learning_rate="constant",
                       eta0=eta, random_state=0)
    preds = []
    for w in weeks:
        m = wk == w
        if w <= cut:
            sgd.partial_fit(X[m], y[m])
        else:
            preds.append(sgd.predict(X[m])); sgd.partial_fit(X[m], y[m])
    if not preds:
        return None
    # OOS long/short book, then vol-target the weekly series to `vt`
    df = pd.DataFrame({"p": np.concatenate(preds), "y": y[te]}, index=wk[te])
    rets = []
    for _, g in df.groupby(df.index):
        if len(g) < 30:
            continue
        hi = g.p >= g.p.quantile(2/3); lo = g.p <= g.p.quantile(1/3)
        if hi.sum() and lo.sum():
            rets.append(0.5*g.y[hi].mean() - 0.5*g.y[lo].mean())
    r = pd.Series(rets)
    if len(r) < 8 or r.std() == 0:
        return None
    realized = r.rolling(13, min_periods=6).std() * np.sqrt(S.ANN)
    scaled = r * (vt / realized).clip(upper=3.0).fillna(1.0)
    eq = (1 + scaled).cumprod(); maxdd = (eq/eq.cummax() - 1).min()
    ir = scaled.mean() / scaled.std() * np.sqrt(S.ANN) if scaled.std() else np.nan
    return {"market": mkt, "alpha": alpha, "eta": eta, "vol_target": vt,
            "oos_ir": round(float(ir), 3), "oos_maxdd": round(float(maxdd*100), 1),
            "oos_ann_ret": round(float(scaled.mean()*S.ANN*100), 2)}


def main():
    cells = list(itertools.product(S.MARKETS, ALPHAS, ETAS, VOLTGT))
    nproc = max(1, min(cpu_count() - 1, 16))
    LOG.info(f"sweep: {len(cells)} cells across {len(S.MARKETS)} markets on {nproc} procs "
             f"(WH={S.WH})")
    # build data caches serially (parallel workers each rebuild their own cache)
    results = []
    with Pool(nproc) as pool:
        for i, res in enumerate(pool.imap_unordered(eval_cell, cells), 1):
            if res:
                results.append(res)
            if i % 20 == 0:
                LOG.info(f"  {i}/{len(cells)} cells done")
    df = pd.DataFrame(results)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    LOG.info(f"wrote {OUT} ({len(df)} cells)")
    print("\n=== best hyperparameters per market (max OOS IR) ===")
    best = df.loc[df.groupby("market")["oos_ir"].idxmax()] if not df.empty else df
    print(best.to_string(index=False))
    for _, r in best.iterrows():
        LOG.info(f"BEST {r.market}: α={r.alpha} η={r.eta} vt={r.vol_target} "
                 f"-> OOS IR {r.oos_ir}, maxDD {r.oos_maxdd}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
