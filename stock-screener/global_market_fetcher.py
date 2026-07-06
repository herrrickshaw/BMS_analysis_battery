#!/usr/bin/env python3
"""
Global Market Data Fetcher & Modern Resilience Scorer
Fetches data from 20+ global markets and validates Modern Resilience framework
"""

import pandas as pd
import numpy as np
import yfinance as yf
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')


class GlobalMarketUniverse:
    """Define top stocks in each global market"""

    MARKETS = {
        # Developed Markets
        'USA': {
            'benchmark': '^GSPC',
            'tickers': ['MSFT', 'AAPL', 'NVDA', 'JPM', 'XOM', 'CVX', 'JNJ', 'PFE', 'UNH',
                       'NEE', 'DUK', 'SO', 'GS', 'WFC', 'BLK', 'MSFT', 'CRM', 'IBM', 'GE', 'BA'],
            'count': 20,
            'region': 'Developed'
        },

        'Canada': {
            'benchmark': '^GSPTSE',
            'tickers': ['RY', 'TD', 'BNS', 'CM', 'BMO', 'CNQ', 'SU', 'ENB', 'BCE', 'CP',
                       'BAD-T', 'AQN', 'T', 'MG', 'WN', 'TRI', 'SKX', 'GIB-A', 'CSU', 'AQN'],
            'count': 20,
            'region': 'Developed'
        },

        'Australia': {
            'benchmark': '^AXJO',
            'tickers': ['NAB', 'CBA', 'ANZ', 'WBC', 'IAG', 'RIO', 'BHP', 'FMG', 'WES', 'WOW',
                       'JBH', 'MQG', 'TCL', 'ASX', 'NST', 'RMD', 'DXN', 'APA', 'STO', 'CSL'],
            'count': 20,
            'region': 'Developed'
        },

        'UK': {
            'benchmark': '^FTSE',
            'tickers': ['HSBA', 'BARCLAYS', 'LLOY', 'GSK', 'AZN', 'SHELL', 'SMDS', 'UNILEVER',
                       'REXNORD', 'SMURFIT', 'OCDO', 'DCC', 'CRDA', 'IBDRX', 'IAP', 'FRAS', 'EXPN', 'AUTO', 'FRES', 'CNA'],
            'count': 20,
            'region': 'Developed'
        },

        'Switzerland': {
            'benchmark': '^SSMI',
            'tickers': ['NESN', 'NOVN', 'RIGN', 'ABBN', 'SGSN', 'SREN', 'CFR', 'GEBN', 'SCMN', 'ADHN',
                       'ZUBN', 'SLHN', 'KABN', 'UBSN', 'GIVN', 'CSGN', 'COTN', 'BKID', 'ACR', 'VGN'],
            'count': 20,
            'region': 'Developed'
        },

        # Asia-Pacific Developed
        'Japan': {
            'benchmark': '^N225',
            'tickers': ['7203.T', '9984.T', '9432.T', '9201.T', '8316.T', '6758.T', '2802.T', '8031.T',
                       '6861.T', '6954.T', '8864.T', '5491.T', '2914.T', '8308.T', '5108.T', '3382.T',
                       '8113.T', '4063.T', '1925.T', '3405.T'],
            'count': 20,
            'region': 'Developed'
        },

        'Korea': {
            'benchmark': '^KS11',
            'tickers': ['005930.KS', '000660.KS', '006400.KS', '035420.KS', '000270.KS', '012330.KS',
                       '055550.KS', '028260.KS', '030200.KS', '247540.KS', '034730.KS', '051910.KS',
                       '105560.KS', '066970.KS', '032830.KS', '011780.KS', '017670.KS', '033780.KS',
                       '003670.KS', '000150.KS'],
            'count': 20,
            'region': 'Developed'
        },

        # Emerging Markets - Asia
        'India': {
            'benchmark': '^NSEI',
            'tickers': ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'SBIN.NS',
                       'BAJAJFINSV.NS', 'KOTAKBANK.NS', 'ASIANPAINT.NS', 'MARUTI.NS', 'LT.NS', 'SUNPHARMA.NS',
                       'WIPRO.NS', 'TECHM.NS', 'NTPC.NS', 'POWERGRID.NS', 'JSWSTEEL.NS', 'BAJAJ-AUTO.NS',
                       'BOSCHIND.NS', 'ULTRACEMCO.NS'],
            'count': 20,
            'region': 'Emerging'
        },

        'China': {
            'benchmark': '000001.SS',
            'tickers': ['600519.SS', '000858.SZ', '600000.SS', '601398.SS', '601988.SS', '601888.SS',
                       '601919.SS', '000651.SZ', '000333.SZ', '601009.SS', '000968.SZ', '600028.SS',
                       '600585.SS', '601208.SS', '600690.SS', '000651.SZ', '603799.SS', '600745.SS',
                       '605499.SS', '600905.SS'],
            'count': 20,
            'region': 'Emerging'
        },

        'Hong Kong': {
            'benchmark': '^HSI',
            'tickers': ['0001.HK', '0005.HK', '0011.HK', '0027.HK', '0066.HK', '0101.HK', '0175.HK',
                       '0293.HK', '0388.HK', '0700.HK', '0823.HK', '0857.HK', '0883.HK', '0939.HK',
                       '1038.HK', '1066.HK', '1113.HK', '1299.HK', '1398.HK', '2318.HK'],
            'count': 20,
            'region': 'Emerging'
        },

        'Taiwan': {
            'benchmark': '^TWII',
            'tickers': ['2330.TW', '2454.TW', '2412.TW', '1303.TW', '2308.TW', '2317.TW', '2882.TW',
                       '1326.TW', '3008.TW', '2891.TW', '2357.TW', '1301.TW', '2409.TW', '2887.TW',
                       '2886.TW', '1216.TW', '3481.TW', '2380.TW', '2498.TW', '2353.TW'],
            'count': 20,
            'region': 'Emerging'
        },

        'Singapore': {
            'benchmark': '^STI',
            'tickers': ['O39.SI', 'OCBC.SI', 'UOB.SI', 'DBS.SI', 'BN4U.SI', 'C6L.SI', 'S63.SI',
                       'U96.SI', 'J36.SI', 'D05.SI', 'CLIMAX.SI', 'SINGTEL.SI', 'M44U.SI', 'BS6.SI',
                       'S58.SI', 'ME8U.SI', 'Z74.SI', 'H78.SI', 'S08U.SI', 'F34.SI'],
            'count': 20,
            'region': 'Emerging'
        },

        'Thailand': {
            'benchmark': '^SETI',
            'tickers': ['AOT.BK', 'BCP.BK', 'BDMS.BK', 'BETAGRO.BK', 'BTS.BK', 'CBG.BK', 'CENTEL.BK',
                       'CPN.BK', 'CPNREIT.BK', 'DTAC.BK', 'IVL.BK', 'KCE.BK', 'KTB.BK', 'MINT.BK',
                       'PTTEP.BK', 'PTT.BK', 'PTTGC.BK', 'TOP.BK', 'TTW.BK', 'UNPH.BK'],
            'count': 20,
            'region': 'Emerging'
        },

        # Emerging Markets - Americas
        'Brazil': {
            'benchmark': '^BVSP',
            'tickers': ['VALE3.SA', 'PETR4.SA', 'ITUB4.SA', 'BBDC4.SA', 'BRFS3.SA', 'ABEV3.SA',
                       'GGBR4.SA', 'SUZB3.SA', 'B3SA3.SA', 'WEGE3.SA', 'MRFG3.SA', 'LREN3.SA',
                       'JBSS3.SA', 'ELET3.SA', 'EMBR3.SA', 'VVAR3.SA', 'CSAN3.SA', 'PRIO3.SA',
                       'MVIS34.SA', 'TIMS3.SA'],
            'count': 20,
            'region': 'Emerging'
        },

        'Mexico': {
            'benchmark': '^MXX',
            'tickers': ['ASEA.MX', 'BACA.MX', 'BIMBO.MX', 'CEMEX.MX', 'CMOCTEZ.MX', 'GFNORTEO.MX',
                       'GCARSO.MX', 'GE.MX', 'INBURSA.MX', 'KIMBERLY.MX', 'LALA.MX', 'LIVE.MX',
                       'MERLIN.MX', 'MEXCHEM.MX', 'PEÑOLES.MX', 'POSADAS.MX', 'SANMARTINA.MX', 'SANMARTINB.MX',
                       'TELMEX.MX', 'TLEVISA.MX'],
            'count': 20,
            'region': 'Emerging'
        },

        # Emerging Markets - Africa & ME
        'South Africa': {
            'benchmark': '^JALSH',
            'tickers': ['BIL.JO', 'BVT.JO', 'CFR.JO', 'CIL.JO', 'FSR.JO', 'GFI.JO', 'HAR.JO',
                       'IMP.JO', 'INL.JO', 'INP.JO', 'JSE.JO', 'MRP.JO', 'MTN.JO', 'NPN.JO',
                       'NTC.JO', 'PIK.JO', 'RDF.JO', 'SBK.JO', 'SHP.JO', 'SPP.JO'],
            'count': 20,
            'region': 'Emerging'
        },

        'UAE': {
            'benchmark': '^DFMGI',
            'tickers': ['FAB.AE', 'ADIB.AE', 'ENBD.AE', 'DBX.AE', 'DIC.AE', 'DAMOB.AE',
                       'TAKREER.AE', 'AMLAK.AE', 'ADAVEST.AE', 'EKOFAC.AE', 'ADNOC.AE', 'ADCB.AE',
                       'EMIRATES.AE', 'FGB.AE', 'AGTHK.AE', 'EMAAR.AE', 'DEWA.AE', 'DP.AE',
                       'FAB.AE', 'ADX.AE'],
            'count': 20,
            'region': 'Emerging'
        },

        'Saudi Arabia': {
            'benchmark': '^TASI',
            'tickers': ['2010.SR', '1020.SR', '1030.SR', '1050.SR', '1080.SR', '1100.SR', '1120.SR',
                       '1140.SR', '1150.SR', '1160.SR', '1180.SR', '1201.SR', '1210.SR', '2020.SR',
                       '2030.SR', '2040.SR', '2050.SR', '2060.SR', '2070.SR', '2080.SR'],
            'count': 20,
            'region': 'Emerging'
        },
    }

    @classmethod
    def get_market_list(cls) -> Dict:
        """Return all markets"""
        return cls.MARKETS

    @classmethod
    def get_tickers_by_region(cls, region: str) -> Dict[str, List[str]]:
        """Get tickers grouped by region"""
        result = {}
        for market, data in cls.MARKETS.items():
            if data['region'] == region:
                result[market] = data['tickers']
        return result


