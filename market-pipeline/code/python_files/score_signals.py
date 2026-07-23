#!/usr/bin/env python3
"""Score every signal in the ledger against realized forward returns.

Closes the loop the ledger left open: signals were recorded with
price_at_signal but never marked to market. This computes forward returns
at +5/+21/+63/+252 *trading* days (per-symbol calendar) from the
global-market-data warehouse, plus market-median excess return, and writes:

  reports/signal_outcomes.parquet   one row per signal x horizon
  reports/SIGNAL_CALIBRATION.md     hit rates by market x filter x horizon

Signals whose horizon hasn't elapsed yet are 'pending' and fill in on the
next run (weekly cron). Re-runs are idempotent — full recompute, cheap.

Prices: IN reads the full adjusted copy (warehouse/ohlcv_adj/IN); JP/KR/US
read overlay-first (yf-adjusted base panels + confirmed residual-split
corrections in ohlcv_adj/<MKT>/corrected_symbols.parquet); CN/EU read the
base panels (yf-adjusted, no residuals). Each signal also gets a PIT-safe
volatility-regime label (build_regimes.py) and the report conditions
outcomes on it.
"""
import os
from datetime import datetime

import duckdb
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
GMD = os.path.expanduser("~/repos/global-market-data")
LEDGER = os.path.join(BASE, "cache_seed", "signal_ledger.parquet")
OUT_PARQUET = os.path.join(BASE, "reports", "signal_outcomes.parquet")
OUT_MD = os.path.join(BASE, "reports", "SIGNAL_CALIBRATION.md")
HORIZONS = [5, 21, 63, 252]

MARKET_SRC = {  # market -> base price partition (IN uses full adjusted copy)
    "IN": "ohlcv_adj/IN", "US": "ohlcv/US", "JP": "ohlcv/JP",
    "KR": "ohlcv/KR", "CN": "ohlcv/CN", "EU": "ohlcv/EU",
}


def px_source_sql(mkt: str, sub: str) -> str:
    """OVERLAY-FIRST price source: non-IN panels are yfinance-adjusted at
    collection, but symbols with confirmed post-assembly split breaks live
    corrected in ohlcv_adj/<MKT>/corrected_symbols.parquet — those rows
    supersede the base panel (see gmd DATA_ACCESS.md, price_adjuster_global)."""
    base = os.path.join(GMD, "warehouse", sub, "*.parquet")
    overlay = os.path.join(GMD, "warehouse", "ohlcv_adj", mkt,
                           "corrected_symbols.parquet")
    if mkt == "IN" or not os.path.exists(overlay):
        return f"select Symbol, Date, Close from parquet_scan('{base}')"
    return f"""(
      select Symbol, Date, Close from parquet_scan('{base}')
      where Symbol not in (select distinct Symbol
                           from parquet_scan('{overlay}'))
      union all
      select Symbol, Date, Close from parquet_scan('{overlay}')
    )"""


