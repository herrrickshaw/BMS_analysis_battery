#!/usr/bin/env python3
"""
Modern Resilience Strategy (2021-2026)
Novel reward optimization combining:
- AI Disruption Resilience
- Inflation Pricing Power
- Supply Chain Resilience
- Rate Hike Resilience
- Insider Accumulation Signal
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple
import yfinance as yf
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


@dataclass
class ModernResilience:
    """Modern Resilience reward signal framework"""

    r_ai_safe: float = 0.0          # AI disruption resilience (0-1)
    r_pricing_power: float = 0.0    # Inflation pricing power (0-1)
    r_supply_chain: float = 0.0     # Supply chain resilience (0-1)
    r_rate_resilient: float = 0.0   # Rate hike resilience (0-1)
    r_insider_smart: float = 0.0    # Insider accumulation signal (0-1)

    # Composite score
    r_modern: float = 0.0

    # Individual components for debugging
    components: Dict = None


class ModernResilienceScorer:
    """
    Calculate novel reward signals for 2021-2026 market environment
    """

    # Weights for composite score (can be optimized)
    DEFAULT_WEIGHTS = {
        'ai_safe': 0.20,
        'pricing_power': 0.25,
        'supply_chain': 0.15,
        'rate_resilient': 0.30,
        'insider_smart': 0.10
    }

    def __init__(self, ticker: str, market: str = 'us'):
        self.ticker = ticker
        self.market = market
        self.stock = None
        self.financials = None
        self.info = None

    def fetch_data(self):
        """Fetch stock data from yfinance"""
        try:
            self.stock = yf.Ticker(self.ticker)
            self.info = self.stock.info
            self.financials = self.stock.quarterly_financials
            return True
        except Exception as e:
            print(f"Error fetching {self.ticker}: {e}")
            return False

    # ============================================================
    # SIGNAL 1: AI DISRUPTION RESILIENCE
    # ============================================================
    def calculate_ai_safe(self) -> float:
        """
        r_ai_safe = (AI-proof moat + AI adoption capacity) / 2

        AI-proof moat indicators:
        - Recurring revenue model (SaaS) → 0.9
        - Customer switching costs (enterprise) → 0.85
        - Proprietary data moat → 0.8
        - Market maker position (exchanges) → 0.9

        AI adoption indicators:
        - Cloud infrastructure spend proxy (% of capex in software/cloud)
        - Digital revenue % of total
        - R&D spend normalized by revenue (innovation capacity)
        """
        try:
            # Proxy 1: Is this a cloud/software company? (high AI adoption)
            sector = self.info.get('sector', '')
            industry = self.info.get('industry', '')

            ai_adoption = 0.5  # Default neutral
            if 'cloud' in industry.lower() or 'software' in industry.lower():
                ai_adoption = 0.85
            elif 'technology' in sector.lower():
                ai_adoption = 0.75
            elif 'financial' in sector.lower():
                ai_adoption = 0.60
            elif 'healthcare' in sector.lower():
                ai_adoption = 0.65
            elif 'utility' in sector.lower():
                ai_adoption = 0.40
            elif 'energy' in sector.lower():
                ai_adoption = 0.45

            # Proxy 2: Is this AI-proof? (recurring revenue, switching costs)
            ai_proof = 0.5  # Default neutral
            if 'software' in industry.lower() or 'saas' in industry.lower():
                ai_proof = 0.90  # High switching costs
            elif 'financial' in sector.lower():
                ai_proof = 0.75  # Switching costs, regulations
            elif 'healthcare' in sector.lower():
                ai_proof = 0.80  # Regulatory moat
            elif 'retail' in sector.lower():
                ai_proof = 0.30  # Highly disrupted
            elif 'energy' in sector.lower():
                ai_proof = 0.85  # Essential commodity

            r_ai_safe = (ai_adoption + ai_proof) / 2.0
            return min(1.0, max(0.0, r_ai_safe))

        except Exception as e:
            return 0.5

    # ============================================================
    # SIGNAL 2: INFLATION PRICING POWER
    # ============================================================
    def calculate_pricing_power(self) -> float:
        """
        r_pricing_power = (Gross margin expansion + Revenue resilience) / 2

        During 2021-2024 inflation:
        - Did gross margins expand or stay stable? (pricing power)
        - Did revenue grow despite macro headwinds? (customer acceptance)

        Proxies:
        - Sector with pricing power: Energy, Luxury, Healthcare, Utilities
        - Revenue growth 2021-2024: Should be >5% CAGR despite inflation
        """
        try:
            sector = self.info.get('sector', '')
            revenue = self.info.get('totalRevenue', 0)
            gross_margin = self.info.get('grossMargins', 0)
            profit_margin = self.info.get('profitMargins', 0)

            # Pricing power by sector
            pricing_power_sector = 0.5
            if 'energy' in sector.lower():
                pricing_power_sector = 0.95  # Commodity pricing pass-through
            elif 'luxury' in industry.lower() or 'apparel' in industry.lower():
                pricing_power_sector = 0.90
            elif 'healthcare' in sector.lower():
                pricing_power_sector = 0.85
            elif 'utility' in sector.lower():
                pricing_power_sector = 0.80
            elif 'financial' in sector.lower():
                pricing_power_sector = 0.75
            elif 'consumer staples' in sector.lower():
                pricing_power_sector = 0.70
            elif 'retail' in sector.lower():
                pricing_power_sector = 0.40  # Price-taker
            elif 'technology' in sector.lower():
                pricing_power_sector = 0.65

            # Revenue resilience (did company grow?)
            revenue_resilience = 0.5
            if revenue > 0:
                # Assuming healthy revenue = pricing power maintained
                if profit_margin and profit_margin > 0.10:
                    revenue_resilience = 0.80
                elif profit_margin and profit_margin > 0.05:
                    revenue_resilience = 0.65
                else:
                    revenue_resilience = 0.45

            r_pricing_power = (pricing_power_sector + revenue_resilience) / 2.0
            return min(1.0, max(0.0, r_pricing_power))

        except Exception as e:
            return 0.5

    # ============================================================
    # SIGNAL 3: SUPPLY CHAIN RESILIENCE
    # ============================================================
    def calculate_supply_chain(self) -> float:
        """
        r_supply_chain = (Operational efficiency + Diversification capacity) / 2

        Post-COVID supply chain importance:
        - Inventory turnover stability (did it spike in 2020-2021?)
        - R&D as % of revenue (proprietary supply = less exposed)
        - Manufacturing diversification (% sales from single region)
        """
        try:
            sector = self.info.get('sector', '')
            industry = self.info.get('industry', '')

            # Sectors with supply chain vulnerability
            supply_chain_risk = 0.5
            if 'semiconductor' in industry.lower() or 'chip' in industry.lower():
                supply_chain_risk = 0.95  # Critical supply chain dependency
            elif 'automotive' in industry.lower():
                supply_chain_risk = 0.85
            elif 'retail' in sector.lower():
                supply_chain_risk = 0.70
            elif 'manufacturing' in industry.lower():
                supply_chain_risk = 0.75
            elif 'software' in industry.lower():
                supply_chain_risk = 0.95  # Least supply-chain vulnerable
            elif 'healthcare' in sector.lower():
                supply_chain_risk = 0.80
            elif 'utility' in sector.lower():
                supply_chain_risk = 0.90  # Local/regulated sourcing
            elif 'energy' in sector.lower():
                supply_chain_risk = 0.85  # Commodity sourced

            # R&D as proxy for proprietary supply
            rd_ratio = self.info.get('rd', 0) / self.info.get('totalRevenue', 1)
            rd_score = 0.5
            if rd_ratio > 0.15:
                rd_score = 0.85  # High R&D = proprietary supply
            elif rd_ratio > 0.05:
                rd_score = 0.70
            elif rd_ratio > 0.01:
                rd_score = 0.55

            r_supply_chain = (supply_chain_risk + rd_score) / 2.0
            return min(1.0, max(0.0, r_supply_chain))

        except Exception as e:
            return 0.5

    # ============================================================
    # SIGNAL 4: RATE HIKE RESILIENCE
    # ============================================================
    def calculate_rate_resilient(self) -> float:
        """
        r_rate_resilient = (Low refinancing risk + FCF coverage) / 2

        2022-2024 rate shock environment:
        - Low debt burden (D/E < 0.5 ideal)
        - Long debt maturity (avoid refinancing risk)
        - Strong FCF/Debt ratio (survive rate spike)

        Also benefit from rate rise:
        - Financial services (wider spreads)
        - Insurance companies (asset yield improvement)
        """
        try:
            sector = self.info.get('sector', '')
            debt_ratio = self.info.get('debtToEquity', 1.0)
            fcf = self.info.get('freeCashflow', 0)
            total_debt = self.info.get('totalDebt', 1)

            # Sectors that benefit from rate hikes
            rate_benefit = 0.5
            if 'financial' in sector.lower():
                rate_benefit = 0.95  # Banks, insurers benefit
            elif 'utility' in sector.lower():
                rate_benefit = 0.85  # Regulated pricing, low debt
            elif 'real estate' in sector.lower():
                rate_benefit = 0.35  # Mortgage rates hurt
            elif 'technology' in sector.lower():
                rate_benefit = 0.40  # Debt-heavy, growth-oriented
            elif 'energy' in sector.lower():
                rate_benefit = 0.75  # Strong FCF, low debt
            elif 'healthcare' in sector.lower():
                rate_benefit = 0.75  # Essential, stable FCF
            else:
                rate_benefit = 0.50

            # Debt/leverage assessment
            leverage_score = 0.5
            if debt_ratio is not None and debt_ratio < 0.3:
                leverage_score = 0.95  # Very safe
            elif debt_ratio is not None and debt_ratio < 0.5:
                leverage_score = 0.85  # Safe
            elif debt_ratio is not None and debt_ratio < 1.0:
                leverage_score = 0.65  # Moderate
            elif debt_ratio is not None and debt_ratio < 2.0:
                leverage_score = 0.40  # High
            else:
                leverage_score = 0.20  # Very high

            r_rate_resilient = (rate_benefit + leverage_score) / 2.0
            return min(1.0, max(0.0, r_rate_resilient))

        except Exception as e:
            return 0.5

    # ============================================================
    # SIGNAL 5: INSIDER ACCUMULATION SMART
    # ============================================================
    def calculate_insider_smart(self) -> float:
        """
        r_insider_smart = (Insider confidence + Smart timing) / 2

        Insider buying during market downturns (2020, 2022, 2023):
        - Buy-to-sell ratio > 2.0 = high conviction
        - Buying in downturns vs routine exercises = smart

        Note: Requires SEC Form 4 data - using proxy for now

        Proxies:
        - If stock performed well 2021-2026: insiders were right
        - Strong insider ownership % (alignment)
        """
        try:
            info = self.info

            # Check if stock appreciated significantly (proxy for smart insider buying)
            # In 2021-2026, did this company outperform?
            ytd_return = 0.0
            try:
                hist = yf.download(
                    self.ticker,
                    start='2021-01-01',
                    end='2024-12-31',
                    progress=False
                )
                if len(hist) > 0:
                    start_price = hist['Adj Close'].iloc[0]
                    end_price = hist['Adj Close'].iloc[-1]
                    ytd_return = (end_price - start_price) / start_price
            except:
                pass

            # Insider ownership as proxy for insider conviction
            insider_score = 0.5
            if ytd_return > 0.15:
                insider_score = 0.85  # Stock ran up, insiders were right
            elif ytd_return > 0.05:
                insider_score = 0.70
            elif ytd_return > -0.05:
                insider_score = 0.55
            elif ytd_return > -0.20:
                insider_score = 0.40
            else:
                insider_score = 0.25

            # Check if there's institutional ownership concentration
            # (proxy for smart money concentration)
            market_cap = self.info.get('marketCap', 0)
            if market_cap > 1e10:  # $10B+ = likely institutional interest
                institutional_proxy = 0.80
            elif market_cap > 1e9:
                institutional_proxy = 0.70
            elif market_cap > 1e8:
                institutional_proxy = 0.60
            else:
                institutional_proxy = 0.40

            r_insider_smart = (insider_score + institutional_proxy) / 2.0
            return min(1.0, max(0.0, r_insider_smart))

        except Exception as e:
            return 0.5

    # ============================================================
    # COMPOSITE SCORE
    # ============================================================
    def calculate_modern_resilience(
        self,
        weights: Dict = None
    ) -> ModernResilience:
        """Calculate composite Modern Resilience score"""

        if weights is None:
            weights = self.DEFAULT_WEIGHTS

        # Calculate individual signals
        r_ai = self.calculate_ai_safe()
        r_pricing = self.calculate_pricing_power()
        r_supply = self.calculate_supply_chain()
        r_rate = self.calculate_rate_resilient()
        r_insider = self.calculate_insider_smart()

        # Composite score
        r_composite = (
            weights['ai_safe'] * r_ai +
            weights['pricing_power'] * r_pricing +
            weights['supply_chain'] * r_supply +
            weights['rate_resilient'] * r_rate +
            weights['insider_smart'] * r_insider
        )

        return ModernResilience(
            r_ai_safe=r_ai,
            r_pricing_power=r_pricing,
            r_supply_chain=r_supply,
            r_rate_resilient=r_rate,
            r_insider_smart=r_insider,
            r_modern=r_composite,
            components={
                'ai_safe': r_ai,
                'pricing_power': r_pricing,
                'supply_chain': r_supply,
                'rate_resilient': r_rate,
                'insider_smart': r_insider,
                'weights': weights
            }
        )

    def score_universe(self, tickers: List[str]) -> pd.DataFrame:
        """Score multiple tickers and return ranked DataFrame"""
        results = []

        for ticker in tickers:
            self.ticker = ticker
            if self.fetch_data():
                score = self.calculate_modern_resilience()
                results.append({
                    'ticker': ticker,
                    'r_ai_safe': score.r_ai_safe,
                    'r_pricing_power': score.r_pricing_power,
                    'r_supply_chain': score.r_supply_chain,
                    'r_rate_resilient': score.r_rate_resilient,
                    'r_insider_smart': score.r_insider_smart,
                    'r_modern': score.r_modern,
                    'sector': self.info.get('sector', 'Unknown'),
                    'market_cap': self.info.get('marketCap', 0),
                })

        df = pd.DataFrame(results).sort_values('r_modern', ascending=False)
        return df


# ============================================================
# DEMO: Score a sample universe
# ============================================================
if __name__ == '__main__':
    print("=" * 80)
    print("MODERN RESILIENCE STRATEGY - Sample Scoring")
    print("=" * 80)

    # Sample tickers across markets
    sample_tickers = [
        # Large Tech
        'MSFT', 'AAPL', 'GOOGL', 'NVDA', 'META',
        # Energy
        'XOM', 'CVX', 'COP',
        # Healthcare
        'JNJ', 'PFE', 'UNH',
        # Financials
        'JPM', 'GS', 'WFC',
        # Utilities
        'NEE', 'DUK', 'SO',
        # Semiconductors
        'TSM', 'QCOM', 'AMD',
    ]

    scorer = ModernResilienceScorer('AAPL')
    df = scorer.score_universe(sample_tickers[:5])  # Start with 5 for demo

    print("\nTop 5 Modern Resilience Stocks:")
    print(df.head())

    print("\n" + "=" * 80)
    print("Signal Breakdown (MSFT example):")
    print("=" * 80)
    scorer.ticker = 'MSFT'
    if scorer.fetch_data():
        score = scorer.calculate_modern_resilience()
        print(f"AI Disruption Resilience:    {score.r_ai_safe:.3f}")
        print(f"Inflation Pricing Power:     {score.r_pricing_power:.3f}")
        print(f"Supply Chain Resilience:     {score.r_supply_chain:.3f}")
        print(f"Rate Hike Resilience:        {score.r_rate_resilient:.3f}")
        print(f"Insider Accumulation Smart:  {score.r_insider_smart:.3f}")
        print(f"\nComposite Score (r_modern):  {score.r_modern:.3f}")

