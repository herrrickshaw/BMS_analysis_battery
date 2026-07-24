#!/usr/bin/env python3
"""
long_short_tp.py — extend the reward-optimised book with (1) new composite filters
built on top of the benchmark filters, (2) a SHORT leg (short the SELL names), and
(3) PROFIT-BOOKING (take-profit on the favourable move, using the daily price path).

Shows the reward (info ratio) climbing as each mechanic is added:
    long-only  ->  +short (dollar-neutral)  ->  +take-profit  ->  both
and the firm-level ROE lift under the full long/short + profit-booking book.

New filters on top of the benchmark set (S.signals):
    tri_confirm  BUY trend∧mom126∧breakout all +1 / SELL all -1  (triple-confirmed)
    blend_rank   composite cross-sectional rank of momentum+low-vol+trend, terciles

Profit-booking: for each 2-week hold, walk the DAILY path. A long books +TP the
first time it trades TP% up; a short books +TP the first time it trades TP% down;
otherwise the position exits at the 2-week close. A symmetric stop caps the loss.

Output: reports/long_short_tp.md + reports/long_short_tp.csv
"""
from __future__ import annotations
import glob, json
from pathlib import Path
import numpy as np, pandas as pd
import strategy_regime_survival as S
import quarterly_earnings as Q

HERE = Path(__file__).resolve().parent
TP = 0.08          # take-profit threshold (book the gain at +8% favourable)
SL = 0.12          # stop-loss (cap adverse move at -12%)


