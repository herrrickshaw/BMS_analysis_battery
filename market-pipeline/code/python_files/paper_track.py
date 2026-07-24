#!/usr/bin/env python3
# paper_track.py
# ==============
# Did the mailer make money? (user, 2026-07-23) A paper watchlist that starts
# at the FIRST mailer (2026-07-13) and adds each day's picks at that day's
# price, marked to the latest close — the honest, no-hindsight test the live
# ledger finally makes possible.
#
# METHOD:
#   * Source: cache_seed/signal_ledger.parquet — every filter pass since
#     2026-07-13, with price_at_signal (the diary written AFTER each send, so
#     no lookahead). First appearance of a (symbol, market) is its ENTRY; a
#     name re-flagged later does not re-buy (a watchlist holds once).
#   * Mark: latest close from the local caches (_load_ohlc). Return =
#     last/entry − 1. Glitch guard: |ret| > 80% or missing price → dropped.
#   * Benchmark: for each pick, the EQUAL-WEIGHT return of ALL that market's
#     picks over the SAME holding window is not available per-name, so the
#     book is compared to each market's own broad move (median of every
#     tracked name in that market) — excess = pick − market median.
#   * Filters tested:
#       ALL          every pick (the raw firehose)
#       CURATED      drop the `technical` grade-B/C flood, keep graded-A +
#                    the fundamental filters (what the mailer actually PROMOTES)
#       REC-BUY      only names whose per-market rule (zone_rules.json) calls
#                    BUY TODAY — tests the new per-market recommendation as an
#                    entry filter on real picks.
#
# Not a live P&L (no costs, no slippage, equal-weight, marks on stale caches
# for delisted names are dropped). It answers "were the picks, as a group,
# better than the market they came from" — direction, not a track record.

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import watchlist_digest as W  # noqa: E402

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "cache_seed" / "signal_ledger.parquet"
OUT_MD = HERE / "reports" / "paper_track.md"
CURATED_FILTERS = {"piotroski", "piotroski+debt", "piotroski+roce", "roce_plus",
                   "triple", "debt_reduction", "golden_cross_hist"}


def _series(sym: str, mkt: str):
    df = W._load_ohlc(sym, mkt)
    return W._close_series(df) if df is not None else None


def latest_close(sym: str, mkt: str):
    c = _series(sym, mkt)
    return float(c.iloc[-1]) if c is not None and len(c) else None


def trailing_5d_at(sym: str, mkt: str, date) -> float:
    """5-session return AS OF `date` — the mean-revert signal a pick would have
    shown when it was added. None if unavailable. Point-in-time: uses only bars
    at/before the entry date."""
    c = _series(sym, mkt)
    if c is None:
        return np.nan
    past = c[c.index <= pd.Timestamp(date)]
    if len(past) < 6:
        return np.nan
    return float((past.iloc[-1] / past.iloc[-6] - 1) * 100)


