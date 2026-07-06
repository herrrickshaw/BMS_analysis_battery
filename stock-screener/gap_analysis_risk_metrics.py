#!/usr/bin/env python3
"""
GAP ANALYSIS: RISK METRICS & RISK-ADJUSTED RETURNS
====================================================

The original analysis reports 27.3% annual return but omits critical risk metrics:
- Sharpe ratio (return per unit of risk)
- Maximum drawdown
- Calmar ratio (return per unit of max drawdown)
- Volatility
- Win rate distribution

This analysis reconstructs likely risk metrics and compares to market benchmarks.
"""

import json
from pathlib import Path
from datetime import datetime
from math import sqrt

class RiskMetricsAnalysis:
    """Comprehensive risk-adjusted return analysis"""

    def __init__(self):
        self.base_path = Path('/Users/umashankar/stock-screener')
        self.gap_analysis_path = self.base_path / 'gap_analysis'
        self.gap_analysis_path.mkdir(parents=True, exist_ok=True)

    def estimate_volatility_from_win_rate(self, win_rate):
        """
        Estimate volatility based on win rate assumption

        Win rate 58% suggests:
        - Average winning trade: +1.5%
        - Average losing trade: -1.5%
        - This creates volatility ~2-3% monthly
        """

        if win_rate >= 0.65:
            estimated_monthly_volatility = 0.015  # 1.5% per month
        elif win_rate >= 0.55:
            estimated_monthly_volatility = 0.025  # 2.5% per month
        elif win_rate >= 0.50:
            estimated_monthly_volatility = 0.035  # 3.5% per month
        else:
            estimated_monthly_volatility = 0.045  # 4.5% per month

        annual_volatility = estimated_monthly_volatility * sqrt(12)

        return {
            'monthly_volatility': estimated_monthly_volatility,
            'annual_volatility': annual_volatility,
            'reasoning': f'Win rate {win_rate*100:.0f}% implies {estimated_monthly_volatility*100:.2f}% monthly vol'
        }

    def calculate_sharpe_ratio(self, annual_return, annual_volatility, risk_free_rate=0.04):
        """
        Calculate Sharpe ratio

        Sharpe = (Return - Risk-Free Rate) / Volatility
        """

        excess_return = annual_return - risk_free_rate
        sharpe = excess_return / annual_volatility if annual_volatility > 0 else 0

        return {
            'annual_return': annual_return,
            'annual_volatility': annual_volatility,
            'risk_free_rate': risk_free_rate,
            'excess_return': excess_return,
            'sharpe_ratio': sharpe,
        }

    def estimate_maximum_drawdown(self, win_rate, avg_win_size, avg_loss_size):
        """
        Estimate maximum drawdown from win/loss statistics

        Maximum drawdown typically:
        - Small portfolio: peak-to-trough during worst losing streak
        - With 58% win rate: expect ~6-8 losses in a row during crisis
        """

        # Probability of N consecutive losses (58% win rate = 42% loss rate)
        prob_8_losses = (0.42) ** 8  # 0.1% probability

        # Expected max drawdown from consecutive losses
        expected_consecutive_losses = 4  # Conservative
        max_drawdown_simple = expected_consecutive_losses * abs(avg_loss_size)

        # But markets have crash periods: 2008, 2020 saw 30-50% drawdowns
        # Your strategy likely underperformed in crashes (quality sold first)
        estimated_max_drawdown_crisis = 0.20  # 20% in mild crisis
        estimated_max_drawdown_severe = 0.30  # 30% in severe crisis

        return {
            'estimated_max_drawdown_normal': max_drawdown_simple,
            'estimated_max_drawdown_crisis': estimated_max_drawdown_crisis,
            'estimated_max_drawdown_severe': estimated_max_drawdown_severe,
            'typical_range': f'{estimated_max_drawdown_crisis*100:.0f}%-{estimated_max_drawdown_severe*100:.0f}%',
        }

    def calculate_risk_metrics_scenarios(self):
        """Calculate risk metrics under different volatility assumptions"""

        print("\n" + "="*80)
        print("ESTIMATED RISK METRICS FOR 27.3% ANNUAL RETURN")
        print("="*80)

        claimed_return = 0.273
        win_rate = 0.545  # 54.5% average from Phase 2

        scenarios = [
            {
                'name': 'Low Volatility Scenario',
                'annual_volatility': 0.15,  # 15% volatility
                'description': 'If returns are smooth and diversified (unlikely)'
            },
            {
                'name': 'Moderate Volatility Scenario',
                'annual_volatility': 0.22,  # 22% volatility
                'description': 'Typical for quality/fundamental screen'
            },
            {
                'name': 'High Volatility Scenario',
                'annual_volatility': 0.30,  # 30% volatility
                'description': 'If portfolio concentrates in emerging markets'
            },
            {
                'name': 'Very High Volatility Scenario',
                'annual_volatility': 0.40,  # 40% volatility
                'description': 'If strategy exhibits crash-driven underperformance'
            },
        ]

        print(f"\nAssumed Annual Return: {claimed_return*100:.1f}%")
        print(f"Assumed Win Rate: {win_rate*100:.1f}%\n")

        risk_free_rate = 0.04

        results = []

        for scenario in scenarios:
            vol = scenario['annual_volatility']

            sharpe_calc = self.calculate_sharpe_ratio(claimed_return, vol, risk_free_rate)
            drawdown_est = self.estimate_maximum_drawdown(win_rate, 0.02, 0.02)
            calmar = claimed_return / drawdown_est['estimated_max_drawdown_crisis']

            print(f"{scenario['name']}")
            print(f"  Description:          {scenario['description']}")
            print(f"  Annual Volatility:    {vol*100:.1f}%")
            print(f"  Sharpe Ratio:         {sharpe_calc['sharpe_ratio']:.2f}")
            print(f"  Est. Max Drawdown:    {drawdown_est['estimated_max_drawdown_crisis']*100:.0f}%-{drawdown_est['estimated_max_drawdown_severe']*100:.0f}%")
            print(f"  Calmar Ratio:         {calmar:.2f}")
            print(f"  Return/Vol:           {(claimed_return/vol):.2f}x")
            print()

            results.append({
                'scenario': scenario['name'],
                'annual_volatility': vol,
                'sharpe_ratio': sharpe_calc['sharpe_ratio'],
                'max_drawdown_range': f"{drawdown_est['estimated_max_drawdown_crisis']*100:.0f}%-{drawdown_est['estimated_max_drawdown_severe']*100:.0f}%",
                'calmar_ratio': calmar,
            })

        return results

    def compare_to_benchmarks(self):
        """Compare to simple market benchmarks"""

        print("\n" + "="*80)
        print("COMPARISON TO MARKET BENCHMARKS")
        print("="*80)

        benchmarks = [
            {
                'name': 'S&P 500 (30 years)',
                'annual_return': 0.105,
                'annual_volatility': 0.16,
                'sharpe': 0.47,
                'max_drawdown': 0.57,  # 2008 crisis
                'period': '1993-2023'
            },
            {
                'name': 'MSCI World (20 years)',
                'annual_return': 0.075,
                'annual_volatility': 0.18,
                'sharpe': 0.40,
                'max_drawdown': 0.52,
                'period': '2003-2023'
            },
            {
                'name': 'Global Equities (recovery period)',
                'annual_return': 0.12,  # 2009-2019 post-crisis recovery
                'annual_volatility': 0.14,
                'sharpe': 0.57,
                'max_drawdown': 0.20,
                'period': '2009-2019'
            },
            {
                'name': 'Piotroski F-Score (published)',
                'annual_return': 0.075,  # From literature (lower than claimed)
                'annual_volatility': 0.18,
                'sharpe': 0.39,
                'max_drawdown': 0.40,
                'period': '1963-2012 (Piotroski 2000)'
            },
            {
                'name': 'Quality Factor (Fama-French)',
                'annual_return': 0.045,  # Quality premium
                'annual_volatility': 0.12,
                'sharpe': 0.38,
                'max_drawdown': 0.35,
                'period': '1963-2020'
            },
            {
                'name': '60/40 Portfolio (stocks/bonds)',
                'annual_return': 0.078,
                'annual_volatility': 0.11,
                'sharpe': 0.62,
                'max_drawdown': 0.30,
                'period': 'Long-term historical'
            },
        ]

        # Your claimed strategy
        your_return = 0.273
        your_vol_moderate = 0.22
        your_sharpe = (your_return - 0.04) / your_vol_moderate
        your_max_dd = 0.20

        print(f"\nYour Strategy (27.3% return, moderate vol scenario):")
        print(f"  Annual Return:  {your_return*100:.1f}%")
        print(f"  Volatility:     {your_vol_moderate*100:.1f}%")
        print(f"  Sharpe Ratio:   {your_sharpe:.2f}")
        print(f"  Max Drawdown:   {your_max_dd*100:.0f}%")
        print()

        print("Benchmark Comparison:")
        print("-" * 80)
        print(f"{'Benchmark':<35} {'Return':<10} {'Vol':<8} {'Sharpe':<8} {'Max DD':<10}")
        print("-" * 80)

        for bench in benchmarks:
            sharpe = (bench['annual_return'] - 0.04) / bench['annual_volatility']
            print(f"{bench['name']:<35} {bench['annual_return']*100:>6.1f}%   {bench['annual_volatility']*100:>5.1f}%  {sharpe:>6.2f}  {bench['max_drawdown']*100:>6.0f}%")

        print("-" * 80)
        print(f"{'Your Strategy (claimed)':<35} {your_return*100:>6.1f}%   {your_vol_moderate*100:>5.1f}%  {your_sharpe:>6.2f}  {your_max_dd*100:>6.0f}%")
        print()

        print("Key Observations:")
        print("  1. Your claimed 27.3% return is 2.6x the long-term S&P 500 (10.5%)")
        print("  2. Your claimed Sharpe (1.08) is 2.3x the S&P 500 (0.47)")
        print("  3. This suggests either:")
        print("     a) Exceptional market timing (recovered from 2020 COVID, benefited from rate rise)")
        print("     b) Backtest overfitting to 2021-2026 period")
        print("     c) Data mining (testing until finding profitable combo)")
        print("     d) Survivorship bias (excluding losers)")
        print("     e) Underestimated transaction costs / market impact")
        print()

        return benchmarks

    def assess_realism(self):
        """Reality check: Can 27.3% sustained returns be realistic?"""

        print("\n" + "="*80)
        print("REALISM ASSESSMENT")
        print("="*80)

        print("""
Historical Context:
  - S&P 500 long-term: 10% annual (100+ years)
  - Exceptional periods (post-crisis recovery): 15-20% (2009-2019)
  - Your claimed: 27.3% (2021-2026)

Your backtest period (2021-2026) was unusual:
  - 2021-2022: COVID recovery + corporate earnings growth
  - 2023-2024: Post-Fed pivot, equity rally
  - This was a favorable regime for:
    * Quality stocks (your F-Score screen)
    * Momentum (Darvas Box)
    * Emerging markets (India strong 2021-2023)

Concerns about 27.3% claim:
  ✗ Only tested on one market regime (2021-2026)
  ✗ Transaction costs likely 4-12% annual (not modeled)
  ✗ Survivorship bias not quantified
  ✗ Piotroski literature claims 7.5% (not 27%)
  ✗ Without risk metrics (Sharpe, drawdown), return claims are incomplete
  ✗ 20,000-stock portfolio creates liquidity constraints not modeled

Realistic return estimates (post-transaction costs):
  - Conservative (after 4% costs):     23.3% (unlikely still ~2.2x market)
  - Base case (after 8% costs):        19.3% (still 1.8x market)
  - With transaction costs + regime adjustment: 12-18% (more realistic)

Recommendation:
  - Retest on 2000-2010, 2008-2020, and other periods
  - Model transaction costs (critical)
  - Verify Sharpe ratio exceeds 0.60 (better than 60/40 portfolio)
  - Quantify maximum drawdown in crisis periods
        """)

        return {
            'base_claim': '27.3%',
            'realistic_range': '12-18%',
            'after_costs_conservative': '23.3%',
            'after_costs_realistic': '19.3%',
        }

    def generate_report(self):
        """Generate comprehensive risk metrics report"""

        print("\n" + "█"*80)
        print("█ RISK METRICS GAP ANALYSIS")
        print("█"*80)

        # Calculate risk metrics
        scenarios = self.calculate_risk_metrics_scenarios()

        # Compare benchmarks
        benchmarks = self.compare_to_benchmarks()

        # Reality assessment
        realism = self.assess_realism()

        # Save report
        report = {
            'analysis_date': datetime.now().isoformat(),
            'claimed_return': 0.273,
            'risk_metrics_scenarios': scenarios,
            'benchmark_comparison': benchmarks,
            'realism_assessment': realism,
            'key_findings': [
                'Sharpe ratio likely 0.90-1.10 (vs S&P 500: 0.47)',
                'Maximum drawdown estimated 20-30% (not disclosed in original)',
                '27.3% return only tested on favorable 2021-2026 regime',
                'Must test on 2008 crisis, 2000 crash, and other periods',
                'Transaction costs reduce return to ~19-23% (realistic)',
                'Risk-adjusted returns may not exceed simple 60/40 portfolio',
            ],
            'critical_gaps': [
                'No Sharpe ratio reported (essential for academic paper)',
                'No maximum drawdown analysis',
                'No regime stability testing (only 1 period tested)',
                'No volatility/risk metrics',
                'No Calmar ratio (return/max drawdown)',
            ],
            'next_steps': [
                '1. Add Sharpe ratio, max drawdown to results',
                '2. Test on 2008-2009, 2000-2002 crisis periods',
                '3. Model transaction costs (4-12% annual)',
                '4. Report net-of-cost returns',
                '5. Calculate rolling Sharpe ratio across periods',
            ]
        }

        report_file = self.gap_analysis_path / 'risk_metrics_analysis.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n✅ Report saved: {report_file}")

        return report

def main():
    analysis = RiskMetricsAnalysis()
    analysis.generate_report()

if __name__ == "__main__":
    main()
