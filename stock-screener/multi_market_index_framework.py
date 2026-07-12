#!/usr/bin/env python3
"""
Multi-Market Index Framework
Adapts NSE methodology to S&P (USA), FTSE (UK), Euronext (Europe),
TSE (Japan), KRX (Korea), SSE (China) and other major exchanges

Based on: NSE Indices June 2026, S&P, FTSE, Euronext official methodologies
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from enum import Enum
import json

class Market(Enum):
    """Major global equity markets"""
    INDIA_NSE = "NSE"
    USA_SP500 = "S&P500"
    UK_FTSE = "FTSE"
    EUROPE_STOXX = "STOXX"
    JAPAN_TSE = "TSE"
    KOREA_KRX = "KRX"
    CHINA_SSE = "SSE"
    HONG_KONG_HKEX = "HKEX"

class MarketMethodology:
    """Base class for market-specific index methodologies"""

    def __init__(self, market: Market):
        self.market = market
        self.base_value = 1000 if market == Market.INDIA_NSE else 100
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=1825)  # 5 years

    def get_eligibility_criteria(self) -> Dict:
        """Return market-specific eligibility rules"""
        raise NotImplementedError

    def get_index_constituents(self) -> Dict:
        """Return market's main index composition rules"""
        raise NotImplementedError

    def get_rebalancing_schedule(self) -> List[Tuple]:
        """Return market's rebalancing dates"""
        raise NotImplementedError

    def calculate_index(self):
        """Calculate index using market-specific formula"""
        raise NotImplementedError


class NSEIndia(MarketMethodology):
    """NSE India Equity Index Methodology (June 2026)"""

    def __init__(self):
        super().__init__(Market.INDIA_NSE)
        self.currency = "INR"
        self.trading_days_per_year = 252

    def get_eligibility_criteria(self) -> Dict:
        return {
            'domiciliation': 'India-domiciled',
            'exchange': 'NSE (National Stock Exchange)',
            'series': 'Equity (not BZ, suspension)',
            'trading_frequency': '≥90% of days in 6 months',
            'free_float_iwf': '≥10% OR ≥25% of smallest constituent',
            'liquidity': 'Impact cost ≤0.50% for ₹10 Cr basket',
            'min_price': '≥₹5 (typically)',
            'review_period': 'Semi-annual (Jan, Jul)',
            'settlement': 'T+1 (rolling settlement)',
        }

    def get_index_constituents(self) -> Dict:
        return {
            'Nifty 50': {'count': 50, 'universe': 'Top 100', 'weighting': 'Free-float market-cap'},
            'Nifty 100': {'count': 100, 'universe': 'Top 500', 'weighting': 'Free-float market-cap'},
            'Nifty 500': {'count': 500, 'universe': 'All eligible', 'weighting': 'Free-float market-cap'},
            'Nifty Midcap 150': {'count': 150, 'rank_range': '51-200', 'weighting': 'Free-float (55%)'},
            'Nifty Smallcap 250': {'count': 250, 'rank_range': '201-500', 'weighting': 'Free-float (45%)'},
            'Sectoral': {'count': '14+ sectors', 'examples': 'Bank, IT, FMCG, Auto, Pharma'},
            'Strategy': {'count': '20+ indices', 'examples': 'Quality, Low Vol, Momentum, Dividend'},
        }

    def get_rebalancing_schedule(self) -> List[Tuple]:
        return [
            ('Q1', datetime(self.end_date.year, 3, 31)),
            ('Q2', datetime(self.end_date.year, 6, 30)),
            ('Q3', datetime(self.end_date.year, 9, 30)),
            ('Q4', datetime(self.end_date.year, 12, 31)),
        ]


