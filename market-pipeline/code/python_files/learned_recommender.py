#!/usr/bin/env python3
"""
learned_recommender.py — apply the learned Lasso factor weights (factor_learning.py)
to score the live universe, cached for the digest to join cheaply.

Runs OFFLINE (heavy factor compute once), writes cache_seed/learned_recs.parquet
(market, symbol, learned_score, rec_learned). The digest joins by symbol and sets
r['rec_learned'] in SHADOW mode — it does not replace the production r['rec'] until
the learned model is validated live. Markets where Lasso kept no factors are skipped
(the digest keeps the regime-conditional rule there).

Output: cache_seed/learned_recs.parquet + reports/learned_recommender.md
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd
import strategy_regime_survival as S
from profitability_optimizer import factor_library
from obs import get_logger, timed, DecisionLog

HERE = Path(__file__).resolve().parent
LOG = get_logger("learned_recommender")


def main() -> int:
    dl = DecisionLog()
    wpath = HERE / "cache_seed" / "factor_weights.json"
    if not wpath.exists():
        LOG.error("factor_weights.json absent — run factor_learning.py first"); return 1
    weights = json.loads(wpath.read_text())
    out = []
    for mkt in S.MARKETS:
        w = weights.get(mkt, {}).get("lasso_weights", {})
        if not w:
            LOG.info(f"{mkt}: no learned factors (Lasso zeroed all) — digest keeps regime rule")
            continue
        with timed(LOG, f"score {mkt} ({len(w)} learned factors)"):
            close, turn = S.load_panel(mkt)
            lib = factor_library(close)
            liq = S.liquidity_mask(turn.iloc[-1], close.iloc[-1])
            univ = close.columns[liq.values]
            # learned score = Σ weight_f · latest factor signal_f  (weights were ×1e4)
            score = pd.Series(0.0, index=close.columns)
            for f, wt in w.items():
                score = score.add(lib[f].iloc[-1].fillna(0) * (wt / 1e4), fill_value=0)
            score = score.reindex(univ).dropna()
            if score.empty:
                continue
            rank = score.rank(pct=True)
            rec = pd.Series(np.where(rank >= 2/3, "BUY",
                            np.where(rank <= 1/3, "SELL", "HOLD")), index=score.index)
        for sym in score.index:
            out.append({"market": mkt, "symbol": str(sym),
                        "learned_score": round(float(score[sym]), 5), "rec_learned": rec[sym]})
        n = rec.value_counts().to_dict()
        LOG.info(f"{mkt}: scored {len(score)} names -> {n}")
        dl.record("learned_recs", market=mkt, factors=list(w), n_scored=len(score),
                  buys=int((rec == "BUY").sum()), sells=int((rec == "SELL").sum()))
    df = pd.DataFrame(out)
    cache = HERE / "cache_seed" / "learned_recs.parquet"
    df.to_parquet(cache, index=False)
    L = ["# Learned-model recommendations (shadow mode)", "",
         f"Lasso-weighted factor score applied to the live liquid universe; cached to "
         f"`{cache.name}` for the digest to join (sets `rec_learned`, does NOT replace the "
         f"production `rec` until validated live). Active markets = those where Lasso kept "
         f"factors.", "",
         "| market | learned factors | names scored | BUY | HOLD | SELL |",
         "|---|---|--:|--:|--:|--:|"]
    for mkt in S.MARKETS:
        m = df[df.market == mkt] if not df.empty else df
        if m.empty:
            L.append(f"| {mkt} | (none — regime rule) | 0 | — | — | — |"); continue
        vc = m.rec_learned.value_counts()
        L.append(f"| {mkt} | {', '.join(weights[mkt]['lasso_weights'])} | {len(m)} | "
                 f"{vc.get('BUY',0)} | {vc.get('HOLD',0)} | {vc.get('SELL',0)} |")
    L += ["", "> Shadow mode: `rec_learned` is recorded and comparable against the live "
          "`rec` but does not drive eviction or the mailer until it beats the regime rule "
          "on forward paper-track data. Not investment advice."]
    (HERE / "reports" / "learned_recommender.md").write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nwrote {cache}, reports/learned_recommender.md ({len(df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
