#!/usr/bin/env python3
"""
pit_event_studies.py — the XBRL × corporate-actions × bhavcopy join
(CIO-review "biggest exhaustiveness upside" item). India, fully point-in-time.

Three studies, all on ADJUSTED prices (warehouse/ohlcv_adj/IN) with abnormal
returns vs the daily cross-sectional market median:

1. PEAD, announcement-return sorted (ALL 66k+ filing-dated events):
   NSE results_index gives the broadcast TIMESTAMP of every quarterly result.
   Financials are parsed for only ~2% of events, so the primary sort variable
   is the classic fundamentals-free one: the announcement-window [0,+1]
   abnormal return. Quintile within calendar quarter -> drift CAR [+2,+21]
   and [+2,+63]. PIT discipline: broadcast after 15:30 IST -> day 0 is the
   NEXT trading day.

2. PEAD, surprise-sorted (parsed XBRL subset): PAT YoY surprise terciles on
   pit_quarterly.parquet where the same file holds the year-ago quarter.

3. Post-CA event study: splits & bonuses from corp_actions_history (10y,
   parsed with price_adjuster.py's regexes) -> CAR windows around the
   ex-date on adjusted prices ([-20,-1] run-up, [0,+20], [+21,+60]).

OUTPUT
    reports/pit_event_studies.parquet   per-event rows, all three studies
    reports/PIT_EVENT_STUDIES.md        the three tables + caveats
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
MC = os.path.expanduser("~/market-pipeline/market_cache")
ADJ = os.path.expanduser("~/repos/global-market-data/warehouse/ohlcv_adj/IN/*.parquet")
OUT_PQ = os.path.join(BASE, "reports", "pit_event_studies.parquet")
OUT_MD = os.path.join(BASE, "reports", "PIT_EVENT_STUDIES.md")

SPLIT_RE = re.compile(
    r"From\s+R[se]\.?\s*([\d.]+)/?-?\s*(?:Per Share)?\s*To\s+R[se]\.?\s*([\d.]+)", re.I)
BONUS_RE = re.compile(r"Bonus\s+(\d+)\s*:\s*(\d+)", re.I)


def load_prices(con) -> None:
    """px: per-symbol trading calendar + log returns; mkt: daily median."""
    con.sql(f"""
    CREATE TEMP TABLE px AS
    SELECT Symbol AS symbol, CAST(Date AS DATE) AS date, Close AS close,
           row_number() OVER (PARTITION BY Symbol ORDER BY Date) AS rn,
           ln(Close / lag(Close) OVER (PARTITION BY Symbol ORDER BY Date)) AS lr
    FROM read_parquet('{ADJ}')
    WHERE Close > 0
    """)
    con.sql("""
    CREATE TEMP TABLE mkt AS
    SELECT date, median(lr) AS mlr,
           row_number() OVER (ORDER BY date) AS mrn
    FROM px WHERE lr IS NOT NULL GROUP BY date
    """)
    con.sql("""
    CREATE TEMP TABLE mcum AS
    SELECT date, mrn, sum(mlr) OVER (ORDER BY mrn) AS cum FROM mkt
    """)
    # per-symbol cumulative abnormal log return (symbol lr - market mlr)
    con.sql("""
    CREATE TEMP TABLE acum AS
    SELECT p.symbol, p.date, p.rn,
           sum(coalesce(p.lr,0) - coalesce(m.mlr,0))
             OVER (PARTITION BY p.symbol ORDER BY p.rn) AS acum
    FROM px p LEFT JOIN mkt m USING (date)
    """)


def car(con, events: pd.DataFrame, w1: int, w2: int, col: str) -> pd.DataFrame:
    """CAR over trading-day window [w1,w2] relative to each event's day0 rn.
    events must have (event_id, symbol, rn0)."""
    con.register("ev", events[["event_id", "symbol", "rn0"]])
    df = con.sql(f"""
    SELECT e.event_id,
           b.acum - a.acum AS {col}
    FROM ev e
    JOIN acum a ON a.symbol = e.symbol AND a.rn = e.rn0 + {w1} - 1
    JOIN acum b ON b.symbol = e.symbol AND b.rn = e.rn0 + {w2}
    """).df()
    return df


def anchor_events(con, ev: pd.DataFrame) -> pd.DataFrame:
    """day0 = first trading day >= eff_date; rn0 = its per-symbol rn."""
    con.register("raw_ev", ev)
    return con.sql("""
    SELECT r.event_id, r.symbol, r.eff_date, min_by(p.rn, p.date) AS rn0,
           min(p.date) AS day0
    FROM raw_ev r
    JOIN px p ON p.symbol = r.symbol AND p.date >= r.eff_date
    GROUP BY 1,2,3
    """).df()


def pead_events() -> pd.DataFrame:
    idx = pd.read_parquet(os.path.join(MC, "nse_xbrl", "results_index.parquet"))
    idx["bc"] = pd.to_datetime(idx["broadCastDate"],
                               format="%d-%b-%Y %H:%M:%S", errors="coerce")
    idx = idx.dropna(subset=["bc", "symbol", "toDate"])
    # one event per (symbol, period): the FIRST broadcast is the news
    idx = idx.sort_values("bc").drop_duplicates(["symbol", "toDate"], keep="first")
    # after-close broadcasts hit the tape next trading day
    idx["eff_date"] = np.where(
        idx["bc"].dt.time <= pd.Timestamp("15:30").time(),
        idx["bc"].dt.normalize(),
        idx["bc"].dt.normalize() + pd.Timedelta(days=1))
    idx["eff_date"] = pd.to_datetime(idx["eff_date"]).dt.date
    idx = idx.reset_index(drop=True)
    idx["event_id"] = idx.index
    idx["quarter"] = idx["bc"].dt.to_period("Q").astype(str)
    return idx[["event_id", "symbol", "eff_date", "quarter", "toDate"]]


def ca_events() -> pd.DataFrame:
    ca = pd.read_parquet(os.path.join(MC, "exchange_extras",
                                      "corp_actions_history.parquet"))
    ca["ex"] = pd.to_datetime(ca["exDate"], format="%d-%b-%Y", errors="coerce")
    rows = []
    for _, r in ca.iterrows():
        subj = str(r.get("subject", ""))
        if pd.isna(r["ex"]):
            continue
        m = SPLIT_RE.search(subj)
        if m and ("split" in subj.lower() or "sub-division" in subj.lower()):
            rows.append({"symbol": r["symbol"], "eff_date": r["ex"].date(),
                         "kind": "split"})
            continue
        if BONUS_RE.search(subj) and "bonus" in subj.lower():
            rows.append({"symbol": r["symbol"], "eff_date": r["ex"].date(),
                         "kind": "bonus"})
    ev = pd.DataFrame(rows).drop_duplicates()
    ev = ev.reset_index(drop=True)
    ev["event_id"] = ev.index
    return ev


def ann_ca_events(ca: pd.DataFrame) -> pd.DataFrame:
    """Match each split/bonus ex-date to its earliest board-meeting INTIMATION
    (bm_timestamp within 180d before ex) — the first public, timestamped
    signal. corp_actions' own caBroadcastDate is null in every row (verified
    against the live API 2026-07-23); the intimation is the honest anchor."""
    bm_path = os.path.join(MC, "exchange_extras",
                           "board_meetings_bonus_split.parquet")
    if not os.path.exists(bm_path):
        return pd.DataFrame()
    bm = pd.read_parquet(bm_path)
    bm["ann"] = pd.to_datetime(bm["bm_timestamp"],
                               format="%d-%b-%Y %H:%M:%S", errors="coerce")
    bm = bm.dropna(subset=["ann"])
    m = ca.merge(bm[["bm_symbol", "ann"]], left_on="symbol",
                 right_on="bm_symbol")
    ex = pd.to_datetime(m["eff_date"])
    m = m[(m["ann"] < ex) & (m["ann"] >= ex - pd.Timedelta(days=180))]
    if m.empty:
        return pd.DataFrame()
    idxmin = m.groupby("event_id")["ann"].idxmin()
    m = m.loc[idxmin, ["event_id", "symbol", "kind", "eff_date", "ann"]]
    # intimation after 15:30 -> tradeable from the next day
    m["ann_eff"] = np.where(
        m["ann"].dt.time <= pd.Timestamp("15:30").time(),
        m["ann"].dt.normalize(),
        m["ann"].dt.normalize() + pd.Timedelta(days=1))
    m["ann_eff"] = pd.to_datetime(m["ann_eff"]).dt.date
    return m.reset_index(drop=True)


def surprise_events() -> pd.DataFrame:
    q = pd.read_parquet(os.path.join(MC, "nse_xbrl", "pit_quarterly.parquet"))
    q["filing"] = pd.to_datetime(q["filing_date"],
                                 format="%d-%b-%Y %H:%M", errors="coerce")
    q["period_end"] = pd.to_datetime(q["period_end"])
    q = q.dropna(subset=["filing", "pat", "period_end"])
    q = q.sort_values("filing").drop_duplicates(["symbol", "period_end"])
    prior = q.copy()
    prior["period_end"] = prior["period_end"] + pd.offsets.DateOffset(years=1)
    m = q.merge(prior[["symbol", "period_end", "pat"]],
                on=["symbol", "period_end"], suffixes=("", "_yoy"))
    m = m[m["pat_yoy"].abs() > 0]
    m["surprise"] = (m["pat"] - m["pat_yoy"]) / m["pat_yoy"].abs()
    m["eff_date"] = np.where(
        m["filing"].dt.time <= pd.Timestamp("15:30").time(),
        m["filing"].dt.normalize(),
        m["filing"].dt.normalize() + pd.Timedelta(days=1))
    m["eff_date"] = pd.to_datetime(m["eff_date"]).dt.date
    m = m.reset_index(drop=True)
    m["event_id"] = m.index
    return m[["event_id", "symbol", "eff_date", "surprise"]]


def qtable(df: pd.DataFrame, sortcol: str, buckets: int, bucket_name: str,
           within: str | None = None) -> pd.DataFrame:
    d = df.dropna(subset=[sortcol, "car_2_21", "car_2_63"]).copy()
    if within:
        d[bucket_name] = d.groupby(within)[sortcol].transform(
            lambda s: pd.qcut(s, buckets, labels=False, duplicates="drop"))
    else:
        d[bucket_name] = pd.qcut(d[sortcol], buckets, labels=False,
                                 duplicates="drop")
    g = d.groupby(bucket_name)
    return pd.DataFrame({
        "n": g.size(),
        "sort_median": g[sortcol].median(),
        "CAR_2_21_mean": g["car_2_21"].mean(),
        "CAR_2_63_mean": g["car_2_63"].mean(),
        "hit_63": g["car_2_63"].apply(lambda s: (s > 0).mean()),
    })


def main() -> int:
    con = duckdb.connect()
    print("loading adjusted panel…")
    load_prices(con)

    # ---- Study 1: announcement-return-sorted PEAD -------------------------
    ev = pead_events()
    n_events_total = len(ev)
    print(f"PEAD events: {len(ev):,}")
    anch = anchor_events(con, ev)
    ev = ev.merge(anch[["event_id", "rn0", "day0"]], on="event_id")
    print(f"  anchored: {len(ev):,}")
    ev = ev.merge(car(con, ev, 0, 1, "ann_ret"), on="event_id", how="left")
    ev = ev.merge(car(con, ev, 2, 21, "car_2_21"), on="event_id", how="left")
    ev = ev.merge(car(con, ev, 2, 63, "car_2_63"), on="event_id", how="left")
    t1 = qtable(ev, "ann_ret", 5, "quintile", within="quarter")

    # ---- Study 2: surprise-sorted PEAD (parsed subset) --------------------
    sv = surprise_events()
    print(f"surprise events: {len(sv):,}")
    t2 = None
    if len(sv) >= 60:
        anch2 = anchor_events(con, sv)
        sv = sv.merge(anch2[["event_id", "rn0", "day0"]], on="event_id")
        sv = sv.merge(car(con, sv, 2, 21, "car_2_21"), on="event_id", how="left")
        sv = sv.merge(car(con, sv, 2, 63, "car_2_63"), on="event_id", how="left")
        t2 = qtable(sv, "surprise", 3, "tercile")

    # ---- Study 3: post-split / post-bonus ---------------------------------
    cv = ca_events()
    print(f"CA events: {len(cv):,} ({(cv.kind == 'split').sum()} splits, "
          f"{(cv.kind == 'bonus').sum()} bonuses)")
    anch3 = anchor_events(con, cv)
    cv = cv.merge(anch3[["event_id", "rn0", "day0"]], on="event_id")
    cv = cv.merge(car(con, cv, -20, -1, "car_pre"), on="event_id", how="left")
    cv = cv.merge(car(con, cv, 0, 20, "car_0_20"), on="event_id", how="left")
    cv = cv.merge(car(con, cv, 21, 60, "car_21_60"), on="event_id", how="left")
    t3 = cv.dropna(subset=["car_0_20"]).groupby("kind").agg(
        n=("event_id", "size"),
        car_pre_mean=("car_pre", "mean"),
        car_0_20_mean=("car_0_20", "mean"),
        car_21_60_mean=("car_21_60", "mean"),
        hit_0_20=("car_0_20", lambda s: (s > 0).mean()),
    )

    # ---- Study 3b: intimation-anchored (was the run-up tradeable?) --------
    av = ann_ca_events(ca_events())
    t4 = None
    if len(av):
        # anchor the intimation day
        ann_frame = av[["event_id", "symbol"]].assign(eff_date=av["ann_eff"])
        ann_anchor = anchor_events(con, ann_frame)
        av = av.merge(ann_anchor[["event_id", "rn0"]].rename(
            columns={"rn0": "rn_ann"}), on="event_id")
        # anchor the ex day
        ex_anchor = anchor_events(con, av[["event_id", "symbol", "eff_date"]])
        av = av.merge(ex_anchor[["event_id", "rn0"]].rename(
            columns={"rn0": "rn_ex"}), on="event_id")
        av = av[av["rn_ex"] > av["rn_ann"] + 2]
        con.register("av", av[["event_id", "symbol", "rn_ann", "rn_ex"]])
        seg = con.sql("""
        SELECT e.event_id,
               r1.acum - a0.acum AS car_react,      -- intimation day 0..+1
               x1.acum - r1.acum AS car_drift_ex    -- +2 .. ex-1 (tradeable)
        FROM av e
        JOIN acum a0 ON a0.symbol = e.symbol AND a0.rn = e.rn_ann - 1
        JOIN acum r1 ON r1.symbol = e.symbol AND r1.rn = e.rn_ann + 1
        JOIN acum x1 ON x1.symbol = e.symbol AND x1.rn = e.rn_ex - 1
        """).df()
        av = av.merge(seg, on="event_id", how="left")
        av["gap_td"] = av["rn_ex"] - av["rn_ann"]
        t4 = av.dropna(subset=["car_drift_ex"]).groupby("kind").agg(
            n=("event_id", "size"),
            gap_med=("gap_td", "median"),
            car_react_mean=("car_react", "mean"),
            car_drift_mean=("car_drift_ex", "mean"),
            hit_drift=("car_drift_ex", lambda s: (s > 0).mean()),
        )

    # ---- persist ----------------------------------------------------------
    ev["study"] = "pead_annret"
    sv["study"] = "pead_surprise"
    cv["study"] = "post_ca"
    parts = [ev, sv, cv]
    if t4 is not None:
        av["study"] = "post_ca_intimation"
        parts.append(av)
    allrows = pd.concat(parts, ignore_index=True)
    os.makedirs(os.path.dirname(OUT_PQ), exist_ok=True)
    allrows.to_parquet(OUT_PQ, index=False)

    pct = "{:+.2%}".format
    lines = [
        f"# PIT event studies (India) — generated {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "The XBRL × corporate-actions × bhavcopy join. All returns are",
        "cumulative ABNORMAL log returns (symbol − daily market median) on",
        "split/bonus-ADJUSTED prices. Event timing is the NSE broadcast",
        "timestamp; after-15:30 broadcasts anchor to the next trading day —",
        "fully point-in-time, no period-end dating anywhere.",
        "",
        "## 1. PEAD sorted on announcement-window [0,+1] abnormal return",
        "",
        f"{len(ev):,} anchored filing-dated events (deduped index universe:",
        f"{n_events_total:,}; the rest fall outside the 2016+ adjusted panel",
        "or lack price coverage).",
        "Quintiles are WITHIN calendar quarter (cross-sectional).",
        "",
        "| quintile | n | ann ret (med) | CAR +2..+21 | CAR +2..+63 | hit(63d) |",
        "|---|---|---|---|---|---|",
    ]
    for iq, r in t1.iterrows():
        lines.append(f"| Q{int(iq) + 1} | {int(r.n):,} | {pct(r.sort_median)} "
                     f"| {pct(r.CAR_2_21_mean)} | {pct(r.CAR_2_63_mean)} "
                     f"| {r.hit_63:.0%} |")
    lines += [
        "",
        "Reading: classic PEAD predicts Q5 (best announcement reaction)",
        "drifts UP and Q1 drifts DOWN. Q5−Q1 CAR63 spread = "
        f"{pct(t1.CAR_2_63_mean.iloc[-1] - t1.CAR_2_63_mean.iloc[0])}.",
        "",
        "## 2. PEAD sorted on PAT YoY surprise (parsed-XBRL subset)",
        "",
    ]
    if t2 is not None:
        lines += [
            f"{int(t2.n.sum()):,} events with a same-file year-ago quarter.",
            "",
            "| tercile | n | surprise (med) | CAR +2..+21 | CAR +2..+63 | hit(63d) |",
            "|---|---|---|---|---|---|",
        ]
        for it, r in t2.iterrows():
            lines.append(f"| T{int(it) + 1} | {int(r.n):,} | {r.sort_median:+.0%} "
                         f"| {pct(r.CAR_2_21_mean)} | {pct(r.CAR_2_63_mean)} "
                         f"| {r.hit_63:.0%} |")
        lines += ["", "Small sample — directional read only; grows as the XML",
                  "parse queue drains (2,194 of 110,942 filings parsed)."]
    else:
        lines.append("(too few parsed filings with year-ago comparables — "
                     "skipped)")
    lines += [
        "",
        "## 3. Post-split / post-bonus event study (ex-date anchored)",
        "",
        "| kind | n | CAR −20..−1 | CAR 0..+20 | CAR +21..+60 | hit(0..+20) |",
        "|---|---|---|---|---|---|",
    ]
    for k, r in t3.iterrows():
        lines.append(f"| {k} | {int(r.n):,} | {pct(r.car_pre_mean)} "
                     f"| {pct(r.car_0_20_mean)} | {pct(r.car_21_60_mean)} "
                     f"| {r.hit_0_20:.0%} |")
    if t4 is not None:
        lines += [
            "",
            "## 3b. Intimation-anchored: was the pre-ex run-up tradeable?",
            "",
            "Anchor = board-meeting INTIMATION broadcast (bm_timestamp — the",
            "first public signal a bonus/split is being considered; NSE's",
            "caBroadcastDate field is null in every corp-actions row).",
            "`react` = intimation day 0..+1 (not tradeable in advance);",
            "`drift` = day +2 .. ex−1 (fully tradeable window).",
            "",
            "| kind | n | gap (td, med) | CAR react [0,+1] | CAR drift [+2,ex−1] "
            "| hit(drift) |",
            "|---|---|---|---|---|---|",
        ]
        for k, r in t4.iterrows():
            lines.append(f"| {k} | {int(r.n):,} | {r.gap_med:.0f} "
                         f"| {pct(r.car_react_mean)} | {pct(r.car_drift_mean)} "
                         f"| {r.hit_drift:.0%} |")
        lines += [
            "",
            "Sum react+drift vs Study 3's pre-ex run-up tells how much of the",
            "anticipation was announced-then-earned vs already priced before",
            "any public intimation.",
        ]
    lines += [
        "",
        "## Caveats (encode before citing)",
        "- 🔴 LEVEL BIAS: every quintile carries ~+13%/63d abnormal CAR — the",
        "  filing universe (2,495 real, alive companies) systematically beats",
        "  the all-panel median benchmark (microcap drag), and the inner-join",
        "  window requires 63 subsequent bars (within-window survivorship).",
        "  ONLY CROSS-SECTIONAL SPREADS (Q5−Q1, T3−T1, pre-vs-post) are",
        "  interpretable; never cite a level.",
        "- Median-market abnormal returns, no beta adjustment — factor-model",
        "  CARs are the upgrade path.",
        "- 2025-26 index coverage RESTORED 2026-07-23 via the integrated-",
        "  filing API (NSE silently migrated post-2024 results there); the",
        "  legacy-API-only era of this index under-sampled 2025 cohorts.",
        "- Study 3b hit rates ride the same universe-level bias — compare",
        "  its 75-83% drift hits against the ~70-75% baseline hit of the",
        "  filing universe, not against 50%.",
        "- Announcement-return sorting conditions on day-0/+1 price action",
        "  (tradeable from day +2); it is NOT a fundamentals surprise.",
        "- No FDR pass yet: treat every spread here as PROVISIONAL until",
        "  multiple_testing.py includes these families.",
    ]
    with open(OUT_MD, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {OUT_PQ} ({len(allrows):,} rows)")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