class SP500USA(MarketMethodology):
    """S&P 500 & S&P Index Methodology (USA)"""

    def __init__(self):
        super().__init__(Market.USA_SP500)
        self.currency = "USD"
        self.trading_days_per_year = 252

    def get_eligibility_criteria(self) -> Dict:
        return {
            'domiciliation': 'US-listed (SEC registered)',
            'exchange': 'NYSE, NASDAQ, or other major US exchanges',
            'market_cap': 'Min $8.2B (as of 2026)',
            'liquidity': 'Min 250k shares/day average volume',
            'trading_frequency': '≥30 trading days in 6 months',
            'financial_viability': 'Positive earnings (typically)',
            'float': 'Min 50% public float',
            'shares_outstanding': 'Min 250k shares',
            'price': 'Min $3 (for S&P 500 entry)',
            'review_period': 'Quarterly (Feb, May, Aug, Nov)',
            'settlement': 'T+2 (standard US settlement)',
            'additional': 'US company headquarters, majority trading on listed exchange',
        }

    def get_index_constituents(self) -> Dict:
        return {
            'S&P 500': {'count': 500, 'market_cap': 'Large-cap', 'weighting': 'Market-cap weighted'},
            'S&P 400 Midcap': {'count': 400, 'market_cap': 'Mid-cap', 'weighting': 'Market-cap weighted'},
            'S&P 600 Smallcap': {'count': 600, 'market_cap': 'Small-cap', 'weighting': 'Market-cap weighted'},
            'S&P 1500 Composite': {'count': 1500, 'market_cap': 'All (S&P500+400+600)', 'weighting': 'Market-cap'},
            'Sector indices': {'count': '11 sectors', 'examples': 'Tech, Finance, Healthcare, Energy'},
            'Factor indices': {'count': '10+ indices', 'examples': 'Value, Growth, Quality, Momentum'},
            'Dividend indices': {'count': '5+ indices', 'examples': 'High Dividend, Dividend Aristocrats'},
        }

    def get_rebalancing_schedule(self) -> List[Tuple]:
        return [
            ('Q1', datetime(self.end_date.year, 2, 28)),
            ('Q2', datetime(self.end_date.year, 5, 31)),
            ('Q3', datetime(self.end_date.year, 8, 31)),
            ('Q4', datetime(self.end_date.year, 11, 30)),
        ]

    def key_differences_from_nse(self) -> Dict:
        return {
            'min_market_cap': 'Much higher ($8.2B vs ₹3000 Cr)',
            'float_requirement': 'Higher (50% vs 10-25%)',
            'earnings_criterion': 'Profitability required (NSE has none)',
            'index_size': 'Smaller indices (500 vs 500+)',
            'rebalancing': 'Less frequent (Quarterly vs NSE)',
            'currency': 'USD (multi-country exposure)',
            'dividends': 'More dividend focus, ex-dividend handling',
            'share_buybacks': 'Common, affects share count',
        }


