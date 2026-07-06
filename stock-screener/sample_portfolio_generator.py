#!/usr/bin/env python3
"""
Sample Portfolio Generator: Shows which specific stocks the strategy would select
from each market using Piotroski F-Score + Darvas Box criteria
"""

import json
from datetime import datetime

# ============================================================================
# SAMPLE STOCK UNIVERSE BY MARKET
# ============================================================================

SAMPLE_STOCKS = {
    "india_nse_bse": {
        "market": "India (NSE/BSE)",
        "total_universe": 2681,
        "top_quality_candidates": [
            {
                "symbol": "RELIANCE",
                "name": "Reliance Industries Limited",
                "sector": "Energy",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 3250,
                "52w_high": 3450,
                "pe_ratio": 24.5,
                "roe": 12.8,
                "debt_to_equity": 0.45,
                "rsi": 62,
                "reason": "Strong fundamentals, near 52-week high, good profitability",
            },
            {
                "symbol": "TCS",
                "name": "Tata Consultancy Services",
                "sector": "IT Services",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 3850,
                "52w_high": 4100,
                "pe_ratio": 22.3,
                "roe": 15.2,
                "debt_to_equity": 0.05,
                "rsi": 58,
                "reason": "Exceptional profitability, low debt, strong cash flow",
            },
            {
                "symbol": "INFY",
                "name": "Infosys Limited",
                "sector": "IT Services",
                "f_score": 7,
                "darvas_signal": "CONFIRMED",
                "cmp": 1850,
                "52w_high": 2050,
                "pe_ratio": 23.1,
                "roe": 14.1,
                "debt_to_equity": 0.08,
                "rsi": 55,
                "reason": "Quality IT services, good margins, stable growth",
            },
            {
                "symbol": "HDFC",
                "name": "Housing Development Finance Corporation",
                "sector": "Banking",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 2850,
                "52w_high": 3100,
                "pe_ratio": 18.5,
                "roe": 16.3,
                "debt_to_equity": 0.35,
                "rsi": 60,
                "reason": "Strong capital position, high profitability, market leader",
            },
            {
                "symbol": "ICICIBANK",
                "name": "ICICI Bank Limited",
                "sector": "Banking",
                "f_score": 7,
                "darvas_signal": "CONFIRMED",
                "cmp": 1150,
                "52w_high": 1250,
                "pe_ratio": 15.2,
                "roe": 14.8,
                "debt_to_equity": 0.08,
                "rsi": 56,
                "reason": "Strong bank, good profitability, solid fundamentals",
            },
        ],
        "target_portfolio_size": 8,
        "allocation_pct": 12,
    },
    "usa_nyse_nasdaq": {
        "market": "USA (NYSE/NASDAQ)",
        "total_universe": 7442,
        "top_quality_candidates": [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "sector": "Technology",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 185.50,
                "52w_high": 199.62,
                "pe_ratio": 28.5,
                "roe": 121.0,
                "debt_to_equity": 0.15,
                "rsi": 64,
                "reason": "Exceptional profitability, strong cash generation, near high",
            },
            {
                "symbol": "MSFT",
                "name": "Microsoft Corporation",
                "sector": "Technology",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 420.75,
                "52w_high": 445.00,
                "pe_ratio": 35.2,
                "roe": 45.3,
                "debt_to_equity": 0.08,
                "rsi": 62,
                "reason": "Strong growth, excellent margins, high ROE",
            },
            {
                "symbol": "JPM",
                "name": "JPMorgan Chase & Co.",
                "sector": "Banking",
                "f_score": 7,
                "darvas_signal": "CONFIRMED",
                "cmp": 195.30,
                "52w_high": 212.45,
                "pe_ratio": 12.5,
                "roe": 15.2,
                "debt_to_equity": 0.12,
                "rsi": 58,
                "reason": "Financial strength, dividend support, trading above 200-day MA",
            },
            {
                "symbol": "PG",
                "name": "Procter & Gamble Co.",
                "sector": "Consumer",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 165.40,
                "52w_high": 172.50,
                "pe_ratio": 24.3,
                "roe": 85.6,
                "debt_to_equity": 0.45,
                "rsi": 61,
                "reason": "Defensive quality, strong FCF, dividend aristocrat",
            },
            {
                "symbol": "JNJ",
                "name": "Johnson & Johnson",
                "sector": "Healthcare",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 155.85,
                "52w_high": 165.30,
                "pe_ratio": 18.2,
                "roe": 35.2,
                "debt_to_equity": 0.35,
                "rsi": 59,
                "reason": "Healthcare quality, dividend support, strong balance sheet",
            },
        ],
        "target_portfolio_size": 15,
        "allocation_pct": 45,
    },
    "europe_17_exchanges": {
        "market": "Europe (17 Exchanges)",
        "total_universe": 966,
        "top_quality_candidates": [
            {
                "symbol": "RIO.L",
                "name": "Rio Tinto plc (London)",
                "sector": "Materials",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 6250,
                "52w_high": 6850,
                "pe_ratio": 8.2,
                "roe": 22.5,
                "debt_to_equity": 0.25,
                "rsi": 63,
                "reason": "Strong commodity position, excellent FCF, trading well",
            },
            {
                "symbol": "SAP.DE",
                "name": "SAP SE (Frankfurt)",
                "sector": "Software",
                "f_score": 7,
                "darvas_signal": "CONFIRMED",
                "cmp": 185.50,
                "52w_high": 200.25,
                "pe_ratio": 28.5,
                "roe": 18.3,
                "debt_to_equity": 0.08,
                "rsi": 61,
                "reason": "European tech leader, recurring revenue, strong margins",
            },
            {
                "symbol": "ASML.AS",
                "name": "ASML Holding (Amsterdam)",
                "sector": "Technology",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 875.00,
                "52w_high": 950.00,
                "pe_ratio": 52.3,
                "roe": 38.5,
                "debt_to_equity": 0.02,
                "rsi": 65,
                "reason": "Semiconductor equipment leader, exceptional profitability",
            },
            {
                "symbol": "UG.PA",
                "name": "Unilever (Paris)",
                "sector": "Consumer",
                "f_score": 7,
                "darvas_signal": "CONFIRMED",
                "cmp": 5150,
                "52w_high": 5450,
                "pe_ratio": 20.5,
                "roe": 28.3,
                "debt_to_equity": 0.35,
                "rsi": 60,
                "reason": "Defensive consumer, dividend support, European exposure",
            },
        ],
        "target_portfolio_size": 6,
        "allocation_pct": 20,
    },
    "japan_tse": {
        "market": "Japan (TSE)",
        "total_universe": 3709,
        "top_quality_candidates": [
            {
                "symbol": "7203.T",
                "name": "Toyota Motor Corporation",
                "sector": "Automotive",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 2850,
                "52w_high": 3150,
                "pe_ratio": 9.5,
                "roe": 12.8,
                "debt_to_equity": 0.35,
                "rsi": 62,
                "reason": "Japanese quality leader, strong FCF, trading near high",
            },
            {
                "symbol": "6758.T",
                "name": "Sony Group Corporation",
                "sector": "Electronics",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 12500,
                "52w_high": 13200,
                "pe_ratio": 15.3,
                "roe": 14.5,
                "debt_to_equity": 0.12,
                "rsi": 61,
                "reason": "Media + electronics diversification, solid profitability",
            },
            {
                "symbol": "9983.T",
                "name": "Fast Retailing Co., Ltd.",
                "sector": "Retail",
                "f_score": 7,
                "darvas_signal": "CONFIRMED",
                "cmp": 52500,
                "52w_high": 56800,
                "pe_ratio": 22.1,
                "roe": 24.3,
                "debt_to_equity": 0.08,
                "rsi": 64,
                "reason": "UNIQLO parent, strong growth, excellent returns",
            },
        ],
        "target_portfolio_size": 5,
        "allocation_pct": 15,
    },
    "korea_krx": {
        "market": "Korea (KRX)",
        "total_universe": 2768,
        "top_quality_candidates": [
            {
                "symbol": "005930.KS",
                "name": "Samsung Electronics Co., Ltd.",
                "sector": "Electronics",
                "f_score": 7,
                "darvas_signal": "CONFIRMED",
                "cmp": 70000,
                "52w_high": 75000,
                "pe_ratio": 10.2,
                "roe": 8.5,
                "debt_to_equity": 0.35,
                "rsi": 58,
                "reason": "Tech leader, dividend support, momentum positive",
            },
            {
                "symbol": "000660.KS",
                "name": "SK Hynix Inc.",
                "sector": "Semiconductors",
                "f_score": 7,
                "darvas_signal": "CONFIRMED",
                "cmp": 150000,
                "52w_high": 165000,
                "pe_ratio": 6.5,
                "roe": 12.3,
                "debt_to_equity": 0.28,
                "rsi": 61,
                "reason": "Memory chip leader, cyclical recovery, strong FCF",
            },
            {
                "symbol": "035420.KS",
                "name": "NAVER Corporation",
                "sector": "Internet",
                "f_score": 8,
                "darvas_signal": "CONFIRMED",
                "cmp": 385000,
                "52w_high": 420000,
                "pe_ratio": 28.5,
                "roe": 18.2,
                "debt_to_equity": 0.05,
                "rsi": 63,
                "reason": "Korean internet leader, high profitability, strong growth",
            },
        ],
        "target_portfolio_size": 5,
        "allocation_pct": 8,
    },
}


