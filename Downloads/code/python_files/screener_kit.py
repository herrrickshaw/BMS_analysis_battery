#!/usr/bin/env python3
# screener_kit.py
# ===============
# ONE simple entry point. The committed seed parquets act as a STARTER KIT: after
# cloning you call bootstrap() once and you already have ~1yr of OHLCV for every
# market loaded into the fast NoSQL store — then update() pulls fresh/real-time
# bars on top of that baseline.
#
#   import screener_kit as kit
#   kit.bootstrap()                       # one-time: seeds → working cache + store
#   kit.update("IN")                      # pull new official bhavcopy days
#   df = kit.get("RELIANCE")              # OHLCV DataFrame
#   kit.screen("darvas", "IN", top=20)    # run a built-in strategy across a market
#   kit.custom_screen({"rsi14": ("<",35), "above_200dma": ("==",True)}, "US")
#
# Markets: IN US JP KR CN SG EU.  Seeds live in cache_seed/ (committed, LFS);
# the live working copy lives under $BHAV_CACHE (default ~/Downloads/.../bhavcopy_cache).

from __future__ import annotations

import os
import shutil
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

warnings.filterwarnings("ignore")

from strategies.base import StockData
import strategies as st
import custom_screener as cs

MARKETS = ["IN", "US", "JP", "KR", "CN", "SG", "EU",        # core official feeds
           "HK", "TW", "CA", "AU", "UK", "DE", "SA",        # major exchanges added
           "BR", "CH", "ZA", "SE", "FI", "DK"]              # (Wikipedia top-20)
SEED_DIR = Path(__file__).parent / "cache_seed"
CACHE = Path(os.environ.get("BHAV_CACHE",
                            Path.home() / "Downloads" / "data" / "bhavcopy_cache"))
CACHE.mkdir(parents=True, exist_ok=True)


def _seed_name(market: str) -> str:
    return "cleaned_long.parquet" if market == "IN" else f"cleaned_long_{market}.parquet"


def _live_path(market: str) -> Path:
    """Prefer the live working copy; fall back to the committed seed."""
    live = CACHE / _seed_name(market)
    seed = SEED_DIR / _seed_name(market)
    return live if live.exists() else seed


# ── starter-kit setup ───────────────────────────────────────────────────────────
def bootstrap(rebuild_store: bool = True, verbose: bool = True) -> dict:
    """Copy committed seeds into the working cache and build the NoSQL store.
    Run once after cloning — gives you the full multi-market baseline offline."""
    copied = []
    for mkt in MARKETS:
        seed = SEED_DIR / _seed_name(mkt)
        live = CACHE / _seed_name(mkt)
        if seed.exists() and not live.exists():
            shutil.copy2(seed, live); copied.append(mkt)
    if verbose:
        print(f"  bootstrap: seeded {len(copied)} markets into {CACHE} ({copied})")
    if rebuild_store:
        import bhavcopy_store as store
        n = store.build(verbose=verbose)
        if verbose:
            print(f"  store ready: {n} symbols")
    return {"seeded": copied, "cache": str(CACHE)}


def markets() -> List[str]:
    return [m for m in MARKETS if _live_path(m).exists()]


# ── data access ─────────────────────────────────────────────────────────────────
def load(market: str, min_turnover_usd: float = 0.0) -> Dict[str, pd.DataFrame]:
    """{symbol: OHLCV} for a market, from the live cache or committed seed.

    min_turnover_usd > 0 applies the liquidity pre-filter (keeps only names trading
    at least that many USD/day) BEFORE building frames — much faster screening on
    markets with long illiquid tails (e.g. India 8,931 → a few hundred)."""
    p = _live_path(market)
    if not p.exists():
        return {}
    keep = None
    if min_turnover_usd and min_turnover_usd > 0:
        try:
            from liquidity import liquid_symbols
            keep = set(liquid_symbols(market, min_usd=min_turnover_usd))
        except Exception:
            keep = None
    long = pd.read_parquet(p)
    long["Date"] = pd.to_datetime(long["Date"])
    if keep is not None:
        long = long[long["Symbol"].isin(keep)]
    out = {}
    for sym, g in long.groupby("Symbol"):
        out[str(sym)] = g.set_index("Date").sort_index()[
            ["Open", "High", "Low", "Close", "Volume"]]
    return out


def get(symbol: str) -> Optional[pd.DataFrame]:
    """Fast single-symbol OHLCV from the NoSQL store (falls back to seeds)."""
    try:
        import bhavcopy_store as store
        d = store.get(symbol)
        if d is not None:
            return d
    except Exception:
        pass
    for m in MARKETS:
        data = load(m)
        if symbol in data:
            return data[symbol]
    return None