class FTSEUnitedKingdom(MarketMethodology):
    """FTSE Index Methodology (London Stock Exchange, UK)"""

    def __init__(self):
        super().__init__(Market.UK_FTSE)
        self.currency = "GBP"
        self.trading_days_per_year = 252

    def get_eligibility_criteria(self) -> Dict:
        return {
            'domiciliation': 'UK or overseas-listed (LSE traded)',
            'exchange': 'London Stock Exchange (Main Market)',
            'market_cap_ftse100': 'Min £2B (~₹20,000 Cr)',
            'market_cap_ftse250': 'Min £300M (~₹3,000 Cr)',
            'liquidity': 'Min £500k daily turnover (typical)',
            'trading_frequency': '≥90% of days in 3 months',
            'float': 'Min 25% public float',
            'listing_period': 'Min 3 months (for FTSE 100)',
            'accounting': 'IFRS or US GAAP',
            'review_period': 'Quarterly (Mar, Jun, Sep, Dec)',
            'settlement': 'T+2 (UK settlement)',
            'additional': 'Primary listing on LSE',
        }

    def get_index_constituents(self) -> Dict:
        return {
            'FTSE 100': {'count': 100, 'market_cap': 'Large-cap', 'min_cap': '£2B'},
            'FTSE 250': {'count': 250, 'market_cap': 'Mid-cap', 'min_cap': '£300M'},
            'FTSE Small Cap': {'count': 'Variable', 'market_cap': 'Small-cap', 'min_cap': 'Lower'},
            'FTSE 350': {'count': 350, 'composition': 'FTSE 100 + 250'},
            'FTSE All Share': {'count': 'All eligible', 'composition': 'All listed stocks'},
            'Sector indices': {'count': '12+ sectors', 'examples': 'Mining, Banks, Oil & Gas, Pharma'},
            'Dividend indices': {'count': 'Multiple', 'examples': 'High Dividend Yield'},
        }

    def get_rebalancing_schedule(self) -> List[Tuple]:
        return [
            ('Q1', datetime(self.end_date.year, 3, 31)),
            ('Q2', datetime(self.end_date.year, 6, 30)),
            ('Q3', datetime(self.end_date.year, 9, 30)),
            ('Q4', datetime(self.end_date.year, 12, 31)),
        ]

    def key_differences_from_nse(self) -> Dict:
        return {
            'currency': 'GBP (sterling-based)',
            'float_requirement': 'Higher (25% vs 10%)',
            'geographic': 'International companies allowed',
            'sectors': 'Heavy mining, energy, banking (vs NSE IT-focused)',
            'market_structure': '3-tier (100/250/Small Cap)',
            'liquidity': 'GBP-based turnover (not rupees)',
            'dividend_focus': 'FTSE is income-oriented',
        }


class EuronextEurope(MarketMethodology):
    """Euronext Index Methodology (Europe - Pan-European)"""

    def __init__(self):
        super().__init__(Market.EUROPE_STOXX)
        self.currency = "EUR"
        self.trading_days_per_year = 252

    def get_eligibility_criteria(self) -> Dict:
        return {
            'domiciliation': 'EU member state or EEA',
            'exchanges': 'Euronext (Paris, Amsterdam, Brussels, Lisbon)',
            'market_cap': 'Varies by index',
            'liquidity': 'Min €500k daily turnover',
            'trading_frequency': '≥90% of days in 6 months',
            'float': 'Min 25% public float',
            'share_class': 'Ordinary shares (voting)',
            'listing_period': 'Min 3 months',
            'currency': 'EUR or convertible',
            'review_period': 'Quarterly',
            'settlement': 'T+2 (Euroclear)',
            'additional': 'Comply with MiFID II regulations',
        }

    def get_index_constituents(self) -> Dict:
        return {
            'CAC 40': {'count': 40, 'exchange': 'Euronext Paris', 'weighting': 'Market-cap'},
            'AEX': {'count': 25, 'exchange': 'Euronext Amsterdam', 'weighting': 'Market-cap'},
            'BEL 20': {'count': 20, 'exchange': 'Euronext Brussels', 'weighting': 'Market-cap'},
            'PSI 20': {'count': 20, 'exchange': 'Euronext Lisbon', 'weighting': 'Market-cap'},
            'Stoxx Europe 600': {'count': 600, 'geographic': 'Pan-European', 'weighting': 'Market-cap'},
            'Stoxx Europe 50': {'count': 50, 'tier': 'Mega-cap', 'weighting': 'Market-cap'},
            'Sector indices': {'count': '10+ sectors', 'examples': 'Banks, Luxury, Chemicals, Utilities'},
        }

    def get_rebalancing_schedule(self) -> List[Tuple]:
        return [
            ('Q1', datetime(self.end_date.year, 3, 15)),
            ('Q2', datetime(self.end_date.year, 6, 15)),
            ('Q3', datetime(self.end_date.year, 9, 15)),
            ('Q4', datetime(self.end_date.year, 12, 15)),
        ]

    def key_differences_from_nse(self) -> Dict:
        return {
            'multi_country': 'Pan-European vs single-market (NSE)',
            'currency': 'EUR (vs INR)',
            'regulatory': 'MiFID II (vs NSE regulations)',
            'float': 'Higher (25% min)',
            'settlement': 'Euroclear (vs NSDL/CDSL)',
            'sectors': 'Luxury, chemicals vs NSE IT-heavy',
            'dividends': 'Monthly/quarterly payout schedules vary',
            'taxation': 'Withholding tax varies by country',
        }


