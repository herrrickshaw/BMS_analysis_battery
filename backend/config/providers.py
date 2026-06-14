"""
Data provider API key configuration.

All keys are read from environment variables.  Copy .env.providers.example
to .env.providers and fill in keys, then source it before starting the app:

    set -a && source .env.providers && set +a

Or export them directly in your shell / deployment environment.
"""
from __future__ import annotations

import os


def _env(key: str, default: str = '') -> str:
    return os.environ.get(key, default).strip()


class ProviderConfig:
    # ── Yahoo Finance ─────────────────────────────────────────────────────────
    # No API key required — uses yfinance library (unofficial scraper)

    # ── Alpha Vantage ─────────────────────────────────────────────────────────
    # Free tier: 25 req/day · Premium: up to 1200/min
    # https://www.alphavantage.co/support/#api-key
    ALPHA_VANTAGE_KEY: str = _env('ALPHA_VANTAGE_API_KEY')

    # ── Polygon.io ────────────────────────────────────────────────────────────
    # Free tier: 5 req/min delayed · Paid: unlimited real-time
    # https://polygon.io/dashboard/signup
    POLYGON_KEY: str = _env('POLYGON_API_KEY')

    # ── IEX Cloud ─────────────────────────────────────────────────────────────
    # Credit-based; free sandbox available (sandbox.iexapis.com)
    # https://iexcloud.io/cloud-login#/register
    IEX_TOKEN: str = _env('IEX_TOKEN')
    IEX_BASE: str  = _env('IEX_BASE_URL', 'https://cloud.iexapis.com/stable')

    # ── Tradier ───────────────────────────────────────────────────────────────
    # Brokerage or developer sandbox account
    # https://developer.tradier.com/user/sign_up
    TRADIER_TOKEN: str = _env('TRADIER_API_KEY')
    TRADIER_BASE: str  = _env('TRADIER_BASE_URL', 'https://api.tradier.com/v1')

    # ── Quandl / Nasdaq Data Link ─────────────────────────────────────────────
    # https://data.nasdaq.com/sign-up
    QUANDL_KEY: str = _env('NASDAQ_DATA_LINK_API_KEY') or _env('QUANDL_API_KEY')

    # ── Currencylayer ─────────────────────────────────────────────────────────
    # Free tier: 100 req/month (USD base only) · https://currencylayer.com/signup
    CURRENCYLAYER_KEY: str = _env('CURRENCYLAYER_ACCESS_KEY')
    CURRENCYLAYER_BASE: str = 'https://api.currencylayer.com'

    # ── Interactive Brokers (ib_insync) ───────────────────────────────────────
    # Requires IB Gateway or TWS running locally
    # Paper trading port: 7497  |  Live trading port: 7496
    IB_HOST: str      = _env('IB_HOST', '127.0.0.1')
    IB_PORT: int      = int(_env('IB_PORT', '7497'))
    IB_CLIENT_ID: int = int(_env('IB_CLIENT_ID', '1'))

    # ── TradingView (tvdatafeed — unofficial) ─────────────────────────────────
    # Works without credentials (delayed data) or with TV account for more history
    TRADINGVIEW_USER: str = _env('TRADINGVIEW_USERNAME')
    TRADINGVIEW_PASS: str = _env('TRADINGVIEW_PASSWORD')


cfg = ProviderConfig()


def configured_providers() -> list[str]:
    """Return list of provider names that have keys set."""
    out = ['yahoo']  # always available
    if cfg.ALPHA_VANTAGE_KEY:
        out.append('alpha_vantage')
    if cfg.POLYGON_KEY:
        out.append('polygon')
    if cfg.IEX_TOKEN:
        out.append('iex')
    if cfg.TRADIER_TOKEN:
        out.append('tradier')
    if cfg.QUANDL_KEY:
        out.append('quandl')
    if cfg.CURRENCYLAYER_KEY:
        out.append('currencylayer')
    out.append('tradingview')   # works without credentials
    out.append('interactive_brokers')  # tried at runtime; fails gracefully if gateway offline
    return out