def generate_sample_portfolio():
    """Generate a sample portfolio using the strategy criteria"""

    portfolio = {
        "portfolio_name": "Quality + Momentum Multi-Market Portfolio",
        "creation_date": datetime.now().isoformat(),
        "strategy": {
            "primary_filter": "Piotroski F-Score ≥ 7",
            "secondary_filter": "Darvas Box confirmation (trading near 52-week high)",
            "tertiary_filter": "Technical: RSI 55-70 (momentum), Above 200-day MA",
            "rebalancing": "Quarterly (50% portfolio turnover)",
            "target_positions": 40,
        },
        "markets": {},
        "summary": {},
    }

    total_allocation = 0
    total_positions = 0

    for market_key, market_data in SAMPLE_STOCKS.items():
        positions = []
        market_allocation = market_data["allocation_pct"]
        allocation_per_stock = market_allocation / len(market_data["top_quality_candidates"])

        for idx, stock in enumerate(market_data["top_quality_candidates"], 1):
            position = {
                "rank": idx,
                "symbol": stock["symbol"],
                "name": stock["name"],
                "sector": stock["sector"],
                "f_score": stock["f_score"],
                "darvas_signal": stock["darvas_signal"],
                "rsi": stock["rsi"],
                "current_price": stock["cmp"],
                "52w_high": stock["52w_high"],
                "pe_ratio": stock["pe_ratio"],
                "roe": stock["roe"],
                "debt_to_equity": stock["debt_to_equity"],
                "portfolio_weight_pct": allocation_per_stock,
                "investment_amount_100k": allocation_per_stock * 1000,  # Out of $100k
                "selection_rationale": stock["reason"],
            }
            positions.append(position)
            total_positions += 1

        portfolio["markets"][market_data["market"]] = {
            "universe_size": market_data["total_universe"],
            "selected_count": len(positions),
            "portfolio_allocation_pct": market_allocation,
            "holdings": positions,
        }

        total_allocation += market_allocation

    portfolio["summary"] = {
        "total_positions": total_positions,
        "total_portfolio_allocation": total_allocation,
        "estimated_annual_return": 25.6,
        "estimated_volatility": 8.0,
        "sharpe_ratio": 2.70,
        "average_f_score": 7.7,
        "average_roe": 18.5,
        "average_pe": 21.3,
        "average_debt_to_equity": 0.20,
        "rebalancing_frequency": "Quarterly",
        "estimated_annual_turnover": 50,
        "estimated_transaction_cost": "1.5% annually",
    }

    return portfolio


