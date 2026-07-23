#!/usr/bin/env python3
# portfolio_bundles.py
# ====================
# Bundle the digest's single-stock picks into MUTUAL-FUND-STYLE portfolios
# (user, 2026-07-23 — the DSP portfolio-creator idea applied to our own picks).
#
# RATIONALE. Stocks that cluster together on return behaviour tend to keep
# behaving similarly; a pick list is noisy name-by-name but a CO-MOVING BASKET
# of picks is a tradeable thesis ("IN Energy cluster", "US semis cluster").
# The watchlist becomes the bundling tool: screens nominate names, clustering
# groups them, weights size them, the bundle is what you act on.
#
# METHOD (deliberately dependency-light — numpy/scipy/pandas only):
#   * UNIVERSE  per market: priced, above the liquidity floor, BUY or HOLD
#     zone, ≥60 aligned daily bars. Sell-zone picks don't get bundled — a
#     bundle of broken trends is a themed way to lose money.
#   * CLUSTERS  average-linkage hierarchical clustering on 1−corr distance of
#     daily returns (last 90 bars), cut so clusters are tight (avg intra-corr
#     ≥ 0.30); keep clusters of 4–10 names (cap by dropping the least-
#     correlated members). Correlation IS the bundling criterion, per the
#     user's rationale — sector labels only NAME the result.
#   * WEIGHTS   inverse-volatility (60d), capped at 25% and renormalised.
#     Chosen over max-Sharpe on purpose: mean estimates from 90 daily bars
#     are noise, and PyPortfolioOpt-style MV optimisers amplify exactly that
#     noise into corner solutions. Inverse-vol is the boring, robust cousin
#     (risk parity lite) and needs no expected-return estimate at all.
#   * REBALANCE monthly, riding the first pipeline run of the month (same
#     exactly-once marker pattern as the Dropbox purge archive). Between
#     rebalances the bundle drifts naturally, like a real fund; daily
#     valuation reports weight drift so the next rebalance is explainable.
#
# Persistence: cache_seed/portfolio_bundles.json — formation date, target
# weights, formation prices, per-constituent rationale (screen, sector, zone
# at formation). Valuation is recomputed each morning from the same frames
# the digest already loaded; nothing here fetches from the network.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STORE = HERE / "cache_seed" / "portfolio_bundles.json"
MARK = Path.home() / ".local" / "state" / "portfolio_bundles_last_build"

MIN_BARS = 60
CORR_BARS = 90
MIN_CLUSTER, MAX_CLUSTER = 4, 10
MIN_INTRA_CORR = 0.30
WEIGHT_CAP = 0.25


def _closes(frames: dict, r: dict, bars: int = CORR_BARS + 10) -> Optional[pd.Series]:
    df = frames.get((r["market"], r["symbol"]))
    if df is None:
        return None
    d = df
    for c in ("Date", "date", "price_date"):
        if c in d.columns:
            d = (d.assign(_dt=pd.to_datetime(d[c], errors="coerce"))
                   .dropna(subset=["_dt"]).set_index("_dt"))
            break
    if not isinstance(d.index, pd.DatetimeIndex):
        return None
    s = pd.to_numeric(d["Close"], errors="coerce").dropna().tail(bars)
    return s[~s.index.duplicated(keep="last")] if len(s) >= MIN_BARS else None


def _bundle_name(members: List[dict], mkt: str) -> str:
    from collections import Counter
    secs = Counter(m.get("sector") for m in members
                   if m.get("sector") not in (None, "", "Unclassified"))
    top = [s for s, _ in secs.most_common(2)]
    label = " + ".join(top) if top else "Mixed"
    return f"{mkt} · {label}"


