#!/usr/bin/env python3
"""
regime_price_model_filtered_eval.py — does regime_price_model.py's prediction
accuracy improve on stocks that PASS quality/liquidity filters, tested tier
by tier starting with High liquidity?

Reuses (does not refit differently per tier — same model, same train/test
split as regime_price_model.py) the two regime-conditional OLS models fit on
the FULL 400-symbol panel, then slices the held-out test set (>=2024) by:

  1. LIQUIDITY TIER — from liquidity.py's cached index (cache_seed/
     liquidity_index.parquet, USD median daily turnover; India cutoffs:
     High >= $5M/day, Medium >= $500k/day, else Low). This is a STATIC
     snapshot (~2026-07-13), not a time-varying tier through 2024-2026 —
     a real limitation, noted rather than hidden.
  2. DARVAS "PASS" — state == BREAKOUT (bullish scan pass) vs BREAKDOWN
     (bearish) vs IN_BOX (no signal / consolidation).
  3. PIOTROSKI "PASS" — F-score >= 7 (standard high-quality threshold),
     computed via the SAME _piotroski() scoring logic as
     global-stock-screener/backtest_piotroski_in.py, from screener.in
     point-in-time annuals (fy_end + 90-day filing lag, no look-ahead).
     Coverage caveat: this collection only reached 75 of ~3,476 India
     tickers (still-blocked screener.in collection, see project memory) —
     the Piotroski-tagged slice will be a SMALL sample; reported as such,
     not papered over.

Order of reporting matches the request: High liquidity first, then Medium,
then Low.
"""
from __future__ import annotations

import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import regime_price_model as rpm

LIQ_INDEX_PATH = "cache_seed/liquidity_index.parquet"
FUND_HIST_PATH = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/IN.parquet"
PIOTROSKI_LAG_DAYS = 90
PIOTROSKI_PASS = 7


def _piotroski(df: pd.DataFrame) -> pd.DataFrame:
    """Identical scoring logic to global-stock-screener/backtest_piotroski_in.py's
    _piotroski() (screener.in-schema branch) — copied, not reimplemented
    differently, so results are directly comparable to that backtest."""
    df = df.sort_values(["ticker", "fy_end"]).copy()
    for c in ["net_income", "revenue", "cfo", "borrowings", "reserves",
              "equity_capital", "other_liab", "inventory", "receivables",
              "cash", "shares"]:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df["equity"] = df["equity_capital"].fillna(0) + df["reserves"].fillna(0)
    df["total_assets"] = df["equity"] + df["borrowings"].fillna(0) + df["other_liab"].fillna(0)
    df["cur_assets"] = df["inventory"].fillna(0) + df["receivables"].fillna(0) + df["cash"].fillna(0)
    g = df.groupby("ticker")

    def prev(c):
        return g[c].shift(1)

    ta, ta1 = df["total_assets"], prev("total_assets")
    ni, cfo = df["net_income"], df["cfo"]
    roa, roa1 = ni / ta, prev("net_income") / ta1
    lev = df["borrowings"] / ta
    lev1 = prev("borrowings") / ta1
    cr = df["cur_assets"] / df["other_liab"]
    cr1 = prev("cur_assets") / prev("other_liab")
    sh, sh1 = df["shares"], prev("shares")
    gm = ni / df["revenue"]
    gm1 = prev("net_income") / prev("revenue")
    at, at1 = df["revenue"] / ta, prev("revenue") / ta1

    f = ((roa > 0).astype(float) + (cfo > 0).astype(float) + (roa > roa1).astype(float)
         + ((cfo / ta) > roa).astype(float) + (lev < lev1).astype(float)
         + (cr > cr1).astype(float) + (sh <= sh1 * 1.02).astype(float)
         + (gm > gm1).astype(float) + (at > at1).astype(float))
    df["F"] = np.where(ta1.notna() & (ta1 != 0), f, np.nan)
    return df.dropna(subset=["F"])[["ticker", "fy_end", "F"]]


def load_liquidity_tiers() -> pd.DataFrame:
    idx = pd.read_parquet(LIQ_INDEX_PATH)
    idx = idx[idx["Market"] == "IN"][["Symbol", "turnover_usd"]]
    idx["Liquidity"] = np.select(
        [idx["turnover_usd"] >= 5_000_000, idx["turnover_usd"] >= 500_000],
        ["High", "Medium"], default="Low")
    return idx.rename(columns={"Symbol": "symbol"})


def load_piotroski_pit() -> pd.DataFrame:
    """Point-in-time F-score per ticker, effective from fy_end+90d until the
    next fiscal year's score arrives — an asof-mergeable table."""
    raw = pd.read_parquet(FUND_HIST_PATH)
    scored = _piotroski(raw)
    scored["effective_date"] = pd.to_datetime(scored["fy_end"]) + pd.Timedelta(days=PIOTROSKI_LAG_DAYS)
    return scored.rename(columns={"ticker": "symbol"})[["symbol", "effective_date", "F"]]