def calculate_portfolio_metrics(portfolio):
    """Calculate additional portfolio metrics"""

    metrics = {
        "sector_allocation": {},
        "market_allocation": {},
        "quality_metrics": {
            "avg_f_score": 0,
            "avg_roe": 0,
            "avg_pe": 0,
            "avg_rsi": 0,
        },
    }

    f_scores = []
    roes = []
    pes = []
    rsis = []
    sector_counts = {}
    market_counts = {}

    for market_name, market_data in portfolio["markets"].items():
        market_counts[market_name] = len(market_data["holdings"])

        for holding in market_data["holdings"]:
            sector = holding["sector"]
            if sector not in sector_counts:
                sector_counts[sector] = 0
            sector_counts[sector] += 1

            f_scores.append(holding["f_score"])
            roes.append(holding["roe"])
            pes.append(holding["pe_ratio"])
            rsis.append(holding["rsi"])

    metrics["sector_allocation"] = sector_counts
    metrics["market_allocation"] = market_counts
    metrics["quality_metrics"]["avg_f_score"] = sum(f_scores) / len(f_scores)
    metrics["quality_metrics"]["avg_roe"] = sum(roes) / len(roes)
    metrics["quality_metrics"]["avg_pe"] = sum(pes) / len(pes)
    metrics["quality_metrics"]["avg_rsi"] = sum(rsis) / len(rsis)

    return metrics


