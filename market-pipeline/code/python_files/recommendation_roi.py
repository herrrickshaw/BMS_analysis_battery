#!/usr/bin/env python3
"""
recommendation_roi.py — CFO-level P&L view of the platform's trading
recommendations: earnings and ROI on the overall recommendation set.

Two books, both marked to realized forward returns (adjusted prices, abnormal
vs market median where relevant):

  A. SCAN SIGNALS  — the daily Darvas/golden-cross recommendations in the
     signal ledger (scored at +5/+21 trading days).
  B. CA INTIMATION — the validated bonus/split intimation-drift strategy
     (from pit_event_studies), the one FDR-surviving edge.

For each: gross return, benchmark-excess, hit rate, an annualized ROI (return
scaled by holding period), a per-Rs-deployed earnings figure at a stated book
size, and a naive Sharpe. Everything conditioned on the honesty caveats
already in claims.yaml (single sample, no live slippage beyond the cost model).

Output: reports/RECOMMENDATION_ROI.md
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_MD = os.path.join(BASE, "reports", "RECOMMENDATION_ROI.md")
TD_YEAR = 252


def book(df: pd.DataFrame, ret_col: str, h_td: float) -> dict:
    r = df[ret_col].dropna()
    if r.empty:
        return {}
    ann = (1 + r.mean()) ** (TD_YEAR / h_td) - 1
    sharpe = (r.mean() / r.std() * np.sqrt(TD_YEAR / h_td)) if r.std() else np.nan
    return {
        "n": len(r), "mean": r.mean(), "median": r.median(),
        "hit": (r > 0).mean(), "ann_roi": ann, "sharpe": sharpe,
        "best": r.max(), "worst": r.min(),
    }


def main() -> int:
    lines = [f"# Recommendation ROI & earnings — {pd.Timestamp.now():%Y-%m-%d}",
             "",
             "CFO-level P&L on the platform's two recommendation books, marked "
             "to realized forward returns on split/bonus-adjusted prices. "
             "Returns are per-signal; annualized ROI scales the mean by the "
             "holding period. NOT personalized advice — realized backtest "
             "statistics on recorded recommendations.", ""]

    # ---- Book A: scan signals -------------------------------------------
    o = pd.read_parquet(os.path.join(BASE, "reports", "signal_outcomes.parquet"))
    sc = o[o["status"] == "scored"].copy()
    sc["dir"] = np.where(sc["detail"].astype(str).str.contains("SELL"),
                         "SELL", "BUY")
    lines += ["## Book A — daily scan signals (Darvas / golden-cross)", "",
              f"{sc['signal_id'].nunique():,} scored signals · "
              f"{o[o.status == 'pending']['signal_id'].nunique():,} still "
              "pending (horizon not elapsed).", "",
              "| market | dir | horizon | n | mean ret | hit% | ann ROI | "
              "median excess | Sharpe |",
              "|---|---|---|---|---|---|---|---|---|"]
    buy = sc[sc["dir"] == "BUY"]
    for (mkt, h), g in buy.groupby(["market", "h"]):
        b = book(g, "fwd_ret", h)
        if not b or b["n"] < 30:
            continue
        exc = g["excess_ret"].median()
        lines.append(
            f"| {mkt} | BUY | {int(h)}d | {b['n']:,} | {b['mean']:+.2%} "
            f"| {b['hit']:.0%} | {b['ann_roi']:+.1%} | {exc:+.2%} "
            f"| {b['sharpe']:.2f} |")
    # headline all-BUY 21d
    b21 = book(buy[buy["h"] == 21], "fwd_ret", 21)
    lines += ["",
              f"**All-market BUY, +21d:** {b21['n']:,} signals, "
              f"{b21['mean']:+.2%} mean ({b21['hit']:.0%} hit), "
              f"annualized ROI {b21['ann_roi']:+.1%}, Sharpe {b21['sharpe']:.2f}. "
              "This is a gross, cost-free, equal-weight read — the scan is a "
              "watchlist generator, not a costed strategy.", ""]

    # ---- Book B: CA intimation drift (the validated edge) ---------------
    ev_path = os.path.join(BASE, "reports", "pit_event_studies.parquet")
    if os.path.exists(ev_path):
        ev = pd.read_parquet(ev_path)
        iv = ev[(ev["study"] == "post_ca_intimation")
                & ev["car_drift_ex"].notna()].copy()
        lines += ["## Book B — CA intimation drift (validated, FDR-surviving)",
                  "",
                  "Enter intimation+2 trading days, exit ex−1. Abnormal return "
                  "vs market median on adjusted prices. Split leg is the FDR "
                  "survivor (see claims.yaml `india-ca-intimation-drift`).", "",
                  "| kind | n | mean drift | hit% | median hold (td) | ann ROI |",
                  "|---|---|---|---|---|---|"]
        for kind, g in iv.groupby("kind"):
            hold = (g["rn_ex"] - g["rn_ann"]).median() if "rn_ex" in g else 43
            b = book(g, "car_drift_ex", hold)
            lines.append(
                f"| {kind} | {b['n']} | {b['mean']:+.2%} | {b['hit']:.0%} "
                f"| {hold:.0f} | {b['ann_roi']:+.1%} |")
        # cost-adjusted earnings at book sizes (from cost model medians)
        lines += ["",
                  "### Cost-adjusted economics (split leg, per COST_INTIMATION_"
                  "DRIFT.md, 10%-ADV cap over ~2.5yr of events)", "",
                  "| position/event | executable events (2.5yr) | net/event "
                  "| earnings/event | events/yr |",
                  "|---|---|---|---|---|"]
        # net medians from the cost run (splits); executable events span the
        # ~2.5yr board-meeting collection window -> per-year ≈ /2.5
        cost_tbl = [("Rs 1L", 1e5, 0.137, 223), ("Rs 10L", 1e6, 0.131, 157),
                    ("Rs 50L", 5e6, 0.104, 101), ("Rs 2Cr", 2e7, 0.103, 52)]
        for label, pos, net, nexec in cost_tbl:
            earn = pos * net
            lines.append(
                f"| {label} | {nexec} | {net:+.1%} | Rs {earn / 1e5:.2f}L "
                f"| ~{nexec / 2.5:.0f} |")
        lines += ["",
                  "Read — per position, not per book: each split event returns "
                  "net +10-14% over ~50 trading days. ROI is book-size-flat "
                  "(cost is ~1%); what shrinks with size is the COUNT of "
                  "executable events (223 → 52 as the 10%-ADV cap bites). "
                  "Portfolio earnings = position × net × concurrent slots your "
                  "book can fund — at Rs 1L you can take nearly every event "
                  "(~90/yr); at Rs 2Cr only the ~20 liquid ones/yr. Absolute "
                  "rupees therefore depend on total book size, not position "
                  "size; the durable statement is the book-size-flat +10-14%/"
                  "event net ROI. Platform's only cost-and-FDR-validated edge."]

    lines += ["", "## Overall",
              "", "- **Validated ROI edge:** CA intimation drift (split), "
              "net-of-cost +10-14%/event, FDR-surviving.",
              "- **Watchlist ROI (indicative):** all-market Darvas BUY +21d "
              f"{b21['mean']:+.2%} gross ({b21['ann_roi']:+.1%} annualized) — "
              "uncosted, use as a funnel not a P&L.",
              "- **Dead on arrival:** announcement-sorted PEAD, post-ex drift, "
              "all 12 factor-combo cells (0 survive FDR).",
              "", "The honest CFO summary: one recommendation stream clears "
              "the bar for real capital; the rest are research funnel or "
              "negative results — which is itself the deliverable the FDR "
              "discipline was built to produce."]

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
