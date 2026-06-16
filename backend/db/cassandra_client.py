"""
Cassandra session singleton with graceful fallback.

All blocking driver calls (connect, execute) must be dispatched from a
thread via run_in_threadpool or loop.run_in_executor — never called
directly inside an async handler.  is_available() is a fast, non-blocking
flag check that is safe to call from any context.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

log = logging.getLogger(__name__)

KEYSPACE = 'herrrickshaw'

_lock = threading.Lock()
_cluster = None
_session: Optional[object] = None   # cassandra.cluster.Session | None
_available: bool = False

_SCHEMA: list[str] = [
    f"""CREATE KEYSPACE IF NOT EXISTS {KEYSPACE}
        WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}""",
    # ── instruments tables (seeded from CSV, static) ──────────────────────────
    f"""CREATE TABLE IF NOT EXISTS {KEYSPACE}.instruments (
        market      text,
        yf_ticker   text,
        symbol      text,
        name        text,
        name_lower  text,
        isin        text,
        exchange    text,
        country     text,
        PRIMARY KEY (market, yf_ticker)
    ) WITH CLUSTERING ORDER BY (yf_ticker ASC)""",
    f"""CREATE TABLE IF NOT EXISTS {KEYSPACE}.instruments_by_symbol (
        market      text,
        symbol      text,
        yf_ticker   text,
        name        text,
        PRIMARY KEY (market, symbol)
    ) WITH CLUSTERING ORDER BY (symbol ASC)""",
    f"""CREATE TABLE IF NOT EXISTS {KEYSPACE}.instruments_by_name (
        market      text,
        name_lower  text,
        yf_ticker   text,
        name        text,
        PRIMARY KEY (market, name_lower)
    ) WITH CLUSTERING ORDER BY (name_lower ASC)""",
    f"""CREATE TABLE IF NOT EXISTS {KEYSPACE}.instruments_by_isin (
        isin        text PRIMARY KEY,
        market      text,
        yf_ticker   text,
        symbol      text,
        name        text
    )""",
    # ── live quote cache (updated after every yfinance fetch) ─────────────────
    f"""CREATE TABLE IF NOT EXISTS {KEYSPACE}.stock_quotes (
        market          text,
        yf_ticker       text,
        fetched_at      timestamp,
        cmp             double,
        rsi             double,
        ema_50          double,
        rsi_signal      text,
        pe              double,
        pb              double,
        roe             double,
        opm             double,
        market_cap      double,
        volume          bigint,
        high_52w        double,
        low_52w         double,
        debt_to_equity  double,
        PRIMARY KEY (market, yf_ticker)
    ) WITH CLUSTERING ORDER BY (yf_ticker ASC)""",
    # ── historical price cache (date of purchase lookups) ────────────────────
    f"""CREATE TABLE IF NOT EXISTS {KEYSPACE}.price_history (
        yf_ticker   text,
        price_date  date,
        close_price double,
        PRIMARY KEY (yf_ticker, price_date)
    ) WITH CLUSTERING ORDER BY (price_date DESC)""",
    # ── seeding book-keeping ──────────────────────────────────────────────────
    f"""CREATE TABLE IF NOT EXISTS {KEYSPACE}.seed_status (
        market      text PRIMARY KEY,
        seeded_at   timestamp,
        row_count   int
    )""",
]

# Applied at startup with per-statement try/except — safe to run repeatedly
_MIGRATIONS: list[str] = [
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD ema_200        double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD macd           double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD macd_signal    double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD volume_20d_avg bigint",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD volume_ratio   double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD beta           double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD current_ratio  double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD revenue_growth double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD eps            double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD dividend_yield double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD ret_1d         double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD ret_1w         double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD ret_1m         double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD ret_3m         double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD ret_6m         double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD ret_1y         double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD sector         text",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD industry       text",
    # Phase-1 extended technical indicators
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD ema_20         double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD bb_upper       double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD bb_lower       double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD bb_pct         double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD atr_14         double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD stoch_k        double",
    f"ALTER TABLE {KEYSPACE}.stock_quotes ADD stoch_d        double",
]


def connect(hosts: list[str] | None = None) -> bool:
    """
    Attempt to connect and bootstrap the schema.  Idempotent.
    Returns True on success.  Called from a background thread at startup.
    """
    global _cluster, _session, _available
    with _lock:
        if _available:
            return True
        try:
            from cassandra.cluster import Cluster
            from cassandra.policies import RoundRobinPolicy

            from config.providers import cfg
            _cluster = Cluster(
                hosts or [cfg.CASSANDRA_HOST],
                port=cfg.CASSANDRA_PORT,
                load_balancing_policy=RoundRobinPolicy(),
                connect_timeout=5,
                control_connection_timeout=5,
            )
            sess = _cluster.connect()
            for ddl in _SCHEMA:
                sess.execute(ddl)
            for ddl in _MIGRATIONS:
                try:
                    sess.execute(ddl)
                except Exception:
                    pass  # column already exists
            sess.set_keyspace(KEYSPACE)
            _session = sess
            _available = True
            log.info('Cassandra: connected — keyspace %s ready', KEYSPACE)
            return True
        except Exception as exc:
            log.warning('Cassandra: unavailable (%s) — CSV fallback active', exc)
            _available = False
            return False


def session():
    """Return the live Session or None if Cassandra is offline."""
    return _session


def is_available() -> bool:
    return _available


def close():
    """Graceful shutdown — called from FastAPI lifespan teardown."""
    global _cluster, _session, _available
    with _lock:
        if _cluster:
            try:
                _cluster.shutdown()
            except Exception:
                pass
        _cluster = None
        _session = None
        _available = False
