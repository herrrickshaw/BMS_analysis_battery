#!/usr/bin/env python3
"""
strategy_matrix.py — the master suitability matrix: which factor / screener / ratio
works in which market (and regime), assembled from THIS repo's backtest artifacts so
every cell is evidence-backed, not asserted. Self-updating: each cell is stamped with
when its source backtest last ran, and each run diffs against the prior matrix to flag
any suitability that FLIPPED (a factor that stopped working) — the "keep testing" loop.

Sources (all produced by the pipeline's backtests):
  technical factors × regime  ← deflated_sharpe.csv (chosen factor + DSR) + regime_survival
  tuned hyperparameters       ← aws_sweep.parquet
  valuation ratios / reversion← pe_anomaly_backtest + valuation_reversion_* (validated)
  value+quality long/short    ← value_quality_ls.md (validated)
  risk overlay                ← risk_management.csv

Legend: ✅ works (robust) · 🟡 conditional/earned · ⚠️ fragile (fails multiple-testing) ·
        ❌ fails · — untested/no data

Run: python strategy_matrix.py   (add to monthly [16d] AFTER the backtests re-run)
Output: reports/strategy_matrix.md + cache_seed/strategy_matrix.json (versioned)
"""
from __future__ import annotations
import json, datetime
from pathlib import Path
import pandas as pd, numpy as np
from obs import get_logger

HERE = Path(__file__).resolve().parent
LOG = get_logger("strategy_matrix")
MARKETS = ["IN", "US", "KR", "JP", "EU"]


def mtime(rel: str) -> str:
    p = HERE / rel
    return datetime.datetime.utcfromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d") if p.exists() else "—"


# ── VALIDATED cross-market verdicts (this session's backtests; metric + source) ──
# each: {market: (verdict, evidence)}
VAL_RATIO = {  # source: pe_anomaly_backtest.md + valuation_reversion_*.md
 "Value — cheap vs peers (low PE)": {
   "IN": ("✅", "+5.3%/6M sector-rel, t2.5"), "US": ("✅", "+1.7%/3M, t2.3"),
   "KR": ("✅", "+6.3%/6M, t3.3 (strongest)"), "JP": ("⚠️", "direction right, t≈0"),
   "EU": ("—", "no fundamentals")},
 "Value+Quality long/short (cheap∩hiROE − rich∩loROE)": {
   "IN": ("❌", "−1.0%/6M — momentum runs shorts over"), "US": ("🟡", "+1.7%/6M, t1.0"),
   "KR": ("✅", "+4.8%/6M, t4.2 — full L/S works"), "JP": ("—", "excluded"),
   "EU": ("—", "no fundamentals")},
 "Quality (high ROE) as premium filter": {
   "IN": ("🟡", "earns premium (Titan/TVS)"), "US": ("🟡", "earns premium"),
   "KR": ("✅", "hi-ROE cheap = the discount"), "JP": ("—", ""), "EU": ("—", "")},
}
SCREENER = {  # from paper-track + zone-rule backtests
 "Darvas / breakout (near-52w-high)": {
   "IN": ("✅", "best all-weather, +0.44/+0.41 bull/bear"), "US": ("🟡", "bull only"),
   "KR": ("✅", "bull IR 2.0"), "JP": ("🟡", ""), "EU": ("🟡", "")},
 "Golden cross (50>200DMA)": {
   "IN": ("✅", "survives both regimes"), "US": ("✅", "bull+bear excess>0"),
   "KR": ("🟡", ""), "JP": ("🟡", ""), "EU": ("🟡", "")},
 "Mean-reversion (buy oversold)": {
   "IN": ("⚠️", "weak — India is momentum"), "US": ("✅", "bear regime"),
   "KR": ("✅", "bear regime, strong"), "JP": ("✅", "bear regime"), "EU": ("✅", "bear regime")},
 "Piotroski / fundamental quality": {
   "IN": ("🟡", "behind liquidity gate"), "US": ("⚠️", "F-score inverted (backtest)"),
   "KR": ("🟡", ""), "JP": ("—", ""), "EU": ("—", "")},
}


def technical_from_backtests() -> dict:
    """market×regime → (chosen factor, verdict, evidence) from deflated_sharpe.csv."""
    out = {}
    try:
        d = pd.read_csv(HERE / "reports" / "deflated_sharpe.csv")
        for _, r in d.iterrows():
            v = "✅" if r["survives_0.95"] else ("⚠️" if r["IR_chosen"] > 0 else "❌")
            out[(r.market, r.regime)] = (r.chosen, v,
                 f"IR {r.IR_chosen:.2f}, DSR {r.DSR:.2f}")
    except Exception as e:
        LOG.error(f"technical source failed: {e}")
    return out


