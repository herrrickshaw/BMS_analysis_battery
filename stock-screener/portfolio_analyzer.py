#!/usr/bin/env python3
"""
Portfolio Analyzer - Comprehensive portfolio analysis and evaluation tool
Supports multi-market analysis (India, US, Europe, Japan, Korea)
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
import warnings
from pathlib import Path

warnings.filterwarnings('ignore')

class PortfolioAnalyzer:
    """Main portfolio analysis engine"""

    def __init__(self, portfolio_data: pd.DataFrame):
        """
        Initialize portfolio analyzer

        Args:
            portfolio_data: DataFrame with columns:
                - ticker: Stock ticker
                - quantity: Number of shares
                - purchase_price: Purchase price per share
                - purchase_date: Purchase date (YYYY-MM-DD)
                - market: Market (india, us, europe, japan, korea, china)
                - sector: Sector classification (optional)
                - current_price: Current price (optional, will fetch if not provided)
        """
        self.portfolio = portfolio_data.copy()
        self.portfolio['purchase_date'] = pd.to_datetime(self.portfolio['purchase_date'])
        self.current_date = datetime.now().date()
        self.market_tickers = self._normalize_tickers()
        self.fundamentals = {}
        self.price_history = {}

    def _normalize_tickers(self) -> Dict[str, str]:
        """Normalize tickers based on market"""
        tickers = {}
        for idx, row in self.portfolio.iterrows():
            ticker = row['ticker']
            market = row['market'].lower()

            # Add market-specific suffixes
            if market == 'india':
                yf_ticker = f"{ticker}.NS" if not ticker.endswith(('.NS', '.BO')) else ticker
            elif market == 'us':
                yf_ticker = ticker
            elif market == 'europe':
                yf_ticker = ticker  # Already pre-suffixed
            elif market == 'japan':
                yf_ticker = ticker  # Already pre-suffixed (e.g., 7203.T)
            elif market == 'korea':
                yf_ticker = ticker  # Already pre-suffixed (e.g., 005930.KS)
            elif market == 'china':
                yf_ticker = ticker  # Already pre-suffixed (e.g., 600519.SS)
            else:
                yf_ticker = ticker

            tickers[idx] = yf_ticker

        return tickers

    def fetch_current_prices(self) -> None:
        """Fetch current prices from yfinance"""
        print("Fetching current prices...")
        unique_tickers = list(set(self.market_tickers.values()))

        for ticker in unique_tickers:
            try:
                data = yf.download(ticker, period='1d', progress=False)
                if not data.empty:
                    current_price = float(data['Close'].iloc[-1])
                    self.portfolio.loc[self.market_tickers[self.market_tickers == ticker].index[0],
                                      'current_price'] = current_price
            except:
                print(f"Warning: Could not fetch price for {ticker}")

    def fetch_fundamentals(self) -> None:
        """Fetch fundamental data for stocks"""
        print("Fetching fundamentals...")
        for idx, yf_ticker in self.market_tickers.items():
            try:
                ticker_obj = yf.Ticker(yf_ticker)
                info = ticker_obj.info

                self.fundamentals[idx] = {
                    'pe_ratio': info.get('trailingPE'),
                    'pb_ratio': info.get('priceToBook'),
                    'roe': info.get('returnOnEquity'),
                    'debt_to_equity': info.get('debtToEquity'),
                    'dividend_yield': info.get('dividendYield'),
                    'market_cap': info.get('marketCap'),
                    'revenue': info.get('totalRevenue'),
                    'net_income': info.get('netIncome'),
                    'free_cash_flow': info.get('freeCashflow'),
                }
            except Exception as e:
                print(f"Warning: Could not fetch fundamentals for {yf_ticker}: {str(e)}")
                self.fundamentals[idx] = {}

    def calculate_portfolio_metrics(self) -> Dict:
        """Calculate overall portfolio metrics"""
        # Calculate position values
        self.portfolio['cost_basis'] = self.portfolio['quantity'] * self.portfolio['purchase_price']
        self.portfolio['current_value'] = self.portfolio['quantity'] * self.portfolio['current_price']
        self.portfolio['gain_loss'] = self.portfolio['current_value'] - self.portfolio['cost_basis']
        self.portfolio['gain_loss_pct'] = (self.portfolio['gain_loss'] / self.portfolio['cost_basis'] * 100).round(2)
        self.portfolio['days_held'] = (self.current_date - self.portfolio['purchase_date'].dt.date).dt.days
        self.portfolio['allocation_pct'] = (self.portfolio['current_value'] / self.portfolio['current_value'].sum() * 100).round(2)

        # Portfolio totals
        total_cost = self.portfolio['cost_basis'].sum()
        total_value = self.portfolio['current_value'].sum()
        total_gain = total_value - total_cost
        total_gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0

        # Risk metrics
        concentration_ratio = self.portfolio['allocation_pct'].max()  # Largest position
        herfindahl_index = (self.portfolio['allocation_pct'] ** 2).sum() / 100  # 0-1, lower is better
        diversification_ratio = 1 / herfindahl_index  # Effective number of positions

        # Dividend yield
        dividend_yield_total = 0
        for idx, row in self.portfolio.iterrows():
            if idx in self.fundamentals and 'dividend_yield' in self.fundamentals[idx]:
                dy = self.fundamentals[idx].get('dividend_yield', 0) or 0
                if dy:
                    dividend_yield_total += row['current_value'] * dy

        dividend_yield_pct = (dividend_yield_total / total_value * 100) if total_value > 0 else 0

        # Market exposure
        market_breakdown = self.portfolio.groupby('market')['current_value'].sum()
        market_pct = (market_breakdown / total_value * 100).round(2)

        metrics = {
            'summary': {
                'total_invested': round(total_cost, 2),
                'current_value': round(total_value, 2),
                'total_gain': round(total_gain, 2),
                'total_gain_pct': round(total_gain_pct, 2),
                'number_of_stocks': len(self.portfolio),
                'portfolio_value_₹': round(total_value, 2),
            },
            'risk': {
                'concentration_ratio': round(concentration_ratio, 2),  # % of largest position
                'herfindahl_index': round(herfindahl_index, 4),  # Portfolio concentration
                'diversification_ratio': round(diversification_ratio, 2),  # Effective positions
                'largest_position': self.portfolio.loc[self.portfolio['allocation_pct'].idxmax(), 'ticker'],
                'largest_position_pct': round(concentration_ratio, 2),
            },
            'income': {
                'dividend_yield': round(dividend_yield_pct, 2),
                'estimated_annual_dividend': round(dividend_yield_total, 2),
            },
            'market_exposure': market_pct.to_dict(),
            'average_holding_period_days': round(self.portfolio['days_held'].mean(), 0),
        }

        return metrics

    def calculate_position_quality(self) -> pd.DataFrame:
        """Calculate quality scores for individual positions"""
        quality_scores = []

        for idx, row in self.portfolio.iterrows():
            score_data = {
                'ticker': row['ticker'],
                'market': row['market'],
                'allocation_pct': row['allocation_pct'],
                'gain_loss_pct': row['gain_loss_pct'],
                'days_held': row['days_held'],
                'ltcg_eligible': row['days_held'] >= 365,  # LTCG after 1 year
            }

            # Add fundamentals if available
            if idx in self.fundamentals:
                funda = self.fundamentals[idx]
                score_data.update({
                    'pe_ratio': funda.get('pe_ratio'),
                    'pb_ratio': funda.get('pb_ratio'),
                    'roe': funda.get('roe'),
                    'dividend_yield': funda.get('dividend_yield'),
                })

                # Quality score (simplified Piotroski-like)
                quality_score = self._calculate_quality_score(funda)
                score_data['quality_score'] = quality_score

            quality_scores.append(score_data)

        return pd.DataFrame(quality_scores)

    def _calculate_quality_score(self, fundamentals: Dict) -> float:
        """Calculate simplified quality score based on fundamentals"""
        score = 0
        max_score = 5

        # PE Ratio (lower is better, but not too low)
        pe = fundamentals.get('pe_ratio')
        if pe and 8 <= pe <= 25:
            score += 1

        # PB Ratio (lower is better)
        pb = fundamentals.get('pb_ratio')
        if pb and pb <= 3:
            score += 1

        # ROE (higher is better)
        roe = fundamentals.get('roe')
        if roe and roe > 0.15:
            score += 1

        # Dividend (presence of dividend)
        dividend_yield = fundamentals.get('dividend_yield')
        if dividend_yield and dividend_yield > 0.01:
            score += 1

        # Market Cap (size)
        market_cap = fundamentals.get('market_cap')
        if market_cap and market_cap > 1e9:  # > $1B or equivalent
            score += 1

        return round((score / max_score) * 100, 1)

    def identify_rebalancing_opportunities(self, max_position_pct: float = 10) -> Dict:
        """Identify positions that need rebalancing"""
        overweight = self.portfolio[self.portfolio['allocation_pct'] > max_position_pct][
            ['ticker', 'allocation_pct', 'current_value', 'gain_loss_pct']
        ].to_dict('records')

        underweight = self.portfolio[self.portfolio['allocation_pct'] < 2][
            ['ticker', 'allocation_pct', 'current_value']
        ].to_dict('records')

        # Tax implications
        tax_implications = []
        for idx, row in self.portfolio.iterrows():
            if row['gain_loss'] > 0 and row['days_held'] < 365:
                tax_implications.append({
                    'ticker': row['ticker'],
                    'unrealized_gain': round(row['gain_loss'], 2),
                    'holding_period_days': int(row['days_held']),
                    'tax_status': 'STCG',  # Short-term capital gain
                    'tax_rate_pct': 30,  # Slab rate for STCG
                    'estimated_tax': round(row['gain_loss'] * 0.30, 2)
                })
            elif row['gain_loss'] > 0 and row['days_held'] >= 365:
                tax_implications.append({
                    'ticker': row['ticker'],
                    'unrealized_gain': round(row['gain_loss'], 2),
                    'holding_period_days': int(row['days_held']),
                    'tax_status': 'LTCG',  # Long-term capital gain
                    'tax_rate_pct': 20,  # LTCG rate
                    'estimated_tax': round(row['gain_loss'] * 0.20, 2)
                })

        return {
            'overweight_positions': overweight,
            'underweight_positions': underweight,
            'tax_implications': tax_implications,
        }

    def get_sector_allocation(self) -> Dict:
        """Get sector-wise allocation"""
        if 'sector' not in self.portfolio.columns:
            return {}

        sector_allocation = self.portfolio.groupby('sector').agg({
            'current_value': 'sum',
            'allocation_pct': 'sum',
            'gain_loss_pct': 'mean',
            'ticker': 'count'
        }).round(2)

        sector_allocation.columns = ['value', 'allocation_pct', 'avg_gain_loss_pct', 'stock_count']
        sector_allocation = sector_allocation.sort_values('allocation_pct', ascending=False)

        return sector_allocation.to_dict('index')

    def generate_report(self, output_format: str = 'dict') -> Dict:
        """Generate complete portfolio analysis report"""
        print("Generating portfolio report...")

        # Calculate all metrics
        portfolio_metrics = self.calculate_portfolio_metrics()
        position_quality = self.calculate_position_quality()
        rebalancing_ops = self.identify_rebalancing_opportunities()
        sector_alloc = self.get_sector_allocation()

        report = {
            'generated_at': datetime.now().isoformat(),
            'portfolio_metrics': portfolio_metrics,
            'position_quality': position_quality.to_dict('records'),
            'rebalancing_opportunities': rebalancing_ops,
            'sector_allocation': sector_alloc,
            'detailed_holdings': self.portfolio[[
                'ticker', 'market', 'quantity', 'purchase_price', 'current_price',
                'cost_basis', 'current_value', 'gain_loss', 'gain_loss_pct',
                'allocation_pct', 'days_held'
            ]].to_dict('records'),
        }

        return report

    def export_to_json(self, output_path: str) -> None:
        """Export report to JSON"""
        report = self.generate_report()

        # Convert non-serializable types
        report['generated_at'] = str(report['generated_at'])

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        print(f"Report exported to {output_path}")

    def export_to_csv(self, output_path: str) -> None:
        """Export portfolio to CSV"""
        export_df = self.portfolio[[
            'ticker', 'market', 'quantity', 'purchase_price', 'current_price',
            'cost_basis', 'current_value', 'gain_loss', 'gain_loss_pct',
            'allocation_pct', 'days_held'
        ]].copy()

        export_df.to_csv(output_path, index=False)
        print(f"Portfolio exported to {output_path}")


# CLI Interface
def load_portfolio_from_csv(csv_path: str) -> pd.DataFrame:
    """Load portfolio from CSV file"""
    df = pd.read_csv(csv_path)
    required_cols = ['ticker', 'quantity', 'purchase_price', 'purchase_date', 'market']

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    return df


def load_portfolio_from_excel(excel_path: str, sheet_name: str = 0) -> pd.DataFrame:
    """Load portfolio from Excel file"""
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    required_cols = ['ticker', 'quantity', 'purchase_price', 'purchase_date', 'market']

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    return df


def main():
    """Main CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description='Portfolio Analyzer Tool')
    parser.add_argument('--file', type=str, required=True, help='Portfolio file (CSV or Excel)')
    parser.add_argument('--output', type=str, default='portfolio_report.json', help='Output file path')
    parser.add_argument('--fetch-prices', action='store_true', help='Fetch current prices from yfinance')
    parser.add_argument('--fetch-fundamentals', action='store_true', help='Fetch fundamental data')
    parser.add_argument('--export-csv', type=str, help='Export portfolio to CSV')

    args = parser.parse_args()

    # Load portfolio
    if args.file.endswith('.csv'):
        portfolio = load_portfolio_from_csv(args.file)
    elif args.file.endswith(('.xls', '.xlsx')):
        portfolio = load_portfolio_from_excel(args.file)
    else:
        raise ValueError("Unsupported file format. Use CSV or Excel.")

    # If current_price not provided, fetch it
    if 'current_price' not in portfolio.columns:
        portfolio['current_price'] = 0.0

    # Initialize analyzer
    analyzer = PortfolioAnalyzer(portfolio)

    # Fetch data if requested
    if args.fetch_prices:
        analyzer.fetch_current_prices()

    if args.fetch_fundamentals:
        analyzer.fetch_fundamentals()

    # Generate report
    analyzer.export_to_json(args.output)

    # Export CSV if requested
    if args.export_csv:
        analyzer.export_to_csv(args.export_csv)

    # Print summary
    metrics = analyzer.calculate_portfolio_metrics()
    print("\n" + "="*60)
    print("PORTFOLIO SUMMARY")
    print("="*60)
    print(f"Total Invested: ₹{metrics['summary']['total_invested']:,.0f}")
    print(f"Current Value: ₹{metrics['summary']['current_value']:,.0f}")
    print(f"Total Gain: ₹{metrics['summary']['total_gain']:,.0f} ({metrics['summary']['total_gain_pct']:.2f}%)")
    print(f"Number of Stocks: {metrics['summary']['number_of_stocks']}")
    print(f"\nConcentration Ratio: {metrics['risk']['concentration_ratio']:.2f}%")
    print(f"Diversification Ratio: {metrics['risk']['diversification_ratio']:.2f}")
    print(f"Dividend Yield: {metrics['income']['dividend_yield']:.2f}%")
    print(f"Annual Dividend Income: ₹{metrics['income']['estimated_annual_dividend']:,.0f}")
    print("\nMarket Exposure:")
    for market, pct in metrics['market_exposure'].items():
        print(f"  {market.upper()}: {pct:.1f}%")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
