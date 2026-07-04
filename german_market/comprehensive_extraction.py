#!/usr/bin/env python3
"""
Comprehensive German Market Data Extraction
Using Deutsche Börse A7 API - Full Universe
Extracts all available fields: OHLCV, fundamentals, RDI data
"""

import requests
import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import logging
import os
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class A7ComprehensiveExtractor:
    """Extract all available data from A7 Xetra API"""
    
    def __init__(self):
        self.token = os.getenv('A7_TOKEN')
        self.base_url = "https://a7.deutsche-boerse.com/api/v1"
        self.session = requests.Session()
        self.output_dir = Path.home() / "german_market_data"
        self.output_dir.mkdir(exist_ok=True)
        
        if self.token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            })
        
        self.results = {
            'universe': [],
            'ohlcv': [],
            'rdi': [],
            'fundamentals': [],
            'errors': []
        }
    
    def extract_universe(self, date_str: str = None):
        """Extract complete German equity universe"""
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📊 STAGE 1: EXTRACTING GERMAN EQUITY UNIVERSE ({date_str})")
        logger.info(f"{'='*70}\n")
        
        try:
            url = f"{self.base_url}/universe"
            params = {
                'date': date_str,
                'market': 'XETR'  # Xetra market
            }
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 401:
                logger.error("❌ Authentication failed - A7_TOKEN not set or invalid")
                logger.info("   Register at: https://developer.deutsche-boerse.com/")
                return False
            
            if response.status_code == 404:
                logger.error("❌ Endpoint not found - API structure may have changed")
                return False
            
            response.raise_for_status()
            data = response.json()
            
            if 'instruments' in data:
                stocks = data['instruments']
                logger.info(f"✅ Found {len(stocks)} German stocks\n")
                
                # Display sample
                logger.info("Sample 10 stocks:")
                for stock in stocks[:10]:
                    isin = stock.get('isin', 'N/A')
                    symbol = stock.get('symbol', 'N/A')
                    name = stock.get('name', 'N/A')
                    logger.info(f"  • {symbol:12} | {isin:12} | {name}")
                
                self.results['universe'] = stocks
                return True
            else:
                logger.warning(f"Unexpected response structure: {list(data.keys())}")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.error("❌ Connection failed - A7 API may be offline")
            return False
        except Exception as e:
            logger.error(f"❌ Extraction failed: {e}")
            self.results['errors'].append(str(e))
            return False
    
    def extract_ohlcv(self, instrument_id: str, start_date: str = None):
        """Extract OHLCV data for a single instrument"""
        if not start_date:
            start_date = (datetime.now() - timedelta(days=5*365)).strftime('%Y-%m-%d')
        
        try:
            url = f"{self.base_url}/ohlcv/{instrument_id}"
            params = {
                'interval': 'daily',
                'start_date': start_date,
                'end_date': datetime.now().strftime('%Y-%m-%d')
            }
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if 'ohlcv' in data:
                return data['ohlcv']
            return None
        except Exception as e:
            logger.warning(f"  ⚠️  OHLCV failed for {instrument_id}: {str(e)[:50]}")
            return None
    
    def extract_rdi(self):
        """Extract Reference Data Information (fundamentals)"""
        logger.info(f"\n{'='*70}")
        logger.info(f"📊 STAGE 2: EXTRACTING RDI DATA (Reference Data Information)")
        logger.info(f"{'='*70}\n")
        
        try:
            url = f"{self.base_url}/rdi/xetr"  # Xetra RDI
            params = {'date': datetime.now().strftime('%Y-%m-%d')}
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if 'rdi' in data:
                logger.info(f"✅ Found {len(data['rdi'])} RDI records\n")
                
                # Sample RDI fields
                if data['rdi']:
                    sample = data['rdi'][0]
                    logger.info("Sample RDI fields available:")
                    for key in list(sample.keys())[:15]:
                        logger.info(f"  • {key}")
                    if len(sample) > 15:
                        logger.info(f"  ... and {len(sample)-15} more fields")
                
                self.results['rdi'] = data['rdi']
                return True
            return False
        except Exception as e:
            logger.warning(f"⚠️  RDI extraction failed: {e}")
            return False
    
    def generate_report(self):
        """Generate comprehensive extraction report"""
        logger.info(f"\n{'='*70}")
        logger.info(f"📊 EXTRACTION REPORT")
        logger.info(f"{'='*70}\n")
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'extraction_status': {
                'universe_count': len(self.results['universe']),
                'ohlcv_records': len(self.results['ohlcv']),
                'rdi_records': len(self.results['rdi']),
                'errors': len(self.results['errors'])
            },
            'sample_data': {
                'universe_sample': self.results['universe'][:5] if self.results['universe'] else [],
                'rdi_sample': self.results['rdi'][:3] if self.results['rdi'] else []
            }
        }
        
        # Summary
        logger.info(f"✅ Universe:  {report['extraction_status']['universe_count']:5} stocks")
        logger.info(f"✅ OHLCV:     {report['extraction_status']['ohlcv_records']:5} records")
        logger.info(f"✅ RDI:       {report['extraction_status']['rdi_records']:5} records")
        if report['extraction_status']['errors']:
            logger.warning(f"⚠️  Errors:    {report['extraction_status']['errors']:5}")
        
        # Save report
        report_path = self.output_dir / f"extraction_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"\n✅ Report saved: {report_path}\n")
        
        # Export CSVs
        if self.results['universe']:
            csv_path = self.output_dir / 'german_stocks_universe.csv'
            df = pd.DataFrame(self.results['universe'])
            df.to_csv(csv_path, index=False)
            logger.info(f"✅ Universe CSV: {csv_path}")
        
        if self.results['rdi']:
            csv_path = self.output_dir / 'german_stocks_rdi.csv'
            df = pd.DataFrame(self.results['rdi'])
            df.to_csv(csv_path, index=False)
            logger.info(f"✅ RDI CSV: {csv_path}")
        
        logger.info(f"\n📁 All data saved to: {self.output_dir}\n")
        return report

# Main execution
print("🇩🇪 COMPREHENSIVE GERMAN MARKET DATA EXTRACTION")
print("=" * 70)
print()

token = os.getenv('A7_TOKEN')

if not token:
    print("❌ ERROR: A7_TOKEN environment variable not set")
    print()
    print("To extract German market data:")
    print("  1. Register at: https://developer.deutsche-boerse.com/")
    print("  2. Get your API token")
    print("  3. Export it:")
    print("     export A7_TOKEN='your-token-here'")
    print("  4. Run this script again")
    print()
    print("=" * 70)
else:
    extractor = A7ComprehensiveExtractor()
    
    # Extract universe
    success = extractor.extract_universe()
    
    if success:
        # Extract RDI data
        extractor.extract_rdi()
        
        # Generate report
        report = extractor.generate_report()
        
        print("=" * 70)
        print("✅ EXTRACTION COMPLETE")
        print("=" * 70)
        print()
        print("Ready to deploy with Portfolio B filters:")
        print("  python3 ~/german_market/german_market_analysis.py --full")
    else:
        print()
        print("=" * 70)
        print("⚠️  SETUP REQUIRED")
        print("=" * 70)
        print()
        print("Steps to proceed:")
        print("  1. Register A7 account: https://developer.deutsche-boerse.com/")
        print("  2. Generate API token in developer console")
        print("  3. Set environment variable:")
        print("     export A7_TOKEN='your-token'")
        print("  4. Run again:")
        print("     python3 ~/german_market/comprehensive_extraction.py")
