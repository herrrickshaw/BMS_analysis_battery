"""
Data provider API key configuration via pydantic-settings.

HOW THIS WORKS
--------------
Instead of reading environment variables with os.environ.get() scattered across
the codebase, we define one Settings class here.  At import time, pydantic-settings
reads every field from:
  1. Real environment variables  (highest priority)
  2. .env.providers file         (if it exists)
  3. .env file                   (if it exists)
  4. The default= value below    (lowest priority / fallback)

Anywhere in the code you need an API key, just do:
    from config.providers import cfg
    key = cfg.ALPHA_VANTAGE_KEY

SETUP
-----
Copy .env.providers.example → .env.providers, fill in your API keys,
then start the app.  The file is gitignored so keys are never committed.
"""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Tell pydantic-settings where to look for .env files.
    # Both files are optional — missing files are silently skipped.
    model_config = SettingsConfigDict(
        env_file=('.env.providers', '.env'),
        env_file_encoding='utf-8',
        extra='ignore',   # don't error on unknown env vars (e.g. PATH, HOME)
    )

    # ── Yahoo Finance — no key required ───────────────────────────────────────
    # yfinance is an unofficial scraper; it works without credentials.

    # ── Alpha Vantage ─────────────────────────────────────────────────────────
    # validation_alias tells pydantic to read the env var ALPHA_VANTAGE_API_KEY
    # but expose it in code as cfg.ALPHA_VANTAGE_KEY (shorter name).
    ALPHA_VANTAGE_KEY: str = Field(default='', validation_alias='ALPHA_VANTAGE_API_KEY')

    # ── Polygon.io ────────────────────────────────────────────────────────────
    POLYGON_KEY: str = Field(default='', validation_alias='POLYGON_API_KEY')

    # ── IEX Cloud ─────────────────────────────────────────────────────────────
    IEX_TOKEN: str = ''   # field name matches env var name exactly, so no alias needed
    IEX_BASE: str = Field(
        default='https://cloud.iexapis.com/stable',
        validation_alias='IEX_BASE_URL',   # reads IEX_BASE_URL from env
    )

    # ── Tradier ───────────────────────────────────────────────────────────────
    TRADIER_TOKEN: str = Field(default='', validation_alias='TRADIER_API_KEY')
    TRADIER_BASE: str = Field(
        default='https://api.tradier.com/v1',
        validation_alias='TRADIER_BASE_URL',
    )

    # ── Quandl / Nasdaq Data Link ─────────────────────────────────────────────
    # AliasChoices lets this field accept EITHER env var name — useful because
    # Quandl was rebranded to Nasdaq Data Link, so users may have either name.
    QUANDL_KEY: str = Field(
        default='',
        validation_alias=AliasChoices('NASDAQ_DATA_LINK_API_KEY', 'QUANDL_API_KEY'),
    )

    # ── Currencylayer ─────────────────────────────────────────────────────────
    CURRENCYLAYER_KEY: str = Field(default='', validation_alias='CURRENCYLAYER_ACCESS_KEY')
    CURRENCYLAYER_BASE: str = 'https://api.currencylayer.com'  # fixed URL, not configurable

    # ── Interactive Brokers ───────────────────────────────────────────────────
    # IB Gateway / TWS must be running locally (or on IB_HOST) for these to work.
    # Paper trading port: 7497  |  Live trading port: 7496
    IB_HOST: str = '127.0.0.1'
    IB_PORT: int = 7497
    IB_CLIENT_ID: int = 1

    # ── TradingView ───────────────────────────────────────────────────────────
    TRADINGVIEW_USER: str = Field(default='', validation_alias='TRADINGVIEW_USERNAME')
    TRADINGVIEW_PASS: str = Field(default='', validation_alias='TRADINGVIEW_PASSWORD')

    # ── Infrastructure / app-level settings ───────────────────────────────────
    # These are NOT API keys — they control where the app connects and how it runs.

    # Cassandra hostname.  In Docker this is "cassandra" (the service name);
    # locally it's "127.0.0.1".  Overridden by docker-compose via environment:.
    CASSANDRA_HOST: str = '127.0.0.1'
    CASSANDRA_PORT: int = 9042

    # Which browser origins are allowed to call our API.
    # In production, change this to your real domain, e.g. ["https://myapp.com"].
    # Set via env: CORS_ORIGINS='["https://myapp.com"]'
    CORS_ORIGINS: list[str] = ['http://localhost:5173', 'http://localhost:3000']

    # Set LOG_JSON=true in production to emit structured JSON log lines,
    # which log aggregators (Datadog, ELK, CloudWatch) can parse and index.
    LOG_JSON: bool = False

    # What time to run the nightly market data prefetch (24-hour clock, server time).
    # Default: midnight (00:00).  Override via PREFETCH_HOUR / PREFETCH_MINUTE env vars.
    PREFETCH_HOUR: int = 0
    PREFETCH_MINUTE: int = 0


# Module-level singleton — import `cfg` anywhere and access settings as attributes.
# pydantic-settings validates types at startup, so a bad CASSANDRA_PORT="abc"
# raises an error immediately rather than crashing later at connection time.
cfg = Settings()


def configured_providers() -> list[str]:
    """Return the list of data provider names that have API keys configured."""
    out = ['yahoo']  # yfinance works without a key — always included
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
    out.append('tradingview')          # works without credentials (limited history)
    out.append('interactive_brokers')  # attempted at runtime; skipped if gateway offline
    return out
