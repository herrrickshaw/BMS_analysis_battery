#!/usr/bin/env python3
"""
Background Task: Dataset Expansion
Collect additional NSE stocks to increase Phase 1 from 205K to 1M+ records
Runs continuously with extended rate limiting
"""

import sqlite3
import pandas as pd
import yfinance as yf
import time
from pathlib import Path

# Additional stocks to collect (beyond initial 145)
ADDITIONAL_STOCKS = [
    'AADHAAR', 'ABG', 'ABSMART', 'ACCLAIM', 'ADARSH', 'ADARSHINV', 'ADHOCTECX',
    'ADINATH', 'ADMK', 'ADNANIGREEN', 'ADVANIOPTICS', 'ADVANIGREEN', 'ADVEG',
    'ADVERT', 'ADVICE', 'AEGIS', 'AECL', 'AELP', 'AEROFLEX', 'AEROTECH',
    'AESPL', 'AETL', 'AFFINE', 'AGAL', 'AGCO', 'AGELCO', 'AGENSYS',
    'AGFLO', 'AGGRITECH', 'AGILEX', 'AGILETECH', 'AGNET', 'AGNT',
]

PERIODS = [
    ('2011-01-01', '2015-12-31', 'india_stocks_2011_2015.db'),
    ('2016-01-01', '2020-12-31', 'india_stocks_2016_2020.db'),
    ('2021-01-01', '2026-06-30', 'india_stocks_2021_2026.db'),
]

def download_stock(symbol, start_date, end_date):
    """Download single stock with robust error handling"""
    try:
        time.sleep(0.7)  # Rate limiting

        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(start=start_date, end=end_date)

        if hist is None or len(hist) == 0:
            return None

        prices_df = hist.reset_index()
        prices_df.columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'dividends', 'splits']
        prices_df['symbol'] = symbol
        prices_df['date'] = prices_df['date'].dt.strftime('%Y-%m-%d')
        prices_df = prices_df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']]

        return prices_df

    except Exception as e:
        return None

def insert_prices(db_path, prices_df):
    """Insert into database"""
    if prices_df is None or len(prices_df) == 0:
        return 0

    try:
        conn = sqlite3.connect(db_path)
        prices_df.to_sql('prices', conn, if_exists='append', index=False)
        conn.commit()
        conn.close()
        return len(prices_df)
    except Exception:
        return 0

def run_expansion():
    """Run dataset expansion"""
    print("🚀 DATASET EXPANSION TASK STARTED")
    print(f"   Target: Add {len(ADDITIONAL_STOCKS)} stocks × 3 periods")
    print(f"   Rate: 0.7s per stock (avoid rate limiting)")
    print("")

    total_added = 0

    for stock in ADDITIONAL_STOCKS:
        print(f"📊 Processing {stock}...", end=' ', flush=True)

        for start_date, end_date, db_path in PERIODS:
            prices_df = download_stock(stock, start_date, end_date)
            records = insert_prices(db_path, prices_df)
            total_added += records

            if records > 0:
                print(f"✅({records})", end=' ', flush=True)
            else:
                print(f"❌", end=' ', flush=True)

        print()  # Newline

    print(f"\n✅ EXPANSION COMPLETE: Added {total_added:,} records")
    print(f"   Expected Phase 1: 205K → {205_000 + total_added:,} records")

    # Show final statistics
    print("\n📈 Final Database Sizes:")
    for start_date, end_date, db_path in PERIODS:
        if Path(db_path).exists():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM prices")
            count = cursor.fetchone()[0]
            cursor.execute("SELECT DISTINCT symbol FROM prices")
            stocks = len(cursor.fetchall())
            conn.close()
            print(f"   {Path(db_path).stem}: {count:,} records ({stocks} stocks)")

if __name__ == "__main__":
    run_expansion()