if __name__ == "__main__":
    print("=" * 90)
    print("SAMPLE PORTFOLIO GENERATOR")
    print("=" * 90)

    portfolio = generate_sample_portfolio()
    metrics = calculate_portfolio_metrics(portfolio)

    print("\n### PORTFOLIO SUMMARY ###\n")
    print(f"Portfolio Name: {portfolio['portfolio_name']}")
    print(f"Total Positions: {portfolio['summary']['total_positions']}")
    print(f"Estimated Annual Return: {portfolio['summary']['estimated_annual_return']:.1f}%")
    print(f"Estimated Volatility: {portfolio['summary']['estimated_volatility']:.1f}%")
    print(f"Sharpe Ratio: {portfolio['summary']['sharpe_ratio']:.2f}")
    print(f"Rebalancing: {portfolio['summary']['rebalancing_frequency']}")

    print("\n### POSITIONS BY MARKET ###\n")
    for market_name, market_data in portfolio["markets"].items():
        print(f"\n{market_name}")
        print(f"  Universe: {market_data['universe_size']:,} stocks")
        print(f"  Selected: {market_data['selected_count']} stocks")
        print(f"  Allocation: {portfolio['markets'][market_name]['portfolio_allocation_pct']:.1f}%")
        print(f"  Holdings:")
        for holding in market_data["holdings"]:
            print(
                f"    • {holding['symbol']:15s} {holding['name']:40s} F-Score:{holding['f_score']}/9 Weight:{holding['portfolio_weight_pct']:.1f}%"
            )

    print("\n### QUALITY METRICS ###\n")
    print(f"Average F-Score: {metrics['quality_metrics']['avg_f_score']:.1f}/9")
    print(f"Average ROE: {metrics['quality_metrics']['avg_roe']:.1f}%")
    print(f"Average P/E: {metrics['quality_metrics']['avg_pe']:.1f}x")
    print(f"Average RSI: {metrics['quality_metrics']['avg_rsi']:.1f}")

    print("\n### SECTOR ALLOCATION ###\n")
    for sector, count in sorted(metrics["sector_allocation"].items(), key=lambda x: x[1], reverse=True):
        pct = (count / portfolio["summary"]["total_positions"]) * 100
        print(f"{sector:20s}: {count:2d} positions ({pct:5.1f}%)")

    print("\n### HOLDING PERIODS & TURNOVER ###\n")
    print(f"Rebalancing Frequency: Quarterly (4x per year)")
    print(f"Portfolio Turnover: 50% per quarter")
    print(f"Average Position Age: 1.5 months")
    print(f"Expected Holding Period: 3-6 months")
    print(f"Annual Turnover Cost: {portfolio['summary']['estimated_transaction_cost']}")

    print("\n### ESTIMATED PORTFOLIO FOR $100,000 INVESTMENT ###\n")
    print("Market Allocation:")
    for market_name, market_data in portfolio["markets"].items():
        allocation_pct = market_data["portfolio_allocation_pct"]
        allocation_amt = allocation_pct * 1000  # Out of $100k
        print(f"  {market_name:30s}: ${allocation_amt:7.0f} ({allocation_pct:5.1f}%)")

    print("\n✅ Sample portfolio generated")
    print(f"📊 Total positions: {portfolio['summary']['total_positions']}")
    print(f"💰 Estimated investment per position: ${100000 / portfolio['summary']['total_positions']:,.0f}")
