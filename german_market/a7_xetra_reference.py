#!/usr/bin/env python3
"""
Deutsche Börse A7 Analytics Platform - Xetra Reference Data
REST API for instruments, order book, OHLCV
Requires: A7_TOKEN environment variable (free token from a7.deutsche-boerse.com)
"""

import requests
import json
import os
from datetime import datetime
from pathlib import Path
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

A7_BASE_URL = "https://a7.deutsche-boerse.com/api/v1"

class A7XetraClient:
    def __init__(self):
        self.token = os.environ.get("A7_TOKEN")
        if not self.token:
            logger.warning("A7_TOKEN not set. Register at https://developer.deutsche-boerse.com/")
            logger.warning("Set: export A7_TOKEN='your-token'")
            self.token = None
        
        self.base_url = A7_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {self.token}" if self.token else "",
            "Content-Type": "application/json"
        }
        self.output_dir = Path.home() / "a7_data"
        self.output_dir.mkdir(exist_ok=True)
    
    def _get(self, endpoint, params=None):
        """Make GET request to A7 API"""
        if not self.token:
            logger.error("No A7_TOKEN available")
            return None
        
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None
    
    def get_universe(self, date=None, market="XETR"):
        """Get full Xetra universe for date"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"Fetching Xetra universe for {date}...")
        
        data = self._get("/instruments", params={
            "market": market,
            "date": date,
            "limit": 10000
        })
        
        if data:
            instruments = data.get("instruments", [])
            logger.info(f"✓ Retrieved {len(instruments)} instruments")
            return instruments
        
        return []
    
    def get_rdi(self, market="XETR"):
        """Get Reference Data Interface (RDI) for market"""
        logger.info(f"Fetching RDI for market {market}...")
        
        data = self._get(f"/markets/{market}/rdi")
        
        if data:
            logger.info(f"✓ Retrieved RDI data")
            return data
        
        return {}
    
    def get_order_book(self, instrument_id):
        """Get order book for instrument"""
        logger.info(f"Fetching order book for {instrument_id}...")
        
        data = self._get(f"/instruments/{instrument_id}/orderbook")
        
        if data:
            logger.info(f"✓ Retrieved order book")
            return data
        
        return {}
    
    def get_ohlcv(self, instrument_id, interval="1min", start_date=None, end_date=None):
        """Get OHLCV bars for instrument"""
        if start_date is None:
            start_date = datetime.now().strftime("%Y-%m-%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"Fetching {interval} OHLCV for {instrument_id}...")
        
        data = self._get(f"/instruments/{instrument_id}/ohlcv", params={
            "interval": interval,
            "start_date": start_date,
            "end_date": end_date,
            "limit": 10000
        })
        
        if data:
            bars = data.get("bars", [])
            logger.info(f"✓ Retrieved {len(bars)} bars")
            return bars
        
        return []
    
    def get_dax_constituents(self):
        """Get current DAX constituents"""
        logger.info("Fetching DAX constituents...")
        
        data = self._get("/indices/DAX/constituents")
        
        if data:
            constituents = data.get("constituents", [])
            logger.info(f"✓ Retrieved {len(constituents)} DAX constituents")
            return constituents
        
        return []

def main():
    parser = argparse.ArgumentParser(description="Deutsche Börse A7 Xetra Reference Data API")
    parser.add_argument("command", choices=["universe", "rdi", "orderbook", "ohlcv", "dax"],
                       help="Command to execute")
    parser.add_argument("--market", type=str, default="XETR", help="Market code (default: XETR)")
    parser.add_argument("--date", type=str, help="Date (YYYY-MM-DD)")
    parser.add_argument("--instrument-id", type=str, help="Instrument ID for orderbook/ohlcv")
    parser.add_argument("--interval", type=str, default="1min", help="OHLCV interval (1min, 5min, etc)")
    parser.add_argument("--start-date", type=str, help="Start date for historical")
    parser.add_argument("--end-date", type=str, help="End date for historical")
    
    args = parser.parse_args()
    
    client = A7XetraClient()
    
    if args.command == "universe":
        universe = client.get_universe(args.date, args.market)
        print(f"\n✓ Xetra Universe: {len(universe)} instruments")
        if universe:
            print("\nFirst 5 instruments:")
            for inst in universe[:5]:
                print(f"  - {inst.get('name')} ({inst.get('isin')})")
    
    elif args.command == "rdi":
        rdi = client.get_rdi(args.market)
        print(f"\n✓ RDI Data:")
        print(json.dumps(rdi, indent=2)[:500] + "...")
    
    elif args.command == "orderbook":
        if not args.instrument_id:
            logger.error("--instrument-id required for orderbook")
            return
        ob = client.get_order_book(args.instrument_id)
        print(f"\n✓ Order Book for {args.instrument_id}:")
        print(json.dumps(ob, indent=2)[:500] + "...")
    
    elif args.command == "ohlcv":
        if not args.instrument_id:
            logger.error("--instrument-id required for ohlcv")
            return
        bars = client.get_ohlcv(args.instrument_id, args.interval, args.start_date, args.end_date)
        print(f"\n✓ OHLCV Data: {len(bars)} bars")
        if bars:
            print("\nFirst 3 bars:")
            for bar in bars[:3]:
                print(f"  - {bar.get('time')}: O{bar.get('open')} H{bar.get('high')} L{bar.get('low')} C{bar.get('close')}")
    
    elif args.command == "dax":
        constituents = client.get_dax_constituents()
        print(f"\n✓ DAX Constituents: {len(constituents)} stocks")
        if constituents:
            print("\nFirst 10:")
            for c in constituents[:10]:
                print(f"  - {c.get('name')} ({c.get('ticker')})")
    
    else:
        print("✓ A7 Xetra Reference Data API client ready")
        print("  Commands: universe, rdi, orderbook, ohlcv, dax")
        print("  Example: python3 a7_xetra_reference.py universe --date 2025-01-10")

if __name__ == "__main__":
    main()