def main():
    con = duckdb.connect()
    sig = pd.read_parquet(LEDGER)
    backfill = os.path.join(BASE, "cache_seed", "signal_ledger_backfill.parquet")
    if os.path.exists(backfill):
        sig = pd.concat([sig, pd.read_parquet(backfill)], ignore_index=True)
    sig = sig.reset_index(drop=True)
    sig["signal_id"] = sig.index
    sig["signal_date"] = pd.to_datetime(sig["signal_date"])

    # normalize ledger symbols to warehouse conventions:
    #   JP ledger '9202'  -> '9202.T';  KR '5360' -> '005360.KS' or '.KQ'
    def variants(row):
        s, m = str(row.symbol), row.market
        if m == "JP":
            return [s if s.endswith(".T") else s + ".T"]
        if m == "KR":
            if s.endswith((".KS", ".KQ")):
                return [s]
            z = s.zfill(6)
            return [z + ".KS", z + ".KQ"]
        return [s]

    sig["wh_symbol"] = sig.apply(variants, axis=1)
    sig = sig.explode("wh_symbol", ignore_index=False).reset_index(drop=True)
    con.register("sig", sig)

    frames = []
    diags = []
    for mkt, sub in MARKET_SRC.items():
        n_sig = int(sig.loc[sig["market"] == mkt, "signal_id"].nunique())
        if n_sig == 0:
            continue
        path = os.path.join(GMD, "warehouse", sub, "*.parquet")
        try:
            con.sql(f"select 1 from parquet_scan('{path}') limit 1")
        except Exception:
            diags.append((mkt, n_sig, 0, "NO PRICE DATA"))
            continue
        q = f"""
        with src as ({px_source_sql(mkt, sub)}),
        px as (
          select Symbol as symbol, Date as date, Close as close,
                 row_number() over (partition by Symbol order by Date) as rn
          from src
        ),
        s as (select * from sig where market = '{mkt}'),
        entry as (
          -- join AND all downstream price lookups use wh_symbol (the
          -- warehouse-suffixed form): joining on the bare ledger symbol
          -- silently zeroed out every JP/KR score until 2026-07-23
          select s.signal_id, s.symbol, s.wh_symbol, s.signal_date,
                 s.price_at_signal, min(px.rn) as rn0
          from s join px on px.symbol = s.wh_symbol and px.date >= s.signal_date
          group by 1,2,3,4,5
        ),
        entry_px as (
          select e.*, px.close as entry_close
          from entry e join px on px.symbol = e.wh_symbol and px.rn = e.rn0
        ),
        horizons as (select unnest([{','.join(map(str, HORIZONS))}]) as h),
        joined as (
          select e.signal_id, e.symbol, e.signal_date, h.h,
                 coalesce(e.price_at_signal, e.entry_close) as entry_price,
                 f.close as exit_price, f.date as exit_date
          from entry_px e
          cross join horizons h
          left join px f on f.symbol = e.wh_symbol and f.rn = e.rn0 + h.h
        )
        select *, case when exit_price is not null
                       then exit_price / entry_price - 1 end as fwd_ret
        from joined
        """
        df = con.sql(q).df()
        df["market"] = mkt
        matched = df["signal_id"].nunique()
        pmx = con.sql(
            f"select max(Date) from parquet_scan('{path}')").fetchone()[0]
        smn = sig.loc[sig["market"] == mkt, "signal_date"].min()
        note = f"{matched / n_sig:.0%} anchored · panel ends {str(pmx)[:10]}"
        if pd.Timestamp(pmx) < smn:
            note += " — PANEL STALE, all signals pending until refresh"
        diags.append((mkt, n_sig, matched, note))
        # market-median benchmark per (signal_date, horizon): median forward
        # return across ALL warehouse symbols entered on the same date
        bq = f"""
        with src as ({px_source_sql(mkt, sub)}),
        px as (
          select Symbol as symbol, Date as date, Close as close,
                 row_number() over (partition by Symbol order by Date) as rn
          from src
        ),
        dates as (select distinct signal_date from sig where market = '{mkt}'),
        entry as (
          select d.signal_date, px.symbol, min(px.rn) as rn0
          from dates d join px on px.date >= d.signal_date
          group by 1,2
        ),
        horizons as (select unnest([{','.join(map(str, HORIZONS))}]) as h),
        rets as (
          select e.signal_date, h.h, f.close / e0.close - 1 as r
          from entry e
          join px e0 on e0.symbol = e.symbol and e0.rn = e.rn0
          cross join horizons h
          join px f on f.symbol = e.symbol and f.rn = e.rn0 + h.h
        )
        select signal_date, h, median(r) as mkt_median from rets group by 1,2
        """
        bench = con.sql(bq).df()
        df = df.merge(bench, on=["signal_date", "h"], how="left")
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    meta = sig[["signal_id", "market", "filter", "detail", "score", "source"]] \
        .drop_duplicates("signal_id")
    out = meta.merge(out.drop(columns=["market"]), on="signal_id", how="left")
    out["excess_ret"] = out["fwd_ret"] - out["mkt_median"]

    # volatility-regime label at signal date (PIT-safe trailing terciles;
    # build_regimes.py). India conditions on IndiaVIX, everything else on VIX.
    reg_path = os.path.join(GMD, "warehouse", "regimes.parquet")
    if os.path.exists(reg_path):
        regimes = pd.read_parquet(reg_path).rename(columns={"date": "signal_date"})
        out = out.merge(
            regimes[["signal_date", "vix_regime", "indiavix_regime"]],
            on="signal_date", how="left")
        out["regime"] = out["indiavix_regime"].where(
            out["market"] == "IN", out["vix_regime"])
    else:
        out["regime"] = None
    out["status"] = out["fwd_ret"].apply(
        lambda x: "scored" if pd.notna(x) else "pending")
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    out.to_parquet(OUT_PARQUET, index=False)

    scored = out[out["status"] == "scored"]
    lines = [
        f"# Signal calibration — generated {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Ledger: {sig['signal_id'].nunique():,} signals "
        f"({sig.signal_date.min():%Y-%m-%d} → {sig.signal_date.max():%Y-%m-%d}) · "
        f"scored rows: {len(scored):,} / {len(out):,} "
        "(rest pending — horizons not yet elapsed or symbol unmatched)",
        "",
        "Prices: IN = split/bonus-ADJUSTED (full copy); JP/KR/US = "
        "yfinance-adjusted panels + confirmed residual-split overlays "
        "(overlay-first); CN/EU = yfinance-adjusted, no residuals "
        "(2026-07-23 — see gmd claims.yaml non-india-panels-already-adjusted).",
        "",
        "## Symbol match diagnostics",
        "",
        "| market | signals | matched | note |",
        "|---|---|---|---|",
    ]
    for m, n, k, note in diags:
        lines.append(f"| {m} | {n} | {k} | {note} |")
    if len(scored):
        lines += ["", "## Outcomes by market × filter × horizon", "",
                  "| market | filter | h | n | hit% | median ret | median excess |",
                  "|---|---|---|---|---|---|---|"]
        scored = scored.copy()
        scored["direction"] = scored["detail"].astype(str).str.contains("SELL") \
            .map({True: "SELL", False: "BUY/long"})
        g = scored.groupby(["market", "filter", "direction", "h"])
        for (m, f, d, h), grp in g:
            # a SELL signal "hits" when the price FALLS
            hit = ((grp.fwd_ret < 0) if d == "SELL" else (grp.fwd_ret > 0)).mean()
            lines.append(
                f"| {m} | {f} {d} | {h}d | {len(grp)} | {hit:.0%} "
                f"| {grp.fwd_ret.median():+.2%} | {grp.excess_ret.median():+.2%} |")

    # regime conditioning: same outcomes split by the vol regime AT signal
    # date (IN: IndiaVIX terciles; others: VIX terciles; PIT-safe trailing
    # windows). One caution baked into the header: a cohort recorded inside a
    # single fortnight sits in a single regime — regime spread only becomes
    # meaningful as multi-month cohorts accrue.
    if len(scored) and scored["regime"].notna().any():
        lines += ["", "## Outcomes by volatility regime at signal date", "",
                  "Regime = tercile of the market's vol index vs its trailing "
                  "~3y window (PIT-safe, build_regimes.py). IN uses IndiaVIX; "
                  "others VIX. NB: a cohort from one short window sits in one "
                  "regime — read spreads only across multi-month samples.", "",
                  "| market | direction | h | regime | n | hit% | median ret "
                  "| median excess |",
                  "|---|---|---|---|---|---|---|---|"]
        gr = scored[scored["regime"].notna()].groupby(
            ["market", "direction", "h", "regime"])
        for (m, d, h, r), grp in gr:
            if h not in (5, 21) or len(grp) < 10:
                continue
            hit = ((grp.fwd_ret < 0) if d == "SELL" else (grp.fwd_ret > 0)).mean()
            lines.append(
                f"| {m} | {d} | {h}d | {r} | {len(grp)} | {hit:.0%} "
                f"| {grp.fwd_ret.median():+.2%} | {grp.excess_ret.median():+.2%} |")
    with open(OUT_MD, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {OUT_PARQUET} ({len(out):,} rows, {len(scored):,} scored)")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
