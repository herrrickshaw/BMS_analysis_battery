"""
Options strategy builder REST API — Sensibull-style.

Exposes the put_call_parity strategy engine over HTTP so the React frontend
can render payoff charts, Greeks tables, and strategy recommendations.

Endpoints:
    GET  /api/options/strategies                   List all 14 supported strategies
    POST /api/options/strategies/analyse           Full analysis: recommended + all strategies
    GET  /api/options/chain                        Raw option chain with IV for a symbol
    POST /api/options/strategies/build             Build one specific named strategy

Typical frontend flow:
    1. User selects a symbol (e.g. BANKNIFTY) and their market outlook (neutral).
    2. POST /api/options/strategies/analyse → get recommended strategies + payoff curves.
    3. Frontend renders payoff chart (spot vs P&L) and the Greeks table.
    4. User can also POST /api/options/strategies/build to customise individual strategies.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

# backend/ runs as the uvicorn cwd, so the repo root (parent of backend/ and
# put_call_parity/) isn't on sys.path by default — add it so the
# `from put_call_parity...` imports below resolve.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/api/options', tags=['options-strategies'])


# ── Pydantic request models ────────────────────────────────────────────────────

class AnalyseRequest(BaseModel):
    """
    Request body for the strategy analysis endpoint.
    All fields except `symbol` have sensible defaults.
    """
    symbol: str = Field(
        ...,
        description=(
            'Instrument symbol.  Use BANKNIFTY, NIFTY, CRUDEOIL, SILVER for Indian '
            'instruments, or any valid yfinance ticker for US/global (e.g. AAPL, SPY, CL=F).'
        ),
        examples=['BANKNIFTY', 'NIFTY', 'AAPL'],
    )
    outlook: str = Field(
        default='neutral',
        description='Your market view: bullish | bearish | neutral | volatile',
        pattern='^(bullish|bearish|neutral|volatile)$',
    )
    lots: int = Field(
        default=1, ge=1, le=50,
        description='Number of contracts per leg.',
    )
    expiry: Optional[str] = Field(
        default=None,
        description='Expiry date in YYYY-MM-DD format.  Omit to use nearest available.',
    )
    otm_pct: float = Field(
        default=0.02, ge=0.005, le=0.10,
        description=(
            'How far out-of-the-money to place spread/strangle short legs, '
            'as a fraction of spot.  0.02 = 2% OTM (default).'
        ),
    )


class BuildRequest(BaseModel):
    """Request body for building one specific strategy."""
    symbol: str
    strategy: str = Field(
        ...,
        description=(
            'Strategy key.  Call GET /api/options/strategies for the full list. '
            'Examples: iron_condor, long_straddle, bull_call_spread.'
        ),
    )
    lots: int = Field(default=1, ge=1, le=50)
    expiry: Optional[str] = None
    otm_pct: float = Field(default=0.02, ge=0.005, le=0.10)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get('/strategies')
def list_strategies():
    """
    Return the catalogue of all 14 supported strategy names with descriptions.

    Use the `key` field when calling the build or analyse endpoints.
    `outlook` tells you which market view each strategy is suited for.
    """
    try:
        from put_call_parity.options_strategies import StrategyBuilder
        return {
            'count': len(StrategyBuilder.STRATEGY_CATALOGUE),
            'strategies': [
                {
                    'key':         key,
                    'name':        name,
                    'outlook':     outlook,
                    'description': desc,
                }
                for key, (name, outlook, desc) in StrategyBuilder.STRATEGY_CATALOGUE.items()
            ],
        }
    except ImportError:
        raise HTTPException(503, 'Options strategy module not installed (scipy required)')


@router.post('/strategies/analyse')
async def analyse_strategies(req: AnalyseRequest):
    """
    Full options strategy analysis for a symbol.

    Returns:
    - Current spot price, ATM IV, and IV rank (0-100 percentile)
    - 2-3 **recommended** strategies suited to your `outlook` and IV environment
    - Complete catalogue of **all 14 strategies** with payoff curves and Greeks
    - Whether data came from a live option chain or a synthetic Black-Scholes chain

    The payoff list in each strategy contains 80 data points covering ±25% around
    spot — suitable for rendering a payoff-at-expiry chart.
    """
    try:
        from put_call_parity.strategy_scanner import run_strategy_scan
        result = await run_in_threadpool(
            run_strategy_scan,
            req.symbol,
            req.outlook,
            req.lots,
            req.expiry,
            req.otm_pct,
        )
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        log.exception('options/analyse failed for %s', req.symbol)
        raise HTTPException(502, f'Strategy analysis failed: {exc}')


@router.get('/chain')
async def get_option_chain(symbol: str, expiry: Optional[str] = None):
    """
    Fetch the raw option chain for a symbol with IV, OI, and volume per strike.

    Useful for inspecting market prices before choosing a strategy.
    Falls back to a synthetic Black-Scholes chain when yfinance has no data.
    """
    try:
        from put_call_parity.strategy_scanner import compute_atm_iv, fetch_option_chain
        chain_data = await run_in_threadpool(fetch_option_chain, symbol, expiry)
        atm_iv     = compute_atm_iv(chain_data)
        return {
            **chain_data,
            'atm_iv_pct': round(atm_iv * 100, 2),
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        log.exception('options/chain failed for %s', symbol)
        raise HTTPException(502, f'Chain fetch failed: {exc}')


@router.post('/strategies/build')
async def build_strategy(req: BuildRequest):
    """
    Build a single named strategy and return payoff curve, Greeks, and metrics.

    Useful when you want to customise one strategy (e.g. change OTM%, lots) without
    running the full analysis.
    """
    try:
        from put_call_parity.options_strategies import StrategyBuilder
        from put_call_parity.strategy_scanner import fetch_option_chain

        chain_data = await run_in_threadpool(fetch_option_chain, req.symbol, req.expiry)
        builder    = StrategyBuilder(chain_data)
        result     = builder.build(req.strategy, lots=req.lots, otm_pct=req.otm_pct)

        return {
            'symbol':      req.symbol,
            'spot':        round(chain_data['spot'], 2),
            'expiry':      chain_data['expiry'],
            'data_source': chain_data['data_source'],
            'strategy':    result.as_dict(),
        }
    except KeyError:
        valid = list(StrategyBuilder.STRATEGY_CATALOGUE) if 'StrategyBuilder' in dir() else []
        raise HTTPException(
            400,
            f'Unknown strategy "{req.strategy}". '
            f'Valid keys: {valid or "call GET /api/options/strategies"}',
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        log.exception('options/build failed for %s/%s', req.symbol, req.strategy)
        raise HTTPException(502, f'Strategy build failed: {exc}')
