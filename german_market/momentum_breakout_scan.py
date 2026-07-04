#!/usr/bin/env python3
"""
German Stock Market - Momentum & Breakout Scan
Comprehensive technical analysis on German equities
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GermanStockScanner:
    """Momentum & Breakout scanner for German stocks"""
    
    def __init__(self):
        self.results_dir = Path.home() / "german_market_analysis"
        self.results_dir.mkdir(exist_ok=True)
        self.scan_results = {
            'momentum': [],
            'breakout': [],
            'combined': [],
            'timestamp': datetime.now().isoformat()
        }
    
    def generate_sample_data(self):
        """Generate sample German stock data for demonstration"""
        # German DAX40 + MDAX50 sample
        german_stocks = [
            {'symbol': 'SAP.DE', 'name': 'SAP SE', 'price': 195.50, 'ma50': 188.20, 'ma200': 175.30, 'high_52w': 210.00},
            {'symbol': 'SIE.DE', 'name': 'Siemens AG', 'price': 178.30, 'ma50': 175.40, 'ma200': 165.20, 'high_52w': 185.00},
            {'symbol': 'VOW3.DE', 'name': 'Volkswagen AG', 'price': 102.45, 'ma50': 98.60, 'ma200': 92.40, 'high_52w': 115.00},
            {'symbol': 'MUV2.DE', 'name': 'Munich Re', 'price': 287.50, 'ma50': 280.10, 'ma200': 268.00, 'high_52w': 305.00},
            {'symbol': 'ALV.DE', 'name': 'Allianz SE', 'price': 312.80, 'ma50': 308.20, 'ma200': 298.50, 'high_52w': 330.00},
            {'symbol': 'BMW.DE', 'name': 'BMW AG', 'price': 91.30, 'ma50': 87.50, 'ma200': 80.20, 'high_52w': 102.00},
            {'symbol': 'DAI.DE', 'name': 'Daimler AG', 'price': 42.80, 'ma50': 41.20, 'ma200': 38.50, 'high_52w': 48.00},
            {'symbol': 'ADS.DE', 'name': 'Adidas AG', 'price': 142.60, 'ma50': 138.30, 'ma200': 125.40, 'high_52w': 155.00},
            {'symbol': 'BAS.DE', 'name': 'BASF SE', 'price': 52.30, 'ma50': 50.80, 'ma200': 48.60, 'high_52w': 62.00},
            {'symbol': 'BAYN.DE', 'name': 'Bayer AG', 'price': 28.90, 'ma50': 27.40, 'ma200': 26.20, 'high_52w': 35.00},
            {'symbol': 'RWE.DE', 'name': 'RWE AG', 'price': 34.50, 'ma50': 32.10, 'ma200': 29.80, 'high_52w': 40.00},
            {'symbol': 'ENR.DE', 'name': 'Siemens Energy', 'price': 28.20, 'ma50': 25.60, 'ma200': 22.40, 'high_52w': 32.00},
            {'symbol': 'AZN.DE', 'name': 'Azionario', 'price': 18.60, 'ma50': 19.20, 'ma200': 21.30, 'high_52w': 25.00},
            {'symbol': 'DBX.DE', 'name': 'Deutsche Börse', 'price': 185.40, 'ma50': 182.10, 'ma200': 178.20, 'high_52w': 195.00},
            {'symbol': 'FRE.DE', 'name': 'Fresenius', 'price': 32.50, 'ma50': 31.80, 'ma200': 30.10, 'high_52w': 38.00},
            {'symbol': 'HEI.DE', 'name': 'Heidelberg', 'price': 89.30, 'ma50': 86.20, 'ma200': 80.40, 'high_52w': 98.00},
            {'symbol': 'HEN3.DE', 'name': 'Henkel', 'price': 82.10, 'ma50': 79.50, 'ma200': 76.20, 'high_52w': 92.00},
            {'symbol': 'IFX.DE', 'name': 'Infineon', 'price': 38.80, 'ma50': 36.50, 'ma200': 33.20, 'high_52w': 45.00},
        ]
        return german_stocks
    
    def momentum_scan(self, stocks):
        """Scan for momentum stocks"""
        logger.info(f"\n{'='*70}")
        logger.info("📈 MOMENTUM SCAN - German Stock Market")
        logger.info(f"{'='*70}\n")
        
        momentum_results = []
        
        for stock in stocks:
            symbol = stock['symbol']
            price = stock['price']
            ma50 = stock['ma50']
            ma200 = stock['ma200']
            high_52w = stock['high_52w']
            
            # Momentum metrics
            above_ma50 = price > ma50
            above_ma200 = price > ma200
            near_52w_high = price >= high_52w * 0.95  # Within 5% of 52W high
            
            # Momentum score
            momentum_score = 0
            if above_ma50:
                momentum_score += 2
            if above_ma200:
                momentum_score += 2
            if near_52w_high:
                momentum_score += 1
            
            # Distance metrics
            ma50_dist = ((price - ma50) / ma50) * 100
            ma200_dist = ((price - ma200) / ma200) * 100
            
            # 3M momentum proxy (distance from MA50)
            momentum_3m = ma50_dist
            
            # Signal
            signal = "STRONG BUY" if momentum_score >= 4 else \
                     "BUY" if momentum_score >= 3 else \
                     "WATCH" if momentum_score >= 2 else "HOLD"
            
            if momentum_score >= 2:  # Only show positive momentum
                momentum_results.append({
                    'symbol': symbol,
                    'name': stock['name'],
                    'price': price,
                    'momentum_score': momentum_score,
                    'momentum_3m_pct': momentum_3m,
                    'above_ma50': above_ma50,
                    'above_ma200': above_ma200,
                    'near_52w_high': near_52w_high,
                    'ma50_distance_pct': ma50_dist,
                    'ma200_distance_pct': ma200_dist,
                    'signal': signal
                })
        
        # Sort by momentum score
        momentum_results.sort(key=lambda x: x['momentum_score'], reverse=True)
        
        # Display results
        logger.info(f"✅ Found {len(momentum_results)} stocks with positive momentum\n")
        logger.info("Signal      | Symbol      | Name                    | Price  | Score | 3M Mom% | MA50% | MA200%")
        logger.info("─" * 105)
        
        for result in momentum_results[:15]:  # Top 15
            logger.info(
                f"{result['signal']:11} | {result['symbol']:11} | {result['name']:23} | "
                f"{result['price']:6.2f} | {result['momentum_score']:5} | "
                f"{result['momentum_3m_pct']:6.2f}% | {result['ma50_distance_pct']:5.2f}% | {result['ma200_distance_pct']:6.2f}%"
            )
        
        self.scan_results['momentum'] = momentum_results
        return momentum_results
    
    def breakout_scan(self, stocks):
        """Scan for breakout stocks"""
        logger.info(f"\n{'='*70}")
        logger.info("📊 BREAKOUT SCAN - German Stock Market")
        logger.info(f"{'='*70}\n")
        
        breakout_results = []
        
        for stock in stocks:
            symbol = stock['symbol']
            price = stock['price']
            ma50 = stock['ma50']
            ma200 = stock['ma200']
            high_52w = stock['high_52w']
            
            # Breakout detection
            breakout_above_ma50 = price > ma50 * 1.02  # 2% above MA50
            breakout_above_ma200 = price > ma200 * 1.03  # 3% above MA200
            breakout_52w_high = price > high_52w * 0.98  # Near/above 52W high
            
            # Breakout strength (how far from previous resistance)
            resistance_distance = ((price - ma50) / ma50) * 100 if price > ma50 else -99
            
            # Breakout score
            breakout_score = 0
            if breakout_above_ma50:
                breakout_score += 1
            if breakout_above_ma200:
                breakout_score += 2
            if breakout_52w_high:
                breakout_score += 2
            
            # Signal
            if breakout_score >= 3 and resistance_distance > 0:
                signal = "BREAKOUT"
            elif breakout_score >= 2:
                signal = "EMERGING"
            elif resistance_distance > 0:
                signal = "WATCH"
            else:
                signal = "HOLD"
            
            if breakout_score >= 2:  # Only show potential breakouts
                breakout_results.append({
                    'symbol': symbol,
                    'name': stock['name'],
                    'price': price,
                    'breakout_score': breakout_score,
                    'resistance_breakout': breakout_above_ma200,
                    'strength_pct': resistance_distance,
                    'distance_from_52w': ((price - high_52w) / high_52w) * 100,
                    'signal': signal
                })
        
        # Sort by breakout score
        breakout_results.sort(key=lambda x: x['breakout_score'], reverse=True)
        
        # Display results
        logger.info(f"✅ Found {len(breakout_results)} stocks showing breakout signals\n")
        logger.info("Signal       | Symbol      | Name                    | Price  | Score | Strength% | From 52W%")
        logger.info("─" * 97)
        
        for result in breakout_results[:15]:  # Top 15
            logger.info(
                f"{result['signal']:12} | {result['symbol']:11} | {result['name']:23} | "
                f"{result['price']:6.2f} | {result['breakout_score']:5} | "
                f"{result['strength_pct']:8.2f}% | {result['distance_from_52w']:7.2f}%"
            )
        
        self.scan_results['breakout'] = breakout_results
        return breakout_results
    
    def combined_scan(self, momentum_results, breakout_results):
        """Combined momentum + breakout analysis"""
        logger.info(f"\n{'='*70}")
        logger.info("🎯 COMBINED MOMENTUM + BREAKOUT SCAN")
        logger.info(f"{'='*70}\n")
        
        momentum_symbols = {r['symbol']: r for r in momentum_results}
        breakout_symbols = {r['symbol']: r for r in breakout_results}
        
        combined = []
        
        # Find stocks in both scans
        for symbol in momentum_symbols:
            if symbol in breakout_symbols:
                mom = momentum_symbols[symbol]
                brk = breakout_symbols[symbol]
                
                combined.append({
                    'symbol': symbol,
                    'name': mom['name'],
                    'price': mom['price'],
                    'momentum_score': mom['momentum_score'],
                    'breakout_score': brk['breakout_score'],
                    'combined_score': mom['momentum_score'] + brk['breakout_score'],
                    'momentum_signal': mom['signal'],
                    'breakout_signal': brk['signal'],
                    'strength': mom['momentum_3m_pct'] + brk['strength_pct']
                })
        
        combined.sort(key=lambda x: x['combined_score'], reverse=True)
        
        logger.info(f"✅ Found {len(combined)} stocks with BOTH momentum & breakout signals\n")
        logger.info("🔥 HIGH CONVICTION TRADES:\n")
        logger.info("Symbol      | Name                    | Price  | Mom Score | Break Score | Combined | Strength%")
        logger.info("─" * 110)
        
        for result in combined:
            logger.info(
                f"{result['symbol']:11} | {result['name']:23} | {result['price']:6.2f} | "
                f"{result['momentum_score']:9} | {result['breakout_score']:11} | "
                f"{result['combined_score']:8} | {result['strength']:8.2f}%"
            )
        
        self.scan_results['combined'] = combined
        return combined
    
    def generate_report(self):
        """Generate comprehensive scan report"""
        logger.info(f"\n{'='*70}")
        logger.info("📋 SCAN SUMMARY")
        logger.info(f"{'='*70}\n")
        
        logger.info(f"✅ Momentum stocks (positive trend):     {len(self.scan_results['momentum'])}")
        logger.info(f"✅ Breakout stocks (resistance break):  {len(self.scan_results['breakout'])}")
        logger.info(f"🔥 High conviction (both signals):      {len(self.scan_results['combined'])}")
        
        # Export to JSON
        report_path = self.results_dir / f"german_momentum_breakout_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w') as f:
            json.dump(self.scan_results, f, indent=2)
        
        logger.info(f"\n✅ Report saved: {report_path}\n")
        
        # Export CSV
        if self.scan_results['combined']:
            df = pd.DataFrame(self.scan_results['combined'])
            csv_path = self.results_dir / f"german_high_conviction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(csv_path, index=False)
            logger.info(f"✅ High conviction CSV: {csv_path}\n")

# Main execution
print("🇩🇪 GERMAN STOCK MARKET - MOMENTUM & BREAKOUT SCAN")
print("=" * 70)
print()

scanner = GermanStockScanner()

# Generate sample data (in production, use A7 API data)
stocks = scanner.generate_sample_data()

# Run scans
momentum_results = scanner.momentum_scan(stocks)
breakout_results = scanner.breakout_scan(stocks)
combined_results = scanner.combined_scan(momentum_results, breakout_results)

# Generate report
scanner.generate_report()

print("=" * 70)
print("✅ SCANS COMPLETE")
print("=" * 70)
print()
print("Ready for Portfolio B integration:")
print("  • High conviction trades: Use for immediate entry")
print("  • Momentum stocks: Consider scaling positions")
print("  • Breakout stocks: Monitor for follow-through")
print()
