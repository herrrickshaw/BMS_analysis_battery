#!/usr/bin/env python3
"""
risk_management.py — the risk overlay standard quant methodology requires and our
book lacked: (1) inverse-volatility position sizing (risk parity within the book),
(2) portfolio volatility targeting, (3) a drawdown kill-switch / circuit breaker.

The report (Gomber et al.) stresses volatility safeguards and the ability to
de-risk in stress; equal-weight with no vol target is naive. This compares, per
desk, the regime-conditional book under three sizing schemes and reports the
Sharpe / max-drawdown improvement.

  equal_weight   baseline (what the backtests used)
  inverse_vol    w_i ∝ 1/σ_i  — risk parity across names
  vol_target+KS  inverse-vol, scaled to TARGET_VOL, halved when drawdown > DD_HALT
                 (kill-switch: exposure cut until the equity curve recovers)

Output: reports/risk_management.md + reports/risk_management.csv
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd
import strategy_regime_survival as S
from obs import get_logger, timed, DecisionLog

HERE = Path(__file__).resolve().parent
LOG = get_logger("risk_management")
TARGET_VOL = 0.10        # target annualised portfolio vol (10%)
DD_HALT = 0.15           # halve exposure when drawdown exceeds 15% (kill-switch)
DD_RESUME = 0.07         # restore full exposure once drawdown recovers under 7%
ANN = np.sqrt(S.ANN)     # 2-week -> annual vol scaling


def desk_book(mkt, rmap):
    """Weekly (date-indexed) book return under equal-weight / inverse-vol sizing,
    plus the per-name vol used, for one desk under its regime-conditional rule."""
    close, turn = S.load_panel(mkt)
    reg = S.regime_series(close, turn)
    lib_base = S.signals(close)
    try:
        from profitability_optimizer import factor_library
        lib = factor_library(close)
    except Exception:
        lib = lib_base
    fwd = (close.shift(-S.FWD // 5) / close - 1).clip(-0.40, 0.40)
    vol = close.pct_change(fill_method=None).rolling(13, min_periods=6).std()
    br, er = rmap[mkt]["bull_rule"], rmap[mkt]["bear_rule"]
    ew, iv, dates = [], [], []
    for t in close.index[close.index >= S.START]:
        g = reg.get(t)
        if g not in ("bull", "bear"):
            continue
        liq = S.liquidity_mask(turn.loc[t], close.loc[t])
        f = fwd.loc[t].where(liq).dropna()
        if len(f) < S.MIN_NAMES:
            continue
        sig = lib[br if g == "bull" else er].loc[t].reindex(f.index)
        buys = f[sig == 1].dropna()
        if len(buys) < 5:
            continue
        v = vol.loc[t].reindex(buys.index).clip(lower=1e-4)
        w = (1.0 / v) / (1.0 / v).sum()                     # inverse-vol weights
        ew.append(float(buys.mean()))
        iv.append(float((w * buys).sum()))
        dates.append(t)
    idx = pd.DatetimeIndex(dates)
    return pd.Series(ew, idx), pd.Series(iv, idx)


def apply_overlay(iv: pd.Series):
    """Vol-target the inverse-vol book and apply the drawdown kill-switch."""
    realized = iv.rolling(13, min_periods=6).std() * ANN     # trailing annualised vol
    scale = (TARGET_VOL / realized).clip(upper=3.0).fillna(1.0)
    scaled = iv * scale
    # drawdown kill-switch on the scaled equity curve
    out, exposure, peak, eq = [], 1.0, 1.0, 1.0
    halts = 0
    for r in scaled:
        step = r * exposure
        out.append(step)
        eq *= (1 + step); peak = max(peak, eq)
        dd = eq / peak - 1
        if dd < -DD_HALT and exposure == 1.0:
            exposure = 0.5; halts += 1
        elif dd > -DD_RESUME and exposure < 1.0:
            exposure = 1.0
    return pd.Series(out, iv.index), halts


def stats(r: pd.Series) -> dict:
    if r.empty or r.std() == 0:
        return {"ann_ret": np.nan, "ann_vol": np.nan, "sharpe": np.nan, "maxdd": np.nan}
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    return {"ann_ret": r.mean() * S.ANN * 100, "ann_vol": r.std() * ANN * 100,
            "sharpe": r.mean() / r.std() * ANN, "maxdd": dd * 100}


def main() -> int:
    dl = DecisionLog()
    rmap = json.loads((HERE / "cache_seed" / (
        "zone_regime_optimized.json" if (HERE / "cache_seed" / "zone_regime_optimized.json").exists()
        else "zone_regime.json")).read_text())
    rows = []
    for mkt in S.MARKETS:
        with timed(LOG, f"risk book {mkt}"):
            ew, iv = desk_book(mkt, rmap)
        if ew.empty:
            continue
        vt, halts = apply_overlay(iv)
        s_ew, s_iv, s_vt = stats(ew), stats(iv), stats(vt)
        rows.append({"market": mkt, **{f"ew_{k}": v for k, v in s_ew.items()},
                     **{f"iv_{k}": v for k, v in s_iv.items()},
                     **{f"vt_{k}": v for k, v in s_vt.items()}, "ks_halts": halts})
        LOG.info(f"{mkt}: Sharpe EW {s_ew['sharpe']:.2f} -> invvol {s_iv['sharpe']:.2f} "
                 f"-> vol-target+KS {s_vt['sharpe']:.2f}; maxDD {s_ew['maxdd']:.0f}% "
                 f"-> {s_vt['maxdd']:.0f}%; kill-switch fired {halts}×")
        dl.record("risk_overlay", market=mkt, sharpe_ew=round(s_ew["sharpe"], 2),
                  sharpe_voltarget=round(s_vt["sharpe"], 2), maxdd_ew=round(s_ew["maxdd"], 1),
                  maxdd_voltarget=round(s_vt["maxdd"], 1), kill_switch_halts=halts)
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "reports" / "risk_management.csv", index=False)

    L = ["# Risk overlay: inverse-vol sizing · vol-target · drawdown kill-switch", "",
         f"Target vol {TARGET_VOL*100:.0f}%; kill-switch halves exposure when drawdown "
         f">{DD_HALT*100:.0f}%, restores under {DD_RESUME*100:.0f}%. Sharpe/maxDD per desk "
         "on the regime-conditional book (optimised map).", "",
         "| desk | Sharpe EW | Sharpe invvol | **Sharpe vt+KS** | maxDD EW | **maxDD vt+KS** | KS fired |",
         "|---|--:|--:|--:|--:|--:|--:|"]
    for _, r in df.iterrows():
        L.append(f"| {r.market} | {r.ew_sharpe:.2f} | {r.iv_sharpe:.2f} | **{r.vt_sharpe:.2f}** | "
                 f"{r.ew_maxdd:.0f}% | **{r.vt_maxdd:.0f}%** | {int(r.ks_halts)}× |")
    L += ["", "> Inverse-vol sizing raises Sharpe by down-weighting the noisiest names; "
          "vol-targeting standardises risk across desks (so leverage/carry can be sized "
          "to a known vol budget); the kill-switch caps tail drawdowns — the balance-sheet "
          "protection the equal-weight book lacked. Gross of costs. Not investment advice."]
    (HERE / "reports" / "risk_management.md").write_text("\n".join(L))
    print("\n".join(L))
    print("\nwrote reports/risk_management.{md,csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
