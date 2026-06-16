"""
Data provider API key configuration via pydantic-settings.

All values are read from environment variables (or .env.providers / .env files).
Copy .env.providers.example to .env.providers and fill in keys before starting.
"""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=('.env.providers', '.env'),
        env_file_encoding='utf-8',
        extra='ignore',
    )

    # ── Yahoo Finance — no key required ───────────────────────────────────────

    # ── Alpha Vantage ─────────────────────────────────────────────────────────
    ALPHA_VANTAGE_KEY: str = Field(default='', validation_alias='ALPHA_VANTAGE_API_KEY')

    # ── Polygon.io ────────────────────────────────────────────────────────────
    POLYGON_KEY: str = Field(default='', validation_alias='POLYGON_API_KEY')

    # ── IEX Cloud ─────────────────────────────────────────────────────────────
    IEX_TOKEN: str = ''
    IEX_BASE: str = Field(
        default='https://cloud.iexapis.com/stable',
        validation_alias='IEX_BASE_URL',
    )

    # ── Tradier ───────────────────────────────────────────────────────────────
    TRADIER_TOKEN: str = Field(default='', validation_alias='TRADIER_API_KEY')
    TRADIER_BASE: str = Field(
        default='https://api.tradier.com/v1',
        validation_alias='TRADIER_BASE_URL',
    )

    # ── Quandl / Nasdaq Data Link — accepts either env var name ───────────────
    QUANDL_KEY: str = Field(
        default='',
        validation_alias=AliasChoices('NASDAQ_DATA_LINK_API_KEY', 'QUANDL_API_KEY'),
    )

    # ── Currencylayer ─────────────────────────────────────────────────────────
    CURRENCYLAYER_KEY: str = Field(default='', validation_alias='CURRENCYLAYER_ACCESS_KEY')
    CURRENCYLAYER_BASE: str = 'https://api.currencylayer.com'

    # ── Interactive Brokers ───────────────────────────────────────────────────
    IB_HOST: str = '127.0.0.1'
    IB_PORT: int = 7497
    IB_CLIENT_ID: int = 1

    # ── TradingView ───────────────────────────────────────────────────────────
    TRADINGVIEW_USER: str = Field(default='', validation_alias='TRADINGVIEW_USERNAME')
    TRADINGVIEW_PASS: str = Field(default='', validation_alias='TRADINGVIEW_PASSWORD')

    # ── App / infrastructure settings ─────────────────────────────────────────
    CASSANDRA_HOST: str = '127.0.0.1'
    CASSANDRA_PORT: int = 9042
    CORS_ORIGINS: list[str] = ['http://localhost:5173', 'http://localhost:3000']
    LOG_JSON: bool = False
    PREFETCH_HOUR: int = 0
    PREFETCH_MINUTE: int = 0


cfg = Settings()


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
    out.append('tradingview')          # works without credentials
    out.append('interactive_brokers')  # tried at runtime; fails gracefully if gateway offline
    return out
