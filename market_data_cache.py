"""
market_data_cache.py
====================
Provides MarketCache — a 3-tier OHLC store used by the DDD composite repository.

Tier 1: in-process dict  (sub-millisecond)
Tier 2: parquet on disk   (~5 ms per symbol)
Tier 3: yfinance network  (~1 s per symbol, batched)

OHLC parquet files are expected at one of these locations (checked in order):
  1. $MARKET_CACHE_DIR  (env override)
  2. ./nse_screener_reference/ohlc_cache/    (repo-local LFS checkout)
  3. ~/Downloads/market_cache/ohlc/          (user's local machine path)
  4. ~/.market_cache/ohlc/                   (generic fallback)

Cache metadata lives in the same parent's cache_meta/cache_index.json.
"""

from __future__ import annotations

import json
import os
import time
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

warnings.filterwarnings("ignore")

# ── Path resolution ───────────────────────────────────────────────────────────

_CANDIDATES = [
    Path(os.environ.get("MARKET_CACHE_DIR", "__none__")),
    Path(__file__).parent / "nse_screener_reference" / "ohlc_cache",
    Path.home() / "Downloads" / "market_cache" / "ohlc",
    Path.home() / ".market_cache" / "ohlc",
]


def _find_ohlc_dir() -> Path:
    for p in _CANDIDATES:
        if p.exists() and any(p.glob("*.parquet")):
            return p
    # Use repo-local path even if empty (so saves land correctly)
    repo_path = Path(__file__).parent / "nse_screener_reference" / "ohlc_cache"
    repo_path.mkdir(parents=True, exist_ok=True)
    return repo_path


OHLC_DIR: Path = _find_ohlc_dir()
META_FILE: Path = OHLC_DIR.parent.parent / "nse_screener_reference" / "cache_meta" / "cache_index.json"
if not META_FILE.parent.exists():
    META_FILE = OHLC_DIR.parent / "cache_meta" / "cache_index.json"


def _is_lfs_pointer(path: Path) -> bool:
    """Return True when the file is a Git LFS pointer text (not real binary)."""
    try:
        if path.stat().st_size > 512:
            return False
        header = path.read_bytes()[:15]
        return header.startswith(b"version https://")
    except Exception:
        return False


# ── yfinance availability ────────────────────────────────────────────────────

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False


# ── MarketCache ───────────────────────────────────────────────────────────────

