#!/usr/bin/env python3
"""
profitability_optimizer.py — reward-driven factor/screener selection to lift the
firm's profitability AND balance-sheet stability.

Treats each desk's (market × regime) screener choice as the decision variable and
MAXIMISES a profitability reward = annualised information ratio of the long-only
book's EXCESS return over its index (mean_excess / std_excess × √26), subject to
mean_excess > 0. Rewarding risk-adjusted excess (not raw return) lifts income and
shrinks loss-year drawdowns — which is what strengthens the balance sheet
(retained earnings, less capital erosion).

Expands the factor library beyond the 6 price factors to low-vol, 12-month
momentum, and multi-factor blends (quality-momentum = momentum ∩ low-vol), all
reconstructable PIT from OHLCV and all liquidity-gated (HIGH+MEDIUM turnover).

Output: reports/profitability_optimizer.md + cache_seed/zone_regime_optimized.json
        (drop-in replacement map for the digest once validated)
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd
import strategy_regime_survival as S

HERE = Path(__file__).resolve().parent


def factor_library(w: pd.DataFrame) -> dict:
    """+1 BUY / -1 SELL / 0 HOLD per factor, aligned to weekly panel w."""
    base = S.signals(w)                       # trend/revert/mom126/mom_st/golden_cross/breakout
    ret = w.pct_change(fill_method=None)
    vol13 = ret.rolling(13, min_periods=6).std()
    r252 = w.pct_change(50, fill_method=None)

    def terc(x, invert=False):
        p = x.rank(axis=1, pct=True)
        hi = (p >= 1 - S.TERCILE).astype(int); lo = (p <= S.TERCILE).astype(int)
        return (lo - hi) if invert else (hi - lo)

    lowvol = terc(vol13, invert=True)         # BUY low realised vol (low-vol anomaly)
    mom252 = terc(r252)                        # 12-month momentum
    # quality-momentum blend: BUY only names that are BOTH high-momentum AND low-vol
    qmom = ((base["mom126"] == 1) & (lowvol == 1)).astype(int) \
         - ((base["mom126"] == -1) & (lowvol == -1)).astype(int)
    # value-ish reversal blend: oversold AND low-vol (defensive mean-revert)
    dmr = ((base["revert"] == 1) & (lowvol == 1)).astype(int) \
        - ((base["revert"] == -1) & (lowvol == -1)).astype(int)
    return {**base, "lowvol": lowvol, "mom252": mom252,
            "qual_mom": qmom, "def_revert": dmr}


def score_factor(w, sig, reg, turn, regime):
    """Per formation week in `regime`: excess = BUY book − index. Returns
    (mean_excess%, info_ratio_ann, mean_book%, hit, n)."""
    fwd = (w.shift(-S.FWD // 5) / w - 1).clip(-0.40, 0.40)
    ex, bk = [], []
    for t in w.index[w.index >= S.START]:
        if reg.get(t) != regime:
            continue
        liq = S.liquidity_mask(turn.loc[t], w.loc[t])
        f = fwd.loc[t].where(liq).dropna()
        if len(f) < S.MIN_NAMES:
            continue
        buys = f[sig.loc[t].reindex(f.index) == 1]
        if len(buys) >= 5:
            ex.append(buys.mean() - f.mean()); bk.append(buys.mean())
    if len(ex) < 10:
        return None
    e = pd.Series(ex)
    ir = e.mean() / e.std() * np.sqrt(S.ANN) if e.std() > 0 else 0.0
    return {"mean_excess": e.mean()*100, "info_ratio": ir,
            "mean_book": np.mean(bk)*100, "hit": float((e > 0).mean()), "n": len(ex)}


def main() -> int:
    cur = {}
    zp = HERE / "cache_seed" / "zone_regime.json"
    if zp.exists():
        cur = json.loads(zp.read_text())
    FACTORS = ["trend","revert","mom126","mom_st","golden_cross","breakout",
               "lowvol","mom252","qual_mom","def_revert"]
    opt, rows = {}, []
    for mkt in S.MARKETS:
        close, turn = S.load_panel(mkt)
        reg = S.regime_series(close, turn)
        lib = factor_library(close)
        best = {}
        for regime in ("bull", "bear"):
            scored = {}
            for fac in FACTORS:
                r = score_factor(close, lib[fac], reg, turn, regime)
                if r:
                    scored[fac] = r
                    rows.append({"market": mkt, "regime": regime, "factor": fac, **r})
            # reward = info ratio, require positive mean excess
            elig = {f: v for f, v in scored.items() if v["mean_excess"] > 0}
            pick = max(elig, key=lambda f: elig[f]["info_ratio"]) if elig else "trend"
            best[regime] = (pick, scored.get(pick, {}))
        cur_reg = cur.get(mkt, {}).get("current_regime", "bull")
        opt[mkt] = {"bull_rule": best["bull"][0], "bear_rule": best["bear"][0],
                    "bull_ir": round(best["bull"][1].get("info_ratio", 0), 2),
                    "bear_ir": round(best["bear"][1].get("info_ratio", 0), 2),
                    "current_regime": cur_reg,
                    "active_rule": best["bull"][0] if cur_reg == "bull" else best["bear"][0]}
        print(f"  {mkt}: bull -> {opt[mkt]['bull_rule']} (IR {opt[mkt]['bull_ir']}) | "
              f"bear -> {opt[mkt]['bear_rule']} (IR {opt[mkt]['bear_ir']})")

    (HERE / "cache_seed" / "zone_regime_optimized.json").write_text(json.dumps(opt, indent=1))
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "reports" / "profitability_optimizer.csv", index=False)

    # ---- report: current vs optimized, per market×regime ---------------------
    L = ["# Reward-optimised factor selection (max information ratio)", "",
         "Decision variable = each desk's screener per regime; reward = annualised "
         "information ratio of the liquidity-gated long-only book's EXCESS over its "
         "index (risk-adjusted, so it lifts income *and* cuts loss-year drawdowns → "
         "stronger balance sheet). Factor library expanded to low-vol, 12m-momentum "
         "and multi-factor blends.", "",
         "| market | regime | current rule | current IR | **optimised rule** | **opt IR** | Δ excess%/2w |",
         "|---|---|---|--:|---|--:|--:|"]
    for mkt in S.MARKETS:
        for regime in ("bull", "bear"):
            crule = cur.get(mkt, {}).get(f"{regime}_rule", "trend")
            m = df[(df.market == mkt) & (df.regime == regime)]
            crow = m[m.factor == crule]
            orule = opt[mkt][f"{regime}_rule"]
            orow = m[m.factor == orule]
            cir = crow.info_ratio.iloc[0] if not crow.empty else float("nan")
            oir = orow.info_ratio.iloc[0] if not orow.empty else float("nan")
            cex = crow.mean_excess.iloc[0] if not crow.empty else float("nan")
            oex = orow.mean_excess.iloc[0] if not orow.empty else float("nan")
            d = (oex - cex) if (oex == oex and cex == cex) else float("nan")
            mark = " ⬆️" if orule != crule else ""
            L.append(f"| {mkt} | {regime} | {crule} | {cir:+.2f} | **{orule}**{mark} | "
                     f"{oir:+.2f} | {d:+.2f} |")
    # top factors overall
    L += ["", "## Best factor per market×regime (reward = info ratio)", "",
          "| market | regime | factor | info ratio | mean excess%/2w | hit |",
          "|---|---|---|--:|--:|--:|"]
    for mkt in S.MARKETS:
        for regime in ("bull", "bear"):
            m = df[(df.market == mkt) & (df.regime == regime)]
            m = m[m.mean_excess > 0].sort_values("info_ratio", ascending=False)
            if m.empty:
                continue
            x = m.iloc[0]
            L.append(f"| {mkt} | {regime} | **{x.factor}** | {x.info_ratio:+.2f} | "
                     f"{x.mean_excess:+.2f} | {x.hit*100:.0f}% |")
    L += ["", "> Reward = info ratio (risk-adjusted); `zone_regime_optimized.json` is a "
          "drop-in replacement for `zone_regime.json` once validated. Gross of costs; "
          "the profitability lift flows into the quarterly-earnings model on re-run."]
    (HERE / "reports" / "profitability_optimizer.md").write_text("\n".join(L))
    print("\n".join(L))
    print("\nwrote reports/profitability_optimizer.{md,csv}, cache_seed/zone_regime_optimized.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
