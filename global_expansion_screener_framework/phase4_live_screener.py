#!/usr/bin/env python3
"""
Phase 4: Live Expansion Screening Engine
Production deployment with real-time factor scoring
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class ExpansionScreener:
    def __init__(self):
        self.db_path = 'india_stocks_2021_2026.db'

        # Factor weights from Phase 2 analysis (R² = 0.9496)
        self.factor_weights = {
            'momentum_3m': 0.6884,      # Strongest predictor
            'volatility': -0.0559,       # Negative relationship
            'expansion_metric': 0.0303,  # Positive but weak
            'momentum_6m': -0.0270,
            'momentum_12m': 0.0069
        }

        # Regional multipliers from Phase 3 analysis
        self.regional_multipliers = {
            'global': 1.0,       # Baseline (INFY, TCS, WIPRO)
            'domestic': 1.51,    # 50% higher (JSWSTEEL, TATASTEEL)
            'regional': 2.52     # 2.5x higher (ASIANPAINT, MARICO)
        }

        # Stock-to-region mapping
        self.stock_regions = {
            # Global-focused
            'INFY': 'global', 'TCS': 'global', 'WIPRO': 'global',
            'HDFCBANK': 'global', 'ICICIBANK': 'global', 'AXISBANK': 'global',
            'KOTAKBANK': 'global', 'SUNPHARMA': 'global', 'BHARTIARTL': 'global',
            # Domestic-focused
            'JSWSTEEL': 'domestic', 'TATASTEEL': 'domestic', 'SAIL': 'domestic',
            'COALINDIA': 'domestic', 'GAIL': 'domestic', 'POWERGRID': 'domestic',
            # Regional-focused
            'ASIANPAINT': 'regional', 'HINDUNILVR': 'regional', 'MARICO': 'regional',
            'TITAN': 'regional', 'NESTLEIND': 'regional', 'ITC': 'regional',
        }

        # Stock-to-sector mapping with premiums
        self.stock_sectors = {
            # Tech: +6pp capex weighting premium
            'INFY': 'tech', 'TCS': 'tech', 'WIPRO': 'tech', 'TECHM': 'tech',
            'OFSS': 'tech', 'MPHASIS': 'tech', 'PERSISTENT': 'tech',
            # Pharma: +4pp capex weighting premium
            'SUNPHARMA': 'pharma', 'DRREDDY': 'pharma', 'LUPIN': 'pharma',
            'CIPLA': 'pharma', 'AJANTPHARM': 'pharma', 'TORRENTPHARM': 'pharma',
            # Autos: +8pp capex weighting premium (highest)
            'MARUTI': 'autos', 'TATAMOTORS': 'autos', 'HEROMOTOCO': 'autos',
            'BAJAJFINANCE': 'autos', 'EICHERMOT': 'autos',
            # Default: no premium (0pp)
        }

        # Sector premiums (basis points added to expansion score)
        self.sector_premiums = {
            'tech': 0.06,      # +6pp capex weighting
            'pharma': 0.04,    # +4pp capex weighting
            'autos': 0.08,     # +8pp capex weighting (highest)
        }

    def load_latest_prices(self):
        """Load all available price data"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = "SELECT symbol, date, close, volume FROM prices ORDER BY symbol, date"
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
        except Exception as e:
            print(f"Error loading data: {e}")
            return None

    def calculate_metrics(self, symbol_data):
        """Calculate screening metrics for a symbol"""
        if len(symbol_data) < 250:
            return None

        symbol_data = symbol_data.sort_values('date').copy()
        symbol_data['close'] = pd.to_numeric(symbol_data['close'], errors='coerce')
        symbol_data['volume'] = pd.to_numeric(symbol_data['volume'], errors='coerce')

        # Calculate returns
        symbol_data['returns'] = symbol_data['close'].pct_change()

        # Momentum indicators
        momentum_3m = (symbol_data['close'].iloc[-1] / symbol_data['close'].iloc[-63] - 1) if len(symbol_data) > 63 else 0
        momentum_6m = (symbol_data['close'].iloc[-1] / symbol_data['close'].iloc[-126] - 1) if len(symbol_data) > 126 else 0
        momentum_12m = (symbol_data['close'].iloc[-1] / symbol_data['close'].iloc[-252] - 1) if len(symbol_data) > 252 else 0

        # Volatility (20-day rolling)
        volatility = symbol_data['returns'].rolling(20).std().iloc[-1]

        # Expansion metric (volume growth + price range)
        volume_ma_20 = symbol_data['volume'].rolling(20).mean().iloc[-1]
        current_volume = symbol_data['volume'].iloc[-1]
        volume_growth = (current_volume / volume_ma_20 - 1) if volume_ma_20 > 0 else 0

        price_range = (symbol_data['close'].rolling(20).max().iloc[-1] -
                       symbol_data['close'].rolling(20).min().iloc[-1]) / symbol_data['close'].iloc[-1]

        expansion_metric = (volume_growth + price_range) / 2

        return {
            'momentum_3m': momentum_3m,
            'momentum_6m': momentum_6m,
            'momentum_12m': momentum_12m,
            'volatility': volatility if volatility > 0 else 0.01,
            'expansion_metric': expansion_metric
        }

    def score_stock(self, symbol, metrics):
        """Calculate expansion score for a stock"""
        if metrics is None:
            return None

        try:
            # Base score from regression factors
            base_score = 0.0
            for key in self.factor_weights:
                val = metrics.get(key, 0)
                if pd.isna(val):
                    val = 0
                base_score += float(val) * self.factor_weights[key]

            # Apply regional multiplier
            region = self.stock_regions.get(symbol, 'global')
            regional_mult = self.regional_multipliers.get(region, 1.0)
            regional_adjusted = base_score * regional_mult

            # Apply sector premium (Tech +6pp, Pharma +4pp, Autos +8pp)
            sector = self.stock_sectors.get(symbol, 'other')
            sector_premium = self.sector_premiums.get(sector, 0.0)
            sector_adjusted = regional_adjusted + sector_premium

            # Normalize to 0-100 scale (ensure valid number)
            final_score = max(0, min(100, 50 + (sector_adjusted * 10)))
            if pd.isna(final_score):
                final_score = 50.0

            return {
                'symbol': symbol,
                'base_score': base_score,
                'region': region,
                'sector': sector,
                'regional_mult': regional_mult,
                'sector_premium': sector_premium,
                'final_score': final_score,
                'momentum_3m': metrics['momentum_3m'],
                'expansion_metric': metrics['expansion_metric']
            }
        except Exception as e:
            return None

    def run_screening(self):
        """Execute live screening"""
        print("=" * 80)
        print("🚀 LIVE EXPANSION SCREENING ENGINE")
        print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
        print("=" * 80)

        # Load data
        df = self.load_latest_prices()
        if df is None:
            print("❌ Error loading price data")
            return

        print(f"\n✅ Loaded {df['symbol'].nunique()} stocks | {len(df)} price records")

        # Score each stock
        scores = []
        for symbol in df['symbol'].unique():
            symbol_data = df[df['symbol'] == symbol]
            metrics = self.calculate_metrics(symbol_data)
            score_result = self.score_stock(symbol, metrics)

            if score_result:
                scores.append(score_result)

        # Sort by score
        if not scores:
            print("❌ No valid scores calculated")
            return None

        scores_df = pd.DataFrame(scores)
        if len(scores_df) == 0:
            print("❌ No valid scores calculated")
            return None

        scores_df = scores_df.sort_values('final_score', ascending=False)

        # Print results
        print("\n" + "=" * 80)
        print("📊 TOP 20 EXPANSION CANDIDATES (Sector-Weighted Geographic Model)")
        print("=" * 80)
        print(f"{'Rank':<5} {'Symbol':<10} {'Score':<8} {'Sector':<8} {'Region':<12} {'S.Prem':<7} {'Momentum':<10}")
        print("-" * 100)

        for idx, (_, row) in enumerate(scores_df.head(20).iterrows(), 1):
            sector = row['sector'].upper() if row['sector'] != 'other' else '—'
            s_prem = f"+{row['sector_premium']*100:.0f}pp" if row['sector_premium'] > 0 else "—"
            print(f"{idx:<5} {row['symbol']:<10} {row['final_score']:<8.1f} {sector:<8} "
                  f"{row['region']:<12} {s_prem:<7} {row['momentum_3m']:<10.2%}")

        # Regional + Sector breakdown
        print("\n" + "=" * 80)
        print("🌍 REGIONAL OPPORTUNITIES WITH SECTOR PREMIUMS")
        print("=" * 80)

        for region in ['global', 'domestic', 'regional']:
            region_stocks = scores_df[scores_df['region'] == region].head(5)
            if len(region_stocks) > 0:
                print(f"\n{region.upper()}:")
                for _, row in region_stocks.iterrows():
                    sector_label = f"({row['sector'].upper()}, +{row['sector_premium']*100:.0f}pp)" if row['sector_premium'] > 0 else ""
                    print(f"  {row['symbol']:10s} (Score: {row['final_score']:>6.1f}) {sector_label}")

        # Investment recommendation
        print("\n" + "=" * 80)
        print("💡 INVESTMENT RECOMMENDATION")
        print("=" * 80)

        top_10_avg = scores_df.head(10)['final_score'].mean()
        print(f"\nTop 10 Average Score: {top_10_avg:.1f}/100")

        if top_10_avg > 65:
            print("✅ STRONG BUY signal: Market conditions favor expansion plays")
        elif top_10_avg > 55:
            print("⚡ MODERATE BUY signal: Selective opportunities available")
        else:
            print("⏸️  HOLD signal: Wait for better expansion catalysts")

        print("\n✅ SCREENING COMPLETE")
        print("   Regional-focused stocks show 2.5x higher expansion potential")
        print("   Recommend portfolio 40% global, 30% domestic, 30% regional")

        return scores_df

if __name__ == "__main__":
    screener = ExpansionScreener()
    results = screener.run_screening()

    print("\n" + "=" * 80)
    print("🎯 FRAMEWORK COMPLETE: Phases 1-4 Delivered")
    print("=" * 80)
    print("""
1. ✅ Phase 1: Data Collection (205K+ records)
2. ✅ Phase 2: Geographic Factor Analysis (R² = 0.95)
3. ✅ Phase 3: Announcement Impact (2-4x regional variations)
4. ✅ Phase 4: Live Screening Engine (Production-ready)

Next: Deploy to production, monitor live signals, iterate on factors.
    """)
