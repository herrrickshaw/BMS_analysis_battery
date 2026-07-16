#!/usr/bin/env python3
"""
regime_price_model_cross_market.py — step back from screener filtering
entirely and ask a different question: on the FULL stock universe of each
market (India, US, Japan, Korea — all four with real 10.5y OHLCV), does
PRICE ACTION ITSELF (consolidation mean-reversion, breakout/breakdown
momentum) carry information, and does the ANSWER differ by market?

Framing (per the request this script responds to): a screener like
Piotroski is a BINNING strategy — it sorts stocks into pass/fail buckets
using accounting fundamentals, on the premise that quality mean-reverts to
fair value. A screener like Darvas is also a binning strategy, but on the
premise that a confirmed breakout continues (momentum/sentiment). Both are
assumptions about how a market "should" price stocks. This script instead
fits the two behaviors directly from price (no fundamentals, no binning)
and asks, PER MARKET:
  kappa  (consolidation error-correction strength) — a market where price
         reliably reverts toward the recent trading range's midpoint is
         behaving like Piotroski's premise: value gravity, price anchored
         to something.
  phi's  (breakout/breakdown momentum persistence) — a market where a
         confirmed break continues is behaving like Darvas's premise:
         sentiment/speculative flow, not mean-reversion.
If a market shows neither (kappa and phi indistinguishable from zero, as
found for India's biggest 400 names in the prior run), that market's price
action doesn't obviously validate either screener philosophy at the
single-day-ahead horizon tested — screeners may still work through OTHER
mechanisms (longer horizons, cross-sectional ranking, fundamentals genuinely
priced in over quarters not days) that this single-day setup cannot see.

Same model as regime_price_model.py (mean-reversion OLS for IN_BOX,
momentum OLS for BREAKOUT/BREAKDOWN, both closed-form per [ICCT15]'s
finding), same train<=2023/test>=2024 split — but now with (a) the FULL
stock universe per market (no symbol cap) and (b) OLS standard errors /
t-stats on the coefficients, since the question here is about the sign and
reliability of kappa/phi themselves, not just prediction accuracy.
"""
from __future__ import annotations

import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import regime_price_model as rpm

MARKETS = ["IN", "US", "JP", "KR"]


def _ols_with_inference(X: np.ndarray, y: np.ndarray) -> dict:
    Xb = np.column_stack([np.ones(len(X)), X])
    theta, *_ = np.linalg.lstsq(Xb, y, rcond=None)
    resid = y - Xb @ theta
    n, k = Xb.shape
    dof = max(n - k, 1)
    sigma2 = float(np.sum(resid ** 2) / dof)
    try:
        XtX_inv = np.linalg.inv(Xb.T @ Xb)
        se = np.sqrt(np.diag(sigma2 * XtX_inv))
        tstat = theta / np.where(se > 0, se, np.nan)
    except np.linalg.LinAlgError:
        se = np.full(len(theta), np.nan)
        tstat = np.full(len(theta), np.nan)
    return {"theta": theta, "se": se, "tstat": tstat, "n": n, "resid_std": float(np.sqrt(sigma2))}