def attach_filters(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    data["date"] = pd.to_datetime(data["date"])

    liq = load_liquidity_tiers()
    data = data.merge(liq[["symbol", "Liquidity"]], on="symbol", how="left")
    data["Liquidity"] = data["Liquidity"].fillna("Unknown")

    pio = load_piotroski_pit().sort_values("effective_date")
    tagged = []
    for sym, g in data.groupby("symbol"):
        p = pio[pio["symbol"] == sym]
        if p.empty:
            g = g.copy()
            g["F_score"] = np.nan
        else:
            g = pd.merge_asof(g.sort_values("date"), p[["effective_date", "F_score" if "F_score" in p.columns else "F"]]
                               .rename(columns={"F": "F_score"}).sort_values("effective_date"),
                               left_on="date", right_on="effective_date", direction="backward")
        tagged.append(g)
    out = pd.concat(tagged, ignore_index=True)
    out["piotroski_pass"] = out["F_score"] >= PIOTROSKI_PASS
    return out


def _score(y_true, y_pred):
    if len(y_true) < 5:
        return None
    rmse_model = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    rmse_naive = float(np.sqrt(np.mean(y_true ** 2)))
    dir_acc = float(np.mean(np.sign(y_pred) == np.sign(y_true)))
    return {"n": int(len(y_true)), "dir_acc": round(dir_acc, 4),
            "rmse_model": round(rmse_model, 6), "rmse_naive": round(rmse_naive, 6),
            "skill_vs_naive_pct": round((1 - rmse_model / rmse_naive) * 100, 3) if rmse_naive else None}


def main():
    print("Loading feature panel + fitting regime models (same as regime_price_model.py)...")
    data = pd.read_parquet("cache_seed/regime_price_model_dataset.parquet")
    data["date"] = pd.to_datetime(data["date"])
    train = data[data["date"] <= rpm.TRAIN_END]

    box_train = train[train["state"] == "IN_BOX"].dropna(subset=["pos_in_box"])
    theta_a = rpm._ols((0.5 - box_train["pos_in_box"].values).reshape(-1, 1), box_train["r_fwd"].values)
    mom_train = train[train["state"].isin(["BREAKOUT", "BREAKDOWN"])].dropna(
        subset=["magnitude", "r_t", "r_tm1", "r_tm2"])
    theta_b = rpm._ols(mom_train[["r_t", "r_tm1", "r_tm2", "magnitude"]].values, mom_train["r_fwd"].values)

    print("Attaching liquidity tiers + point-in-time Piotroski F-scores...")
    tagged = attach_filters(data)
    test = tagged[tagged["date"] >= rpm.TEST_START].copy()

    pio_n = tagged["F_score"].notna().sum()
    pio_syms = tagged.loc[tagged["F_score"].notna(), "symbol"].nunique()
    print(f"  Piotroski coverage: {pio_n} symbol-days across {pio_syms} symbols "
          f"(of {tagged['symbol'].nunique()} total — screener.in collection is "
          f"still only 75/3,476 tickers, see project memory)")
    print(f"  Liquidity tiers in test set:\n{test['Liquidity'].value_counts()}\n")

    def predict_rows(sub):
        box = sub[sub["state"] == "IN_BOX"].dropna(subset=["pos_in_box"])
        mom = sub[sub["state"].isin(["BREAKOUT", "BREAKDOWN"])].dropna(
            subset=["magnitude", "r_t", "r_tm1", "r_tm2"])
        out = {}
        if len(box):
            pred = rpm._predict((0.5 - box["pos_in_box"].values).reshape(-1, 1), theta_a)
            out["IN_BOX"] = _score(box["r_fwd"].values, pred)
        if len(mom):
            pred = rpm._predict(mom[["r_t", "r_tm1", "r_tm2", "magnitude"]].values, theta_b)
            out["BREAKOUT_BREAKDOWN"] = _score(mom["r_fwd"].values, pred)
            for st in ["BREAKOUT", "BREAKDOWN"]:
                s2 = mom[mom["state"] == st]
                if len(s2):
                    p2 = rpm._predict(s2[["r_t", "r_tm1", "r_tm2", "magnitude"]].values, theta_b)
                    out[st] = _score(s2["r_fwd"].values, p2)
        return out

    import json
    for tier in ["High", "Medium", "Low", "Unknown"]:
        sub = test[test["Liquidity"] == tier]
        print(f"\n{'='*70}\n  LIQUIDITY TIER: {tier}  (n={len(sub)} symbol-days, "
              f"{sub['symbol'].nunique()} symbols)\n{'='*70}")
        if sub.empty:
            print("  (empty)")
            continue

        print("  -- all Darvas states --")
        print(json.dumps(predict_rows(sub), indent=2))

        pio_sub = sub[sub["F_score"].notna()]
        if len(pio_sub):
            passed = pio_sub[pio_sub["piotroski_pass"]]
            failed = pio_sub[~pio_sub["piotroski_pass"]]
            print(f"  -- Piotroski F>=7 (PASS, n={len(passed)}) --")
            print(json.dumps(predict_rows(passed), indent=2))
            print(f"  -- Piotroski F<7 (FAIL, n={len(failed)}) --")
            print(json.dumps(predict_rows(failed), indent=2))
        else:
            print("  -- Piotroski: no fundamentals coverage in this tier's test slice --")


if __name__ == "__main__":
    main()
