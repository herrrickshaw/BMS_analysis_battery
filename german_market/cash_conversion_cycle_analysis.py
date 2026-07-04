#!/usr/bin/env python3
"""
Cash Conversion Cycle (CCC) Analysis
German Stock Market - Working Capital Efficiency
"""

import pandas as pd
import json
from datetime import datetime
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CashConversionCycleAnalyzer:
    """Analyze working capital efficiency via CCC"""
    
    def __init__(self):
        self.results_dir = Path.home() / "german_market_analysis"
        self.results_dir.mkdir(exist_ok=True)
        self.ccc_results = []
    
    def generate_sample_ccc_data(self):
        """Generate realistic CCC data for German stocks"""
        # Real-world CCC estimates for German companies
        stocks_ccc = [
            {
                'symbol': 'ENR.DE',
                'name': 'Siemens Energy',
                'sector': 'Industrials',
                'dio': 45,  # Days Inventory Outstanding
                'dso': 38,  # Days Sales Outstanding
                'dpo': 60,  # Days Payable Outstanding
                'revenue_bn': 35.5,
                'growth_rate': 12.5
            },
            {
                'symbol': 'SIE.DE',
                'name': 'Siemens AG',
                'sector': 'Industrials',
                'dio': 52,
                'dso': 42,
                'dpo': 65,
                'revenue_bn': 72.8,
                'growth_rate': 8.3
            },
            {
                'symbol': 'SAP.DE',
                'name': 'SAP SE',
                'sector': 'Technology',
                'dio': 12,
                'dso': 35,
                'dpo': 45,
                'revenue_bn': 35.2,
                'growth_rate': 10.5
            },
            {
                'symbol': 'VOW3.DE',
                'name': 'Volkswagen AG',
                'sector': 'Automotive',
                'dio': 68,
                'dso': 32,
                'dpo': 55,
                'revenue_bn': 296.0,
                'growth_rate': 5.2
            },
            {
                'symbol': 'MUV2.DE',
                'name': 'Munich Re',
                'sector': 'Financials',
                'dio': 0,  # Insurance company
                'dso': 45,
                'dpo': 30,
                'revenue_bn': 65.0,
                'growth_rate': 7.8
            },
            {
                'symbol': 'BMW.DE',
                'name': 'BMW AG',
                'sector': 'Automotive',
                'dio': 72,
                'dso': 28,
                'dpo': 60,
                'revenue_bn': 142.6,
                'growth_rate': 6.4
            },
            {
                'symbol': 'DAI.DE',
                'name': 'Daimler AG',
                'sector': 'Automotive',
                'dio': 75,
                'dso': 35,
                'dpo': 65,
                'revenue_bn': 176.0,
                'growth_rate': 5.8
            },
            {
                'symbol': 'ADS.DE',
                'name': 'Adidas AG',
                'sector': 'Consumer',
                'dio': 95,
                'dso': 42,
                'dpo': 55,
                'revenue_bn': 21.2,
                'growth_rate': 9.1
            },
            {
                'symbol': 'BAS.DE',
                'name': 'BASF SE',
                'sector': 'Materials',
                'dio': 58,
                'dso': 48,
                'dpo': 70,
                'revenue_bn': 76.5,
                'growth_rate': 4.2
            },
            {
                'symbol': 'BAYN.DE',
                'name': 'Bayer AG',
                'sector': 'Pharma',
                'dio': 42,
                'dso': 55,
                'dpo': 50,
                'revenue_bn': 46.3,
                'growth_rate': 3.5
            },
            {
                'symbol': 'RWE.DE',
                'name': 'RWE AG',
                'sector': 'Energy',
                'dio': 38,
                'dso': 62,
                'dpo': 68,
                'revenue_bn': 50.0,
                'growth_rate': 11.2
            },
            {
                'symbol': 'FRE.DE',
                'name': 'Fresenius',
                'sector': 'Healthcare',
                'dio': 35,
                'dso': 58,
                'dpo': 52,
                'revenue_bn': 37.1,
                'growth_rate': 6.8
            },
            {
                'symbol': 'HEI.DE',
                'name': 'Heidelberg',
                'sector': 'Materials',
                'dio': 62,
                'dso': 45,
                'dpo': 62,
                'revenue_bn': 16.5,
                'growth_rate': 8.9
            },
            {
                'symbol': 'HEN3.DE',
                'name': 'Henkel',
                'sector': 'Consumer',
                'dio': 88,
                'dso': 52,
                'dpo': 68,
                'revenue_bn': 22.0,
                'growth_rate': 5.3
            },
            {
                'symbol': 'IFX.DE',
                'name': 'Infineon',
                'sector': 'Technology',
                'dio': 48,
                'dso': 38,
                'dpo': 42,
                'revenue_bn': 14.4,
                'growth_rate': 14.2
            },
            {
                'symbol': 'DBX.DE',
                'name': 'Deutsche Börse',
                'sector': 'Financials',
                'dio': 5,  # Service company
                'dso': 28,
                'dpo': 35,
                'revenue_bn': 8.5,
                'growth_rate': 9.5
            },
            {
                'symbol': 'ALV.DE',
                'name': 'Allianz SE',
                'sector': 'Financials',
                'dio': 0,
                'dso': 50,
                'dpo': 40,
                'revenue_bn': 142.0,
                'growth_rate': 8.1
            },
        ]
        
        return stocks_ccc
    
    def analyze_ccc(self, stocks):
        """Calculate and analyze CCC for each stock"""
        logger.info(f"\n{'='*80}")
        logger.info("💰 CASH CONVERSION CYCLE (CCC) ANALYSIS")
        logger.info(f"{'='*80}\n")
        
        for stock in stocks:
            symbol = stock['symbol']
            dio = stock['dio']
            dso = stock['dso']
            dpo = stock['dpo']
            
            # CCC = DIO + DSO - DPO
            ccc = dio + dso - dpo
            
            # Working capital intensity
            wc_intensity = (dio + dso) / stock['revenue_bn'] if stock['revenue_bn'] > 0 else 0
            
            # Efficiency score (lower CCC is better)
            if ccc < 0:
                efficiency = "EXCELLENT"
                efficiency_score = 5
            elif ccc < 30:
                efficiency = "VERY GOOD"
                efficiency_score = 4
            elif ccc < 60:
                efficiency = "GOOD"
                efficiency_score = 3
            elif ccc < 90:
                efficiency = "FAIR"
                efficiency_score = 2
            else:
                efficiency = "POOR"
                efficiency_score = 1
            
            result = {
                'symbol': symbol,
                'name': stock['name'],
                'sector': stock['sector'],
                'dio': dio,
                'dso': dso,
                'dpo': dpo,
                'ccc': ccc,
                'efficiency': efficiency,
                'efficiency_score': efficiency_score,
                'wc_intensity': wc_intensity,
                'growth_rate': stock['growth_rate'],
                'revenue_bn': stock['revenue_bn']
            }
            
            self.ccc_results.append(result)
        
        # Sort by CCC (lower is better)
        self.ccc_results.sort(key=lambda x: x['ccc'])
        
        # Display results
        logger.info("📊 CCC RANKINGS (Lower is Better)\n")
        logger.info("Rank │ Symbol  │ Company                 │  CCC  │ DIO │ DSO │ DPO │ Efficiency")
        logger.info("─" * 95)
        
        for idx, result in enumerate(self.ccc_results, 1):
            status = "🟢" if result['ccc'] < 30 else "🟡" if result['ccc'] < 60 else "🔴"
            logger.info(
                f" {idx:2}  │ {result['symbol']:7} │ {result['name']:23} │ "
                f"{result['ccc']:5.0f} │ {result['dio']:3.0f} │ {result['dso']:3.0f} │ {result['dpo']:3.0f} │ "
                f"{status} {result['efficiency']}"
            )
        
        return self.ccc_results
    
    def generate_insights(self):
        """Generate working capital insights"""
        logger.info(f"\n{'='*80}")
        logger.info("🔍 WORKING CAPITAL INSIGHTS")
        logger.info(f"{'='*80}\n")
        
        excellent = [r for r in self.ccc_results if r['ccc'] < 0]
        very_good = [r for r in self.ccc_results if 0 <= r['ccc'] < 30]
        good = [r for r in self.ccc_results if 30 <= r['ccc'] < 60]
        poor = [r for r in self.ccc_results if r['ccc'] >= 90]
        
        logger.info(f"✅ Excellent (<0 CCC):      {len(excellent)} stocks")
        for r in excellent:
            logger.info(f"   • {r['symbol']:8} | CCC: {r['ccc']:5.0f} days | {r['name']}")
        
        logger.info(f"\n✅ Very Good (0-30 CCC):    {len(very_good)} stocks")
        for r in very_good:
            logger.info(f"   • {r['symbol']:8} | CCC: {r['ccc']:5.0f} days | {r['name']}")
        
        logger.info(f"\n✅ Good (30-60 CCC):        {len(good)} stocks")
        for r in good:
            logger.info(f"   • {r['symbol']:8} | CCC: {r['ccc']:5.0f} days | {r['name']}")
        
        logger.info(f"\n⚠️  Poor (>90 CCC):          {len(poor)} stocks")
        for r in poor:
            logger.info(f"   • {r['symbol']:8} | CCC: {r['ccc']:5.0f} days | {r['name']}")
    
    def analyze_by_sector(self):
        """Analyze CCC by sector"""
        logger.info(f"\n{'='*80}")
        logger.info("📊 CASH CONVERSION CYCLE BY SECTOR")
        logger.info(f"{'='*80}\n")
        
        sector_data = {}
        for result in self.ccc_results:
            sector = result['sector']
            if sector not in sector_data:
                sector_data[sector] = []
            sector_data[sector].append(result)
        
        # Calculate averages
        for sector, stocks in sorted(sector_data.items()):
            avg_ccc = sum(s['ccc'] for s in stocks) / len(stocks)
            avg_growth = sum(s['growth_rate'] for s in stocks) / len(stocks)
            
            logger.info(f"\n{sector}:")
            logger.info(f"  Avg CCC:      {avg_ccc:6.1f} days")
            logger.info(f"  Avg Growth:   {avg_growth:6.1f}%")
            logger.info(f"  Stocks:       {len(stocks)}")
            for stock in stocks:
                logger.info(f"    • {stock['symbol']:8} | CCC: {stock['ccc']:5.0f} | Growth: {stock['growth_rate']:5.1f}%")
    
    def analyze_growth_vs_efficiency(self):
        """Analyze growth vs working capital efficiency"""
        logger.info(f"\n{'='*80}")
        logger.info("📈 GROWTH vs EFFICIENCY MATRIX")
        logger.info(f"{'='*80}\n")
        
        logger.info("High Growth + Low CCC (Best):\n")
        high_growth_efficient = [r for r in self.ccc_results if r['growth_rate'] > 8 and r['ccc'] < 50]
        for r in high_growth_efficient:
            logger.info(f"  🚀 {r['symbol']:8} | Growth: {r['growth_rate']:5.1f}% | CCC: {r['ccc']:5.0f} | {r['name']}")
        
        logger.info(f"\nHigh Growth + High CCC (Working Capital Heavy):\n")
        high_growth_heavy = [r for r in self.ccc_results if r['growth_rate'] > 8 and r['ccc'] >= 60]
        for r in high_growth_heavy:
            logger.info(f"  ⚠️  {r['symbol']:8} | Growth: {r['growth_rate']:5.1f}% | CCC: {r['ccc']:5.0f} | {r['name']}")
        
        logger.info(f"\nLow Growth + Low CCC (Efficient Cash Generators):\n")
        low_growth_efficient = [r for r in self.ccc_results if r['growth_rate'] <= 8 and r['ccc'] < 50]
        for r in low_growth_efficient:
            logger.info(f"  💰 {r['symbol']:8} | Growth: {r['growth_rate']:5.1f}% | CCC: {r['ccc']:5.0f} | {r['name']}")
    
    def generate_report(self):
        """Generate comprehensive CCC report"""
        logger.info(f"\n{'='*80}")
        logger.info("📋 CASH CONVERSION CYCLE REPORT")
        logger.info(f"{'='*80}\n")
        
        # Summary stats
        avg_ccc = sum(r['ccc'] for r in self.ccc_results) / len(self.ccc_results)
        min_ccc = min(self.ccc_results, key=lambda x: x['ccc'])
        max_ccc = max(self.ccc_results, key=lambda x: x['ccc'])
        
        logger.info(f"Average CCC:        {avg_ccc:6.1f} days")
        logger.info(f"Best (Shortest):    {min_ccc['symbol']:8} | {min_ccc['ccc']:5.0f} days")
        logger.info(f"Worst (Longest):    {max_ccc['symbol']:8} | {max_ccc['ccc']:5.0f} days")
        
        # Export to JSON
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'avg_ccc': float(avg_ccc),
                'best_ccc': float(min_ccc['ccc']),
                'worst_ccc': float(max_ccc['ccc']),
                'total_stocks': len(self.ccc_results)
            },
            'stocks': self.ccc_results
        }
        
        report_path = self.results_dir / f"ccc_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"\n✅ Report saved: {report_path}\n")
        
        # Export to CSV
        df = pd.DataFrame(self.ccc_results)
        csv_path = self.results_dir / f"ccc_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(csv_path, index=False)
        logger.info(f"✅ CSV saved: {csv_path}\n")

# Main execution
print("🇩🇪 GERMAN STOCK MARKET - CASH CONVERSION CYCLE ANALYSIS")
print("=" * 80)
print()

analyzer = CashConversionCycleAnalyzer()

# Generate data
stocks = analyzer.generate_sample_ccc_data()

# Analyze
results = analyzer.analyze_ccc(stocks)

# Generate insights
analyzer.generate_insights()
analyzer.analyze_by_sector()
analyzer.analyze_growth_vs_efficiency()
analyzer.generate_report()

print("=" * 80)
print("✅ CASH CONVERSION CYCLE ANALYSIS COMPLETE")
print("=" * 80)
print()
print("Key Findings:")
print("  • Stocks with negative CCC are cash generators (best)")
print("  • Lower CCC = more efficient working capital management")
print("  • High growth + Low CCC = optimal combination")
print("  • Use CCC to identify capital-efficient growth stocks")
print()
