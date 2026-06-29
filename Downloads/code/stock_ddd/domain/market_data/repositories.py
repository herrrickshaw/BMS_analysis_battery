"""
domain/market_data/repositories.py
=====================================
Market Data Repository Interfaces (Ports).

These are INTERFACES defined in the Domain layer.
The Infrastructure layer provides IMPLEMENTATIONS.

This is the key DDD pattern: the Domain defines WHAT it needs (the contract),
Infrastructure decides HOW to deliver it (yfinance, Parquet, NSE API etc.).

The Domain has no import from Infrastructure — dependency flows inward only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Dict, List, Optional

from domain.market_data.entities import MarketIndex, Stock
from domain.shared.value_objects import Exchange, Ticker


class IStockRepository(ABC):
    """
    Contract for accessing stock price and fundamental data.

    Implementations (in Infrastructure):
      - YFinanceStockRepository    — fetches from Yahoo Finance
      - ParquetCacheRepository     — reads from local Parquet files
      - CompositeStockRepository   — tries cache first, falls back to yfinance
    """

    @abstractmethod
    def get_by_ticker(self, ticker: Ticker) -> Optional[Stock]:
        """Load a Stock aggregate with its full price history."""
        ...

    @abstractmethod
    def get_all_tickers(self, exchange: Exchange) -> List[Ticker]:
        """Return all tickers for a given exchange (e.g. all NSE EQ symbols)."""
        ...

    @abstractmethod
    def save(self, stock: Stock) -> None:
        """Persist a Stock aggregate (e.g. update Parquet cache)."""
        ...

    @abstractmethod
    def get_bulk(self, tickers: List[Ticker],
                 period: str = "1y") -> Dict[str, Stock]:
        """
        Bulk load multiple stocks efficiently.
        Returns {ticker_symbol: Stock} for all successfully loaded stocks.
        """
        ...

    @abstractmethod
    def exists_in_cache(self, ticker: Ticker) -> bool:
        """Check if stock data is available locally (without network call)."""
        ...

    @abstractmethod
    def get_last_updated(self, ticker: Ticker) -> Optional[date]:
        """Return the date of the most recent bar in the cache."""
        ...


class IMarketIndexRepository(ABC):
    """
    Contract for accessing market index data (Nifty 50, S&P 500).

    Implementations:
      - YFinanceIndexRepository   — fetches ^NSEI, ^GSPC from yfinance
      - ParquetIndexRepository    — reads baked-in index Parquet from Docker image
    """

    @abstractmethod
    def get_index(self, symbol: str, period: str = "2y") -> Optional[MarketIndex]:
        """Load index with pre-computed 200 DMA and slope."""
        ...

    @abstractmethod
    def get_current_level(self, symbol: str) -> Optional[float]:
        """Get the current index level (live, no history needed)."""
        ...


class ILiveMarketDataService(ABC):
    """
    Contract for live (real-time) market data.
    Separate from historical because they have different freshness requirements.

    Implementations:
      - NSEPythonLiveService  — wraps nsepython (VIX, FII/DII, bulk deals)
      - YFinanceLiveService   — wraps yfinance Ticker.info
    """

    @abstractmethod
    def get_vix(self) -> Optional[float]:
        """Return current India VIX."""
        ...

    @abstractmethod
    def get_bulk_deals(self) -> list:
        """Return today's bulk deals."""
        ...

    @abstractmethod
    def get_fii_dii_activity(self) -> dict:
        """Return FII/DII net buy/sell data."""
        ...

    @abstractmethod
    def get_upcoming_events(self, days_ahead: int = 7) -> list:
        """Return upcoming NSE corporate events (results, board meetings)."""
        ...

    @abstractmethod
    def get_all_nse_symbols(self) -> List[str]:
        """Return the live NSE EQ symbol list (2,400+ stocks)."""
        ...


class IFundamentalsRepository(ABC):
    """
    Contract for fundamental financial data (income statement, balance sheet).
    Separated from price data because fundamentals have different TTL (weekly refresh).

    Implementations:
      - YFinanceFundamentalsRepository
    """

    @abstractmethod
    def get_annual_financials(self, ticker: Ticker) -> dict:
        """Returns {income_stmt, balance_sheet, cash_flow} DataFrames."""
        ...

    @abstractmethod
    def get_quarterly_financials(self, ticker: Ticker) -> dict:
        """Returns quarterly income statement DataFrame."""
        ...

    @abstractmethod
    def get_stock_info(self, ticker: Ticker) -> dict:
        """Returns metadata: marketCap, trailingPE, sector, shortName etc."""
        ...
