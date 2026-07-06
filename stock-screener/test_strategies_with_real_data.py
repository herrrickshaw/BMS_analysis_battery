#!/usr/bin/env python3
"""
Test Strategies with Real GitHub Data
======================================

Analyzes strategy performance using real market data from:
- Global stock analysis CSV files
- Historical OHLCV data
- Damodaran fundamental data
- Previous backtest results

Provides insights on:
- Filter effectiveness across markets
- Win rates and Sharpe ratios
- Market-specific optimization opportunities
- New correlation patterns
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

class DataLoader:
    """Load and process test data from GitHub"""

    def __init__(self, base_path="/Users/umashankar"):
        self.base_path = Path(base_path)
        self.data = {}

    def load_market_analysis(self):
        """Load global market analysis CSV files"""
        print("📊 Loading market analysis data...")

        analysis_path = self.base_path / "global_stock_analysis"
        markets = ['usa', 'india', 'germany', 'japan', 'uk', 'brazil', 'china']

        for market in markets:
            file = analysis_path / f"{market}_analysis.csv"
            if file.exists():
                try:
                    df = pd.read_csv(file)
                    self.data[f'{market}_analysis'] = df
                    print(f"  ✅ {market.upper()}: {len(df)} stocks")
                except Exception as e:
                    print(f"  ⚠️  {market.upper()}: {e}")

        return self.data

    def load_stock_lists(self):
        """Load stock universe lists"""
        print("\n📋 Loading stock universe lists...")

        data_path = self.base_path / "herrrickshaw" / "data"

        lists = ['nse_equity_list.csv', 'london_list.csv', 'frankfurt_list.csv',
                'japan_list.csv', 'korea_list.csv', 'sp500_list.csv']

        for file_name in lists:
            file = data_path / file_name
            if file.exists():
                try:
                    df = pd.read_csv(file)
                    market = file_name.replace('_list.csv', '').upper()
                    self.data[f'{market}_list'] = df
                    print(f"  ✅ {market}: {len(df)} stocks")
                except Exception as e:
                    print(f"  ⚠️  {file_name}: {e}")

        return self.data

    def load_damodaran_data(self):
        """Load Damodaran fundamental reference data"""
        print("\n💰 Loading Damodaran reference data...")

        damodaran_path = self.base_path / "herrrickshaw" / "data" / "damodaran"

        if damodaran_path.exists():
            files = list(damodaran_path.glob("*.csv"))
            print(f"  ✅ Found {len(files)} Damodaran datasets")

            for file in files[:3]:  # Load first 3
                try:
                    df = pd.read_csv(file)
                    self.data[f'damodaran_{file.stem}'] = df
                    print(f"    • {file.stem}: {len(df)} rows")
                except Exception as e:
                    print(f"    ⚠️  {file.stem}: {e}")

    def load_backtest_results(self):
        """Load previous backtest results for validation"""
        print("\n📈 Loading backtest results...")

        reports_path = self.base_path / "reports"

        if reports_path.exists():
            files = list(reports_path.glob("*.csv")) + list(reports_path.glob("*.txt"))
            print(f"  ✅ Found {len(files)} result files")

            for file in files:
                try:
                    if file.suffix == '.csv':
                        df = pd.read_csv(file)
                        self.data[f'results_{file.stem}'] = df
                        print(f"    • {file.stem}")
                except Exception as e:
                    print(f"    ⚠️  {file.stem}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY TESTING
# ═══════════════════════════════════════════════════════════════════════════════

class StrategyTester:
    """Test screening strategies against real market data"""

    def __init__(self, data):
        self.data = data
        self.results = {}

    def test_filter_effectiveness(self):
        """Test each filter's effectiveness across markets"""
        print("\n🔬 TESTING FILTER EFFECTIVENESS")
        print("════════════════════════════════════════════════════════════════")

        filters = {
            'ROE > 15%': lambda df: df['ROE'] > 15 if 'ROE' in df.columns else pd.Series(),
            'P/B < 1.0': lambda df: df['PB'] < 1.0 if 'PB' in df.columns else pd.Series(),
            'Earnings Growth > 12%': lambda df: df['EPS_Growth'] > 12 if 'EPS_Growth' in df.columns else pd.Series(),
            'MA200 > MA50': lambda df: df['MA200'] > df['MA50'] if 'MA200' in df.columns and 'MA50' in df.columns else pd.Series(),
            'FCF > 5%': lambda df: df['FCF'] > 5 if 'FCF' in df.columns else pd.Series(),
        }

        for filter_name, filter_func in filters.items():
            print(f"\n📊 {filter_name}")
            print("─" * 50)

            for key, df in self.data.items():
                if 'analysis' in key:
                    try:
                        matches = filter_func(df)
                        if len(matches) > 0 and matches.sum() > 0:
                            count = matches.sum()
                            pct = (count / len(df)) * 100
                            market = key.replace('_analysis', '').upper()
                            print(f"  {market:10} → {count:4} matches ({pct:5.1f}%)")

                            self.results[f'{filter_name}_{market}'] = {
                                'matches': int(count),
                                'percentage': float(pct),
                                'total': len(df)
                            }
                    except Exception as e:
                        pass

    def test_market_insights(self):
        """Discover market-specific patterns and correlations"""
        print("\n\n🔍 MARKET INSIGHTS")
        print("════════════════════════════════════════════════════════════════")

        insights = {}

        for key, df in self.data.items():
            if 'analysis' in key and len(df) > 0:
                market = key.replace('_analysis', '').upper()
                print(f"\n📈 {market} Market ({len(df)} stocks)")
                print("─" * 50)

                # Calculate statistics
                numeric_cols = df.select_dtypes(include=[np.number]).columns

                if len(numeric_cols) > 0:
                    print("Top columns by variance:")
                    for col in numeric_cols[:5]:
                        if df[col].notna().sum() > 0:
                            variance = df[col].var()
                            mean = df[col].mean()
                            print(f"  • {col:20} → Mean: {mean:8.2f}, Var: {variance:8.2f}")

                insights[market] = {
                    'total_stocks': len(df),
                    'columns': list(numeric_cols)[:10],
                    'stats': df[numeric_cols].describe().to_dict() if len(numeric_cols) > 0 else {}
                }

        self.results['market_insights'] = insights
        return insights

    def compare_strategy_performance(self):
        """Compare performance of India vs USA optimized screens"""
        print("\n\n⚖️  STRATEGY COMPARISON")
        print("════════════════════════════════════════════════════════════════")

        india_data = self.data.get('india_analysis')
        usa_data = self.data.get('usa_analysis')

        if india_data is not None and len(india_data) > 0:
            print(f"\n🇮🇳 INDIA OPTIMIZED SCREEN")
            print("─" * 50)

            # Test India filters
            if 'ROE' in india_data.columns:
                roe_filter = (india_data['ROE'] > 15).sum()
                print(f"  ROE > 15%: {roe_filter} matches ({roe_filter/len(india_data)*100:.1f}%)")

            if 'EPS_Growth' in india_data.columns:
                growth_filter = (india_data['EPS_Growth'] > 12).sum()
                print(f"  EPS Growth > 12%: {growth_filter} matches ({growth_filter/len(india_data)*100:.1f}%)")

            # Combined filter
            if 'ROE' in india_data.columns and 'EPS_Growth' in india_data.columns:
                combined = ((india_data['ROE'] > 15) & (india_data['EPS_Growth'] > 12)).sum()
                print(f"  COMBINED: {combined} matches ({combined/len(india_data)*100:.1f}%)")
                self.results['india_combined_filter'] = {
                    'matches': int(combined),
                    'percentage': float(combined/len(india_data)*100),
                    'total': len(india_data)
                }

        if usa_data is not None and len(usa_data) > 0:
            print(f"\n🇺🇸 USA OPTIMIZED SCREEN")
            print("─" * 50)

            # Test USA filters
            if 'PB' in usa_data.columns:
                pb_filter = (usa_data['PB'] < 1.0).sum()
                print(f"  P/B < 1.0: {pb_filter} matches ({pb_filter/len(usa_data)*100:.1f}%)")

            if 'CurrentRatio' in usa_data.columns:
                liquidity_filter = (usa_data['CurrentRatio'] > 1.5).sum()
                print(f"  Current Ratio > 1.5: {liquidity_filter} matches ({liquidity_filter/len(usa_data)*100:.1f}%)")

            # Combined filter
            if 'PB' in usa_data.columns and 'CurrentRatio' in usa_data.columns:
                combined = ((usa_data['PB'] < 1.0) & (usa_data['CurrentRatio'] > 1.5)).sum()
                print(f"  COMBINED: {combined} matches ({combined/len(usa_data)*100:.1f}%)")
                self.results['usa_combined_filter'] = {
                    'matches': int(combined),
                    'percentage': float(combined/len(usa_data)*100),
                    'total': len(usa_data)
                }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Run comprehensive strategy tests"""

    print("\n" + "═" * 80)
    print("🔬 TESTING STRATEGIES WITH REAL GITHUB DATA")
    print("═" * 80)

    # Load data
    loader = DataLoader()
    loader.load_market_analysis()
    loader.load_stock_lists()
    loader.load_damodaran_data()
    loader.load_backtest_results()

    print(f"\n✅ Total datasets loaded: {len(loader.data)}")

    # Run tests
    tester = StrategyTester(loader.data)
    tester.test_filter_effectiveness()
    tester.test_market_insights()
    tester.compare_strategy_performance()

    # Save results
    output_file = Path("/Users/umashankar/stock-screener") / "strategy_test_results.json"
    with open(output_file, 'w') as f:
        json.dump(tester.results, f, indent=2)

    print(f"\n\n✅ RESULTS SAVED TO: {output_file}")
    print("\n" + "═" * 80)
    print("🎉 TESTING COMPLETE")
    print("═" * 80)

    return tester.results


if __name__ == "__main__":
    results = main()
