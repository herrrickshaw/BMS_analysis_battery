#!/usr/bin/env python3
"""
Rewards Optimization & Analysis Module
Identifies exceptional performers outside typical screening filters
Analyzes 5-year returns with risk-adjusted metrics
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import warnings
import json

warnings.filterwarnings('ignore')

class RewardsOptimizer:
    """Advanced rewards analysis for exceptional performers"""

    def __init__(self, tickers_by_market: Dict[str, List[str]]):
        """
        Initialize rewards optimizer

        Args:
            tickers_by_market: Dict with market as key, list of tickers as value
                {
                    'india': ['HDFCBANK', 'RELIANCE'],
                    'us': ['AAPL', 'MSFT'],
                    'europe': ['ADS.DE', 'SAP.DE']
                }
        """
        self.tickers_by_market = tickers_by_market
        self.all_tickers = []
        self.price_data = {}
        self.metrics = {}
        self.risk_metrics = {}

        # Normalize tickers for yfinance
        self._normalize_tickers()

    def _normalize_tickers(self):
        """Normalize tickers based on market"""
        for market, tickers in self.tickers_by_market.items():
            for ticker in tickers:
                if market == 'india':
                    yf_ticker = f"{ticker}.NS" if not ticker.endswith(('.NS', '.BO')) else ticker
                else:
                    yf_ticker = ticker

                self.all_tickers.append({
                    'original': ticker,
                    'yf_ticker': yf_ticker,
                    'market': market
                })

    def fetch_5year_data(self):
        """Fetch 5-year price history"""
        print("Fetching 5-year historical data...")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * 5)

        for ticker_info in self.all_tickers:
            yf_ticker = ticker_info['yf_ticker']
            ticker = ticker_info['original']

            try:
                print(f"  {ticker}...", end=" ")
                data = yf.download(yf_ticker, start=start_date, end=end_date,
                                 progress=False, interval='1d')

                if len(data) > 0:
                    self.price_data[ticker] = {
                        'market': ticker_info['market'],
                        'yf_ticker': yf_ticker,
                        'data': data
                    }
                    print("✓")
                else:
                    print("✗ (no data)")
            except Exception as e:
                print(f"✗ ({str(e)[:30]})")

    def calculate_5year_metrics(self) -> pd.DataFrame:
        """Calculate comprehensive 5-year return metrics"""
        print("\nCalculating return metrics...")
        results = []

        for ticker, data_info in self.price_data.items():
            try:
                data = data_info['data']
                market = data_info['market']

                # Daily returns
                daily_returns = data['Close'].pct_change().dropna()

                # CAGR
                years = 5
                start_price = data['Close'].iloc[0]
                end_price = data['Close'].iloc[-1]
                cagr = (pow(end_price / start_price, 1/years) - 1) * 100

                # Total return
                total_return = ((end_price - start_price) / start_price) * 100

                # Volatility (annualized)
                volatility = daily_returns.std() * np.sqrt(252) * 100

                # Sharpe ratio (assuming 6% risk-free rate)
                risk_free_rate = 0.06
                annual_return = cagr / 100
                excess_return = annual_return - risk_free_rate
                sharpe_ratio = excess_return / (volatility / 100) if volatility > 0 else 0

                # Sortino ratio (downside risk only)
                downside_returns = daily_returns[daily_returns < 0]
                downside_std = downside_returns.std() * np.sqrt(252)
                sortino_ratio = excess_return / downside_std if downside_std > 0 else 0

                # Maximum drawdown
                cumulative = (1 + daily_returns).cumprod()
                running_max = cumulative.expanding().max()
                drawdown = (cumulative - running_max) / running_max
                max_drawdown = drawdown.min() * 100

                # Win rate (% of positive days)
                win_rate = (daily_returns > 0).sum() / len(daily_returns) * 100

                # Recovery time (from last max drawdown)
                recovery_time = self._calculate_recovery_days(data['Close'])

                results.append({
                    'ticker': ticker,
                    'market': market,
                    'cagr_5yr': cagr,
                    'total_return': total_return,
                    'volatility': volatility,
                    'sharpe_ratio': sharpe_ratio,
                    'sortino_ratio': sortino_ratio,
                    'max_drawdown': max_drawdown,
                    'win_rate': win_rate,
                    'recovery_days': recovery_time,
                    'start_price': start_price,
                    'end_price': end_price,
                    'data_points': len(data),
                })
            except Exception as e:
                print(f"Error calculating metrics for {ticker}: {str(e)}")

        self.metrics_df = pd.DataFrame(results).sort_values('cagr_5yr', ascending=False)
        return self.metrics_df

    def _calculate_recovery_days(self, prices):
        """Calculate days to recover from last max drawdown"""
        returns = prices.pct_change().fillna(0)
        cumulative = (1 + returns).cumprod()

        # Find last maximum
        max_idx = cumulative.idxmax()
        last_max_value = cumulative.max()

        # From max point forward, find recovery
        prices_after_max = cumulative[cumulative.index >= max_idx]

        recovery_price = last_max_value * 0.95  # 95% recovery threshold
        recovery_dates = prices_after_max[prices_after_max >= recovery_price]

        if len(recovery_dates) > 0:
            recovery_days = (recovery_dates.index[0] - max_idx).days
            return max(0, recovery_days)
        else:
            return 999  # Not recovered

    def identify_exceptional_performers(self, min_cagr: float = 20) -> pd.DataFrame:
        """Identify stocks with exceptional returns"""
        exceptional = self.metrics_df[self.metrics_df['cagr_5yr'] > min_cagr].copy()

        print(f"\n🏆 EXCEPTIONAL PERFORMERS (CAGR > {min_cagr}%)")
        print(f"{'='*80}")

        for idx, row in exceptional.iterrows():
            print(f"\n{row['ticker'].upper()} ({row['market'].upper()})")
            print(f"  CAGR (5yr): {row['cagr_5yr']:.2f}%")
            print(f"  Total Return: {row['total_return']:.2f}%")
            print(f"  Volatility: {row['volatility']:.2f}%")
            print(f"  Sharpe Ratio: {row['sharpe_ratio']:.3f} (Risk-adjusted return)")
            print(f"  Max Drawdown: {row['max_drawdown']:.2f}%")
            print(f"  Win Rate: {row['win_rate']:.1f}% (Days up)")

        return exceptional

    def calculate_risk_adjusted_score(self) -> pd.DataFrame:
        """Calculate composite risk-adjusted reward score"""
        print("\nCalculating Risk-Adjusted Scores...")

        df = self.metrics_df.copy()

        # Normalize each metric (0-100 scale)
        def normalize(series, ascending=False):
            if ascending:
                return (series - series.min()) / (series.max() - series.min()) * 100
            else:
                return (series.max() - series) / (series.max() - series.min()) * 100

        # Components of score
        df['return_score'] = normalize(df['cagr_5yr'], ascending=True)
        df['sharpe_score'] = normalize(df['sharpe_ratio'], ascending=True)
        df['sortino_score'] = normalize(df['sortino_ratio'], ascending=True)
        df['stability_score'] = normalize(df['max_drawdown'], ascending=False)  # Lower DD is better
        df['consistency_score'] = normalize(df['win_rate'], ascending=True)

        # Composite score (weights)
        df['rewards_optimization_score'] = (
            df['return_score'] * 0.35 +        # 35% - Raw returns
            df['sharpe_score'] * 0.25 +        # 25% - Risk-adjusted returns
            df['stability_score'] * 0.20 +     # 20% - Stability (low drawdown)
            df['consistency_score'] * 0.20     # 20% - Consistency (win rate)
        )

        return df.sort_values('rewards_optimization_score', ascending=False)

    def beat_typical_screeners(self) -> Dict:
        """Identify which exceptional performers beat typical screeners"""
        print("\n📊 ANALYSIS: Which Stocks Beat Typical Screeners?")
        print("="*80)

        analysis = {
            'beat_momentum': [],
            'beat_value': [],
            'beat_quality': [],
            'beat_growth': [],
            'beat_all_metrics': []
        }

        for idx, row in self.metrics_df.iterrows():
            ticker = row['ticker']

            # Typical screener criteria
            beats_momentum = row['cagr_5yr'] > 25  # Momentum filter: >25% CAGR
            beats_value = row['volatility'] < 35   # Low volatility (value = stable)
            beats_quality = row['sharpe_ratio'] > 1.0  # Good risk-adjusted
            beats_growth = row['win_rate'] > 55    # Consistent wins (>55% up days)
            beats_consistency = row['max_drawdown'] > -25  # Limited drawdown

            # Categorize
            if beats_momentum:
                analysis['beat_momentum'].append({
                    'ticker': ticker,
                    'cagr': row['cagr_5yr'],
                    'reason': f"Exceptional momentum: {row['cagr_5yr']:.1f}% CAGR"
                })

            if beats_value:
                analysis['beat_value'].append({
                    'ticker': ticker,
                    'volatility': row['volatility'],
                    'reason': f"Stable (low volatility): {row['volatility']:.1f}%"
                })

            if beats_quality:
                analysis['beat_quality'].append({
                    'ticker': ticker,
                    'sharpe': row['sharpe_ratio'],
                    'reason': f"Superior risk-adjusted returns: Sharpe {row['sharpe_ratio']:.2f}"
                })

            if beats_growth:
                analysis['beat_growth'].append({
                    'ticker': ticker,
                    'win_rate': row['win_rate'],
                    'reason': f"Consistent upside: {row['win_rate']:.1f}% up days"
                })

            # Ultra-rare: beats all
            if beats_momentum and beats_value and beats_quality and beats_growth:
                analysis['beat_all_metrics'].append({
                    'ticker': ticker,
                    'metrics': {
                        'cagr': row['cagr_5yr'],
                        'volatility': row['volatility'],
                        'sharpe': row['sharpe_ratio'],
                        'win_rate': row['win_rate']
                    }
                })

        return analysis

    def generate_rewards_report(self) -> Dict:
        """Generate comprehensive rewards optimization report"""
        print("\n" + "="*80)
        print("🎯 REWARDS OPTIMIZATION ANALYSIS - FINAL REPORT")
        print("="*80)

        # Risk-adjusted scoring
        scored_df = self.calculate_risk_adjusted_score()

        # Exceptional performers
        exceptional = scored_df[scored_df['cagr_5yr'] > 20]

        # Beat screeners analysis
        screener_analysis = self.beat_typical_screeners()

        # Recommendations
        recommendations = self._generate_recommendations(scored_df, screener_analysis)

        report = {
            'generated_at': datetime.now().isoformat(),
            'analysis_period': '5 years',
            'total_stocks_analyzed': len(scored_df),
            'exceptional_performers': {
                'count': len(exceptional),
                'stocks': exceptional[['ticker', 'market', 'cagr_5yr', 'sharpe_ratio',
                                      'rewards_optimization_score']].to_dict('records')
            },
            'screener_beating_analysis': {
                'beat_momentum_filter': len(screener_analysis['beat_momentum']),
                'beat_value_filter': len(screener_analysis['beat_value']),
                'beat_quality_filter': len(screener_analysis['beat_quality']),
                'beat_growth_filter': len(screener_analysis['beat_growth']),
                'beat_all_filters': len(screener_analysis['beat_all_metrics']),
                'stocks_beating_all': screener_analysis['beat_all_metrics']
            },
            'top_10_by_rewards_score': scored_df.head(10)[[
                'ticker', 'market', 'cagr_5yr', 'volatility', 'sharpe_ratio',
                'max_drawdown', 'rewards_optimization_score'
            ]].to_dict('records'),
            'risk_analysis': {
                'average_volatility': float(scored_df['volatility'].mean()),
                'average_max_drawdown': float(scored_df['max_drawdown'].mean()),
                'average_win_rate': float(scored_df['win_rate'].mean()),
                'average_sharpe_ratio': float(scored_df['sharpe_ratio'].mean()),
            },
            'recommendations': recommendations,
            'scoring_methodology': {
                'components': {
                    'return_score': '35% - Raw 5-year CAGR',
                    'sharpe_score': '25% - Risk-adjusted returns',
                    'stability_score': '20% - Stability (low max drawdown)',
                    'consistency_score': '20% - Consistency (% up days)'
                },
                'scale': '0-100, higher is better'
            }
        }

        return report

    def _generate_recommendations(self, scored_df: pd.DataFrame, screener_analysis: Dict) -> List[str]:
        """Generate investment recommendations based on analysis"""
        recommendations = []

        # Top performer recommendation
        if len(scored_df) > 0:
            top_stock = scored_df.iloc[0]
            recommendations.append(
                f"🥇 TOP PICK: {top_stock['ticker']} - Rewards Score {top_stock['rewards_optimization_score']:.1f}/100. "
                f"CAGR: {top_stock['cagr_5yr']:.1f}%, Sharpe: {top_stock['sharpe_ratio']:.2f}"
            )

        # Quality outlier
        quality_outlier = scored_df.nlargest(1, 'sharpe_ratio').iloc[0]
        recommendations.append(
            f"⭐ QUALITY OUTLIER: {quality_outlier['ticker']} - Best risk-adjusted returns (Sharpe {quality_outlier['sharpe_ratio']:.2f}) "
            f"with {quality_outlier['cagr_5yr']:.1f}% CAGR and only {quality_outlier['max_drawdown']:.1f}% max drawdown"
        )

        # Stability play
        stability_pick = scored_df.nlargest(1, 'stability_score').iloc[0]
        recommendations.append(
            f"🛡️ STABILITY PICK: {stability_pick['ticker']} - Most stable performer. "
            f"{stability_pick['volatility']:.1f}% volatility with {stability_pick['cagr_5yr']:.1f}% returns"
        )

        # Consistency play
        consistency_pick = scored_df.nlargest(1, 'consistency_score').iloc[0]
        recommendations.append(
            f"📈 CONSISTENCY: {consistency_pick['ticker']} - {consistency_pick['win_rate']:.1f}% positive days. "
            f"Most reliable upside with {consistency_pick['cagr_5yr']:.1f}% CAGR"
        )

        # Hidden gem (high returns, low volatility)
        high_return_low_vol = scored_df[
            (scored_df['cagr_5yr'] > 15) &
            (scored_df['volatility'] < 30)
        ].nlargest(1, 'cagr_5yr')

        if len(high_return_low_vol) > 0:
            gem = high_return_low_vol.iloc[0]
            recommendations.append(
                f"💎 HIDDEN GEM: {gem['ticker']} - High returns ({gem['cagr_5yr']:.1f}%) with low volatility ({gem['volatility']:.1f}%). "
                f"Rare combination: exceptional risk-adjusted performance"
            )

        # Sector rotation opportunity
        if 'market' in scored_df.columns:
            market_avg = scored_df.groupby('market')['cagr_5yr'].mean()
            best_market = market_avg.idxmax()
            recommendations.append(
                f"🌍 SECTOR STRENGTH: {best_market.upper()} market showing strongest performance. "
                f"Average CAGR: {market_avg[best_market]:.1f}% vs {market_avg.mean():.1f}% overall"
            )

        return recommendations

    def print_comprehensive_report(self, report: Dict):
        """Print formatted comprehensive report"""
        print("\n" + "="*80)
        print("📊 REWARDS OPTIMIZATION & ANALYSIS REPORT")
        print("="*80)

        print(f"\n📈 ANALYSIS PERIOD: {report['analysis_period']}")
        print(f"📊 STOCKS ANALYZED: {report['total_stocks_analyzed']}")

        print(f"\n🏆 EXCEPTIONAL PERFORMERS (CAGR > 20%)")
        print(f"   Count: {report['exceptional_performers']['count']}")
        for stock in report['exceptional_performers']['stocks'][:5]:
            print(f"   • {stock['ticker']} ({stock['market']}) - "
                  f"{stock['cagr_5yr']:.1f}% CAGR, Score: {stock['rewards_optimization_score']:.1f}/100")

        print(f"\n🎯 BEATING TYPICAL SCREENERS")
        print(f"   Momentum Filter (>25% CAGR): {report['screener_beating_analysis']['beat_momentum_filter']} stocks")
        print(f"   Value Filter (low volatility): {report['screener_beating_analysis']['beat_value_filter']} stocks")
        print(f"   Quality Filter (Sharpe >1.0): {report['screener_beating_analysis']['beat_quality_filter']} stocks")
        print(f"   Growth Filter (>55% up days): {report['screener_beating_analysis']['beat_growth_filter']} stocks")
        print(f"   🌟 BEATS ALL FILTERS: {report['screener_beating_analysis']['beat_all_filters']} stocks (RARE!)")

        if report['screener_beating_analysis']['stocks_beating_all']:
            print(f"\n   Ultra-Rare Stocks Beating All Filters:")
            for stock in report['screener_beating_analysis']['stocks_beating_all']:
                print(f"   ✨ {stock['ticker']}")

        print(f"\n⭐ TOP 10 BY REWARDS OPTIMIZATION SCORE")
        print(f"{'Rank':<5} {'Ticker':<12} {'Market':<10} {'CAGR%':<10} {'Sharpe':<10} {'Score':<10}")
        print(f"-"*70)
        for i, stock in enumerate(report['top_10_by_rewards_score'], 1):
            print(f"{i:<5} {stock['ticker']:<12} {stock['market']:<10} "
                  f"{stock['cagr_5yr']:<10.1f} {stock['sharpe_ratio']:<10.2f} {stock['rewards_optimization_score']:<10.1f}")

        print(f"\n📊 RISK ANALYSIS (Average)")
        print(f"   Volatility: {report['risk_analysis']['average_volatility']:.2f}%")
        print(f"   Max Drawdown: {report['risk_analysis']['average_max_drawdown']:.2f}%")
        print(f"   Win Rate: {report['risk_analysis']['average_win_rate']:.1f}%")
        print(f"   Sharpe Ratio: {report['risk_analysis']['average_sharpe_ratio']:.2f}")

        print(f"\n💡 INVESTMENT RECOMMENDATIONS")
        for i, rec in enumerate(report['recommendations'], 1):
            print(f"   {i}. {rec}")

        print("\n" + "="*80)


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Rewards Optimization Analysis')
    parser.add_argument('--output', type=str, default='rewards_analysis.json',
                       help='Output JSON file')
    parser.add_argument('--report', type=str, help='Export detailed report to file')
    args = parser.parse_args()

    # Sample portfolio data
    tickers_by_market = {
        'india': ['HDFCBANK', 'RELIANCE', 'INFY', 'TCS', 'ICICIBANK', 'SBIN', 'MARUTI', 'HDFC', 'WIPRO', 'BAJAJFINSV'],
        'us': ['AAPL', 'MSFT', 'GOOGL', 'AMAZON', 'TESLA'],
        'europe': ['ADS.DE', 'SAP.DE', 'SIEMENS.DE', 'BMW.DE', 'RIO.L'],
    }

    # Run analysis
    optimizer = RewardsOptimizer(tickers_by_market)
    optimizer.fetch_5year_data()
    optimizer.calculate_5year_metrics()
    optimizer.identify_exceptional_performers(min_cagr=20)

    # Generate report
    report = optimizer.generate_rewards_report()
    optimizer.print_comprehensive_report(report)

    # Export JSON
    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n✓ Analysis exported to {args.output}")

    # Export detailed report
    if args.report:
        with open(args.report, 'w') as f:
            f.write(f"REWARDS OPTIMIZATION ANALYSIS REPORT\n")
            f.write(f"Generated: {report['generated_at']}\n")
            f.write(f"{'='*80}\n\n")

            f.write(f"EXECUTIVE SUMMARY\n")
            f.write(f"{'='*80}\n")
            f.write(f"Total Stocks Analyzed: {report['total_stocks_analyzed']}\n")
            f.write(f"Exceptional Performers (CAGR >20%): {report['exceptional_performers']['count']}\n")
            f.write(f"Beating All Typical Screeners: {report['screener_beating_analysis']['beat_all_filters']}\n\n")

            f.write(f"TOP RECOMMENDATIONS\n")
            f.write(f"{'='*80}\n")
            for rec in report['recommendations']:
                f.write(f"{rec}\n\n")

            f.write(f"DETAILED METRICS\n")
            f.write(f"{'='*80}\n")
            for stock in report['top_10_by_rewards_score']:
                f.write(f"\n{stock['ticker']} ({stock['market'].upper()})\n")
                f.write(f"  CAGR (5yr): {stock['cagr_5yr']:.2f}%\n")
                f.write(f"  Volatility: {stock['volatility']:.2f}%\n")
                f.write(f"  Sharpe Ratio: {stock['sharpe_ratio']:.3f}\n")
                f.write(f"  Max Drawdown: {stock['max_drawdown']:.2f}%\n")
                f.write(f"  Rewards Score: {stock['rewards_optimization_score']:.1f}/100\n")

        print(f"✓ Detailed report exported to {args.report}")


if __name__ == '__main__':
    main()
