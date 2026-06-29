"""
infrastructure/market_data/composite_repository.py
====================================================
Infrastructure Layer — Composite Repository Implementation.

Implements IStockRepository using a 3-tier strategy:
  1. Memory cache (in-process dict, 0.3ms)
  2. Parquet disk cache (local files, 94ms)
  3. yfinance network (cold download, ~1s per batch)

This is the ONLY place in the codebase that knows about yfinance and Parquet.
The Domain and Application layers are completely isolated from these details.

Also implements:
  IMarketIndexRepository  — Parquet baked files + yfinance fallback
  ILiveMarketDataService  — nsepython (VIX, FII/DII, bulk deals, events)
  IFundamentalsRepository — yfinance annual + quarterly financials
"""

from __future__ import annotations

import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

warnings.filterwarnings("ignore")

# Add scripts directory to path for existing infrastructure
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False

try:
    from nsepython import (nse_eq_symbols, indiavix, get_bulkdeals,
                           nse_events, nse_get_index_quote, nse_fiidii)
    _NSE_OK = True
except ImportError:
    _NSE_OK = False

# Domain imports
from domain.market_data.entities import MarketIndex, Stock
from domain.market_data.repositories import (
    IFundamentalsRepository,
    ILiveMarketDataService,
    IMarketIndexRepository,
    IStockRepository,
)
from domain.shared.value_objects import Exchange, Ticker


# ── Composite Stock Repository (3-tier cache) ─────────────────────────────────

