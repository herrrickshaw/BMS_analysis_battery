#!/usr/bin/env python3
"""
Portfolio Analyzer API - FastAPI backend for portfolio analysis dashboard
Serves portfolio metrics, holdings, and rebalancing recommendations
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import pandas as pd
import json
from typing import Optional
import os
from pathlib import Path
from datetime import datetime
import tempfile

from portfolio_analyzer import PortfolioAnalyzer, load_portfolio_from_csv, load_portfolio_from_excel

app = FastAPI(
    title="Portfolio Analyzer API",
    description="Comprehensive portfolio analysis and evaluation service",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global analyzer instance
current_analyzer: Optional[PortfolioAnalyzer] = None
portfolio_data: Optional[pd.DataFrame] = None

# Storage for uploaded portfolios
PORTFOLIO_STORAGE = Path("/tmp/portfolio_uploads")
PORTFOLIO_STORAGE.mkdir(exist_ok=True)


@app.get("/")
def root():
    """API health check"""
    return {
        "status": "running",
        "service": "Portfolio Analyzer API",
        "version": "1.0.0",
        "endpoints": [
            "POST /portfolio/upload - Upload portfolio file",
            "POST /portfolio/load-sample - Load sample portfolio",
            "GET /portfolio/status - Get current portfolio status",
            "GET /portfolio/metrics - Get portfolio metrics",
            "GET /portfolio/holdings - Get detailed holdings",
            "GET /portfolio/quality - Get position quality scores",
            "GET /portfolio/rebalancing - Get rebalancing opportunities",
            "GET /portfolio/sectors - Get sector allocation",
            "GET /portfolio/report - Get complete report (JSON)",
            "POST /portfolio/fetch-prices - Fetch current prices",
            "POST /portfolio/fetch-fundamentals - Fetch fundamental data",
        ]
    }


@app.post("/portfolio/upload")
async def upload_portfolio(file: UploadFile = File(...)):
    """
    Upload and load a portfolio file (CSV or Excel)

    Returns:
        Portfolio status and basic metrics
    """
    global current_analyzer, portfolio_data

    try:
        # Save uploaded file
        file_path = PORTFOLIO_STORAGE / file.filename
        with open(file_path, 'wb') as f:
            f.write(await file.read())

        # Load portfolio
        if file.filename.endswith('.csv'):
            portfolio_data = load_portfolio_from_csv(str(file_path))
        elif file.filename.endswith(('.xls', '.xlsx')):
            portfolio_data = load_portfolio_from_excel(str(file_path))
        else:
            raise ValueError("Unsupported file format. Use CSV or Excel.")

        # Ensure current_price column exists
        if 'current_price' not in portfolio_data.columns:
            portfolio_data['current_price'] = 0.0

        # Initialize analyzer
        current_analyzer = PortfolioAnalyzer(portfolio_data)

        return {
            "status": "success",
            "message": f"Portfolio loaded: {len(portfolio_data)} stocks",
            "filename": file.filename,
            "stocks": len(portfolio_data),
            "markets": portfolio_data['market'].unique().tolist(),
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/portfolio/load-sample")
def load_sample_portfolio():
    """Load a sample portfolio for testing"""
    global current_analyzer, portfolio_data

    try:
        sample_data = {
            'ticker': [
                'HDFCBANK', 'RELIANCE', 'INFY', 'TCS', 'ICICIBANK',
                'SBIN', 'MARUTI', 'HDFC', 'WIPRO', 'BAJAJFINSV',
                'AAPL', 'MSFT', 'GOOGL', 'AMAZON', 'TESLA',
                'ADS.DE', 'SAP.DE', 'SIEMENS.DE', 'BMW.DE', 'RIO.L'
            ],
            'quantity': [10, 5, 20, 15, 8, 12, 1, 25, 30, 6, 5, 4, 3, 2, 1, 8, 6, 10, 15, 20],
            'purchase_price': [
                1500, 2800, 1600, 3200, 900, 500, 1700, 2400, 700, 550,
                180, 320, 140, 170, 250, 180, 120, 140, 100, 60
            ],
            'purchase_date': [
                '2023-01-15', '2023-02-20', '2023-03-10', '2023-04-05', '2023-05-12',
                '2023-06-18', '2023-07-22', '2023-08-14', '2023-09-09', '2023-10-25',
                '2023-11-10', '2023-12-01', '2024-01-15', '2024-02-20', '2024-03-10',
                '2024-04-05', '2024-05-12', '2024-06-18', '2024-07-22', '2024-08-14'
            ],
            'market': [
                'india', 'india', 'india', 'india', 'india',
                'india', 'india', 'india', 'india', 'india',
                'us', 'us', 'us', 'us', 'us',
                'europe', 'europe', 'europe', 'europe', 'europe'
            ],
            'sector': [
                'banking', 'energy', 'it', 'it', 'banking',
                'banking', 'auto', 'banking', 'it', 'finance',
                'tech', 'tech', 'tech', 'consumer', 'auto',
                'auto', 'software', 'industrials', 'auto', 'materials'
            ]
        }

        portfolio_data = pd.DataFrame(sample_data)
        portfolio_data['current_price'] = portfolio_data['purchase_price'] * 1.15  # 15% gain

        current_analyzer = PortfolioAnalyzer(portfolio_data)

        return {
            "status": "success",
            "message": "Sample portfolio loaded",
            "stocks": len(portfolio_data),
            "markets": portfolio_data['market'].unique().tolist(),
            "sectors": portfolio_data['sector'].unique().tolist(),
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/portfolio/status")
def get_portfolio_status():
    """Get current portfolio status"""
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded. Upload or load sample first.")

    metrics = current_analyzer.calculate_portfolio_metrics()
    return {
        "status": "loaded",
        "stocks": len(portfolio_data),
        "total_value": metrics['summary']['current_value'],
        "total_gain": metrics['summary']['total_gain'],
        "total_gain_pct": metrics['summary']['total_gain_pct'],
        "markets": portfolio_data['market'].unique().tolist(),
        "updated_at": datetime.now().isoformat(),
    }


@app.get("/portfolio/metrics")
def get_portfolio_metrics():
    """Get comprehensive portfolio metrics"""
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    metrics = current_analyzer.calculate_portfolio_metrics()
    return metrics


@app.get("/portfolio/holdings")
def get_portfolio_holdings(sort_by: str = "allocation_pct"):
    """
    Get detailed holdings

    Args:
        sort_by: Field to sort by (allocation_pct, gain_loss_pct, etc.)
    """
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    holdings = current_analyzer.portfolio[[
        'ticker', 'market', 'quantity', 'purchase_price', 'current_price',
        'cost_basis', 'current_value', 'gain_loss', 'gain_loss_pct',
        'allocation_pct', 'days_held'
    ]].copy()

    holdings['days_held'] = holdings['days_held'].astype(int)

    if sort_by in holdings.columns:
        holdings = holdings.sort_values(sort_by, ascending=False)

    return holdings.to_dict('records')


@app.get("/portfolio/quality")
def get_position_quality():
    """Get position quality scores"""
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    quality = current_analyzer.calculate_position_quality()
    return quality.sort_values('allocation_pct', ascending=False).to_dict('records')


@app.get("/portfolio/rebalancing")
def get_rebalancing_opportunities(max_position_pct: float = 10):
    """
    Get rebalancing opportunities

    Args:
        max_position_pct: Maximum recommended position size
    """
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    opportunities = current_analyzer.identify_rebalancing_opportunities(max_position_pct)
    return opportunities


@app.get("/portfolio/sectors")
def get_sector_allocation():
    """Get sector-wise allocation"""
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    sectors = current_analyzer.get_sector_allocation()
    return sectors


@app.get("/portfolio/report")
def get_complete_report():
    """Get complete portfolio analysis report"""
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    report = current_analyzer.generate_report()
    # Convert datetime to string for JSON serialization
    report['generated_at'] = str(report['generated_at'])

    return report


@app.post("/portfolio/fetch-prices")
def fetch_current_prices():
    """Fetch current prices from yfinance"""
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    try:
        current_analyzer.fetch_current_prices()
        return {
            "status": "success",
            "message": "Prices updated successfully",
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching prices: {str(e)}")


@app.post("/portfolio/fetch-fundamentals")
def fetch_fundamental_data():
    """Fetch fundamental data"""
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    try:
        current_analyzer.fetch_fundamentals()
        return {
            "status": "success",
            "message": "Fundamentals fetched successfully",
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching fundamentals: {str(e)}")


@app.post("/portfolio/analyze-stock")
def analyze_single_stock(ticker: str, market: str = "india"):
    """
    Analyze a single stock

    Args:
        ticker: Stock ticker
        market: Market (india, us, europe, japan, korea)
    """
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    try:
        # Find stock in portfolio
        stock = portfolio_data[portfolio_data['ticker'] == ticker]

        if stock.empty:
            return {
                "status": "not_found",
                "message": f"Stock {ticker} not in portfolio",
            }

        stock_data = stock.iloc[0].to_dict()
        stock_idx = stock.index[0]

        # Add fundamentals if available
        fundamentals = current_analyzer.fundamentals.get(stock_idx, {})

        return {
            "ticker": ticker,
            "market": market,
            "holdings": {
                "quantity": stock_data['quantity'],
                "cost_basis": round(stock_data['cost_basis'], 2),
                "current_value": round(stock_data['current_value'], 2),
                "gain_loss": round(stock_data['gain_loss'], 2),
                "gain_loss_pct": round(stock_data['gain_loss_pct'], 2),
                "allocation_pct": round(stock_data['allocation_pct'], 2),
                "days_held": int(stock_data['days_held']),
                "ltcg_eligible": stock_data['days_held'] >= 365,
            },
            "fundamentals": fundamentals,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/portfolio/comparison")
def compare_with_benchmark(benchmark: str = "nifty50"):
    """
    Compare portfolio performance with benchmark

    Args:
        benchmark: Benchmark index (nifty50, sensex, sp500, etc.)
    """
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    metrics = current_analyzer.calculate_portfolio_metrics()

    return {
        "portfolio_gain_pct": metrics['summary']['total_gain_pct'],
        "benchmark": benchmark,
        "benchmark_note": f"Implementation requires {benchmark} historical data fetch",
        "portfolio_metrics": {
            "total_value": metrics['summary']['current_value'],
            "total_gain": metrics['summary']['total_gain'],
            "concentration": metrics['risk']['concentration_ratio'],
            "diversification": metrics['risk']['diversification_ratio'],
            "dividend_yield": metrics['income']['dividend_yield'],
        }
    }


@app.get("/portfolio/alerts")
def get_portfolio_alerts():
    """Get actionable portfolio alerts and recommendations"""
    if current_analyzer is None:
        raise HTTPException(status_code=400, detail="No portfolio loaded.")

    alerts = []
    metrics = current_analyzer.calculate_portfolio_metrics()
    rebalancing = current_analyzer.identify_rebalancing_opportunities()

    # Concentration alert
    if metrics['risk']['concentration_ratio'] > 15:
        alerts.append({
            "severity": "high",
            "type": "concentration",
            "message": f"Largest position is {metrics['risk']['concentration_ratio']:.1f}% of portfolio (>15% threshold)",
            "action": "Consider reducing largest position",
        })

    # Overweight positions
    if rebalancing['overweight_positions']:
        alerts.append({
            "severity": "medium",
            "type": "overweight",
            "message": f"{len(rebalancing['overweight_positions'])} position(s) are overweight (>10%)",
            "action": "Review overweight positions for rebalancing",
        })

    # Tax implications
    high_stcg = [t for t in rebalancing['tax_implications'] if t['tax_status'] == 'STCG' and t['estimated_tax'] > 10000]
    if high_stcg:
        alerts.append({
            "severity": "medium",
            "type": "tax",
            "message": f"{len(high_stcg)} position(s) with high STCG tax implications",
            "action": "Consider holding until LTCG eligibility (365 days)",
        })

    # Dividend yield
    if metrics['income']['dividend_yield'] < 1.5:
        alerts.append({
            "severity": "low",
            "type": "income",
            "message": f"Dividend yield is {metrics['income']['dividend_yield']:.2f}% (industry target: 2-3%)",
            "action": "Consider adding dividend-paying stocks",
        })

    # Sector concentration
    if 'sector' in current_analyzer.portfolio.columns:
        sectors = current_analyzer.get_sector_allocation()
        for sector, data in sectors.items():
            if data['allocation_pct'] > 30:
                alerts.append({
                    "severity": "low",
                    "type": "sector",
                    "message": f"Sector '{sector}' is {data['allocation_pct']:.1f}% of portfolio",
                    "action": "Consider diversifying sector exposure",
                })

    return {
        "total_alerts": len(alerts),
        "alerts": alerts,
        "summary": {
            "high": len([a for a in alerts if a['severity'] == 'high']),
            "medium": len([a for a in alerts if a['severity'] == 'medium']),
            "low": len([a for a in alerts if a['severity'] == 'low']),
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
