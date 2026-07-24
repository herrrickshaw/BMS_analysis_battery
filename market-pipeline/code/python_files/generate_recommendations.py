#!/usr/bin/env python3
"""
generate_recommendations.py — current picks from the SWEEP-TUNED online learned
model (not the weak static Lasso). Trains the online SGD (tuned α per market, η=0.01)
through all history, then ranks the latest liquid cross-section by predicted fwd
return. IN + US first.

Mechanical output of the systematic model for PAPER-TRACK watchlisting — research/
educational, not investment advice. Validate against public sources before use.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.linear_model import SGDRegressor
import strategy_regime_survival as S
from factor_learning import build_xy, FACTORS
from profitability_optimizer import factor_library
from obs import get_logger, DecisionLog

HERE = Path(__file__).resolve().parent
LOG = get_logger("recommendations")
# sweep-optimal hyperparameters (reports/aws_sweep.parquet best per market)
TUNED = {"IN": {"alpha": 2e-4, "eta": 0.01}, "US": {"alpha": 1e-3, "eta": 0.01}}
TOP_N = 15
# heuristic closed-end-fund / ETF exclusion for US (the low-vol tilt surfaces bond/
# loan funds; no us_list.csv on disk to key ISIN/type off, so exclude known funds).
# ⚠️ heuristic — verify instrument type before relying on the US list.
US_FUND_EXCLUDE = {"DBL","CIK","EFR","ISD","VVR","FRA","HGLB","GLDI","KKRT","PDI","PDO",
                   "PTY","JFR","BGT","JQC","EAD","HYT","NCV","NCZ","ACP","DSU","FSCO",
                   "BIT","BGB","GOF","PHK","RA","ECC","OXLC","ARDC","JRO","FCT","BSL","BKT","FXC","MGRE"}


def latest_features(mkt):
    """(symbols, feature matrix) for the latest week's liquid universe."""
    close, turn = S.load_panel(mkt)
    lib = factor_library(close)
    t = close.index[-1]
    liq = S.liquidity_mask(turn.loc[t], close.loc[t])
    univ = close.columns[liq.values]
    feats = np.column_stack([lib[f].loc[t].reindex(univ).values.astype(float) for f in FACTORS])
    ok = np.isfinite(feats).all(axis=1)
    return list(np.array(univ)[ok]), feats[ok], str(t.date())


def main(markets=("IN", "US")) -> int:
    dl = DecisionLog()
    for mkt in markets:
        hp = TUNED[mkt]
        X, y, wk = build_xy(mkt)                          # training panel (valid fwd rets)
        sgd = SGDRegressor(penalty="l1", alpha=hp["alpha"], learning_rate="constant",
                           eta0=hp["eta"], random_state=0)
        for w in wk.unique().sort_values():               # online walk-forward on ALL history
            m = wk == w
            sgd.partial_fit(X[m], y[m])
        syms, Xl, asof = latest_features(mkt)
        pred = sgd.predict(Xl)
        r = pd.Series(pred, index=syms).sort_values(ascending=False)
        if mkt == "US":                                   # drop known closed-end funds/ETFs
            r = r[~r.index.astype(str).str.upper().isin(US_FUND_EXCLUDE)]
        top = r.head(TOP_N)
        z = (top - r.mean()) / r.std()                    # standardised conviction
        print(f"\n=== {mkt} — top {TOP_N} picks (sweep-tuned online model, α={hp['alpha']}, "
              f"η={hp['eta']}) · as-of {asof} · {len(r)} names ranked ===")
        for i, (s, v) in enumerate(top.items(), 1):
            print(f"  {i:>2}. {str(s):<12} pred_fwd {v*100:+.2f}%  (z {z[s]:+.1f})")
        dl.record("recommendations", market=mkt, asof=asof, model="online_sgd_tuned",
                  alpha=hp["alpha"], eta=hp["eta"], picks=[str(s) for s in top.index],
                  n_ranked=len(r))
        top.to_frame("pred_fwd_ret").to_csv(HERE / "reports" / f"recs_{mkt}.csv")
    print("\nwrote reports/recs_{IN,US}.csv  ·  paper-track only, not investment advice")
    return 0


if __name__ == "__main__":
    mk = tuple(sys.argv[1].split(",")) if len(sys.argv) > 1 else ("IN", "US")
    raise SystemExit(main(mk))