def build(rows: List[dict], frames: dict) -> dict:
    """Cluster this morning's picks into bundles. Returns the store dict."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    bundles = []
    for mkt in ("IN", "US", "JP", "KR", "EU"):
        cand = [r for r in rows
                if r["market"] == mkt and not r.get("missing")
                and not r.get("below_floor") and r.get("zone") in ("BUY", "HOLD")]
        series = {}
        for r in cand:
            s = _closes(frames, r)
            if s is not None:
                series[r["symbol"]] = s
        if len(series) < MIN_CLUSTER:
            continue
        wide = pd.DataFrame(series).sort_index().tail(CORR_BARS)
        rets = wide.pct_change(fill_method=None)
        rets = rets.dropna(axis=1, thresh=int(len(rets) * 0.6))
        if rets.shape[1] < MIN_CLUSTER:
            continue
        corr = rets.corr(min_periods=30).clip(-1, 1).fillna(0)
        dist = squareform((1 - corr).values, checks=False)
        Z = linkage(dist, method="average")
        # cut so a cluster's average pairwise distance ≤ 1 - MIN_INTRA_CORR
        labels = fcluster(Z, t=1 - MIN_INTRA_CORR, criterion="distance")
        by_r = {r["symbol"]: r for r in cand}
        for lab in set(labels):
            syms = [c for c, l in zip(corr.columns, labels) if l == lab]
            if len(syms) < MIN_CLUSTER:
                continue
            if len(syms) > MAX_CLUSTER:
                # keep the names most correlated with the cluster's own mean
                mean_corr = corr.loc[syms, syms].mean()
                syms = list(mean_corr.sort_values(ascending=False).index[:MAX_CLUSTER])
            sub = corr.loc[syms, syms]
            intra = float(sub.values[np.triu_indices(len(syms), 1)].mean())
            if intra < MIN_INTRA_CORR:
                continue
            # inverse-volatility weights, capped and renormalised
            vol = rets[syms].tail(60).std()
            iv = (1.0 / vol.replace(0, np.nan)).fillna(0)
            w = iv / iv.sum()
            w = w.clip(upper=WEIGHT_CAP)
            w = w / w.sum()
            members = []
            for sym in syms:
                r = by_r[sym]
                members.append({
                    "symbol": sym, "market": mkt,
                    "weight": round(float(w[sym]), 4),
                    "sector": r.get("sector", "Unclassified"),
                    "zone": r.get("zone"),
                    "screen": r.get("why", "")[:80],
                    "px_formation": round(float(wide[sym].dropna().iloc[-1]), 4),
                    # procurement rationale: screen nominated it, correlation
                    # bundled it, inverse-vol sized it
                    "rationale": (f"nominated by screen; avg corr to bundle "
                                  f"{float(sub[sym].drop(sym).mean()):.2f}; "
                                  f"60d vol {float(vol[sym] * 100):.1f}%/d → "
                                  f"inverse-vol weight"),
                })
            members.sort(key=lambda m: -m["weight"])
            bundles.append({
                "id": f"{mkt}-{lab}-{today}",
                "name": _bundle_name(members, mkt),
                "market": mkt, "formed": today,
                "intra_corr": round(intra, 3),
                "members": members,
            })
    store = {"built": today, "rebalance": "monthly (first pipeline run)",
             "bundles": bundles}
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(store, indent=1))
    MARK.parent.mkdir(parents=True, exist_ok=True)
    MARK.write_text(today[:7])
    return store


def load() -> Optional[dict]:
    try:
        return json.loads(STORE.read_text())
    except Exception:
        return None


def maybe_build(rows: List[dict], frames: dict) -> dict:
    """Monthly rebalance rhythm: rebuild on the first run of a new month (or
    when no store exists); otherwise reuse the standing bundles."""
    this_month = pd.Timestamp.today().strftime("%Y-%m")
    try:
        last = MARK.read_text().strip()
    except Exception:
        last = ""
    store = load()
    if store is None or last != this_month:
        try:
            return build(rows, frames)
        except Exception:
            return store or {"bundles": []}
    return store


def value(store: dict, rows: List[dict], frames: dict) -> List[dict]:
    """Daily valuation of the standing bundles from current frames."""
    out = []
    by_key = {(r["market"], r["symbol"]): r for r in rows}
    for b in store.get("bundles", []):
        vals = []
        for m in b["members"]:
            r = by_key.get((m["market"], m["symbol"]))
            s = _closes(frames, {"market": m["market"], "symbol": m["symbol"]}) \
                if r is None else _closes(frames, r)
            if s is None or not m.get("px_formation"):
                continue
            px = float(s.iloc[-1])
            d1 = float((s.iloc[-1] / s.iloc[-2] - 1) * 100) if len(s) > 1 else 0.0
            since = (px / m["px_formation"] - 1) * 100
            cur_val = m["weight"] * (1 + since / 100)
            vals.append({"m": m, "d1": d1, "since": since, "cur_val": cur_val,
                         "zone_now": (r or {}).get("zone", "?")})
        if len(vals) < MIN_CLUSTER - 1:
            continue
        tot = sum(v["cur_val"] for v in vals) or 1
        drift = max(abs(v["cur_val"] / tot - v["m"]["weight"]) for v in vals)
        out.append({
            "bundle": b,
            "d1": sum(v["d1"] * v["m"]["weight"] for v in vals),
            "since": sum(v["since"] * v["m"]["weight"] for v in vals),
            "drift": drift * 100,
            "members": vals,
            "sell_now": sum(1 for v in vals if v["zone_now"] == "SELL"),
        })
    out.sort(key=lambda x: -x["since"])
    return out