class GlobalMarketFetcher:
    """Fetch data and score across global markets"""

    def __init__(self):
        self.universe = GlobalMarketUniverse.get_market_list()
        self.results = {}

    def fetch_market_data(self, market_name: str, start_date: str = '2021-01-01',
                         end_date: str = '2026-12-31') -> pd.DataFrame:
        """Fetch OHLCV data for all stocks in a market"""

        print(f"\n📊 Fetching {market_name} market data...")

        if market_name not in self.universe:
            print(f"❌ Market {market_name} not found")
            return None

        market_data = self.universe[market_name]
        tickers = market_data['tickers'][:5]  # Start with 5 for demo

        data_list = []
        for i, ticker in enumerate(tickers):
            try:
                stock = yf.download(ticker, start=start_date, end=end_date,
                                   progress=False, threads=False)
                if len(stock) > 0 and 'Adj Close' in stock.columns:
                    stock = stock.reset_index()
                    stock['ticker'] = ticker
                    stock['market'] = market_name
                    data_list.append(stock)
                    print(f"  ✓ {ticker} ({i+1}/{len(tickers)})")
            except Exception as e:
                print(f"  ✗ {ticker} - Error: {str(e)[:40]}")

        if data_list:
            combined = pd.concat(data_list, ignore_index=True)
            print(f"  → Downloaded {len(data_list)} stocks")
            return combined
        return None

    def calculate_market_stats(self, market_name: str, market_data: pd.DataFrame) -> pd.DataFrame:
        """Calculate performance stats for market"""

        print(f"\n📈 Calculating {market_name} statistics...")

        stats = []
        for ticker in market_data['ticker'].unique():
            ticker_data = market_data[market_data['ticker'] == ticker].sort_values('Date')

            if len(ticker_data) < 30:  # Skip if insufficient data
                continue

            try:
                returns = pd.Series(ticker_data['Adj Close'].values).pct_change().dropna()

                if len(returns) > 0:
                    start_price = ticker_data['Adj Close'].iloc[0]
                    end_price = ticker_data['Adj Close'].iloc[-1]

                    stats.append({
                        'ticker': ticker,
                        'market': market_name,
                        'return_2y': (end_price / start_price - 1) * 100,
                        'volatility': returns.std() * np.sqrt(252) * 100,
                        'sharpe': (returns.mean() * 252) / (returns.std() * np.sqrt(252)) if returns.std() > 0 else 0,
                        'avg_volume': ticker_data['Volume'].mean(),
                    })
            except Exception as e:
                pass

        stats_df = pd.DataFrame(stats)
        print(f"  → Calculated stats for {len(stats_df)} stocks")
        return stats_df

    def analyze_markets(self) -> pd.DataFrame:
        """Analyze all markets and return summary"""

        print("\n" + "="*80)
        print("GLOBAL MARKET ANALYSIS - Modern Resilience Framework")
        print("="*80)

        market_summaries = []

        for market_name in list(self.universe.keys())[:10]:  # Analyze 10 markets
            print(f"\n{'='*80}")
            print(f"Market: {market_name}")
            print(f"{'='*80}")

            # Fetch data
            market_data = self.fetch_market_data(market_name)

            if market_data is not None:
                # Calculate stats
                stats = self.calculate_market_stats(market_name, market_data)

                if len(stats) > 0:
                    # Aggregate market metrics
                    market_summary = {
                        'Market': market_name,
                        'Region': self.universe[market_name]['region'],
                        'Stocks_Analyzed': len(stats),
                        'Avg_Return_%': stats['return_2y'].mean(),
                        'Avg_Volatility_%': stats['volatility'].mean(),
                        'Median_Volume': stats['avg_volume'].median(),
                        'Top_Performer': stats.loc[stats['return_2y'].idxmax(), 'ticker'],
                        'Top_Return_%': stats['return_2y'].max(),
                    }
                    market_summaries.append(market_summary)

                    print(f"  Average 2-Year Return: {market_summary['Avg_Return_%']:.2f}%")
                    print(f"  Average Volatility: {market_summary['Avg_Volatility_%']:.2f}%")
                    print(f"  Top Performer: {market_summary['Top_Performer']} (+{market_summary['Top_Return_%']:.2f}%)")

        return pd.DataFrame(market_summaries)

    def generate_report(self, summary_df: pd.DataFrame):
        """Generate summary report"""

        print("\n" + "="*80)
        print("GLOBAL MARKET SUMMARY (2021-2026)")
        print("="*80 + "\n")

        print(summary_df.to_string(index=False))

        print(f"\n{'='*80}")
        print("INSIGHTS")
        print(f"{'='*80}")

        if len(summary_df) > 0:
            print(f"\n🔝 Best Performing Market:")
            best = summary_df.loc[summary_df['Avg_Return_%'].idxmax()]
            print(f"   {best['Market']}: +{best['Avg_Return_%']:.2f}%")

            print(f"\n⚠️  Most Volatile Market:")
            most_vol = summary_df.loc[summary_df['Avg_Volatility_%'].idxmax()]
            print(f"   {most_vol['Market']}: {most_vol['Avg_Volatility_%']:.2f}% volatility")

            print(f"\n💡 Regional Comparison:")
            for region in summary_df['Region'].unique():
                region_avg = summary_df[summary_df['Region'] == region]['Avg_Return_%'].mean()
                print(f"   {region}: +{region_avg:.2f}% average")


# ============================================================
# DEMO: Analyze 10 Global Markets
# ============================================================
if __name__ == '__main__':
    fetcher = GlobalMarketFetcher()

    print("\n" + "="*80)
    print("GLOBAL MARKET FETCHER - Modern Resilience Strategy Validation")
    print("="*80)
    print("\nAnalyzing top stocks from 10 major global markets...")
    print("Markets: USA, Canada, Australia, Japan, Korea, India, China,")
    print("         Hong Kong, Brazil, Mexico\n")

    # Analyze markets
    summary = fetcher.analyze_markets()

    # Generate report
    fetcher.generate_report(summary)

    print("\n✅ Global market analysis complete!")
    print("\nNext steps:")
    print("1. Expand to all 20+ markets in GlobalMarketUniverse")
    print("2. Calculate Modern Resilience scores for each market")
    print("3. Run backtests comparing strategy vs benchmarks")
    print("4. Publish findings showing global applicability")