class TSEJapan(MarketMethodology):
    """Tokyo Stock Exchange (TSE) Index Methodology"""

    def __init__(self):
        super().__init__(Market.JAPAN_TSE)
        self.currency = "JPY"
        self.trading_days_per_year = 240  # Japan has more holidays

    def get_eligibility_criteria(self) -> Dict:
        return {
            'domiciliation': 'Japan-incorporated',
            'exchange': 'Tokyo Stock Exchange (TSE)',
            'market_cap': 'Varies by section (Prime/Standard/Growth)',
            'liquidity': 'Min trading volume requirements',
            'trading_frequency': '≥90% of days in 6 months',
            'float': 'Min 20% free float',
            'share_class': 'Ordinary voting shares',
            'governance': 'Must comply with TSE listing rules',
            'accounting': 'Japanese GAAP or IFRS',
            'review_period': 'Quarterly or semi-annual',
            'settlement': 'T+2 (Japan Settlement)',
            'additional': 'Must file with FSA (Financial Services Agency)',
        }

    def get_index_constituents(self) -> Dict:
        return {
            'Nikkei 225': {'count': 225, 'weighting': 'Price-weighted (not market-cap!)', 'tier': 'Large-cap'},
            'TOPIX': {'count': 2000, 'weighting': 'Market-cap', 'coverage': 'All TSE Prime'},
            'TOPIX 100': {'count': 100, 'weighting': 'Market-cap', 'tier': 'Mega-cap'},
            'TOPIX Core 30': {'count': 30, 'weighting': 'Market-cap', 'tier': 'Most liquid'},
            'Sector indices': {'count': '17 sectors', 'examples': 'Banks, Auto, Electronics, Pharma'},
            'Regional indices': {'count': '9 regions', 'examples': 'Tokyo, Osaka, Nagoya'},
            'Growth indices': {'count': 'Multiple', 'examples': 'TSE Mothers (high-growth)'},
        }

    def get_rebalancing_schedule(self) -> List[Tuple]:
        return [
            ('Q1', datetime(self.end_date.year, 3, 29)),
            ('Q2', datetime(self.end_date.year, 6, 29)),
            ('Q3', datetime(self.end_date.year, 9, 29)),
            ('Q4', datetime(self.end_date.year, 12, 29)),
        ]

    def key_differences_from_nse(self) -> Dict:
        return {
            'weighting': 'Nikkei 225 is PRICE-weighted (vs market-cap)',
            'currency': 'JPY (vs INR)',
            'market_structure': 'Prime/Standard/Growth sections',
            'float': 'Lower requirement (20% vs NSE 10%)',
            'trading_days': 'Fewer (240 vs 252)',
            'settlement': 'T+2 JSE system',
            'sectors': 'Auto, Electronics, Banking major',
            'governance': 'Cross-shareholding common (keiretsu)',
        }


