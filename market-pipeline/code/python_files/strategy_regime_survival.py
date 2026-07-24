#!/usr/bin/env python3
# strategy_regime_survival.py
# ===========================
# Do the best strategies/filters SURVIVE bull AND bear markets? (user, 2026-07-24)
#
# The paper-track book (signal_outcomes.parquet) is only ~2-3 sessions of forward
# data — it cannot tell bull from bear. This runs the SAME price-based filters the
# digest uses, point-in-time on each market's own 10y weekly panel (2016→2026,
# which contains the 2018 correction, the 2020 COVID crash, the 2022 bear, and the
# 2020-21 + 2023-24 bulls), and scores each filter's edge SEPARATELY in bull and
# bear weeks. A strategy "survives" only if its BUY-book beats the index benchmark
# in BOTH regimes.
#
# Regime per market per week = BREADTH (drift-neutral): the fraction of liquid
# (HIGH+MEDIUM turnover) names above their own 40-week trend.
#   BEAR = breadth < 0.45 (participation washout: 2018/2020/2022); BULL otherwise.
# Universe traded each week = HIGH+MEDIUM turnover tier only (liquidity survival).
#
# Filters tested (price-derived — the ones reconstructable PIT from OHLCV):
#   trend        BUY close>EMA20>EMA50 / SELL close<EMA50        (digest incumbent)
#   revert       BUY 1w return oversold tercile / SELL overbought (mean-reversion)
#   mom126       BUY 6-month return top tercile / SELL bottom     (classic momentum)
#   mom_st       BUY 1-month return top tercile / SELL bottom     (short momentum)
#   golden_cross BUY EMA10>EMA40 (50>200DMA proxy) / SELL below   (your GC filter)
#   breakout     BUY within 5% of 52w high / SELL >20% below      (Darvas proxy)
# Fundamental filters (piotroski/ccc/roce/value) need PIT fundamentals, not price —
# those are covered by backtest_piotroski_plus.py / backtest_pe_anomalies.py.
#
# Output: reports/strategy_regime_survival.md  + reports/strategy_regime_survival.csv
#         + cache_seed/strategy_regime_survival.json
#
# Book economics (ties to trading_financials.py): long-only BUY book, $10k/position,
# forward-10d hold, winsorized ±40%, $1 local-currency price floor. Returns shown
# per-2-week and annualized (×26); excess = BUY book − equal-weight index.

from __future__ import annotations
import glob, json, os, sys
from pathlib import Path
import numpy as np, pandas as pd
from obs import get_logger, timed, DecisionLog

HERE = Path(__file__).resolve().parent
LOG = get_logger("regime_survival")
# warehouse path is env-configurable so this runs unchanged on AWS (set MARKET_WH
# to wherever the panels were pulled from Dropbox/S3); defaults to the local tree.
WH = os.environ.get("MARKET_WH", "/Users/umashankar/repos/global-market-data/warehouse/ohlcv")
MARKETS = ("IN", "US", "JP", "KR", "EU")
FWD = 10                 # forward horizon (trading days) -> //5 on weekly grid
START = "2016-07-01"     # ~2y warmup consumed by 40wk MA / 126d lookbacks
MIN_NAMES = 60
TERCILE = 1/3.0
NOTIONAL = 10_000.0
ANN = 26                 # 2-week periods per year