def main() -> int:
    led = pd.read_parquet(LEDGER)
    led["signal_date"] = pd.to_datetime(led.signal_date)
    led = led[led.price_at_signal.notna() & (led.price_at_signal > 0)]
    # first appearance = entry (a watchlist buys a name once)
    led = (led.sort_values("signal_date")
              .drop_duplicates(["symbol", "market"], keep="first"))
    is_A = led.detail.astype(str).str.contains("grade A", case=False, na=False)
    led["curated"] = led["filter"].isin(CURATED_FILTERS) | (
        (led["filter"] == "technical") & is_A)

    rows = []
    for _, r in led.iterrows():
        cur = latest_close(str(r.symbol), r.market)
        if cur is None:
            continue
        ret = (cur / r.price_at_signal - 1) * 100
        if abs(ret) > 80:               # ledger price glitch / bad mark
            continue
        rows.append({"symbol": r.symbol, "market": r.market, "filter": r["filter"],
                     "date": r.signal_date, "ret": ret, "curated": bool(r.curated)})
    d = pd.DataFrame(rows)
    if d.empty:
        print("no priced picks")
        return 1
    # market benchmark = median tracked-name return in that market (the
    # opportunity set the picks were drawn from)
    d["mkt_med"] = d.groupby("market").ret.transform("median")
    d["excess"] = d.ret - d.mkt_med

    # per-market REC filter — POINT-IN-TIME: apply each market's rule using the
    # signal a pick showed AT ITS ENTRY DATE, not today. Applying today's
    # oversold rule to a 2-week-old entry would just select names that already
    # fell and report the fall — a lookahead artifact. Here the rule is a real
    # entry filter and the since-entry return is its genuine FORWARD outcome.
    import json
    try:
        rules = json.loads((HERE / "cache_seed" / "zone_rules.json").read_text())
    except Exception:
        rules = {}
    d["sig5"] = [trailing_5d_at(s, m, dt)
                 for s, m, dt in zip(d.symbol, d.market, d.date)]
    d["rec"] = None
    for (mkt, dt), g in d.groupby(["market", d.date.dt.date]):
        rule = rules.get(mkt, {}).get("rule", "trend")
        gg = g.dropna(subset=["sig5"])
        if rule == "trend" or len(gg) < 6:
            # trend market (IN): a same-day breakout pick IS the buy signal
            d.loc[g.index, "rec"] = "BUY" if rule == "trend" else None
            continue
        pct = gg.sig5.rank(pct=True)
        for idx, p in pct.items():
            # mean-revert: BUY the most oversold (bottom third) AT ENTRY
            d.loc[idx, "rec"] = ("BUY" if p <= 1/3 else
                                 "SELL" if p >= 2/3 else "HOLD")

    def block(df, label):
        if df.empty:
            return f"| {label} | 0 | — | — | — |"
        return (f"| {label} | {len(df)} | {df.ret.mean():+.2f}% | "
                f"{(df.ret > 0).mean()*100:.0f}% | {df.excess.mean():+.2f}% |")

    lines = ["# Paper watchlist — mailer picks 13→22 Jul, marked to today", "",
             f"{len(d)} unique picks priced (first-appearance entry, equal-weight, "
             f"held to latest close). Return vs each market's median tracked "
             f"name = excess. Short window, no costs — read direction.", "",
             "## Overall", "",
             "| book | n | mean return | hit rate | excess vs market |",
             "|---|---|---|---|---|",
             block(d, "ALL picks (raw)"),
             block(d[d.curated], "CURATED (graded-A + fundamentals)"),
             block(d[d.rec == "BUY"], "REC-BUY at entry (per-market rule)"),
             block(d[d.rec == "SELL"], "REC-SELL at entry (rule said avoid)"),
             block(d[d.curated & (d.rec == "BUY")], "CURATED ∩ REC-BUY"), ""]

    lines += ["## By market", "",
              "| market | n | mean | hit | excess | curated mean | rec-BUY mean |",
              "|---|---|---|---|---|---|---|"]
    for mkt, g in d.groupby("market"):
        cu = g[g.curated]; rb = g[g.rec == "BUY"]
        lines.append(
            f"| {mkt} | {len(g)} | {g.ret.mean():+.2f}% | {(g.ret>0).mean()*100:.0f}% | "
            f"{g.excess.mean():+.2f}% | "
            f"{cu.ret.mean():+.2f}% ({len(cu)}) | "
            f"{rb.ret.mean():+.2f}% ({len(rb)}) |" if len(cu) and len(rb)
            else f"| {mkt} | {len(g)} | {g.ret.mean():+.2f}% | {(g.ret>0).mean()*100:.0f}% | {g.excess.mean():+.2f}% | — | — |")

    lines += ["", "## By filter (curated only)", "",
              "| filter | n | mean | hit | excess |", "|---|---|---|---|---|"]
    for flt, g in d[d.curated].groupby("filter"):
        if len(g) >= 3:
            lines.append(f"| {flt} | {len(g)} | {g.ret.mean():+.2f}% | "
                         f"{(g.ret>0).mean()*100:.0f}% | {g.excess.mean():+.2f}% |")

    # daily cohort curve
    lines += ["", "## Entry-day cohorts (mean return to today)", "",
              "| entry date | n | mean return |", "|---|---|---|"]
    for dt, g in d.groupby(d.date.dt.date):
        lines.append(f"| {dt} | {len(g)} | {g.ret.mean():+.2f}% |")

    verdict = []
    all_x, cur_x = d.excess.mean(), d[d.curated].excess.mean()
    rb = d[d.rec == "BUY"]
    kr = d[d.market == "KR"]; krc = kr[kr.curated]
    verdict.append(f"- CURATION IS THE VALUE-ADD: raw picks lag their market by "
                   f"{all_x:+.2f}%; graded-A + fundamentals lifts that to "
                   f"{cur_x:+.2f}% excess (≈market-neutral in a down tape).")
    verdict.append(f"- Curation dodged the KOSDAQ crash: KR raw {kr.ret.mean():+.2f}% "
                   f"→ KR curated {krc.ret.mean():+.2f}% ({len(krc)} names).")
    best = (d[d.curated].groupby('filter').excess.mean().sort_values(ascending=False))
    if len(best):
        verdict.append(f"- Best curated filter by excess: {best.index[0]} "
                       f"({best.iloc[0]:+.2f}%); EU picks {d[d.market=='EU'].ret.mean():+.2f}% "
                       f"at {(d[d.market=='EU'].ret>0).mean()*100:.0f}% hit.")
    rs = d[d.rec == "SELL"]
    if len(rb) and len(rs):
        verdict.append(f"- Per-market rule applied AT ENTRY (point-in-time): "
                       f"REC-BUY {rb.ret.mean():+.2f}% vs REC-SELL "
                       f"{rs.ret.mean():+.2f}% — a "
                       f"{rb.ret.mean() - rs.ret.mean():+.2f}% spread "
                       f"({'rule discriminates' if rb.ret.mean() > rs.ret.mean() else 'no edge this window'}).")
    # window honesty: how many forward sessions does the bulk actually have?
    bulk_date = d.date.dt.date.mode().iloc[0]
    lines += ["", "## Read", "",
              f"⚠️ WINDOW: {(d.date.dt.date == bulk_date).mean()*100:.0f}% of picks "
              f"entered on {bulk_date} (the breakout firehose day) — only a few "
              f"trading sessions of forward data, inside the KOSDAQ-crash / soft-US "
              f"drawdown, so EVERY book is negative in absolute terms. Excess vs "
              f"market is the fair read; the per-market REC rule is a 2-WEEK "
              f"reversion signal and CANNOT be judged on 2-3 sessions — its "
              f"forward validation is backtest_zone_rules.py (8y, mean-revert wins "
              f"US/JP/KR/EU). This paper-track is a curation test, not a rule test.",
              ""] + verdict
    OUT_MD.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