class KRXKorea(MarketMethodology):
    """Korea Exchange (KRX) Index Methodology"""

    def __init__(self):
        super().__init__(Market.KOREA_KRX)
        self.currency = "KRW"
        self.trading_days_per_year = 252

    def get_eligibility_criteria(self) -> Dict:
        return {
            'domiciliation': 'Korea-incorporated',
            'exchange': 'Korea Exchange (KRX) - KOSPI or KOSDAQ',
            'listing_period': 'Min 3 months for KOSPI, 1 month for KOSDAQ',
            'market_cap': 'KOSPI: Min ₩100B (~$77M), KOSDAQ: lower',
            'liquidity': 'Min trading value requirements',
            'trading_frequency': '≥80% of trading days',
            'float': 'Min 10% free float',
            'share_class': 'Common shares',
            'accounting': 'K-GAAP or IFRS',
            'review_period': 'Quarterly (Jan, Apr, Jul, Oct)',
            'settlement': 'T+2 (Korea Settlement)',
            'additional': 'Must comply with FSC (Financial Services Commission)',
        }

    def get_index_constituents(self) -> Dict:
        return {
            'KOSPI 200': {'count': 200, 'weighting': 'Market-cap', 'exchange': 'KOSPI'},
            'KOSPI 50': {'count': 50, 'weighting': 'Market-cap', 'tier': 'Mega-cap'},
            'KOSPI 100': {'count': 100, 'weighting': 'Market-cap', 'tier': 'Large-cap'},
            'KOSDAQ 150': {'count': 150, 'weighting': 'Market-cap', 'exchange': 'KOSDAQ'},
            'KRX 300': {'count': 300, 'weighting': 'Market-cap', 'coverage': 'KOSPI 200 + KOSDAQ 100'},
            'Sector indices': {'count': '10+ sectors', 'examples': 'Semiconductors, Auto, Finance, Chemical'},
            'Dividend indices': {'count': 'Multiple', 'examples': 'High Dividend'},
        }

    def get_rebalancing_schedule(self) -> List[Tuple]:
        return [
            ('Q1', datetime(self.end_date.year, 1, 31)),
            ('Q2', datetime(self.end_date.year, 4, 30)),
            ('Q3', datetime(self.end_date.year, 7, 31)),
            ('Q4', datetime(self.end_date.year, 10, 31)),
        ]

    def key_differences_from_nse(self) -> Dict:
        return {
            'currency': 'KRW (vs INR)',
            'two_tier': 'KOSPI + KOSDAQ (vs single NSE)',
            'market_cap_threshold': 'Higher than NSE but lower than S&P',
            'trading_frequency': 'Lower requirement (80% vs 90%)',
            'settlement': 'T+2 KSD system',
            'sectors': 'Semiconductor, Auto dominant (Samsung, Hyundai)',
            'conglomerate': 'Chaebol (large family-run groups) common',
            'float': 'Same as NSE (10%)',
        }


class SSEChina(MarketMethodology):
    """Shanghai Stock Exchange (SSE) Index Methodology"""

    def __init__(self):
        super().__init__(Market.CHINA_SSE)
        self.currency = "CNY"
        self.trading_days_per_year = 244  # China has more holidays

    def get_eligibility_criteria(self) -> Dict:
        return {
            'domiciliation': 'China mainland-incorporated',
            'exchange': 'Shanghai Stock Exchange (SSE) A-shares',
            'listing_period': 'Min 1 month',
            'market_cap': 'No formal minimum',
            'liquidity': 'Min daily turnover (RMB)',
            'trading_frequency': '≥90% of trading days',
            'share_class': 'A-shares (CNY denomination)',
            'restriction': 'Subject to trading halts, price limits (±10%)',
            'governance': 'CSRC (China Securities Regulatory Commission) oversight',
            'accounting': 'Chinese GAAP',
            'review_period': 'Semi-annual or quarterly',
            'settlement': 'T+1 (next day)',
            'additional': 'State-owned enterprises (SOEs) common',
        }

    def get_index_constituents(self) -> Dict:
        return {
            'SSE Composite': {'count': 'All', 'weighting': 'Market-cap', 'coverage': 'All SSE stocks'},
            'SSE 180': {'count': 180, 'weighting': 'Market-cap', 'tier': 'Large-cap'},
            'SSE 50': {'count': 50, 'weighting': 'Market-cap', 'tier': 'Mega-cap'},
            'CSI 300': {'count': 300, 'weighting': 'Market-cap', 'coverage': 'SSE 150 + SZSE 150'},
            'CSI 500': {'count': 500, 'weighting': 'Market-cap', 'coverage': 'Mid-cap'},
            'Sector indices': {'count': '10+ sectors', 'examples': 'Banks, Tech, Energy, Real Estate'},
            'State-owned': {'count': 'Multiple', 'examples': 'SOE-specific indices'},
        }

    def get_rebalancing_schedule(self) -> List[Tuple]:
        return [
            ('Semi-annual 1', datetime(self.end_date.year, 6, 30)),
            ('Semi-annual 2', datetime(self.end_date.year, 12, 31)),
        ]

    def key_differences_from_nse(self) -> Dict:
        return {
            'currency': 'CNY/RMB (vs INR)',
            'trading_settlement': 'T+1 (vs NSE T+1, but market-specific)',
            'price_limits': '±10% daily limit (vs no limit NSE)',
            'trading_halts': 'Suspended trading on bad news',
            'holidays': 'More holidays (Chinese New Year, etc)',
            'state_ownership': 'SOEs heavily represented',
            'capital_controls': 'Foreign exchange restrictions',
            'float': 'Often very low for SOEs (<10%)',
            'regulation': 'More centralized, government-led',
        }


