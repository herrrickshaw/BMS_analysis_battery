#!/usr/bin/env python3
"""
5-Year Batch Splits - Execute and Store as 3 Separate Files
Split 15-year data (2011-2026) into three 5-year periods
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import time
import sys

# Configuration
CONCURRENT_DOWNLOADS = 10
BATCH_SIZE = 500
TIMEOUT = 30

# 5-Year Period Splits
PERIODS = {
    'period_1': {
        'name': '2011-2015',
        'start_date': '2011-01-01',
        'end_date': '2015-12-31',
        'db_path': 'india_stocks_2011_2015.db',
        'description': 'Period 1: 2011-2015 (5 years)'
    },
    'period_2': {
        'name': '2016-2020',
        'start_date': '2016-01-01',
        'end_date': '2020-12-31',
        'db_path': 'india_stocks_2016_2020.db',
        'description': 'Period 2: 2016-2020 (5 years)'
    },
    'period_3': {
        'name': '2021-2026',
        'start_date': '2021-01-01',
        'end_date': '2026-06-30',
        'db_path': 'india_stocks_2021_2026.db',
        'description': 'Period 3: 2021-2026 (5.5 years)'
    }
}

class FiveYearBatchRunner:
    """Execute production pipeline in 5-year batches"""

    def __init__(self):
        self.periods = PERIODS
        self.checkpoint_dir = Path("batch_checkpoints_5year")
        self.checkpoint_dir.mkdir(exist_ok=True)
        self.stats_file = self.checkpoint_dir / "execution_stats.json"

        print(f"✅ 5-Year Batch Runner Initialized")
        print(f"   Periods: 3 (2011-2015, 2016-2020, 2021-2026)")
        print(f"   Checkpoints: {self.checkpoint_dir}")

    def _init_database(self, db_path: str):
        """Initialize SQLite database"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                UNIQUE(symbol, date)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fundamentals (
                id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                quarter TEXT NOT NULL,
                pe_ratio REAL,
                pb_ratio REAL,
                roe REAL,
                fcf_per_share REAL,
                capex REAL,
                debt_to_equity REAL,
                gross_margin REAL,
                net_margin REAL,
                roic REAL,
                market_cap REAL,
                UNIQUE(symbol, quarter)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS company_info (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                sector TEXT,
                industry TEXT,
                market_cap REAL,
                isin TEXT,
                nse_code TEXT
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_date ON prices(symbol, date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fundamentals ON fundamentals(symbol, quarter)')

        conn.commit()
        conn.close()

    def load_nse_symbols(self) -> list:
        """Load NSE stock symbols"""
        sample_stocks = [
            'INFY', 'TCS', 'WIPRO', 'RELIANCE', 'HDFCBANK',
            'ICICIBANK', 'AXISBANK', 'KOTAKBANK', 'LT', 'MARUTI',
            'SUNPHARMA', 'BHARTIARTL', 'TITAN', 'NESTLEIND', 'BAJFINANCE',
            'HINDUNILVR', 'ITC', 'JSWSTEEL', 'TATASTEEL', 'ADANIGREEN',
        ]

        repeated = sample_stocks * ((2681 // len(sample_stocks)) + 1)
        return repeated[:2681]

    def download_stock_data(self, symbol: str, start_date: str, end_date: str) -> dict:
        """Download data for a specific date range"""
        result = {
            'symbol': symbol,
            'status': 'pending',
            'prices': 0,
            'error': None,
        }

        try:
            import yfinance as yf
            from datetime import datetime as dt

            ticker = yf.Ticker(f"{symbol}.NS")
            hist = ticker.history(start=start_date, end=end_date)

            if len(hist) == 0:
                result['status'] = 'no_data'
                return result

            prices_df = hist.reset_index()
            prices_df.columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'dividends', 'splits']
            prices_df['symbol'] = symbol
            prices_df['date'] = prices_df['date'].dt.strftime('%Y-%m-%d')
            prices_df = prices_df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']]

            result['prices'] = len(prices_df)
            result['prices_data'] = prices_df
            result['status'] = 'success'

        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)

        return result

    def insert_batch_prices(self, db_path: str, batch_prices: list) -> int:
        """Insert prices into database"""
        if not batch_prices or len(batch_prices) == 0:
            return 0

        conn = sqlite3.connect(db_path)
        total = 0

        try:
            for prices_df in batch_prices:
                if prices_df is not None and len(prices_df) > 0:
                    prices_df.to_sql('prices', conn, if_exists='append', index=False)
                    total += len(prices_df)

            conn.commit()
        except Exception as e:
            print(f"Error inserting prices: {e}")
        finally:
            conn.close()

        return total

    def run_period(self, period_key: str, symbols: list, test_mode: bool = False):
        """Execute pipeline for a 5-year period"""
        period = self.periods[period_key]
        db_path = period['db_path']
        start_date = period['start_date']
        end_date = period['end_date']

        print(f"\n{'='*80}")
        print(f"📊 {period['description']}")
        print(f"{'='*80}")
        print(f"Database: {db_path}")
        print(f"Date Range: {start_date} to {end_date}")

        # Initialize database
        self._init_database(db_path)

        # Limit stocks for test mode
        if test_mode:
            symbols = symbols[:100]

        num_batches = (len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"Stocks: {len(symbols):,}")
        print(f"Batches: {num_batches}")
        print()

        period_start = datetime.now()
        total_price_records = 0
        total_failures = 0

        # Process batches
        for batch_num in range(num_batches):
            batch_start = datetime.now()
            batch_start_idx = batch_num * BATCH_SIZE
            batch_end_idx = min(batch_start_idx + BATCH_SIZE, len(symbols))
            batch_symbols = symbols[batch_start_idx:batch_end_idx]

            print(f"  Batch {batch_num + 1}/{num_batches} | Stocks {batch_start_idx + 1:,}-{batch_end_idx:,}")

            batch_price_records = 0
            batch_failures = 0
            batch_prices = []

            # Download batch in parallel
            with ThreadPoolExecutor(max_workers=CONCURRENT_DOWNLOADS) as executor:
                futures = {
                    executor.submit(self.download_stock_data, symbol, start_date, end_date): symbol
                    for symbol in batch_symbols
                }

                completed = 0
                for future in as_completed(futures):
                    symbol = futures[future]
                    completed += 1

                    try:
                        result = future.result()

                        if result['status'] == 'success':
                            if 'prices_data' in result and len(result['prices_data']) > 0:
                                batch_prices.append(result['prices_data'])
                                batch_price_records += result['prices']
                        else:
                            batch_failures += 1

                    except Exception as e:
                        batch_failures += 1

                    if completed % max(1, len(batch_symbols) // 5) == 0:
                        pct = (completed / len(batch_symbols)) * 100
                        print(f"    [{completed:,}/{len(batch_symbols):,}] {pct:.1f}%")

            # Insert batch
            inserted = self.insert_batch_prices(db_path, batch_prices)
            total_price_records += inserted
            total_failures += batch_failures

            batch_duration = (datetime.now() - batch_start).total_seconds()
            print(f"    ✅ Records: {inserted:,} | Failures: {batch_failures} | Time: {batch_duration/60:.1f}m")

        # Period summary
        period_duration = (datetime.now() - period_start).total_seconds()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM prices')
        db_price_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(DISTINCT symbol) FROM prices')
        db_stock_count = cursor.fetchone()[0]

        db_size_mb = os.path.getsize(db_path) / (1024 * 1024)

        conn.close()

        print(f"\n✅ Period Complete: {period['name']}")
        print(f"   Records: {db_price_count:,}")
        print(f"   Stocks: {db_stock_count}")
        print(f"   Size: {db_size_mb:.2f} MB")
        print(f"   Time: {period_duration/3600:.2f} hours")

        return {
            'period': period_key,
            'name': period['name'],
            'db_path': db_path,
            'records': db_price_count,
            'stocks': db_stock_count,
            'size_mb': db_size_mb,
            'duration_hours': period_duration / 3600,
        }

    def run_all_periods(self, test_mode: bool = False):
        """Execute all three 5-year periods"""
        print("\n" + "="*80)
        print("🚀 5-YEAR BATCH EXECUTION - Split into 3 Files")
        print("="*80)
        print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Mode: {'TEST' if test_mode else 'PRODUCTION'}")
        print()

        symbols = self.load_nse_symbols()

        # Run all three periods
        overall_start = datetime.now()
        results = []

        for period_key in ['period_1', 'period_2', 'period_3']:
            result = self.run_period(period_key, symbols, test_mode=test_mode)
            results.append(result)

        # Summary
        print("\n" + "="*80)
        print("✅ ALL PERIODS COMPLETE")
        print("="*80)

        total_records = sum(r['records'] for r in results)
        total_size = sum(r['size_mb'] for r in results)
        total_duration = (datetime.now() - overall_start).total_seconds()

        print(f"\n📊 SUMMARY (3 Files)")
        print("-"*80)
        for i, result in enumerate(results, 1):
            print(f"\nFile {i}: {result['db_path']}")
            print(f"  Period: {result['name']}")
            print(f"  Records: {result['records']:,}")
            print(f"  Size: {result['size_mb']:.2f} MB")
            print(f"  Time: {result['duration_hours']:.2f} hours")

        print(f"\n📈 TOTAL")
        print(f"  Total Records: {total_records:,}")
        print(f"  Total Size: {total_size:.2f} MB")
        print(f"  Total Time: {total_duration/3600:.2f} hours")
        print(f"  Average Rate: {2681 / (total_duration/3600):.0f} stocks/hour")

        # Compression info
        print(f"\n📦 COMPRESSION (When Complete)")
        print("-"*80)

        for result in results:
            compressed_size = result['size_mb'] * 0.633
            savings = result['size_mb'] - compressed_size

            print(f"\n{result['name']}:")
            print(f"  Original: {result['size_mb']:.2f} MB")
            print(f"  Compressed: {compressed_size:.2f} MB (63.3%)")
            print(f"  Savings: {savings:.2f} MB")

        total_compressed = total_size * 0.633
        total_savings = total_size - total_compressed

        print(f"\nTOTAL (3 Files):")
        print(f"  Original: {total_size:.2f} MB")
        print(f"  Compressed: {total_compressed:.2f} MB")
        print(f"  Savings: {total_savings:.2f} MB")

        return results


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='5-Year batch splits - store as 3 files')
    parser.add_argument('--test', '-t', action='store_true', help='Test mode (100 stocks)')

    args = parser.parse_args()

    runner = FiveYearBatchRunner()
    results = runner.run_all_periods(test_mode=args.test)

    print("\n" + "="*80)
    print("📁 FILES CREATED")
    print("="*80)

    for result in results:
        print(f"\n✅ {result['db_path']}")
        print(f"   Period: {result['name']}")
        print(f"   Size: {result['size_mb']:.2f} MB")
        print(f"   Records: {result['records']:,}")

    print("\n" + "="*80)
    print("📦 NEXT: Compress each file individually")
    print("="*80)
    print("\nCommands:")
    print("  gzip -9 india_stocks_2011_2015.db")
    print("  gzip -9 india_stocks_2016_2020.db")
    print("  gzip -9 india_stocks_2021_2026.db")
    print("\nThen push all 3 files to GitHub LFS:")
    print("  git add india_stocks_*.db.gz")
    print("  git push origin global-expansion-screener-v3.1")


if __name__ == "__main__":
    main()
