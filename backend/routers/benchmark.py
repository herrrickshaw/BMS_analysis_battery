"""
Benchmark router — portfolio vs S&P 500 / NASDAQ analytics.

Endpoints:
  POST /api/benchmark/portfolio   Compare holdings to a benchmark index
  GET  /api/benchmark/ticker/{t}  Single ticker vs benchmark
  GET  /api/benchmark/status      Dataset load status + summary
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from benchmarks.benchmark_engine import engine

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/benchmark', tags=['benchmark'])


class HoldingItem(BaseModel):
    yf_ticker: str
    market: str = 'us'
    purchase_date: str | None = None
    purchase_price: float | None = None
    quantity: float | None = None
    name: str | None = None


class PortfolioBenchmarkRequest(BaseModel):
    holdings: list[HoldingItem]
    benchmark: str = 'sp500'     # sp500 | nasdaq


@router.post('/portfolio')
async def compare_portfolio(req: PortfolioBenchmarkRequest):
    """
    Compare portfolio returns and risk metrics against a benchmark index.
    Returns alpha, beta, Sharpe ratio, max drawdown, correlation,
    tracking error, information ratio, and per-holding S&P 500 fundamentals.
    """
    holdings = [h.model_dump() for h in req.holdings]
    result = await run_in_threadpool(engine.portfolio_metrics, holdings, req.benchmark)
    return result


@router.get('/ticker/{ticker}')
async def ticker_vs_benchmark(
    ticker: str,
    market: str = Query(default='us'),
    period_days: int = Query(default=365, ge=30, le=1825),
    benchmark: str = Query(default='sp500'),
):
    """Single ticker performance vs benchmark over last N days."""
    result = await run_in_threadpool(
        engine.ticker_vs_benchmark, ticker.upper(), market, period_days, benchmark
    )
    return result


@router.get('/status')
async def benchmark_status():
    """Return loaded dataset status and available benchmark series."""
    return engine.benchmark_summary()


@router.get('/sentiment/status')
async def sentiment_status():
    """Return sentiment scorer dataset status."""
    from ml.sentiment_scorer import scorer
    return {
        'datasets_loaded': scorer.loaded_datasets,
        'lexicon_size': len(scorer._lexicon),
        'model_trained': scorer._model is not None,
    }
