"""
Helper utilities for querying market data from PostgreSQL
Use for Phase 1 analysis and beyond
"""

import psycopg2
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class MarketDataQuery:
    """Query interface for market data analysis"""

    def __init__(self, db_name="market_data", user="postgres", password="postgres", host="localhost", port=5432):
        self.db_name = db_name
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.conn = None

    def connect(self):
        """Connect to PostgreSQL"""
        try:
            self.conn = psycopg2.connect(
                dbname=self.db_name,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )
            logger.info(f"✅ Connected to {self.db_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            return False

    def get_stocks_by_market(self, market_name: str) -> pd.DataFrame:
        """Get all stocks for a market"""
        query = """
            SELECT s.stock_id, s.ticker, s.name, s.sector, s.market_cap_usd
            FROM stocks s
            JOIN markets m ON s.market_id = m.market_id
            WHERE m.market_name = %s
            ORDER BY s.market_cap_usd DESC NULLS LAST
        """
        return pd.read_sql(query, self.conn, params=(market_name,))

    def get_ohlcv_data(self, ticker: str, market_name: str, days: int = 252) -> pd.DataFrame:
        """Get OHLCV history for a stock (default: 1 year)"""
        query = """
            SELECT h.date, h.open_price, h.high_price, h.low_price, h.close_price, h.volume
            FROM ohlcv_history h
            JOIN stocks s ON h.stock_id = s.stock_id
            JOIN markets m ON s.market_id = m.market_id
            WHERE s.ticker = %s AND m.market_name = %s
            AND h.date > CURRENT_DATE - INTERVAL '1 day' * %s
            ORDER BY h.date ASC
        """
        df = pd.read_sql(query, self.conn, params=(ticker, market_name, days))
        df['date'] = pd.to_datetime(df['date'])
        return df

    def get_fundamentals(self, ticker: str, market_name: str) -> Dict:
        """Get fundamental data for a stock"""
        query = """
            SELECT f.pe_ratio, f.pb_ratio, f.roe, f.roa, f.debt_to_equity,
                   f.dividend_yield, f.eps, f.revenue, f.net_income,
                   f.operating_margin, f.profit_margin, f.updated_at
            FROM fundamentals f
            JOIN stocks s ON f.stock_id = s.stock_id
            JOIN markets m ON s.market_id = m.market_id
            WHERE s.ticker = %s AND m.market_name = %s
        """
        df = pd.read_sql(query, self.conn, params=(ticker, market_name))
        if not df.empty:
            return df.iloc[0].to_dict()
        return {}

    def get_sector_summary(self, market_name: str) -> pd.DataFrame:
        """Get sector-level statistics for a market"""
        query = """
            SELECT s.sector, COUNT(*) as stock_count,
                   ROUND(AVG(CAST(f.pe_ratio AS FLOAT)), 2) as avg_pe,
                   ROUND(AVG(CAST(f.pb_ratio AS FLOAT)), 2) as avg_pb,
                   ROUND(AVG(CAST(f.roe AS FLOAT)), 2) as avg_roe,
                   ROUND(AVG(CAST(f.dividend_yield AS FLOAT)), 2) as avg_dividend_yield
            FROM stocks s
            LEFT JOIN fundamentals f ON s.stock_id = f.stock_id
            WHERE s.market_id = (SELECT market_id FROM markets WHERE market_name = %s)
            GROUP BY s.sector
            ORDER BY stock_count DESC
        """
        return pd.read_sql(query, self.conn, params=(market_name,))

    def get_quality_stocks(self, market_name: str, min_roe: float = 0.15, max_de: float = 0.5, limit: int = 50) -> pd.DataFrame:
        """Get high-quality stocks by fundamental criteria"""
        query = """
            SELECT s.ticker, s.name, s.sector, s.market_cap_usd,
                   f.pe_ratio, f.roe, f.debt_to_equity, f.dividend_yield
            FROM stocks s
            JOIN fundamentals f ON s.stock_id = f.stock_id
            WHERE s.market_id = (SELECT market_id FROM markets WHERE market_name = %s)
            AND CAST(f.roe AS FLOAT) > %s
            AND CAST(f.debt_to_equity AS FLOAT) < %s
            ORDER BY CAST(f.roe AS FLOAT) DESC
            LIMIT %s
        """
        return pd.read_sql(query, self.conn, params=(market_name, min_roe, max_de, limit))

    def get_52week_stats(self, market_name: str, limit: int = 50) -> pd.DataFrame:
        """Get 52-week high/low for stocks in a market"""
        query = """
            SELECT s.ticker, s.name, s.sector,
                   ROUND(MAX(h.high_price)::NUMERIC, 2) as high_52w,
                   ROUND(MIN(h.low_price)::NUMERIC, 2) as low_52w,
                   (SELECT ROUND(close_price::NUMERIC, 2) FROM ohlcv_history
                    WHERE stock_id = s.stock_id ORDER BY date DESC LIMIT 1) as latest_close
            FROM stocks s
            JOIN ohlcv_history h ON s.stock_id = h.stock_id
            WHERE s.market_id = (SELECT market_id FROM markets WHERE market_name = %s)
            AND h.date > CURRENT_DATE - INTERVAL '1 year'
            GROUP BY s.stock_id, s.ticker, s.name, s.sector
            ORDER BY (MAX(h.high_price) - MIN(h.low_price)) DESC
            LIMIT %s
        """
        return pd.read_sql(query, self.conn, params=(market_name, limit))

    def get_portfolio_ohlcv(self, tickers: List[str], market_name: str, days: int = 252) -> Dict[str, pd.DataFrame]:
        """Get OHLCV for multiple tickers (portfolio)"""
        portfolio_data = {}
        for ticker in tickers:
            df = self.get_ohlcv_data(ticker, market_name, days)
            if not df.empty:
                portfolio_data[ticker] = df
        return portfolio_data

    def calculate_returns(self, ticker: str, market_name: str, days: int = 252) -> Dict:
        """Calculate returns statistics for a stock"""
        df = self.get_ohlcv_data(ticker, market_name, days)

        if df.empty or len(df) < 2:
            return {}

        # Daily returns
        df['returns'] = df['close_price'].pct_change()

        # Statistics
        return {
            'total_return': (df['close_price'].iloc[-1] / df['close_price'].iloc[0] - 1) * 100,
            'annualized_volatility': df['returns'].std() * (252 ** 0.5) * 100,
            'sharpe_ratio': (df['returns'].mean() * 252) / (df['returns'].std() * (252 ** 0.5)),
            'max_drawdown': ((df['close_price'].cummax() - df['close_price']) / df['close_price'].cummax()).max() * 100,
            'avg_volume': df['volume'].mean(),
            'volatility_daily': df['returns'].std() * 100,
        }

    def get_market_summary(self) -> pd.DataFrame:
        """Get summary statistics for all markets"""
        query = """
            SELECT m.market_name, m.country, m.currency,
                   COUNT(DISTINCT s.stock_id) as total_stocks,
                   COUNT(DISTINCT f.fundamental_id) as with_fundamentals,
                   ROUND(100.0 * COUNT(DISTINCT f.fundamental_id) / COUNT(DISTINCT s.stock_id), 1) as fundamentals_coverage,
                   COUNT(DISTINCT h.stock_id) as with_ohlcv
            FROM markets m
            LEFT JOIN stocks s ON m.market_id = s.market_id
            LEFT JOIN fundamentals f ON s.stock_id = f.stock_id
            LEFT JOIN ohlcv_history h ON s.stock_id = h.stock_id
            GROUP BY m.market_id, m.market_name, m.country, m.currency
            ORDER BY total_stocks DESC
        """
        return pd.read_sql(query, self.conn)

    def export_to_csv(self, query: str, filepath: str):
        """Export query results to CSV"""
        try:
            df = pd.read_sql(query, self.conn)
            df.to_csv(filepath, index=False)
            logger.info(f"✅ Exported {len(df)} rows to {filepath}")
        except Exception as e:
            logger.error(f"❌ Export error: {e}")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("✅ Connection closed")


def main():
    """Demo queries"""
    db = MarketDataQuery()

    if not db.connect():
        return

    try:
        # Market summary
        print("\n" + "="*80)
        print("📊 MARKET SUMMARY")
        print("="*80)
        summary = db.get_market_summary()
        print(summary.to_string(index=False))

        # India stocks
        print("\n" + "="*80)
        print("🇮🇳 INDIA TOP STOCKS BY MARKET CAP")
        print("="*80)
        india_stocks = db.get_stocks_by_market('india').head(20)
        print(india_stocks[['ticker', 'name', 'sector', 'market_cap_usd']].to_string(index=False))

        # Quality stocks
        print("\n" + "="*80)
        print("💎 QUALITY STOCKS (India: ROE>15%, D/E<0.5)")
        print("="*80)
        quality = db.get_quality_stocks('india', min_roe=0.15, max_de=0.5, limit=20)
        print(quality[['ticker', 'name', 'sector', 'roe', 'debt_to_equity', 'dividend_yield']].to_string(index=False))

        # Sector analysis
        print("\n" + "="*80)
        print("📈 SECTOR SUMMARY (India)")
        print("="*80)
        sectors = db.get_sector_summary('india')
        print(sectors.to_string(index=False))

        # Sample stock analysis
        print("\n" + "="*80)
        print("📊 RELIANCE (NSE) - RETURNS ANALYSIS")
        print("="*80)
        returns = db.calculate_returns('RELIANCE', 'india', days=252)
        for key, value in returns.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}%")

        print("\n" + "="*80)
        print("✅ Database queries working correctly!")
        print("="*80)

    finally:
        db.close()


if __name__ == "__main__":
    main()
