#!/usr/bin/env python3
"""
Nifty Composite Indices Comparison
Compares screener portfolios against all major Nifty composite indices
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

class NiftyCompositeComparison:
    def __init__(self):
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=1825)  # 5 years
        self.indices = {}
        self.screener_portfolios = {
            'Modern Resilience': {
                'tickers': ['MSFT', 'AAPL', 'WMT', 'JNJ', 'XOM', 'TCS.NS', 'INFY.NS', 'RELIANCE.NS', 'HDFC.NS', 'ICICIBANK.NS'],
                'weights': [0.12, 0.10, 0.08, 0.08, 0.08, 0.12, 0.10, 0.12, 0.10, 0.10]
            },
            'Rewards Optimization': {
                'tickers': ['NVDA', 'MSFT', 'AAPL', 'GOOGL', 'TSLA', 'INFY.NS', 'TCS.NS', 'ICICIBANK.NS', 'HDFC.NS', 'RELIANCE.NS'],
                'weights': [0.15, 0.12, 0.10, 0.10, 0.08, 0.12, 0.10, 0.10, 0.10, 0.13]
            },
            'Quality Dividend': {
                'tickers': ['WMT', 'XOM', 'JNJ', 'KO', 'PG', 'REALTY.NS', 'SBILIFE.NS', 'NESTLEIND.NS', 'BRITANNIA.NS', 'MARUTI.NS'],
                'weights': [0.12, 0.12, 0.10, 0.08, 0.08, 0.12, 0.10, 0.10, 0.10, 0.08]
            }
        }

    def fetch_index_data(self):
        """Fetch data for major Nifty composite indices"""
        # Note: Using NSE symbols that work with yfinance
        nifty_indices = {
            'Nifty 50': '^NSEI',
            'Nifty Bank': '^NSEBANK',
        }

        print("📊 Fetching Nifty composite indices data...")
        for name, ticker in nifty_indices.items():
            try:
                data = yf.download(ticker, start=self.start_date, end=self.end_date, progress=False)
                if not data.empty and len(data) > 100:
                    self.indices[name] = data['Close']
                    print(f"  ✓ {name}: {len(data)} days")
            except Exception as e:
                print(f"  ✗ {name}: {str(e)[:50]}")

    def fetch_portfolio_data(self):
        """Fetch price data for all screener portfolio tickers"""
        all_tickers = set()
        for portfolio in self.screener_portfolios.values():
            all_tickers.update(portfolio['tickers'])

        print("\n📈 Fetching portfolio ticker data...")
        price_data = {}
        for ticker in sorted(all_tickers):
            try:
                data = yf.download(ticker, start=self.start_date, end=self.end_date, progress=False)
                if not data.empty and len(data) > 1000:
                    price_data[ticker] = data['Close']
                    print(f"  ✓ {ticker}: {len(data)} days")
            except Exception as e:
                print(f"  ✗ {ticker}: {str(e)[:50]}")

        return price_data

    def calculate_metrics(self, returns_series):
        """Calculate 5-year performance metrics"""
        try:
            # Clean data
            returns_series = returns_series.dropna()

            if returns_series.empty or len(returns_series) < 100:
                return None

            start_price = returns_series.iloc[0]
            end_price = returns_series.iloc[-1]

            if start_price <= 0 or pd.isna(start_price) or pd.isna(end_price):
                return None

            # Calculate CAGR
            cagr = ((end_price / start_price) ** (1/5) - 1) * 100

            # Daily returns
            daily_returns = returns_series.pct_change().dropna()

            if daily_returns.empty or len(daily_returns) < 50:
                return None

            # Volatility
            volatility = daily_returns.std() * np.sqrt(252) * 100

            # Sharpe
            sharpe = ((cagr / 100 - 0.06) / (volatility / 100)) if volatility > 0 else 0

            # Sortino
            downside_returns = daily_returns[daily_returns < 0]
            sortino = ((cagr / 100 - 0.06) / (downside_returns.std() * np.sqrt(252))) if len(downside_returns) > 0 else 0

            # Drawdown
            cumulative = (1 + daily_returns).cumprod()
            running_max = cumulative.expanding().max()
            drawdown = (cumulative - running_max) / running_max
            max_dd = drawdown.min() * 100

            # Win rate
            win_rate = (daily_returns > 0).sum() / len(daily_returns) * 100
            best_day = daily_returns.max() * 100
            worst_day = daily_returns.min() * 100

            return {
                'cagr_5yr': cagr,
                'volatility': volatility,
                'sharpe': sharpe,
                'sortino': sortino,
                'max_drawdown': max_dd,
                'win_rate': win_rate,
                'best_day': best_day,
                'worst_day': worst_day,
                'current_price': end_price,
                'start_price': start_price
            }
        except Exception as e:
            return None

    def calculate_portfolio_performance(self, portfolio_name, tickers, weights, price_data):
        """Calculate weighted portfolio performance"""
        aligned_data = []
        valid_weights = []
        valid_tickers = []

        for ticker, weight in zip(tickers, weights):
            if ticker in price_data:
                aligned_data.append(price_data[ticker])
                valid_weights.append(weight)
                valid_tickers.append(ticker)

        if not aligned_data:
            print(f"  ✗ {portfolio_name}: No valid tickers found")
            return None

        # Align all series to common dates
        df = pd.DataFrame({ticker: price_data[ticker] for ticker in valid_tickers})
        df = df.dropna()

        if df.empty or len(df) < 100:
            return None

        # Normalize weights
        total_weight = sum(valid_weights)
        weights_norm = [w/total_weight for w in valid_weights]

        # Calculate portfolio value
        portfolio_series = pd.Series(0.0, index=df.index)
        for (ticker, weight) in zip(valid_tickers, weights_norm):
            col = price_data[ticker]
            # Align with df
            col = col[col.index.isin(df.index)]
            if len(col) > 0:
                norm_prices = col / col.iloc[0]
                portfolio_series += norm_prices * weight

        if len(portfolio_series) < 100:
            return None

        return self.calculate_metrics(portfolio_series)

    def run_analysis(self):
        """Run complete analysis"""
        print("=" * 80)
        print("🎯 NIFTY COMPOSITE INDICES vs SCREENER PORTFOLIOS COMPARISON")
        print("=" * 80)
        print(f"\n📅 Analysis Period: {self.start_date.date()} to {self.end_date.date()} (5 years)\n")

        # Fetch data
        self.fetch_index_data()
        price_data = self.fetch_portfolio_data()

        # Calculate metrics for indices
        print("\n" + "=" * 80)
        print("📊 NIFTY COMPOSITE INDICES PERFORMANCE")
        print("=" * 80)

        indices_results = {}
        for name, series in sorted(self.indices.items()):
            try:
                metrics = self.calculate_metrics(series)
                if metrics:
                    indices_results[name] = metrics
                    print(f"\n{name}")
                    print(f"  CAGR (5yr):      {metrics['cagr_5yr']:>7.2f}%")
                    print(f"  Volatility:      {metrics['volatility']:>7.2f}%")
                    print(f"  Sharpe Ratio:    {metrics['sharpe']:>7.2f}")
                    print(f"  Max Drawdown:    {metrics['max_drawdown']:>7.2f}%")
                    print(f"  Win Rate:        {metrics['win_rate']:>7.2f}%")
                    print(f"  Best Day:        {metrics['best_day']:>7.2f}%")
                    print(f"  Worst Day:       {metrics['worst_day']:>7.2f}%")
                else:
                    print(f"  ✗ {name}: Could not calculate metrics")
            except Exception as e:
                print(f"  ✗ {name}: {str(e)[:50]}")

        # Calculate metrics for screener portfolios
        print("\n" + "=" * 80)
        print("📈 SCREENER PORTFOLIO PERFORMANCE")
        print("=" * 80)

        portfolio_results = {}
        for portfolio_name, portfolio_info in self.screener_portfolios.items():
            try:
                metrics = self.calculate_portfolio_performance(
                    portfolio_name,
                    portfolio_info['tickers'],
                    portfolio_info['weights'],
                    price_data
                )
                if metrics:
                    portfolio_results[portfolio_name] = metrics
                    print(f"\n{portfolio_name}")
                    print(f"  CAGR (5yr):      {metrics['cagr_5yr']:>7.2f}%")
                    print(f"  Volatility:      {metrics['volatility']:>7.2f}%")
                    print(f"  Sharpe Ratio:    {metrics['sharpe']:>7.2f}")
                    print(f"  Max Drawdown:    {metrics['max_drawdown']:>7.2f}%")
                    print(f"  Win Rate:        {metrics['win_rate']:>7.2f}%")
                else:
                    print(f"  ✗ {portfolio_name}: Could not calculate metrics")
            except Exception as e:
                print(f"  ✗ {portfolio_name}: {str(e)[:60]}")

        # Generate comparison report
        self.generate_comparison_report(indices_results, portfolio_results)

    def generate_comparison_report(self, indices_results, portfolio_results):
        """Generate comparison tables and analysis"""
        print("\n" + "=" * 80)
        print("🎯 OUTPERFORMANCE ANALYSIS")
        print("=" * 80)

        if not indices_results or not portfolio_results:
            print("Insufficient data for comparison")
            return

        # Find baseline (Nifty 50)
        baseline = indices_results.get('Nifty 50')
        if not baseline:
            baseline = list(indices_results.values())[0] if indices_results else None

        if not baseline:
            return

        print(f"\nBenchmark: Nifty 50")
        print(f"  CAGR: {baseline['cagr_5yr']:.2f}%")
        print(f"  Sharpe: {baseline['sharpe']:.2f}")
        print(f"  Max DD: {baseline['max_drawdown']:.2f}%\n")

        for portfolio_name, metrics in portfolio_results.items():
            outperformance = metrics['cagr_5yr'] - baseline['cagr_5yr']
            sharpe_multiple = metrics['sharpe'] / baseline['sharpe'] if baseline['sharpe'] != 0 else 0

            print(f"{portfolio_name}")
            print(f"  Outperformance:  {outperformance:>6.2f}pp CAGR")
            print(f"  Sharpe Multiple: {sharpe_multiple:>6.2f}X")
            print(f"  Better Downside: {baseline['max_drawdown'] - metrics['max_drawdown']:>6.2f}pp")

            # Calculate wealth accumulation
            base_wealth = (1 + baseline['cagr_5yr']/100) ** 5 * 100000
            portfolio_wealth = (1 + metrics['cagr_5yr']/100) ** 5 * 100000
            extra_profit = portfolio_wealth - base_wealth
            print(f"  Extra profit:    ₹{extra_profit:>10,.0f} per ₹100k\n")

        # Sector analysis
        print("\n" + "=" * 80)
        print("📊 COMPOSITE INDEX COMPARISON")
        print("=" * 80)

        sector_comparison = []
        for sector_name, metrics in sorted(indices_results.items()):
            if sector_name != 'Nifty 50':
                outperformance = metrics['cagr_5yr'] - baseline['cagr_5yr']
                sector_comparison.append({
                    'index': sector_name,
                    'cagr': metrics['cagr_5yr'],
                    'outperformance': outperformance,
                    'sharpe': metrics['sharpe'],
                    'volatility': metrics['volatility'],
                    'max_dd': metrics['max_drawdown']
                })

        if sector_comparison:
            sector_df = pd.DataFrame(sector_comparison).sort_values('cagr', ascending=False)
            print("\nOther Nifty Composite Indices (vs Nifty 50):")
            for idx, row in sector_df.iterrows():
                print(f"  {row['index']:25} CAGR: {row['cagr']:6.2f}% (Δ {row['outperformance']:+6.2f}pp, Sharpe: {row['sharpe']:.2f})")

        # Save results
        results = {
            'timestamp': datetime.now().isoformat(),
            'period': f"{self.start_date.date()} to {self.end_date.date()}",
            'indices': indices_results,
            'portfolios': portfolio_results
        }

        with open('nifty_composite_comparison.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n✓ Results saved to nifty_composite_comparison.json")


if __name__ == '__main__':
    comparison = NiftyCompositeComparison()
    comparison.run_analysis()