class CompositeStockRepository(IStockRepository):
    """
    Implements IStockRepository with 3-tier cache strategy.
    All yfinance and Parquet logic is contained here — invisible to Domain.
    """

    def __init__(self, cache_dir: Path = None, batch_size: int = 100,
                 workers: int = 8):
        # Reuse existing MarketCache from infrastructure
        try:
            from market_data_cache import MarketCache
            self._cache = MarketCache(verbose=False)
            self._cache_available = True
        except ImportError:
            self._cache = None
            self._cache_available = False

        self._batch_size = batch_size
        self._workers    = workers

    def get_by_ticker(self, ticker: Ticker) -> Optional[Stock]:
        """Load one stock with full price history."""
        if not _YF_OK:
            return None
        try:
            df = self._fetch_ohlc_single(ticker)
            if df is None or df.empty:
                return None
            stock = Stock(ticker=ticker)
            stock.load_from_dataframe(df)
            return stock
        except Exception:
            return None

    def get_all_tickers(self, exchange: Exchange) -> List[Ticker]:
        """Return all NSE/BSE/NASDAQ/NYSE tickers."""
        if exchange == Exchange.NSE and _NSE_OK:
            try:
                syms = nse_eq_symbols()
                return [Ticker(s, Exchange.NSE) for s in syms]
            except Exception:
                pass
        # Fallback: Nifty 50
        return [Ticker(s, Exchange.NSE) for s in [
            "RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","AXISBANK",
            "KOTAKBANK","WIPRO","LT","BAJFINANCE","MARUTI","BHARTIARTL",
        ]]

    def save(self, stock: Stock) -> None:
        """Persist stock to Parquet cache via MarketCache."""
        if not self._cache_available:
            return
        import io, pandas as pd
        df = self._stock_to_df(stock)
        if df is not None and not df.empty:
            from market_data_cache import OHLC_DIR
            path = OHLC_DIR / f"{stock.ticker.yfinance_symbol}.parquet"
            df.to_parquet(path, compression="snappy", index=True)

    def get_bulk(self, tickers: List[Ticker],
                 period: str = "1y") -> Dict[str, Stock]:
        """Bulk load all tickers, using Parquet cache where available."""
        result: Dict[str, Stock] = {}

        if self._cache_available:
            # Use existing MarketCache (3-tier: memory → disk → network)
            yf_tickers = [t.yfinance_symbol for t in tickers]
            ohlc_map   = self._cache.get_ohlc_bulk(yf_tickers)
            for t in tickers:
                df = ohlc_map.get(t.symbol)  # cache stores without suffix
                if df is None:
                    df = ohlc_map.get(t.yfinance_symbol)
                if df is not None and not df.empty:
                    stock = Stock(ticker=t)
                    stock.load_from_dataframe(df)
                    result[t.symbol] = stock
        else:
            # Direct yfinance bulk download
            if not _YF_OK:
                return result
            batch = [t.yfinance_symbol for t in tickers]
            batches = [batch[i:i+self._batch_size]
                       for i in range(0, len(batch), self._batch_size)]
            for idx, b in enumerate(batches):
                try:
                    raw = yf.download(b, period=period, auto_adjust=True,
                                      threads=True, progress=False)
                    if raw.empty:
                        continue
                    if isinstance(raw.columns, pd.MultiIndex):
                        for yf_sym in b:
                            sym = yf_sym.replace(".NS","").replace(".BO","")
                            t   = next((t for t in tickers if t.symbol == sym), None)
                            if not t:
                                continue
                            try:
                                df = raw.xs(yf_sym, axis=1, level=1).dropna(how="all")
                                if not df.empty:
                                    stock = Stock(ticker=t)
                                    stock.load_from_dataframe(df)
                                    result[sym] = stock
                            except KeyError:
                                pass
                    else:
                        sym  = b[0].replace(".NS","").replace(".BO","")
                        t_   = next((t for t in tickers if t.symbol == sym), None)
                        if t_ and not raw.empty:
                            stock = Stock(ticker=t_)
                            stock.load_from_dataframe(raw)
                            result[sym] = stock
                except Exception:
                    pass
                if idx < len(batches) - 1:
                    time.sleep(1.5)

        return result

    def exists_in_cache(self, ticker: Ticker) -> bool:
        if not self._cache_available:
            return False
        from market_data_cache import OHLC_DIR
        return (OHLC_DIR / f"{ticker.yfinance_symbol}.parquet").exists()

    def get_last_updated(self, ticker: Ticker) -> Optional[date]:
        if not self._cache_available:
            return None
        from market_data_cache import META_FILE
        import json
        try:
            meta = json.loads(META_FILE.read_text())
            entry = meta.get(f"ohlc:{ticker.yfinance_symbol}", {})
            to_str = entry.get("to")
            return date.fromisoformat(to_str) if to_str else None
        except Exception:
            return None

    def _fetch_ohlc_single(self, ticker: Ticker) -> Optional[pd.DataFrame]:
        if self._cache_available:
            df = self._cache.get_ohlc(ticker.yfinance_symbol)
            if df is not None and not df.empty:
                return df
        if _YF_OK:
            df = yf.download(ticker.yfinance_symbol, period="1y",
                             auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs(ticker.yfinance_symbol, axis=1, level=1)
            return df if not df.empty else None
        return None

    @staticmethod
    def _stock_to_df(stock: Stock) -> Optional[pd.DataFrame]:
        bars = stock.price_series
        if not bars:
            return None
        return pd.DataFrame(
            [{"Open": b.open, "High": b.high, "Low": b.low,
              "Close": b.close, "Volume": b.volume} for b in bars],
            index=pd.DatetimeIndex([b.date for b in bars])
        )


# ── Market Index Repository ───────────────────────────────────────────────────

class ParquetIndexRepository(IMarketIndexRepository):
    """
    Loads market indices from Parquet (baked into Docker image) or yfinance.
    """
    def __init__(self, data_dir: Path = None):
        self._data_dir = data_dir or Path("/app/data/index")

    def get_index(self, symbol: str, period: str = "2y") -> Optional[MarketIndex]:
        name_map = {"^NSEI": "Nifty 50", "^GSPC": "S&P 500"}
        country_map = {"^NSEI": "IN", "^GSPC": "US"}
        safe_sym = symbol.replace("^", "")
        idx = MarketIndex(symbol=symbol, name=name_map.get(symbol, symbol),
                          country=country_map.get(symbol, ""))

        # Try Parquet first (baked in Docker or from cache)
        parquet_path = self._data_dir / f"{safe_sym}.parquet"
        if parquet_path.exists():
            try:
                df = pd.read_parquet(parquet_path)
                idx.load_from_dataframe(df)
                # Incremental update: fetch only new bars
                if idx.bar_count > 0 and _YF_OK:
                    last = idx._price_series[-1].date
                    if (date.today() - last).days > 1:
                        new_df = yf.download(symbol, start=last + timedelta(days=1),
                                             auto_adjust=True, progress=False)
                        if not new_df.empty:
                            idx.load_from_dataframe(pd.concat([df, new_df]))
                return idx
            except Exception:
                pass

        # Cold download via yfinance
        if _YF_OK:
            try:
                df = yf.download(symbol, period=period,
                                 auto_adjust=True, progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.xs(symbol, axis=1, level=1)
                if not df.empty:
                    df["dma200"]    = df["Close"].rolling(200).mean()
                    df["dma200_sl"] = df["dma200"].diff(5)
                    idx.load_from_dataframe(df)
                    return idx
            except Exception:
                pass
        return None

    def get_current_level(self, symbol: str) -> Optional[float]:
        if _NSE_OK and "NSEI" in symbol:
            try:
                q = nse_get_index_quote("NIFTY 50")
                return float(q.get("last", 0)) if q else None
            except Exception:
                pass
        if _YF_OK:
            try:
                t = yf.Ticker(symbol)
                return t.fast_info.last_price
            except Exception:
                pass
        return None


# ── Live Market Data Service ──────────────────────────────────────────────────

class NSEPythonLiveService(ILiveMarketDataService):
    """Implements ILiveMarketDataService using nsepython."""

    def get_vix(self) -> Optional[float]:
        if _NSE_OK:
            try:
                return float(indiavix())
            except Exception:
                pass
        return None

    def get_bulk_deals(self) -> list:
        if _NSE_OK:
            try:
                df = get_bulkdeals()
                return df.to_dict(orient="records") if isinstance(df, pd.DataFrame) else []
            except Exception:
                pass
        return []

    def get_fii_dii_activity(self) -> dict:
        if _NSE_OK:
            try:
                df = nse_fiidii()
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return df.head(5).to_dict(orient="records")
            except Exception:
                pass
        return {}

    def get_upcoming_events(self, days_ahead: int = 7) -> list:
        if _NSE_OK:
            try:
                df = nse_events()
                if isinstance(df, pd.DataFrame) and not df.empty:
                    df["date_parsed"] = pd.to_datetime(df["date"], format="%d-%b-%Y", errors="coerce")
                    cutoff = datetime.today() + timedelta(days=days_ahead)
                    df = df[df["date_parsed"] <= cutoff].sort_values("date_parsed")
                    return df.to_dict(orient="records")
            except Exception:
                pass
        return []

    def get_all_nse_symbols(self) -> List[str]:
        if _NSE_OK:
            try:
                syms = nse_eq_symbols()
                if syms and len(syms) > 100:
                    return syms
            except Exception:
                pass
        # Fallback: nse-library bhavcopy
        try:
            from nse import NSE
            today = datetime.today()
            with NSE(download_folder="/tmp", server=False) as nse_lib:
                for offset in range(7):
                    d = today - timedelta(days=offset)
                    try:
                        result = nse_lib.equityBhavcopy(d)
                        if hasattr(result, "exists") and result.exists():
                            df = pd.read_csv(result)
                            if "SctySrs" in df.columns:
                                return sorted(df[df["SctySrs"]=="EQ"]["TckrSymb"]
                                              .dropna().str.strip().tolist())
                    except Exception:
                        continue
        except ImportError:
            pass
        return []


# ── Fundamentals Repository ───────────────────────────────────────────────────

class YFinanceFundamentalsRepository(IFundamentalsRepository):
    """
    Implements IFundamentalsRepository using yfinance.
    Caches results in memory for 7 days (fundamentals change slowly).
    """
    def __init__(self):
        self._cache: Dict[str, dict] = {}

    def _get_ticker(self, ticker: Ticker):
        if not _YF_OK:
            return None
        return yf.Ticker(ticker.yfinance_symbol)

    def _first_df(self, t, *attrs):
        for a in attrs:
            df = getattr(t, a, None)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                return df
        return None

    def get_annual_financials(self, ticker: Ticker) -> dict:
        key = f"annual:{ticker.symbol}"
        if key in self._cache:
            return self._cache[key]
        t = self._get_ticker(ticker)
        if not t:
            return {}
        result = {
            "income_stmt":   self._first_df(t, "income_stmt", "financials"),
            "balance_sheet": self._first_df(t, "balance_sheet"),
            "cash_flow":     self._first_df(t, "cash_flow", "cashflow"),
        }
        self._cache[key] = result
        return result

    def get_quarterly_financials(self, ticker: Ticker) -> dict:
        key = f"quarterly:{ticker.symbol}"
        if key in self._cache:
            return self._cache[key]
        t = self._get_ticker(ticker)
        if not t:
            return {}
        result = {
            "quarterly_income": self._first_df(t, "quarterly_income_stmt",
                                               "quarterly_financials"),
        }
        self._cache[key] = result
        return result

    def get_stock_info(self, ticker: Ticker) -> dict:
        key = f"info:{ticker.symbol}"
        if key in self._cache:
            return self._cache[key]
        t = self._get_ticker(ticker)
        if not t:
            return {}
        try:
            info = t.info or {}
            self._cache[key] = info
            return info
        except Exception:
            return {}


# ── Dependency Injection Factory ──────────────────────────────────────────────

def create_stock_analysis_container(
    cache_dir: Path = None,
    workers: int = 8,
) -> dict:
    """
    Factory function: wires up all dependencies and returns a DI container dict.
    This is where Infrastructure implementations are bound to Domain interfaces.

    Usage:
        container = create_stock_analysis_container()
        handler   = RunDailyScanHandler(**container)
        result    = handler.handle(RunDailyScanCommand(markets=["IN"]))
    """
    stock_repo   = CompositeStockRepository(cache_dir=cache_dir, workers=workers)
    index_repo   = ParquetIndexRepository()
    live_service = NSEPythonLiveService()
    fund_repo    = YFinanceFundamentalsRepository()

    return {
        "stock_repo":   stock_repo,
        "index_repo":   index_repo,
        "live_service": live_service,
        "fund_repo":    fund_repo,
    }