class MarketCache:
    """
    3-tier OHLC cache.

    Usage:
        cache = MarketCache()
        df = cache.get_ohlc("RELIANCE.NS")   # returns DataFrame or None
        bulk = cache.get_ohlc_bulk(["TCS.NS", "INFY.NS"])
    """

    def __init__(self, ohlc_dir: Path = None, verbose: bool = True):
        self._dir     = Path(ohlc_dir) if ohlc_dir else OHLC_DIR
        self._verbose = verbose
        self._mem: Dict[str, pd.DataFrame] = {}
        self._meta: dict = self._load_meta()

    # ── public API ─────────────────────────────────────────────────────────

    def get_ohlc(self, symbol: str) -> Optional[pd.DataFrame]:
        """Load one symbol (returns None on failure)."""
        if symbol in self._mem:
            return self._mem[symbol]
        df = self._from_parquet(symbol)
        if df is not None:
            self._mem[symbol] = df
            return df
        df = self._from_yfinance(symbol)
        if df is not None:
            self._save_parquet(symbol, df)
            self._mem[symbol] = df
        return df

    def get_ohlc_bulk(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Load multiple symbols; fallback to yfinance batch for misses."""
        result: Dict[str, pd.DataFrame] = {}
        missing: List[str] = []

        for sym in symbols:
            if sym in self._mem:
                result[sym] = self._mem[sym]
                continue
            df = self._from_parquet(sym)
            if df is not None:
                self._mem[sym] = df
                result[sym] = df
            else:
                missing.append(sym)

        if missing and _YF_OK:
            result.update(self._yf_bulk(missing))

        return result

    def available_symbols(self) -> List[str]:
        """List symbols with real (non-LFS-pointer) parquet files on disk."""
        out = []
        for p in self._dir.glob("*.parquet"):
            if not _is_lfs_pointer(p):
                out.append(p.stem)
        return sorted(out)

    def cache_info(self) -> dict:
        """Return metadata summary for all cached symbols."""
        return dict(self._meta)

    # ── internal helpers ───────────────────────────────────────────────────

    def _from_parquet(self, symbol: str) -> Optional[pd.DataFrame]:
        path = self._dir / f"{symbol}.parquet"
        if not path.exists():
            return None
        if _is_lfs_pointer(path):
            if self._verbose:
                print(f"  [cache] {symbol}: LFS pointer — skipping (run git lfs pull)")
            return None
        try:
            df = pd.read_parquet(path)
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            df.columns = [c.capitalize() for c in df.columns]
            for col in ("Open", "High", "Low", "Close", "Volume"):
                if col not in df.columns:
                    df[col] = None
            if self._verbose:
                print(f"  [cache] {symbol}: {len(df)} rows from parquet ({df.index[0].date()} → {df.index[-1].date()})")
            return df
        except Exception as e:
            if self._verbose:
                print(f"  [cache] {symbol}: parquet read error — {e}")
            return None

    def _from_yfinance(self, symbol: str) -> Optional[pd.DataFrame]:
        if not _YF_OK:
            return None
        try:
            df = yf.download(symbol, period="5y", auto_adjust=True,
                             progress=False, timeout=10)
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs(symbol, axis=1, level=1)
            if df.empty:
                return None
            if self._verbose:
                print(f"  [cache] {symbol}: {len(df)} rows from yfinance")
            return df
        except Exception:
            return None

    def _yf_bulk(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        if not _YF_OK:
            return {}
        result: Dict[str, pd.DataFrame] = {}
        batch_size = 50
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            try:
                raw = yf.download(batch, period="5y", auto_adjust=True,
                                  threads=True, progress=False, timeout=20)
                if raw.empty:
                    continue
                if isinstance(raw.columns, pd.MultiIndex):
                    for sym in batch:
                        try:
                            df = raw.xs(sym, axis=1, level=1).dropna(how="all")
                            if not df.empty:
                                stem = sym.replace(".NS", "").replace(".BO", "")
                                self._save_parquet(sym, df)
                                self._mem[sym] = df
                                result[sym] = df
                        except KeyError:
                            pass
                else:
                    sym = batch[0]
                    stem = sym.replace(".NS", "").replace(".BO", "")
                    self._save_parquet(sym, raw)
                    self._mem[sym] = raw
                    result[sym] = raw
            except Exception:
                pass
            if i + batch_size < len(symbols):
                time.sleep(1.0)
        return result

    def _save_parquet(self, symbol: str, df: pd.DataFrame) -> None:
        try:
            path = self._dir / f"{symbol}.parquet"
            df.to_parquet(path, compression="snappy", index=True)
            self._update_meta(symbol, df)
        except Exception:
            pass

    def _load_meta(self) -> dict:
        try:
            if META_FILE.exists():
                return json.loads(META_FILE.read_text())
        except Exception:
            pass
        return {}

    def _update_meta(self, symbol: str, df: pd.DataFrame) -> None:
        key = f"ohlc:{symbol}"
        self._meta[key] = {
            "rows":    len(df),
            "from":    str(df.index[0].date()),
            "to":      str(df.index[-1].date()),
            "updated": datetime.utcnow().isoformat(),
            "file":    str(self._dir / f"{symbol}.parquet"),
        }
        try:
            META_FILE.parent.mkdir(parents=True, exist_ok=True)
            META_FILE.write_text(json.dumps(self._meta, indent=2))
        except Exception:
            pass


# ── Convenience helpers (used by composite_repository.py) ────────────────────

_DEFAULT_CACHE: Optional[MarketCache] = None


def get_default_cache() -> MarketCache:
    global _DEFAULT_CACHE
    if _DEFAULT_CACHE is None:
        _DEFAULT_CACHE = MarketCache(verbose=False)
    return _DEFAULT_CACHE


def load_nifty_stocks_from_cache(
    symbols: Optional[List[str]] = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Convenience function: load OHLC for symbols and return a merged DataFrame
    with last-close, 50/200-DMA, RSI-14, volume_ratio, 52W hi/lo, and returns.

    Returns one row per symbol — ready to feed into Pegu / Sarvas scoring.
    """
    cache = MarketCache(verbose=verbose)

    if symbols is None:
        symbols = cache.available_symbols()
        if not symbols:
            symbols = [
                "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS",
                "ICICIBANK.NS", "WIPRO.NS", "AXISBANK.NS", "KOTAKBANK.NS",
                "LT.NS", "BAJFINANCE.NS", "MARUTI.NS", "NESTLEIND.NS",
                "TITAN.NS", "SUNPHARMA.NS", "BHARTIARTL.NS",
            ]

    ohlc_map = cache.get_ohlc_bulk(symbols)

    rows = []
    for sym, df in ohlc_map.items():
        if df is None or df.empty or len(df) < 20:
            continue
        df = df.sort_index()
        close = df["Close"]

        # Technicals
        dma50  = close.rolling(50).mean().iloc[-1]
        dma200 = close.rolling(200).mean().iloc[-1]
        last   = close.iloc[-1]
        high52 = close.tail(252).max()
        low52  = close.tail(252).min()

        # RSI-14
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, float("nan"))
        rsi   = (100 - 100 / (1 + rs)).iloc[-1]

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd  = (ema12 - ema26).iloc[-1]

        # Volume ratio (20-day avg)
        vol_ratio = None
        if "Volume" in df.columns:
            avg_vol = df["Volume"].tail(20).mean()
            last_vol = df["Volume"].iloc[-1]
            vol_ratio = (last_vol / avg_vol) if avg_vol > 0 else None

        # Returns
        def ret(n):
            return ((close.iloc[-1] / close.iloc[-min(n, len(close))]) - 1) * 100 if len(close) >= n else None

        clean = sym.replace(".NS", "").replace(".BO", "")
        rows.append({
            "symbol":           clean,
            "exchange":         "NSE" if ".NS" in sym else "BSE",
            "last_price":       round(last, 2),
            "week52_high":      round(high52, 2),
            "week52_low":       round(low52, 2),
            "ma50":             round(dma50, 2) if not pd.isna(dma50) else None,
            "ma200":            round(dma200, 2) if not pd.isna(dma200) else None,
            "rsi_14":           round(rsi, 2) if not pd.isna(rsi) else None,
            "macd":             round(macd, 4) if not pd.isna(macd) else None,
            "volume_ratio":     round(vol_ratio, 3) if vol_ratio else None,
            "pct_above_50dma":  round((last / dma50 - 1) * 100, 2) if not pd.isna(dma50) else None,
            "pct_above_200dma": round((last / dma200 - 1) * 100, 2) if not pd.isna(dma200) else None,
            "pct_from_52w_high":round((last / high52 - 1) * 100, 2) if high52 else None,
            "ret_1m":           ret(21),
            "ret_3m":           ret(63),
            "ret_6m":           ret(126),
            "bars":             len(df),
        })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    print("MarketCache diagnostics")
    print(f"  OHLC dir  : {OHLC_DIR}")
    print(f"  META file : {META_FILE}")
    cache = MarketCache(verbose=True)
    syms = cache.available_symbols()
    print(f"  Available : {len(syms)} symbols — {syms[:5]}{'...' if len(syms) > 5 else ''}")
    if syms:
        df = load_nifty_stocks_from_cache(verbose=False)
        print(f"  Loaded    : {len(df)} rows")
        print(df[["symbol", "last_price", "rsi_14", "pct_above_200dma"]].to_string(index=False))