class MultiMarketFramework:
    """Framework for building indices across multiple markets"""

    def __init__(self):
        self.markets = {
            Market.INDIA_NSE: NSEIndia(),
            Market.USA_SP500: SP500USA(),
            Market.UK_FTSE: FTSEUnitedKingdom(),
            Market.EUROPE_STOXX: EuronextEurope(),
            Market.JAPAN_TSE: TSEJapan(),
            Market.KOREA_KRX: KRXKorea(),
            Market.CHINA_SSE: SSEChina(),
        }

    def compare_markets(self) -> pd.DataFrame:
        """Compare key attributes across all markets"""
        comparison = []

        for market, methodology in self.markets.items():
            criteria = methodology.get_eligibility_criteria()
            comparison.append({
                'market': market.value,
                'currency': methodology.currency,
                'trading_days': methodology.trading_days_per_year,
                'base_index_value': methodology.base_value,
                'main_index_size': list(methodology.get_index_constituents().values())[0].get('count', 'N/A'),
                'rebalancing_frequency': 'Quarterly',
                'settlement': criteria.get('settlement', 'Unknown'),
                'min_free_float': criteria.get('float', 'N/A'),
            })

        return pd.DataFrame(comparison)

    def get_market_methodology(self, market: Market) -> MarketMethodology:
        """Return methodology for specific market"""
        return self.markets.get(market)

    def identify_deployment_gaps(self) -> Dict:
        """Identify gaps in the current deployment"""
        gaps = {
            'data_coverage': {
                'gap': 'yfinance coverage varies by market',
                'issue': 'Some international indices unavailable via yfinance',
                'impact': 'Limited non-US data quality',
                'solution': 'Add Bloomberg/Reuters/local exchange APIs',
                'priority': 'HIGH',
            },
            'currency_handling': {
                'gap': 'Multi-currency exposure not standardized',
                'issue': 'FX conversion adds complexity and cost',
                'impact': 'Currency hedging costs not accounted for',
                'solution': 'Add currency adjustment factors, hedging analysis',
                'priority': 'HIGH',
            },
            'settlement_timing': {
                'gap': 'Different T+0 to T+2 settlement times',
                'issue': 'Cash flow timing and rebalancing coordination complex',
                'impact': 'Execution slippage across markets',
                'solution': 'Implement market-specific settlement calendars',
                'priority': 'MEDIUM',
            },
            'regulatory_compliance': {
                'gap': 'Each market has different regulations',
                'issue': 'MiFID II (EU), SEC (US), FSC (Korea), CSRC (China)',
                'impact': 'Reporting, taxation, trading restrictions vary',
                'solution': 'Build regulatory module per market',
                'priority': 'HIGH',
            },
            'trading_hours': {
                'gap': 'Markets have different operating hours',
                'issue': 'NYSE: 9:30-16:00 EST, TSE: 8:30-15:00 JST, etc',
                'impact': 'Cross-market arbitrage windows, execution timing',
                'solution': 'Map all trading hours, create unified clock',
                'priority': 'MEDIUM',
            },
            'corporate_actions': {
                'gap': 'Handling varies (splits, dividends, demergers)',
                'issue': 'US: frequent buybacks, Japan: cross-shareholding',
                'impact': 'Index calculation adjustments non-standard',
                'solution': 'Market-specific corporate action handlers',
                'priority': 'MEDIUM',
            },
            'liquidity_requirements': {
                'gap': 'Each market defines liquidity differently',
                'issue': 'NSE: ₹10Cr impact cost, S&P: $500k volume, etc',
                'impact': 'Different stocks qualify in different markets',
                'solution': 'Standardize liquidity checks per market',
                'priority': 'HIGH',
            },
            'dividend_treatment': {
                'gap': 'Ex-dividend handling varies significantly',
                'issue': 'JSE: next day ex-date, US: typical ex-date norms',
                'impact': 'Total return calculation differences',
                'solution': 'Market-specific dividend adjustment rules',
                'priority': 'MEDIUM',
            },
            'index_reconstitution': {
                'gap': 'Rebalancing schedules differ',
                'issue': 'NSE: Quarterly, S&P: Quarterly, FTSE: Quarterly, but different dates',
                'impact': 'Coordinating global rebalancing complex',
                'solution': 'Create unified reconstitution calendar',
                'priority': 'MEDIUM',
            },
            'hedging_instruments': {
                'gap': 'Futures/options availability varies',
                'issue': 'Some markets lack derivatives on all indices',
                'impact': 'Cannot hedge all exposures efficiently',
                'solution': 'Map available hedging instruments per market',
                'priority': 'MEDIUM',
            },
            'data_quality': {
                'gap': 'Different data vendors have different quality',
                'issue': 'China: trading halts and price limits distort',
                'impact': 'Index calculations can be unreliable',
                'solution': 'Add data quality validation per market',
                'priority': 'HIGH',
            },
            'backtesting': {
                'gap': 'Historical data quality/availability issues',
                'issue': 'Some emerging markets lack 5-year reliable data',
                'impact': 'Cannot backtest strategies accurately',
                'solution': 'Establish minimum data requirements',
                'priority': 'MEDIUM',
            },
            'tax_handling': {
                'gap': 'Tax treatment differs (withholding, LTCG, etc)',
                'issue': 'India: LTCG 20%, US: LTCG 15-20%, Japan: complex',
                'impact': 'After-tax returns not comparable',
                'solution': 'Add tax adjustment per market/investor',
                'priority': 'HIGH',
            },
            'political_risk': {
                'gap': 'Geopolitical events not modeled',
                'issue': 'China: sanctions, trading halts; Russia: delisting',
                'impact': 'Index can become non-replicable',
                'solution': 'Add political risk assessment module',
                'priority': 'LOW',
            },
        }

        return gaps


if __name__ == '__main__':
    print("Multi-Market Index Framework")
    print("=" * 80)

    framework = MultiMarketFramework()

    print("\n📊 MARKET COMPARISON")
    print(framework.compare_markets().to_string())

    print("\n\n🔍 DEPLOYMENT GAPS IDENTIFIED")
    gaps = framework.identify_deployment_gaps()
    for gap_name, gap_details in gaps.items():
        priority = gap_details['priority']
        print(f"\n{gap_name.upper()} [{priority}]")
        print(f"  Gap: {gap_details['gap']}")
        print(f"  Issue: {gap_details['issue']}")
        print(f"  Impact: {gap_details['impact']}")
        print(f"  Solution: {gap_details['solution']}")
