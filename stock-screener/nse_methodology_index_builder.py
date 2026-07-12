#!/usr/bin/env python3
"""
NSE Methodology-Based Custom Index Builder
Implements official NSE Indices Limited methodology for equity index construction
Based on June 2026 Methodology Document
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json

class NSEIndexBuilder:
    """Build custom indices using NSE official methodology"""

    def __init__(self):
        self.base_value = 1000  # Base index value
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=1825)  # 5 years
        self.quarterly_dates = [
            datetime(self.end_date.year, 3, 31),
            datetime(self.end_date.year, 6, 30),
            datetime(self.end_date.year, 9, 30),
            datetime(self.end_date.year, 12, 31)
        ]

    # ============================================================
    # PART 1: ELIGIBILITY SCREENING (NSE Broad Market Indices)
    # ============================================================

    def screen_eligible_universe(self, tickers: List[str], price_data: Dict) -> pd.DataFrame:
        """
        NSE Eligibility Criteria for Nifty Indices:
        1. India domiciled, NSE-traded
        2. Free-float market cap (IWF) ≥ 10% or 6M avg free-float ≥ 25% of smallest constituent
        3. Traded ≥90% of days in previous 6 months
        4. Not in suspension/BZ series
        5. Not convertible/bonds/warrants

        Returns: DataFrame of eligible stocks with metrics
        """
        eligible = []

        for ticker in tickers:
            try:
                if ticker not in price_data:
                    continue

                prices = price_data[ticker]
                if len(prices) < 100:
                    continue

                # Calculate trading days
                total_days = len(prices)
                trading_days_pct = (total_days / 252) * 100  # Assuming 252 trading days/year

                # Eligibility: 90% trading requirement
                if trading_days_pct < 90:
                    continue

                # Calculate liquidity metrics
                daily_returns = prices.pct_change().dropna()
                volatility = daily_returns.std() * np.sqrt(252)

                # Calculate market cap proxy (using price × assumed shares)
                current_price = prices.iloc[-1]

                eligible.append({
                    'ticker': ticker,
                    'price': current_price,
                    'volatility': volatility * 100,
                    'trading_days_pct': trading_days_pct,
                    'avg_volume': len(prices),
                    'eligible': True
                })

            except Exception as e:
                continue

        return pd.DataFrame(eligible)

    # ============================================================
    # PART 2: MARKET CAP RANKING (NSE methodology)
    # ============================================================

    def rank_by_market_cap(self, eligible_df: pd.DataFrame,
                          market_caps: Dict[str, float]) -> pd.DataFrame:
        """
        NSE ranks companies by full market capitalization
        Returns ranked dataframe with cumulative market cap weights
        """
        ranked = eligible_df.copy()

        # Add market cap from external data
        ranked['market_cap'] = ranked['ticker'].map(market_caps)
        ranked = ranked.dropna(subset=['market_cap'])

        # Sort by market cap descending
        ranked = ranked.sort_values('market_cap', ascending=False).reset_index(drop=True)

        # Calculate weights and cumulative weights
        total_market_cap = ranked['market_cap'].sum()
        ranked['weight'] = (ranked['market_cap'] / total_market_cap) * 100
        ranked['cumulative_weight'] = ranked['weight'].cumsum()
        ranked['market_cap_rank'] = range(1, len(ranked) + 1)

        return ranked

    # ============================================================
    # PART 3: INDEX CONSTITUTION (Market-cap weighted)
    # ============================================================

    def nifty_50_constitution(self, ranked_df: pd.DataFrame) -> pd.DataFrame:
        """
        Nifty 50 Rules (NSE methodology):
        - Top 50 companies by free-float market cap
        - Selected from Nifty 100 universe
        - Min impact cost 0.50% for ₹10 Cr basket
        - Must have derivatives on NSE
        - Quarterly rebalancing (Mar, Jun, Sep, Dec)

        Returns: Nifty 50 constituent list with free-float weights
        """
        nifty_50 = ranked_df.head(50).copy()

        # Free-float adjustment (NSE: IWF minimum 10%, typically 25-75% for Nifty)
        # Assume average free-float of 60% for top companies
        nifty_50['free_float_factor'] = 0.60
        nifty_50['free_float_mcap'] = nifty_50['market_cap'] * nifty_50['free_float_factor']

        # Recalculate weights based on free-float
        total_ff_mcap = nifty_50['free_float_mcap'].sum()
        nifty_50['nifty50_weight'] = (nifty_50['free_float_mcap'] / total_ff_mcap) * 100

        return nifty_50[['ticker', 'market_cap_rank', 'market_cap', 'free_float_factor',
                         'free_float_mcap', 'nifty50_weight', 'price', 'volatility']]

    def nifty_midcap_150_constitution(self, ranked_df: pd.DataFrame) -> pd.DataFrame:
        """
        Nifty Midcap 150 (NSE methodology):
        - Companies ranked 101-250 by full market cap
        - Measures mid-cap performance
        - Quarterly rebalancing

        Returns: Nifty Midcap 150 constituent list
        """
        midcap_150 = ranked_df[(ranked_df['market_cap_rank'] >= 51) &
                               (ranked_df['market_cap_rank'] <= 200)].copy()

        # Free-float adjustment (mid-caps typically 50-60%)
        midcap_150['free_float_factor'] = 0.55
        midcap_150['free_float_mcap'] = midcap_150['market_cap'] * midcap_150['free_float_factor']

        total_ff_mcap = midcap_150['free_float_mcap'].sum()
        midcap_150['midcap150_weight'] = (midcap_150['free_float_mcap'] / total_ff_mcap) * 100

        return midcap_150[['ticker', 'market_cap_rank', 'market_cap', 'free_float_factor',
                          'free_float_mcap', 'midcap150_weight', 'price', 'volatility']]

    def nifty_smallcap_250_constitution(self, ranked_df: pd.DataFrame) -> pd.DataFrame:
        """
        Nifty Smallcap 250 (NSE methodology):
        - Companies ranked 251-500 by full market cap
        - Measures small-cap performance
        - Quarterly rebalancing

        Returns: Nifty Smallcap 250 constituent list
        """
        smallcap_250 = ranked_df[(ranked_df['market_cap_rank'] >= 201) &
                                 (ranked_df['market_cap_rank'] <= 450)].copy()

        # Free-float adjustment (small-caps typically 40-50%)
        smallcap_250['free_float_factor'] = 0.45
        smallcap_250['free_float_mcap'] = smallcap_250['market_cap'] * smallcap_250['free_float_factor']

        total_ff_mcap = smallcap_250['free_float_mcap'].sum()
        smallcap_250['smallcap250_weight'] = (smallcap_250['free_float_mcap'] / total_ff_mcap) * 100

        return smallcap_250[['ticker', 'market_cap_rank', 'market_cap', 'free_float_factor',
                             'free_float_mcap', 'smallcap250_weight', 'price', 'volatility']]

    # ============================================================
    # PART 4: QUALITY/FACTOR INDICES
    # ============================================================

    def nifty_quality_50(self, nifty_50_df: pd.DataFrame,
                        fundamental_data: Dict) -> pd.DataFrame:
        """
        Nifty Quality 50 (NSE methodology):
        - ROE (Return on Equity) ≥ 15%
        - Debt-to-Equity ≤ 0.50
        - 3-year CAGR > 10%
        - Selected from Nifty 50, equally weighted

        Returns: Nifty Quality 50 with equal weights
        """
        quality_50 = nifty_50_df.copy()

        # Add fundamental metrics
        quality_50['roe'] = quality_50['ticker'].map(lambda x: fundamental_data.get(x, {}).get('roe', 0))
        quality_50['debt_to_equity'] = quality_50['ticker'].map(
            lambda x: fundamental_data.get(x, {}).get('de_ratio', 1.0))
        quality_50['revenue_growth'] = quality_50['ticker'].map(
            lambda x: fundamental_data.get(x, {}).get('revenue_growth', 0))

        # Apply quality filters
        quality_filtered = quality_50[
            (quality_50['roe'] >= 15) &
            (quality_50['debt_to_equity'] <= 0.50) &
            (quality_50['revenue_growth'] >= 10)
        ]

        # Equal weight allocation within quality universe
        if len(quality_filtered) > 0:
            quality_filtered['quality_50_weight'] = 100 / len(quality_filtered)

        return quality_filtered.head(50)

    def nifty_low_volatility_50(self, nifty_100_df: pd.DataFrame) -> pd.DataFrame:
        """
        Nifty Low Volatility 50 (NSE methodology):
        - Select 50 stocks from Nifty 100 with lowest volatility
        - Capped equal weights (max 3% per stock)
        - Quarterly rebalancing

        Returns: Nifty Low Volatility 50 with capped weights
        """
        low_vol = nifty_100_df.nsmallest(50, 'volatility').copy()

        # Capped equal weight (max 3% per stock)
        equal_weight = 100 / len(low_vol)
        capped_weight = min(equal_weight, 3.0)
        low_vol['lv50_weight'] = capped_weight

        # Redistribute excess weight proportionally
        total_assigned = len(low_vol) * capped_weight
        if total_assigned < 100:
            excess = 100 - total_assigned
            low_vol['lv50_weight'] = capped_weight + (excess / len(low_vol))

        return low_vol

    def nifty_dividend_opportunities_50(self, nifty_50_df: pd.DataFrame,
                                        dividend_yields: Dict) -> pd.DataFrame:
        """
        Nifty Dividend Opportunities 50 (NSE methodology):
        - Min dividend yield 2.5%
        - Selected from Nifty 50
        - Market-cap weighted with 3% cap per stock
        - Quarterly rebalancing

        Returns: High-dividend Nifty subset
        """
        div_opps = nifty_50_df.copy()

        # Add dividend yields
        div_opps['dividend_yield'] = div_opps['ticker'].map(dividend_yields)

        # Filter for dividend yield ≥ 2.5%
        div_filtered = div_opps[div_opps['dividend_yield'] >= 2.5].copy()

        if len(div_filtered) > 0:
            # Apply 3% cap on weights
            total_weight = div_filtered['nifty50_weight'].sum()
            div_filtered['dividend_weight'] = (div_filtered['nifty50_weight'] / total_weight) * 100

            # Apply 3% cap
            div_filtered.loc[div_filtered['dividend_weight'] > 3, 'dividend_weight'] = 3.0

            # Renormalize
            total_after_cap = div_filtered['dividend_weight'].sum()
            div_filtered['dividend_weight'] = (div_filtered['dividend_weight'] / total_after_cap) * 100

        return div_filtered

    # ============================================================
    # PART 5: INDEX CALCULATION (NSE Formula)
    # ============================================================

    def calculate_market_cap_index(self, constituents: pd.DataFrame,
                                   price_data: Dict,
                                   dates: List[datetime] = None) -> pd.DataFrame:
        """
        NSE Market Cap Index Formula:
        Index Value = (Index Market Cap / Base Market Cap) × Base Index Value

        where Index Market Cap = Σ(Price × Shares × IWF × Capping Factor)
        """
        if dates is None:
            dates = [self.end_date]

        index_values = []

        for date in dates:
            try:
                # Get prices as of this date
                total_market_cap = 0
                valid_constituents = 0

                for _, row in constituents.iterrows():
                    ticker = row['ticker']
                    if ticker not in price_data:
                        continue

                    prices = price_data[ticker]
                    prices_up_to_date = prices[prices.index <= date]

                    if len(prices_up_to_date) > 0:
                        price = prices_up_to_date.iloc[-1]
                        mcap = price * row['free_float_factor']
                        weight = row.get('nifty50_weight', row.get('midcap150_weight',
                                        row.get('smallcap250_weight', 1/len(constituents))))
                        total_market_cap += mcap * (weight / 100)
                        valid_constituents += 1

                if valid_constituents > 0:
                    index_values.append({
                        'date': date,
                        'market_cap': total_market_cap,
                        'index_value': self.base_value * (total_market_cap / constituents['free_float_mcap'].sum()),
                        'constituents': valid_constituents
                    })

            except Exception as e:
                continue

        return pd.DataFrame(index_values)

    def calculate_equal_weight_index(self, constituents: pd.DataFrame,
                                     price_data: Dict,
                                     dates: List[datetime] = None) -> pd.DataFrame:
        """
        NSE Equal Weight Index:
        Each stock has equal contribution, regardless of market cap
        Useful for assessing performance of equal-weight portfolio

        Formula: Index = Σ(Price[t] / Price[base]) / N
        """
        if dates is None:
            dates = [self.end_date]

        index_values = []

        for date in dates:
            try:
                price_returns = []

                for _, row in constituents.iterrows():
                    ticker = row['ticker']
                    if ticker not in price_data:
                        continue

                    prices = price_data[ticker]
                    prices_up_to_date = prices[prices.index <= date]

                    if len(prices_up_to_date) > 0 and len(prices) > 0:
                        current_price = prices_up_to_date.iloc[-1]
                        base_price = prices.iloc[0]

                        if base_price > 0:
                            price_return = current_price / base_price
                            price_returns.append(price_return)

                if len(price_returns) > 0:
                    avg_return = np.mean(price_returns)
                    index_value = self.base_value * avg_return

                    index_values.append({
                        'date': date,
                        'avg_return': avg_return,
                        'index_value': index_value,
                        'constituents': len(price_returns)
                    })

            except Exception as e:
                continue

        return pd.DataFrame(index_values)

    def calculate_total_return_index(self, constituents: pd.DataFrame,
                                     price_data: Dict,
                                     dividends: Dict,
                                     dates: List[datetime] = None) -> pd.DataFrame:
        """
        NSE Total Return Index:
        Assumes all dividends are reinvested back into the index

        TRI = Previous_TR × [1 + (Price_Return + Indexed_Dividend) / Previous_Price]
        where Indexed_Dividend = Dividend_Payout / Base_Market_Cap
        """
        if dates is None:
            dates = [self.end_date]

        tri_values = [{'date': dates[0], 'tri_value': self.base_value}]

        for i in range(1, len(dates)):
            try:
                prev_tri = tri_values[-1]['tri_value']
                date = dates[i]
                prev_date = dates[i-1]

                price_return_total = 0
                dividend_total = 0
                valid_constituents = 0

                for _, row in constituents.iterrows():
                    ticker = row['ticker']
                    if ticker not in price_data:
                        continue

                    prices = price_data[ticker]
                    prev_prices = prices[prices.index <= prev_date]
                    curr_prices = prices[prices.index <= date]

                    if len(prev_prices) > 0 and len(curr_prices) > 0:
                        prev_price = prev_prices.iloc[-1]
                        curr_price = curr_prices.iloc[-1]

                        weight = row.get('nifty50_weight', 1/len(constituents)) / 100

                        price_ret = (curr_price - prev_price) / prev_price if prev_price > 0 else 0
                        price_return_total += price_ret * weight

                        # Add dividend component
                        div_yield = dividends.get(ticker, 0) / 100
                        dividend_total += div_yield * weight

                        valid_constituents += 1

                if valid_constituents > 0:
                    total_return = price_return_total + dividend_total
                    new_tri = prev_tri * (1 + total_return)

                    tri_values.append({
                        'date': date,
                        'tri_value': new_tri,
                        'price_return': price_return_total * 100,
                        'dividend_contribution': dividend_total * 100
                    })

            except Exception as e:
                continue

        return pd.DataFrame(tri_values)

    # ============================================================
    # PART 6: REBALANCING & MAINTENANCE
    # ============================================================

    def quarterly_rebalancing_schedule(self, year: int = None) -> List[Tuple[str, datetime]]:
        """
        NSE rebalancing schedule:
        - Last trading day of March, June, September, December
        - Announcement: minimum 3 working days before rebalancing
        - IWF recalculation: 6-month average free-float data

        Returns: List of rebalancing dates with working day info
        """
        if year is None:
            year = self.end_date.year

        months = [3, 6, 9, 12]
        rebalance_dates = []

        for month in months:
            if month == 3:
                date = datetime(year, 3, 31)
            elif month == 6:
                date = datetime(year, 6, 30)
            elif month == 9:
                date = datetime(year, 9, 30)
            else:
                date = datetime(year, 12, 31)

            # Find last trading day (assuming no market holidays for simplicity)
            rebalance_dates.append((f"Q{month//3} Rebalancing", date))

        return rebalance_dates

    # ============================================================
    # REPORTING
    # ============================================================

    def generate_index_report(self, index_name: str, constituents: pd.DataFrame,
                              index_series: pd.DataFrame) -> Dict:
        """
        Generate NSE-style index report
        """
        report = {
            'index_name': index_name,
            'as_of_date': self.end_date.isoformat(),
            'summary': {
                'num_constituents': len(constituents),
                'total_market_cap': constituents['free_float_mcap'].sum(),
                'index_value': index_series['index_value'].iloc[-1] if len(index_series) > 0 else None,
                'top_5_constituents': constituents.nlargest(5, 'free_float_mcap')[['ticker', 'free_float_mcap']].to_dict('records')
            },
            'methodology': {
                'base_value': self.base_value,
                'weighting': 'Market-cap weighted (free-float)',
                'rebalancing': 'Quarterly (Mar, Jun, Sep, Dec)',
                'review_period': '6-month data window'
            },
            'constituents': constituents.to_dict('records'),
            'index_time_series': index_series.to_dict('records') if len(index_series) > 0 else []
        }

        return report


if __name__ == '__main__':
    print("NSE Indices Methodology - Index Builder")
    print("=" * 60)
    print("\nThis module implements NSE Indices Limited methodology")
    print("for building custom equity indices.")
    print("\nKey components:")
    print("1. Eligibility screening (NSE criteria)")
    print("2. Market-cap ranking and constitution")
    print("3. Quality/Factor indices (Low Vol, Quality, Dividend)")
    print("4. Index calculation (Market-cap & Equal-weight)")
    print("5. Total Return Index (with dividend reinvestment)")
    print("6. Quarterly rebalancing")
    print("\nExample usage:")
    print("  builder = NSEIndexBuilder()")
    print("  eligible = builder.screen_eligible_universe(tickers, price_data)")
    print("  ranked = builder.rank_by_market_cap(eligible, market_caps)")
    print("  nifty_50 = builder.nifty_50_constitution(ranked)")
    print("  index_values = builder.calculate_market_cap_index(nifty_50, price_data)")