# ── real-time / incremental update ──────────────────────────────────────────────
def update(market: str, verbose: bool = True) -> dict:
    """Pull fresh data on top of the seed baseline.

    IN  → official NSE+BSE bhavcopy, incremental (only new trading days).
    Others → recent bars via the redundant source chain, merged into the seed."""
    if market == "IN":
        from bhavcopy_history import fetch_history
        fetch_history(verbose=verbose)              # appends new days + rebuilds store
        return {"market": "IN", "source": "bhavcopy"}

    from data_sources import fetch as multi_fetch
    from stock_utils import clean_ohlcv
    base = load(market)
    if not base:
        return {"market": market, "error": "no seed; run a full fetch first"}
    last = max((d.index[-1] for d in base.values() if len(d)), default=None)
    period = "1mo"
    if last is not None:
        gap = (pd.Timestamp.today().normalize() - last).days
        period = "5d" if gap <= 7 else ("1mo" if gap <= 35 else "3mo")
    if verbose:
        print(f"  update {market}: {len(base)} symbols, last bar {None if last is None else last.date()}, fetching {period}")
    fresh = multi_fetch(list(base.keys()), order=("yahoo", "stooq"),
                        period=period, min_bars=1, verbose=verbose)
    # merge fresh bars into the baseline
    merged_rows, updated = [], 0
    for sym, old in base.items():
        df = old
        if sym in fresh:
            df = pd.concat([old, fresh[sym]])
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df = clean_ohlcv(df, ticker=sym, min_bars=1) or df
            if len(df) > len(old):
                updated += 1
        g = df.reset_index(); g.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
        for c in ("Open", "High", "Low", "Close"):
            g[c] = g[c].astype("float32")
        g["Volume"] = pd.to_numeric(g["Volume"], errors="coerce").fillna(0).astype("int64")
        g["Symbol"] = sym
        merged_rows.append(g)
    pd.concat(merged_rows, ignore_index=True).to_parquet(
        CACHE / _seed_name(market), compression="zstd", index=False)
    import bhavcopy_store as store
    store.build(verbose=False)
    if verbose:
        print(f"  update {market}: {updated} symbols got new bars; store rebuilt")
    return {"market": market, "updated": updated}


# ── screening ────────────────────────────────────────────────────────────────────
def _stocks(market: str, min_turnover_usd: float = 0.0) -> List[StockData]:
    return [StockData(s, market, ohlcv=d) for s, d in load(market, min_turnover_usd).items()]


def screen(strategy_slug: str, market: str = "IN", top: Optional[int] = None,
           min_turnover_usd: float = 0.0) -> pd.DataFrame:
    """Run one of the 10 built-in strategies across a market's cached stocks."""
    if strategy_slug not in st.STRATEGIES:
        raise ValueError(f"unknown strategy; choose from {list(st.STRATEGIES)}")
    mod = st.STRATEGIES[strategy_slug]
    rows = []
    for sd in _stocks(market, min_turnover_usd):
        try:
            r = mod.screen(sd)
        except Exception:
            r = None
        if r and r.passed:
            rows.append(r.row())
    df = pd.DataFrame(rows)
    if not df.empty and "Score" in df.columns:
        df = df.sort_values("Score", ascending=False)
    df = _add_liquidity(df)
    return df.head(top).reset_index(drop=True) if top else df.reset_index(drop=True)


def custom_screen(criteria, market: str = "IN", rank_by: Optional[str] = None,
                  top: Optional[int] = 50, ascending: bool = False,
                  show: Optional[List[str]] = None, min_turnover_usd: float = 0.0) -> pd.DataFrame:
    """Screen a market on YOUR parameters (see custom_screener for metric names)."""
    out = cs.screen(_stocks(market, min_turnover_usd), criteria, rank_by=rank_by, top=top,
                    ascending=ascending, show=show)
    return _add_liquidity(out)


def _add_liquidity(df):
    """Append Turnover_USD + Liquidity (High/Medium/Low) columns to a result frame."""
    try:
        from liquidity import annotate
        return annotate(df)
    except Exception:
        return df


if __name__ == "__main__":
    print("available markets (cached):", markets())
    print("\nDarvas breakouts (IN, top 10):")
    print(screen("darvas", "IN", top=10).to_string(index=False))
    print("\ncustom: US momentum (above 200-DMA, RSI<65, near highs):")
    print(custom_screen({"above_200dma": ("==", True), "rsi14": ("<", 65),
                         "dist_52w_high": ("<", 10)}, "US", rank_by="ret_126", top=10,
                        show=["ltp", "ret_126", "rsi14", "dist_52w_high"]).to_string(index=False))