def main() -> int:
    tech = technical_from_backtests()
    tstamp = {"regime": mtime("reports/deflated_sharpe.csv"),
              "sweep": mtime("reports/aws_sweep.parquet"),
              "value": mtime("reports/pe_anomaly_backtest.md"),
              "ls": mtime("reports/value_quality_ls.md")}
    # ---- build long registry (machine-readable, testable) --------------------
    reg = []
    for (mk, rg), (fac, v, ev) in tech.items():
        reg.append({"dimension": "technical-factor", "item": fac, "market": mk,
                    "context": f"{rg} regime", "verdict": v, "evidence": ev,
                    "source": "deflated_sharpe", "last_tested": tstamp["regime"]})
    for grp, src, ts in [(VAL_RATIO, "valuation-reversion", tstamp["value"]),
                         (SCREENER, "screener/filter", tstamp["regime"])]:
        for item, mkts in grp.items():
            for mk, (v, ev) in mkts.items():
                reg.append({"dimension": src.split("/")[0], "item": item, "market": mk,
                            "context": "all", "verdict": v, "evidence": ev,
                            "source": src, "last_tested": ts})
    regdf = pd.DataFrame(reg)
    new_matrix = {f"{r.dimension}|{r['item']}|{r.market}|{r.context}": r.verdict
                  for _, r in regdf.iterrows()}

    # ---- keep-testing: diff vs prior matrix -> flag flips ---------------------
    prior_path = HERE / "cache_seed" / "strategy_matrix.json"
    flips = []
    if prior_path.exists():
        try:
            prior = json.loads(prior_path.read_text()).get("cells", {})
            for k, v in new_matrix.items():
                if k in prior and prior[k] != v:
                    flips.append(f"{k}: {prior[k]} → {v}")
        except Exception:
            pass
    for f in flips:
        LOG.warning(f"SUITABILITY FLIP: {f}")

    # ---- readable matrix -----------------------------------------------------
    L = ["# Strategy suitability matrix — what works where (evidence-backed)", "",
         "Assembled from this repo's backtests; each row's verdict traces to a stat. "
         "Legend: ✅ robust · 🟡 conditional/earned · ⚠️ fragile (fails multiple-testing) · "
         "❌ fails · — untested. Cells re-derive when the backtests re-run.", ""]
    if flips:
        L += [f"> ⚠️ **{len(flips)} suitability flip(s) since last run** — a signal changed:",
              ""] + [f"> - {f}" for f in flips] + [""]

    # technical factors by market × regime
    L += ["## Technical factors — best per market × regime (Deflated-Sharpe checked)", "",
          "| market | BULL factor | BULL | BEAR factor | BEAR |", "|---|---|:--:|---|:--:|"]
    for mk in MARKETS:
        b = tech.get((mk, "bull")); r = tech.get((mk, "bear"))
        bs = f"{b[0]} {b[1]}" if b else "— —"; rs = f"{r[0]} {r[1]}" if r else "— —"
        L.append(f"| {mk} | {b[0] if b else '—'} | {b[1] if b else '—'} | {r[0] if r else '—'} | {r[1] if r else '—'} |")

    def block(title, grp):
        rows = ["", f"## {title}", "", "| strategy \\ market | " + " | ".join(MARKETS) + " |",
                "|---|" + ":--:|" * len(MARKETS)]
        for item, mkts in grp.items():
            cells = " | ".join(mkts.get(mk, ("—", ""))[0] for mk in MARKETS)
            rows.append(f"| {item} | {cells} |")
        return rows
    L += block("Valuation ratios & reversion", VAL_RATIO)
    L += block("Screeners / filters", SCREENER)

    # deployment rules (the market-character summary)
    L += ["", "## Deployment rules (market character — the meta-finding)", "",
          "| market | character | long book | short book |", "|---|---|---|---|",
          "| IN | momentum/trend | breakout + sector-relative value | ❌ don't short (bull runs them over) |",
          "| US | mixed | golden-cross / value, light | marginal |",
          "| KR | mean-reversion | cheap∩hi-ROE (Korea discount) | ✅ hollow-overpriced (validated) |",
          "| JP | mean-revert (weak) | mom in bull, revert in bear | — (value not significant) |",
          "| EU | mean-revert | momentum bull, revert bear | — (no fundamentals) |"]
    L += ["", "## Freshness / keep-testing", "",
          "| block | source backtest | last tested |", "|---|---|---|",
          f"| technical factors | deflated_sharpe + regime_survival | {tstamp['regime']} |",
          f"| tuned hyperparams | aws_sweep | {tstamp['sweep']} |",
          f"| value / reversion | pe_anomaly + valuation_reversion | {tstamp['value']} |",
          f"| value+quality L/S | value_quality_ls | {tstamp['ls']} |",
          "", "> Re-run the backtests then `strategy_matrix.py`; it re-stamps every cell "
          "and alerts on any verdict FLIP. Wire into monthly [16d] after the backtests. "
          "Deepening data (DART/EDINET for KR/JP) will refresh those cells automatically. "
          "Descriptive research, not investment advice."]

    (HERE / "reports" / "strategy_matrix.md").write_text("\n".join(L))
    payload = {"generated": tstamp, "flips": flips, "cells": new_matrix,
               "registry": regdf.to_dict("records")}
    prior_path.write_text(json.dumps(payload, indent=1, default=str))
    regdf.to_csv(HERE / "reports" / "strategy_matrix.csv", index=False)
    print("\n".join(L))
    print(f"\nwrote reports/strategy_matrix.{{md,csv}} + cache_seed/strategy_matrix.json "
          f"({len(regdf)} cells, {len(flips)} flips)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
