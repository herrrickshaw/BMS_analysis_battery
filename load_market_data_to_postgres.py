"""
Load all market data CSVs into PostgreSQL database
Supports 8 global markets with unified schema
"""

import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
from typing import List, Dict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class PostgresMarketDB:
    """Load and manage global market data in PostgreSQL"""

    def __init__(self, db_name="market_data", user="umashankar", password="", host="localhost", port=5432):
        self.db_name = db_name
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.conn = None
        self.cursor = None

    def connect(self):
        """Connect to PostgreSQL (creates DB if not exists)"""
        try:
            # Connect to default postgres DB to create our DB
            conn = psycopg2.connect(
                dbname="postgres",
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )
            conn.autocommit = True
            cursor = conn.cursor()

            # Check if DB exists
            cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{self.db_name}'")
            if not cursor.fetchone():
                cursor.execute(f"CREATE DATABASE {self.db_name}")
                logger.info(f"✅ Created database: {self.db_name}")

            cursor.close()
            conn.close()

            # Connect to our database
            self.conn = psycopg2.connect(
                dbname=self.db_name,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )
            self.cursor = self.conn.cursor()
            logger.info(f"✅ Connected to {self.db_name}")

        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            raise

    def create_schema(self):
        """Create normalized schema for market data"""
        try:
            self.cursor.execute("""
                DROP TABLE IF EXISTS ohlcv_history CASCADE;
                DROP TABLE IF EXISTS fundamentals CASCADE;
                DROP TABLE IF EXISTS stocks CASCADE;
                DROP TABLE IF EXISTS markets CASCADE;
            """)

            # Markets table
            self.cursor.execute("""
                CREATE TABLE markets (
                    market_id SERIAL PRIMARY KEY,
                    market_name VARCHAR(50) UNIQUE NOT NULL,
                    exchange VARCHAR(100),
                    country VARCHAR(50),
                    currency VARCHAR(10),
                    timezone VARCHAR(50),
                    trading_hours VARCHAR(100)
                );
            """)

            # Stocks table
            self.cursor.execute("""
                CREATE TABLE stocks (
                    stock_id SERIAL PRIMARY KEY,
                    ticker VARCHAR(50) NOT NULL,
                    name VARCHAR(255),
                    market_id INTEGER REFERENCES markets(market_id),
                    sector VARCHAR(100),
                    industry VARCHAR(100),
                    market_cap_usd NUMERIC,
                    shares_outstanding NUMERIC,
                    currency VARCHAR(10),
                    isin VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, market_id)
                );
            """)

            # OHLCV history table
            self.cursor.execute("""
                CREATE TABLE ohlcv_history (
                    ohlcv_id SERIAL PRIMARY KEY,
                    stock_id INTEGER REFERENCES stocks(stock_id) ON DELETE CASCADE,
                    date DATE NOT NULL,
                    open_price NUMERIC,
                    high_price NUMERIC,
                    low_price NUMERIC,
                    close_price NUMERIC,
                    volume BIGINT,
                    adj_close NUMERIC,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_id, date)
                );
            """)

            # Fundamentals table
            self.cursor.execute("""
                CREATE TABLE fundamentals (
                    fundamental_id SERIAL PRIMARY KEY,
                    stock_id INTEGER UNIQUE REFERENCES stocks(stock_id) ON DELETE CASCADE,
                    pe_ratio NUMERIC,
                    pb_ratio NUMERIC,
                    roe NUMERIC,
                    roa NUMERIC,
                    debt_to_equity NUMERIC,
                    current_ratio NUMERIC,
                    dividend_yield NUMERIC,
                    eps NUMERIC,
                    revenue NUMERIC,
                    net_income NUMERIC,
                    operating_margin NUMERIC,
                    profit_margin NUMERIC,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create indexes for fast querying
            self.cursor.execute("""
                CREATE INDEX idx_stocks_ticker ON stocks(ticker);
                CREATE INDEX idx_stocks_market ON stocks(market_id);
                CREATE INDEX idx_stocks_sector ON stocks(sector);
                CREATE INDEX idx_ohlcv_date ON ohlcv_history(date);
                CREATE INDEX idx_ohlcv_stock ON ohlcv_history(stock_id);
                CREATE INDEX idx_ohlcv_stock_date ON ohlcv_history(stock_id, date);
            """)

            self.conn.commit()
            logger.info("✅ Schema created with indexes")

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Schema creation error: {e}")
            raise

    def load_market_metadata(self):
        """Load market metadata"""
        markets_data = {
            'india': {'exchange': 'NSE/BSE', 'country': 'India', 'currency': 'INR', 'timezone': 'IST', 'trading_hours': '09:15-15:30'},
            'usa': {'exchange': 'NASDAQ/NYSE', 'country': 'USA', 'currency': 'USD', 'timezone': 'EST', 'trading_hours': '09:30-16:00'},
            'uk': {'exchange': 'LSE', 'country': 'UK', 'currency': 'GBP', 'timezone': 'GMT', 'trading_hours': '08:00-16:30'},
            'germany': {'exchange': 'Deutsche Boerse', 'country': 'Germany', 'currency': 'EUR', 'timezone': 'CET', 'trading_hours': '08:00-22:00'},
            'europe': {'exchange': 'Multiple (17)', 'country': 'Europe', 'currency': 'EUR', 'timezone': 'CET', 'trading_hours': 'Varies'},
            'japan': {'exchange': 'TSE', 'country': 'Japan', 'currency': 'JPY', 'timezone': 'JST', 'trading_hours': '09:00-15:00'},
            'korea': {'exchange': 'KRX', 'country': 'South Korea', 'currency': 'KRW', 'timezone': 'KST', 'trading_hours': '09:00-15:30'},
            'china': {'exchange': 'SSE/SZSE', 'country': 'China', 'currency': 'CNY', 'timezone': 'CST', 'trading_hours': '09:30-15:00'},
        }

        try:
            for market_name, meta in markets_data.items():
                self.cursor.execute("""
                    INSERT INTO markets (market_name, exchange, country, currency, timezone, trading_hours)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (market_name) DO NOTHING
                """, (market_name, meta['exchange'], meta['country'], meta['currency'], meta['timezone'], meta['trading_hours']))

            self.conn.commit()
            logger.info("✅ Market metadata loaded")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Metadata error: {e}")

    def discover_csv_files(self, data_dir="/Users/umashankar/market_data_consolidated") -> Dict[str, List[str]]:
        """Discover and categorize CSV files by market"""
        csv_files = {}
        market_prefixes = ['india', 'usa', 'uk', 'germany', 'europe', 'japan', 'korea', 'china']

        for market in market_prefixes:
            csv_files[market] = []

        data_path = Path(data_dir)

        # Check if data_path has market subdirectories (consolidated structure)
        if (data_path / 'india').exists():
            # Use market subdirectories
            for market in market_prefixes:
                market_dir = data_path / market
                if market_dir.exists():
                    for csv_file in market_dir.glob("*.csv"):
                        csv_files[market].append(str(csv_file))
        else:
            # Use flat structure (legacy)
            for csv_file in data_path.glob("*.csv"):
                filename = csv_file.name.lower()
                for market in market_prefixes:
                    if market in filename:
                        csv_files[market].append(str(csv_file))
                        break

        logger.info(f"📁 Discovered CSVs by market:")
        for market, files in csv_files.items():
            logger.info(f"  {market}: {len(files)} files")

        return csv_files

    def load_market_csv(self, csv_path: str, market_name: str):
        """Load CSV into database"""
        try:
            df = pd.read_csv(csv_path)

            if df.empty:
                logger.warning(f"⚠️  Empty CSV: {csv_path}")
                return

            # Get market_id
            self.cursor.execute("SELECT market_id FROM markets WHERE market_name = %s", (market_name,))
            market_result = self.cursor.fetchone()
            if not market_result:
                logger.warning(f"⚠️  Market not found: {market_name}")
                return

            market_id = market_result[0]

            # Detect column types and load data
            filename = Path(csv_path).name

            # Handle OHLCV files (date-based)
            if any(x in filename for x in ['ohlcv', 'history', 'price']):
                self._load_ohlcv(df, market_id, csv_path)

            # Handle fundamentals
            elif any(x in filename for x in ['fundamentals', 'metrics']):
                self._load_fundamentals(df, market_id, csv_path)

            # Handle stock lists
            else:
                self._load_stocks(df, market_id, csv_path)

        except Exception as e:
            logger.error(f"❌ Error loading {csv_path}: {e}")

    def _load_stocks(self, df: pd.DataFrame, market_id: int, csv_path: str):
        """Load stock master data"""
        try:
            # Map common column names
            ticker_col = next((c for c in df.columns if 'ticker' in c.lower() or 'symbol' in c.lower()), df.columns[0])
            name_col = next((c for c in df.columns if 'name' in c.lower()), None)
            sector_col = next((c for c in df.columns if 'sector' in c.lower()), None)

            rows = []
            for _, row in df.iterrows():
                ticker = str(row[ticker_col]).strip()
                if not ticker:
                    continue

                rows.append((
                    ticker,
                    str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else ticker,
                    market_id,
                    str(row[sector_col]).strip() if sector_col and pd.notna(row[sector_col]) else None,
                ))

            if rows:
                execute_values(self.cursor, """
                    INSERT INTO stocks (ticker, name, market_id, sector)
                    VALUES %s
                    ON CONFLICT (ticker, market_id) DO NOTHING
                """, rows, page_size=1000)

                self.conn.commit()
                logger.info(f"✅ Loaded {len(rows)} stocks from {Path(csv_path).name}")

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Stock load error: {e}")

    def _load_ohlcv(self, df: pd.DataFrame, market_id: int, csv_path: str):
        """Load OHLCV history data"""
        try:
            # Map column names
            ticker_col = next((c for c in df.columns if 'ticker' in c.lower() or 'symbol' in c.lower()), None)
            date_col = next((c for c in df.columns if 'date' in c.lower()), None)
            open_col = next((c for c in df.columns if c.lower().startswith('open')), None)
            close_col = next((c for c in df.columns if c.lower().startswith('close')), None)

            if not all([ticker_col, date_col, open_col, close_col]):
                logger.warning(f"⚠️  Missing OHLCV columns in {Path(csv_path).name}")
                return

            rows = []
            for _, row in df.iterrows():
                ticker = str(row[ticker_col]).strip()

                # Get or create stock
                self.cursor.execute(
                    "SELECT stock_id FROM stocks WHERE ticker = %s AND market_id = %s",
                    (ticker, market_id)
                )
                result = self.cursor.fetchone()

                if not result:
                    # Insert new stock
                    self.cursor.execute(
                        "INSERT INTO stocks (ticker, name, market_id) VALUES (%s, %s, %s) RETURNING stock_id",
                        (ticker, ticker, market_id)
                    )
                    stock_id = self.cursor.fetchone()[0]
                else:
                    stock_id = result[0]

                try:
                    date_val = pd.to_datetime(row[date_col]).date()
                    rows.append((
                        stock_id,
                        date_val,
                        float(row[open_col]) if pd.notna(row[open_col]) else None,
                        float(row.get('high', float('nan'))) if 'high' in row and pd.notna(row.get('high')) else None,
                        float(row.get('low', float('nan'))) if 'low' in row and pd.notna(row.get('low')) else None,
                        float(row[close_col]) if pd.notna(row[close_col]) else None,
                        int(row.get('volume', 0)) if 'volume' in row and pd.notna(row.get('volume')) else 0,
                    ))
                except:
                    continue

            if rows:
                execute_values(self.cursor, """
                    INSERT INTO ohlcv_history (stock_id, date, open_price, high_price, low_price, close_price, volume)
                    VALUES %s
                    ON CONFLICT (stock_id, date) DO NOTHING
                """, rows, page_size=1000)

                self.conn.commit()
                logger.info(f"✅ Loaded {len(rows)} OHLCV records from {Path(csv_path).name}")

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ OHLCV load error: {e}")

    def _load_fundamentals(self, df: pd.DataFrame, market_id: int, csv_path: str):
        """Load fundamental data"""
        try:
            ticker_col = next((c for c in df.columns if 'ticker' in c.lower() or 'symbol' in c.lower()), df.columns[0])

            rows = []
            for _, row in df.iterrows():
                ticker = str(row[ticker_col]).strip()

                self.cursor.execute(
                    "SELECT stock_id FROM stocks WHERE ticker = %s AND market_id = %s",
                    (ticker, market_id)
                )
                result = self.cursor.fetchone()

                if result:
                    stock_id = result[0]

                    rows.append((
                        stock_id,
                        float(row['pe_ratio']) if 'pe_ratio' in row and pd.notna(row['pe_ratio']) else None,
                        float(row['pb_ratio']) if 'pb_ratio' in row and pd.notna(row['pb_ratio']) else None,
                        float(row['roe']) if 'roe' in row and pd.notna(row['roe']) else None,
                        float(row['dividend_yield']) if 'dividend_yield' in row and pd.notna(row['dividend_yield']) else None,
                        float(row['debt_to_equity']) if 'debt_to_equity' in row and pd.notna(row['debt_to_equity']) else None,
                    ))

            if rows:
                self.cursor.executemany("""
                    INSERT INTO fundamentals (stock_id, pe_ratio, pb_ratio, roe, dividend_yield, debt_to_equity)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (stock_id) DO UPDATE SET
                        pe_ratio = EXCLUDED.pe_ratio,
                        pb_ratio = EXCLUDED.pb_ratio,
                        roe = EXCLUDED.roe,
                        dividend_yield = EXCLUDED.dividend_yield,
                        debt_to_equity = EXCLUDED.debt_to_equity
                """, rows)

                self.conn.commit()
                logger.info(f"✅ Loaded {len(rows)} fundamentals from {Path(csv_path).name}")

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Fundamentals load error: {e}")

    def load_all(self, data_dir="/Users/umashankar/market_data_consolidated"):
        """Orchestrate full data load"""
        logger.info("🚀 Starting global market data load...")

        csv_files = self.discover_csv_files(data_dir)

        total_files = sum(len(files) for files in csv_files.values())
        loaded = 0

        for market_name, files in csv_files.items():
            for csv_path in files:
                self.load_market_csv(csv_path, market_name)
                loaded += 1
                logger.info(f"Progress: {loaded}/{total_files}")

        logger.info("🎯 All data loaded successfully!")

    def get_summary(self) -> Dict:
        """Get database summary stats"""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM markets")
            markets = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT COUNT(*) FROM stocks")
            stocks = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT COUNT(*) FROM ohlcv_history")
            ohlcv_records = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT COUNT(*) FROM fundamentals")
            fundamentals = self.cursor.fetchone()[0]

            # By market
            self.cursor.execute("""
                SELECT m.market_name, COUNT(DISTINCT s.stock_id) as stock_count
                FROM markets m
                LEFT JOIN stocks s ON m.market_id = s.market_id
                GROUP BY m.market_name
                ORDER BY stock_count DESC
            """)

            by_market = {row[0]: row[1] for row in self.cursor.fetchall()}

            return {
                'total_markets': markets,
                'total_stocks': stocks,
                'total_ohlcv_records': ohlcv_records,
                'total_fundamentals': fundamentals,
                'stocks_by_market': by_market
            }

        except Exception as e:
            logger.error(f"❌ Summary error: {e}")
            return {}

    def close(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("✅ Database connection closed")


def main():
    """Load all market data into PostgreSQL"""
    db = PostgresMarketDB()

    try:
        db.connect()
        db.create_schema()
        db.load_market_metadata()
        db.load_all()

        summary = db.get_summary()

        print("\n" + "="*60)
        print("📊 DATABASE SUMMARY")
        print("="*60)
        print(f"Markets: {summary['total_markets']}")
        print(f"Total Stocks: {summary['total_stocks']}")
        print(f"OHLCV Records: {summary['total_ohlcv_records']:,}")
        print(f"Fundamentals: {summary['total_fundamentals']}")
        print("\nStocks by Market:")
        for market, count in sorted(summary['stocks_by_market'].items(), key=lambda x: x[1], reverse=True):
            print(f"  🌍 {market.upper()}: {count:,}")
        print("="*60)

    finally:
        db.close()


if __name__ == "__main__":
    main()