def load_panel(mkt: str, years=None):
    """Weekly close panel + rolling-median TURNOVER panel (Close*Volume).
    Turnover drives the liquidity tier so the backtest only trades names a
    real book could fill (HIGH+MEDIUM tiers; the illiquid bottom third is
    dropped — the liquidity-survival stress test).
    `years` (list of ints) restricts partitions — used by the fast daily
    regime refresh, which only needs ~2y for the 52-week breadth."""
    parts = sorted(glob.glob(f"{WH}/{mkt}/year=*.parquet"))
    if years:
        parts = [p for p in parts if any(f"year={y}" in p for y in years)]
    df = pd.concat((pd.read_parquet(p, columns=["Date","Symbol","Close","Volume"])
                    for p in parts), ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"])
    df["turn"] = df["Close"] * df["Volume"]
    close = df.pivot_table(index="Date", columns="Symbol", values="Close", aggfunc="last").sort_index()
    turn  = df.pivot_table(index="Date", columns="Symbol", values="turn",  aggfunc="last").sort_index()
    close = close.asfreq("B").ffill(limit=2).resample("W-FRI").last()
    # avg daily turnover that week, then trailing 13-week (~63 session) median
    turn = turn.asfreq("B").resample("W-FRI").mean().rolling(13, min_periods=6).median()
    return close, turn


def liquidity_mask(turn_row: pd.Series, price_row: pd.Series) -> pd.Series:
    """HIGH+MEDIUM liquidity only: keep the top two turnover terciles this week,
    above a $1 price floor. Bottom (illiquid) tercile is excluded from trading."""
    ok = turn_row.notna() & (price_row >= 1.0)
    if ok.sum() < MIN_NAMES:
        return ok & False
    pct = turn_row.where(ok).rank(pct=True)
    return ok & (pct >= 1/3.0)          # drop bottom-tercile (LOW) turnover


def regime_series(w: pd.DataFrame, turn: pd.DataFrame) -> pd.Series:
    """BULL/BEAR per week by BREADTH: the fraction of liquid (top-2 turnover-tercile)
    names trading above their own 40-week EMA. BEAR = breadth < 0.45 (a genuine
    participation washout — collapses in 2018/2020/2022), BULL otherwise.
    Breadth is drift-neutral (bounded 0-1), so it avoids the cumulative-index drift
    that made a mean index degenerate for the US (IPO-inflated) and a median index
    degenerate for KR (microcap bleed)."""
    ema40 = w.ewm(span=40, adjust=False).mean()
    liq = turn.rank(axis=1, pct=True) >= 1/3.0          # HIGH+MEDIUM only
    above = (w > ema40).where(liq)
    breadth = above.mean(axis=1)                        # 0..1, drift-free
    reg = np.where(breadth < 0.45, "bear", "bull")
    return pd.Series(reg, index=w.index).where(breadth.notna())


def signals(w: pd.DataFrame) -> dict:
    ema20 = w.ewm(span=4, adjust=False).mean()
    ema50 = w.ewm(span=10, adjust=False).mean()
    ema10w = w.ewm(span=10, adjust=False).mean()   # 50DMA proxy
    ema40w = w.ewm(span=40, adjust=False).mean()   # 200DMA proxy
    r5, r21, r126 = (w.pct_change(k, fill_method=None) for k in (1, 4, 25))
    hi52 = w.rolling(52, min_periods=26).max()
    off_high = w / hi52 - 1

    def terc(r):
        p = r.rank(axis=1, pct=True)
        return (p >= 1 - TERCILE).astype(int) - (p <= TERCILE).astype(int)

    return {
        "trend":  ((w > ema20) & (ema20 > ema50)).astype(int) - (w < ema50).astype(int),
        "revert": -terc(r5),
        "mom126": terc(r126),
        "mom_st": terc(r21),
        "golden_cross": (ema10w > ema40w).astype(int) - (ema10w <= ema40w).astype(int),
        "breakout": (off_high >= -0.05).astype(int) - (off_high <= -0.20).astype(int),
    }


def score(w, sig, reg, turn):
    """Per regime: (BUY-SELL spread%, t), (BUY-book ret%, t), index ret%, excess%, n_weeks.
    Universe each week = HIGH+MEDIUM turnover tier only (liquidity survival)."""
    fwd = (w.shift(-FWD // 5) / w - 1).clip(-0.40, 0.40)
    rows = {g: {"sp": [], "book": [], "idx": []} for g in ("bull", "bear")}
    for t in w.index[w.index >= START]:
        g = reg.get(t)
        if g not in ("bull", "bear"):
            continue
        s = sig.loc[t]
        liq = liquidity_mask(turn.loc[t], w.loc[t])   # HIGH+MEDIUM names only
        f = fwd.loc[t].where(liq).dropna()
        if len(f) < MIN_NAMES:
            continue
        buys = f[s.reindex(f.index) == 1]
        sells = f[s.reindex(f.index) == -1]
        if len(buys) >= MIN_NAMES // 2 and len(sells) >= MIN_NAMES // 2:
            rows[g]["sp"].append(buys.mean() - sells.mean())
            rows[g]["book"].append(buys.mean())
            rows[g]["idx"].append(f.mean())

    def stat(v):
        s = pd.Series(v)
        if len(s) < 8:
            return np.nan, np.nan
        d = s.iloc[::2]                     # de-overlap 2-week returns
        return float(s.mean()), float(d.mean() / d.std() * np.sqrt(len(d)))

    out = {}
    for g in ("bull", "bear"):
        sp, tsp = stat(rows[g]["sp"])
        bk, tbk = stat(rows[g]["book"])
        ix = float(np.mean(rows[g]["idx"])) if rows[g]["idx"] else np.nan
        out[g] = {"spread_pct": sp*100 if sp==sp else np.nan, "spread_t": tsp,
                  "book_ret_pct": bk*100 if bk==bk else np.nan, "book_t": tbk,
                  "index_ret_pct": ix*100 if ix==ix else np.nan,
                  "excess_pct": (bk-ix)*100 if (bk==bk and ix==ix) else np.nan,
                  "n_weeks": len(rows[g]["sp"])}
    return out


def refresh_regime() -> int:
    """Fast daily update of just current_regime + active_rule in zone_regime.json,
    preserving the monthly-computed bull_rule/bear_rule. Loads only ~2y per market
    (enough for 52-week breadth) so it can run every morning before the mailer."""
    dl = DecisionLog()
    path = HERE / "cache_seed" / "zone_regime.json"
    if not path.exists():
        LOG.warning("zone_regime.json absent — run the full backtest first"); return 0
    zr = json.loads(path.read_text())
    yr = max(int(p.split("year=")[1].split(".")[0])
             for p in glob.glob(f"{WH}/IN/year=*.parquet"))
    with timed(LOG, "regime refresh (all markets)"):
        for mkt in MARKETS:
            if mkt not in zr:
                continue
            try:
                close, turn = load_panel(mkt, years=[yr - 1, yr])
                reg = regime_series(close, turn).dropna()
                cur = str(reg.iloc[-1]) if reg.size else zr[mkt].get("current_regime", "bull")
                asof = str(reg.index[-1].date()) if reg.size else None
            except Exception as e:
                LOG.error(f"{mkt}: regime refresh failed ({e})"); continue
            prev = zr[mkt].get("current_regime")
            zr[mkt]["current_regime"] = cur
            zr[mkt]["active_rule"] = zr[mkt]["bull_rule"] if cur == "bull" else zr[mkt]["bear_rule"]
            if cur != prev:
                LOG.info(f"{mkt}: REGIME FLIP {prev} -> {cur} (active_rule now {zr[mkt]['active_rule']})")
            dl.record("regime_refresh", market=mkt, prev_regime=prev, current_regime=cur,
                      active_rule=zr[mkt]["active_rule"], breadth_asof=asof, flip=(cur != prev))
    path.write_text(json.dumps(zr, indent=1))
    LOG.info("regime refreshed: " + ", ".join(
        f"{m}={zr[m]['current_regime'][:4]}->{zr[m]['active_rule']}" for m in zr))
    LOG.info(f"decision log -> {dl.path} (run {dl.run})")
    return 0


def main() -> int:
    if "--refresh-regime" in sys.argv:
        return refresh_regime()
    dl = DecisionLog()
    LOG.info(f"full regime-survival backtest START (run {dl.run}, WH={WH})")
    zone = {}
    zp = HERE / "cache_seed" / "zone_rules.json"
    if zp.exists():
        zone = json.loads(zp.read_text())
    rules = ["trend", "revert", "mom126", "mom_st", "golden_cross", "breakout"]
    recs, verdict, cur_regime = [], {}, {}
    for mkt in MARKETS:
        try:
            with timed(LOG, f"load+score {mkt}"):
                close, turn = load_panel(mkt)
        except Exception as e:
            LOG.error(f"{mkt}: load failed {e}"); continue
        reg = regime_series(close, turn)
        cur_regime[mkt] = str(reg.dropna().iloc[-1]) if reg.dropna().size else "bull"
        sig = signals(close)
        nb = int((reg == "bull").sum()); nr = int((reg == "bear").sum())
        print(f"{mkt}: {close.shape[1]} names, {reg.dropna().index.min().date()}→"
              f"{reg.dropna().index.max().date()}, {nb} bull / {nr} bear weeks")
        for r in rules:
            sc = score(close, sig[r], reg, turn)
            for g in ("bull", "bear"):
                d = sc[g]; recs.append({"market": mkt, "strategy": r, "regime": g, **d})
        # survival verdict on this market's zone-winner (from zone_rules.json), else trend
        win = zone.get(mkt, {}).get("rule", "trend")
        sc = score(close, sig[win], reg, turn)
        surv = (sc["bull"]["excess_pct"] is not np.nan and sc["bear"]["excess_pct"] is not np.nan
                and (sc["bull"]["excess_pct"] or 0) > 0 and (sc["bear"]["excess_pct"] or 0) > 0)
        verdict[mkt] = {"winning_rule": win,
                        "bull_excess_pct": round(sc["bull"]["excess_pct"], 3) if sc["bull"]["excess_pct"]==sc["bull"]["excess_pct"] else None,
                        "bear_excess_pct": round(sc["bear"]["excess_pct"], 3) if sc["bear"]["excess_pct"]==sc["bear"]["excess_pct"] else None,
                        "survives_both": bool(surv), "bull_weeks": nb, "bear_weeks": nr}

    df = pd.DataFrame(recs)
    df.to_csv(HERE / "reports" / "strategy_regime_survival.csv", index=False)
    (HERE / "cache_seed" / "strategy_regime_survival.json").write_text(json.dumps(verdict, indent=1))

    # ---- regime-conditional zone map for the digest --------------------------
    # For each market pick the best-excess rule SEPARATELY for bull and bear,
    # restricted to the rules assign_recommendations() can apply cross-sectionally
    # (trend/revert/mom126/mom_st — breakout/golden_cross need per-name state the
    # digest doesn't carry). current_regime = this market's latest breadth reading;
    # the digest applies bull_rule when currently bull, bear_rule when bear.
    SUPPORTED = ["trend", "revert", "mom126", "mom_st"]
    zone_regime = {}
    for mkt in MARKETS:
        m = df[(df.market == mkt) & (df.strategy.isin(SUPPORTED))]
        if m.empty:
            continue
        def best(regime):
            sub = m[m.regime == regime].dropna(subset=["excess_pct"])
            sub = sub[sub.excess_pct > 0]
            if sub.empty:                       # nothing beats the index -> hold trend
                return "trend", None
            row = sub.loc[sub.excess_pct.idxmax()]
            return row.strategy, round(float(row.excess_pct), 3)
        br, bx = best("bull"); er, ex = best("bear")
        zone_regime[mkt] = {"bull_rule": br, "bull_excess": bx,
                            "bear_rule": er, "bear_excess": ex,
                            "current_regime": cur_regime.get(mkt, "bull"),
                            "active_rule": br if cur_regime.get(mkt) == "bull" else er,
                            "asof": str(df.attrs.get("asof", ""))}
    (HERE / "cache_seed" / "zone_regime.json").write_text(json.dumps(zone_regime, indent=1))
    print("\n=== regime-conditional zone map (cache_seed/zone_regime.json) ===")
    for mkt, z in zone_regime.items():
        print(f"  {mkt}: bull={z['bull_rule']}({z['bull_excess']}) "
              f"bear={z['bear_rule']}({z['bear_excess']}) "
              f"| now {z['current_regime'].upper()} -> ACTIVE {z['active_rule']}")
        dl.record("regime_rule", market=mkt, **z)     # audit trail of the chosen rules
    LOG.info(f"backtest DONE — regime map written; decision log -> {dl.path} (run {dl.run})")

    # ---- markdown report -----------------------------------------------------
    L = ["# Strategy survival across bull & bear markets (2016→2026)", "",
         "Each price-based filter run PIT on each market's own 10y weekly panel; "
         "returns split by regime (BEAR = breadth <45% of liquid names above their "
         "40-week trend; BULL otherwise). Universe = HIGH+MEDIUM turnover tier only. "
         "`spread` = BUY−SELL fwd-10d; `book` = long-only BUY names; `index` = "
         "equal-weight all names (the benchmark); `excess` = book − index. "
         "**Survives = excess > 0 in BOTH regimes.** No costs, weekly rebalance.", ""]
    for mkt in MARKETS:
        m = df[df.market == mkt]
        if m.empty: continue
        v = verdict.get(mkt, {})
        L += [f"## {mkt}  ({v.get('bull_weeks','?')} bull / {v.get('bear_weeks','?')} bear weeks)"
              f" — zone-winner **{v.get('winning_rule','?')}**, "
              f"survives both: **{'YES' if v.get('survives_both') else 'NO'}**", "",
              "| strategy | regime | spread% (t) | book% | index% | excess% |",
              "|---|---|---|---|---|---|"]
        for r in ["trend","revert","mom126","mom_st","golden_cross","breakout"]:
            for g in ("bull","bear"):
                row = m[(m.strategy==r)&(m.regime==g)]
                if row.empty: continue
                x = row.iloc[0]
                def f(v,p=2): return f"{v:+.{p}f}" if v==v else "—"
                L.append(f"| {r if g=='bull' else ''} | {g} | {f(x.spread_pct)} "
                         f"(t{f(x.spread_t,1)}) | {f(x.book_ret_pct)} | "
                         f"{f(x.index_ret_pct)} | **{f(x.excess_pct)}** |")
        L.append("")
    # annualized economic summary for the zone-winner per market
    L += ["## Book economics — zone-winner, annualized (×26), $10k/position",
          "| market | regime | book ret/2w | annualized | vs index (excess ann.) | $ excess p.a. / $1M book |",
          "|---|---|---|---|---|---|"]
    for mkt in MARKETS:
        v = verdict.get(mkt, {}); win = v.get("winning_rule")
        m = df[(df.market==mkt)&(df.strategy==win)]
        for g in ("bull","bear"):
            row = m[m.regime==g]
            if row.empty: continue
            x = row.iloc[0]
            if x.book_ret_pct != x.book_ret_pct: continue
            ann_b = x.book_ret_pct*ANN; ann_x = (x.excess_pct or 0)*ANN
            dollar = ann_x/100*1_000_000
            L.append(f"| {mkt if g=='bull' else ''} | {g} | {x.book_ret_pct:+.2f}% | "
                     f"{ann_b:+.1f}% | {ann_x:+.1f}% | {dollar:+,.0f} |")
    L += ["", "> ⚠️ Long-only book returns are gross, no costs, no slippage, weekly "
          "rebalance on a $1-floor universe; annualization assumes the per-regime "
          "mean repeats — a ceiling, not a forecast. Excess vs the equal-weight "
          "index is the survival read; the raw book return just inherits beta."]
    md = HERE / "reports" / "strategy_regime_survival.md"
    md.write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nwrote {md}, reports/strategy_regime_survival.csv, cache_seed/strategy_regime_survival.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