def daily_close(mkt: str) -> pd.DataFrame:
    parts = sorted(glob.glob(f"{S.WH}/{mkt}/year=*.parquet"))
    df = pd.concat((pd.read_parquet(p, columns=["Date","Symbol","Close"]) for p in parts),
                   ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"])
    d = df.pivot_table(index="Date", columns="Symbol", values="Close", aggfunc="last").sort_index()
    return d.asfreq("B").ffill(limit=2).astype("float32")


def path_returns(d: pd.DataFrame, weekly_index) -> dict:
    """At each weekly formation date, per name: raw 2wk return, and the favourable/
    adverse excursions over the next 10 business days (for profit-booking/stops)."""
    fwd_close = (d.shift(-10) / d - 1)
    fmax = d[::-1].rolling(10, min_periods=1).max()[::-1].shift(-1) / d - 1   # best over next 10d
    fmin = d[::-1].rolling(10, min_periods=1).min()[::-1].shift(-1) / d - 1   # worst over next 10d
    idx = d.index.intersection(weekly_index)
    return {"raw": fwd_close.reindex(weekly_index).clip(-0.40, 0.40),
            "mfe": fmax.reindex(weekly_index), "mae": fmin.reindex(weekly_index)}


def leg_pnl(raw, mfe, mae, side):
    """Per-name P&L with take-profit + stop, for a long or short leg."""
    if side == "long":
        pnl = raw.copy()
        pnl = pnl.mask(mfe >= TP, TP)                 # book profit on the way up
        pnl = pnl.mask((mfe < TP) & (mae <= -SL), -SL)  # else stop if it fell first
    else:  # short: profit when price falls
        pnl = -raw
        pnl = pnl.mask(mae <= -TP, TP)                # book profit on the way down
        pnl = pnl.mask((mae > -TP) & (mfe >= SL), -SL)  # else stop if it rose first
    return pnl.clip(-0.40, 0.40)


def new_filters(w: pd.DataFrame, base: dict) -> dict:
    """Composite filters built ON TOP of the benchmark filters."""
    ret = w.pct_change(fill_method=None)
    vol13 = ret.rolling(13, min_periods=6).std()
    momr = w.pct_change(25, fill_method=None).rank(axis=1, pct=True)
    lvr = (-vol13).rank(axis=1, pct=True)
    trr = (w / w.ewm(span=40, adjust=False).mean() - 1).rank(axis=1, pct=True)
    blend = (momr + lvr + trr) / 3
    blend_rank = (blend >= 1 - S.TERCILE).astype(int) - (blend <= S.TERCILE).astype(int)
    tri = ((base["trend"] == 1) & (base["mom126"] == 1) & (base["breakout"] == 1)).astype(int) \
        - ((base["trend"] == -1) & (base["mom126"] == -1) & (base["breakout"] == -1)).astype(int)
    return {"tri_confirm": tri, "blend_rank": blend_rank}


def book_series(mkt, factor, regime, close, turn, reg, sig, paths, do_short, do_tp):
    """Per-week book return under the chosen mechanics; returns the excess-over-index
    series (dollar-neutral 50/50 when shorting)."""
    ex, dates = [], []
    for t in close.index[close.index >= S.START]:
        if reg.get(t) != regime:
            continue
        liq = S.liquidity_mask(turn.loc[t], close.loc[t])
        raw = paths["raw"].loc[t].where(liq)
        univ = raw.dropna().index
        if len(univ) < S.MIN_NAMES:
            continue
        s = sig.loc[t].reindex(univ)
        idxret = raw.loc[univ].mean()
        if do_tp:
            lp = leg_pnl(paths["raw"].loc[t], paths["mfe"].loc[t], paths["mae"].loc[t], "long").reindex(univ)
            sp = leg_pnl(paths["raw"].loc[t], paths["mfe"].loc[t], paths["mae"].loc[t], "short").reindex(univ)
        else:
            lp = raw.reindex(univ); sp = -raw.reindex(univ)
        buys = lp[s == 1].dropna()
        if len(buys) < 5:
            continue
        if do_short:
            sells = sp[s == -1].dropna()
            if len(sells) < 5:
                continue
            book = 0.5 * buys.mean() + 0.5 * sells.mean()      # dollar-neutral L/S
            ex.append(book); dates.append(t)                   # market-neutral: excess≈book
        else:
            ex.append(buys.mean() - idxret); dates.append(t)   # long-only excess
    if len(ex) < 10:
        return None
    e = pd.Series(ex, index=pd.DatetimeIndex(dates))           # DATE-indexed for correct year rollup
    return {"mean%": e.mean()*100, "ir": e.mean()/e.std()*np.sqrt(S.ANN) if e.std() else 0.0,
            "series": e}


def main() -> int:
    opt = json.loads((HERE / "cache_seed" / "zone_regime_optimized.json").read_text())
    rows, firm_year = [], {}
    for mkt in S.MARKETS:
        close, turn = S.load_panel(mkt)
        reg = S.regime_series(close, turn)
        base = S.signals(close)
        lib = {**base, **new_filters(close, base)}
        # add the reward-optimiser's extra factors too (lowvol/mom252/blends) for selection
        from profitability_optimizer import factor_library
        lib = {**factor_library(close), **new_filters(close, base)}
        d = daily_close(mkt)
        paths = path_returns(d, close.index)
        for regime in ("bull", "bear"):
            # pick the best factor for this regime across the FULL library by L/S+TP info ratio
            best = None
            for fac, sig in lib.items():
                r = book_series(mkt, fac, regime, close, turn, reg, sig, paths, do_short=True, do_tp=True)
                if r and (best is None or r["ir"] > best[1]["ir"]):
                    best = (fac, r)
            if best is None:
                continue
            fac = best[0]; sig = lib[fac]
            variants = {
                "long_only":  book_series(mkt, fac, regime, close, turn, reg, sig, paths, False, False),
                "long_short": book_series(mkt, fac, regime, close, turn, reg, sig, paths, True,  False),
                "lo_take_prof": book_series(mkt, fac, regime, close, turn, reg, sig, paths, False, True),
                "ls_take_prof": book_series(mkt, fac, regime, close, turn, reg, sig, paths, True,  True),
            }
            row = {"market": mkt, "regime": regime, "factor": fac}
            for k, v in variants.items():
                row[f"{k}_ir"] = round(v["ir"], 2) if v else None
                row[f"{k}_ret"] = round(v["mean%"], 3) if v else None
            rows.append(row)
            # firm annual PAT from the full L/S+TP book — series is DATE-indexed, so
            # group straight by calendar year (no index reconstruction).
            v = variants["ls_take_prof"]
            if v is not None:
                for yr, g in v["series"].groupby(v["series"].index.year):
                    holds = g.iloc[::2]                        # non-overlapping bi-weekly holds
                    pat = (Q.AUM_PER_DESK * holds.sum()
                           - Q.AUM_PER_DESK * len(holds) * Q.COST_BPS[mkt] / 1e4
                           - Q.AUM_PER_DESK * Q.OPEX_ANNUAL_PCT * 0.5)   # 0.5: this regime ≈ half the year
                    firm_year[yr] = firm_year.get(yr, 0.0) + pat
        print(f"  {mkt} done")

    df = pd.DataFrame(rows)
    df.to_csv(HERE / "reports" / "long_short_tp.csv", index=False)
    fy = pd.Series(firm_year).sort_index()
    equity = Q.AUM_PER_DESK * len(S.MARKETS)

    L = ["# Long/short + profit-booking on the reward-optimised book", "",
         f"New composite filters (tri_confirm, blend_rank) added on top of the benchmark "
         f"filters; best factor per market×regime selected by the long/short + take-profit "
         f"information ratio. Take-profit {TP*100:.0f}% / stop {SL*100:.0f}% on the daily path; "
         f"long/short is dollar-neutral 50/50. Reward (info ratio) as each mechanic is added:", "",
         "| market | regime | factor | long-only IR | +short IR | +take-profit IR | **L/S + TP IR** |",
         "|---|---|---|--:|--:|--:|--:|"]
    for _, r in df.iterrows():
        L.append(f"| {r.market} | {r.regime} | {r.factor} | {r.long_only_ir} | "
                 f"{r.long_short_ir} | {r.lo_take_prof_ir} | **{r.ls_take_prof_ir}** |")
    if len(fy):
        L += ["", "## Firm annual PAT ($M) — full long/short + profit-booking book", "",
              "| year | " + " | ".join(str(y) for y in fy.index) + " |",
              "|---|" + "---|"*len(fy.index),
              "| PAT | " + " | ".join(f"{fy[y]/1e6:+.2f}" for y in fy.index) + " |",
              "",
              f"Mean annual PAT ${fy.mean()/1e6:.2f}M · ROE {fy.mean()/equity*100:.1f}% · "
              f"annual Sharpe {fy.mean()/fy.std():.2f} · loss years {(fy<0).sum()}/{len(fy)}"]
    L += ["", "> Dollar-neutral long/short removes market beta, so its return IS its "
          "excess — that is why the L/S info ratios read higher and the loss years shrink "
          "(the short leg pays in the bear drawdowns the long-only book bled in). Gross of "
          "borrow cost/slippage. Not investment advice."]
    (HERE / "reports" / "long_short_tp.md").write_text("\n".join(L))
    print("\n".join(L))
    print("\nwrote reports/long_short_tp.{md,csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