def fit_market(market: str, symbol_cap: int | None = None) -> dict:
    print(f"\n[{market}] building feature panel (full universe, cap={symbol_cap})...")
    data = rpm.build_dataset(symbol_cap=symbol_cap, market=market)
    if data.empty:
        return {"market": market, "error": "no data"}
    print(f"[{market}] {len(data)} symbol-days, {data['symbol'].nunique()} symbols")
    state_dist = data["state"].value_counts(normalize=True).round(4).to_dict()

    data["date"] = pd.to_datetime(data["date"])
    train = data[data["date"] <= rpm.TRAIN_END]
    test = data[data["date"] >= rpm.TEST_START]

    box_train = train[train["state"] == "IN_BOX"].dropna(subset=["pos_in_box"])
    Xa = (0.5 - box_train["pos_in_box"].values).reshape(-1, 1)
    fit_a = _ols_with_inference(Xa, box_train["r_fwd"].values)

    mom_train = train[train["state"].isin(["BREAKOUT", "BREAKDOWN"])].dropna(
        subset=["magnitude", "r_t", "r_tm1", "r_tm2"])
    Xb_ = mom_train[["r_t", "r_tm1", "r_tm2", "magnitude"]].values
    fit_b = _ols_with_inference(Xb_, mom_train["r_fwd"].values)

    def _score_test(sub_state_filter, theta, cols):
        sub = test[test["state"].isin(sub_state_filter)].dropna(subset=cols)
        if len(sub) < 20:
            return None
        Xt = sub[cols].values if len(cols) > 1 else (0.5 - sub["pos_in_box"].values).reshape(-1, 1)
        pred = rpm._predict(Xt, theta, market)   # clamped to this market's real circuit-breaker bound
        y = sub["r_fwd"].values
        rmse_model = float(np.sqrt(np.mean((y - pred) ** 2)))
        rmse_naive = float(np.sqrt(np.mean(y ** 2)))
        dir_acc = float(np.mean(np.sign(pred) == np.sign(y)))
        return {"n": int(len(y)), "dir_acc": round(dir_acc, 4),
                "skill_vs_naive_pct": round((1 - rmse_model / rmse_naive) * 100, 3) if rmse_naive else None}

    consolidation_test = _score_test(["IN_BOX"], fit_a["theta"], ["pos_in_box"])
    momentum_test = _score_test(["BREAKOUT", "BREAKDOWN"], fit_b["theta"], ["r_t", "r_tm1", "r_tm2", "magnitude"])

    kappa, kappa_se, kappa_t = fit_a["theta"][1], fit_a["se"][1], fit_a["tstat"][1]
    phi_names = ["phi0", "phi_r_t", "phi_r_tm1", "phi_r_tm2", "phi_magnitude"]
    phi = {name: {"coef": round(float(fit_b["theta"][i]), 6),
                   "se": round(float(fit_b["se"][i]), 6),
                   "tstat": round(float(fit_b["tstat"][i]), 2)}
           for i, name in enumerate(phi_names)}

    return {
        "market": market, "n_symbols": int(data["symbol"].nunique()),
        "n_total": len(data), "n_train": len(train), "n_test": len(test),
        "state_distribution": state_dist,
        "kappa_mean_reversion": {"coef": round(float(kappa), 6), "se": round(float(kappa_se), 6),
                                  "tstat": round(float(kappa_t), 2), "n_train": fit_a["n"]},
        "phi_momentum": phi, "n_train_momentum": fit_b["n"],
        "test_consolidation": consolidation_test,
        "test_momentum": momentum_test,
        "circuit_bound_pct": rpm.CIRCUIT_BOUND_PCT.get(market, 20.0),
    }


def main():
    results = []
    for m in MARKETS:
        try:
            r = fit_market(m, symbol_cap=None)
        except Exception as e:
            r = {"market": m, "error": str(e)}
        results.append(r)
        print(f"\n[{m}] DONE:")
        import json
        print(json.dumps(r, indent=2, default=str))

    out = pd.DataFrame(results)
    out.to_json("cache_seed/regime_cross_market_results.json", orient="records", indent=2)
    print("\n\n" + "=" * 78)
    print("CROSS-MARKET SUMMARY")
    print("=" * 78)
    for r in results:
        if "error" in r:
            print(f"{r['market']}: ERROR {r['error']}")
            continue
        k = r["kappa_mean_reversion"]
        p = r["phi_momentum"]["phi_r_t"]
        print(f"\n{r['market']}  ({r['n_symbols']} symbols, {r['n_total']} symbol-days)")
        print(f"  state mix: {r['state_distribution']}")
        print(f"  kappa (consolidation mean-reversion): {k['coef']:+.6f}  "
              f"(se={k['se']:.6f}, t={k['tstat']:+.2f})")
        print(f"  phi_r_t (momentum, 1-day-lag persistence): {p['coef']:+.6f}  "
              f"(se={p['se']:.6f}, t={p['tstat']:+.2f})")
        if r["test_consolidation"]:
            print(f"  OOS consolidation: dir_acc={r['test_consolidation']['dir_acc']:.3f}  "
                  f"skill={r['test_consolidation']['skill_vs_naive_pct']:+.3f}%")
        if r["test_momentum"]:
            print(f"  OOS momentum: dir_acc={r['test_momentum']['dir_acc']:.3f}  "
                  f"skill={r['test_momentum']['skill_vs_naive_pct']:+.3f}%")


if __name__ == "__main__":
    main()
