"""
FastAPI application entry point.

This file does three things:
  1. Configures logging (plain text in dev, JSON in production).
  2. Defines the lifespan — code that runs at startup and shutdown.
  3. Wires together all routers (groups of API endpoints).

FastAPI is an async web framework.  Requests are handled by "async def"
functions that can pause and resume without blocking other requests —
important when fetching data from yfinance or Cassandra.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

# ── Router imports ────────────────────────────────────────────────────────────
# Each router file owns a group of related API endpoints.
# Keeping them in separate files stops main.py from growing to thousands of lines.
from config.providers import cfg  # typed settings singleton
from routers import export, live, portfolio, scan, sectors, upload
from routers.alerts import router as alerts_router
from routers.cassandra_router import router as cassandra_router
from routers.files import router as files_router
from routers.news import router as news_router
from routers.options_strategies import router as options_router

# ── Logging setup ─────────────────────────────────────────────────────────────
# This must happen before any module creates a logger, so we call it at the
# very top of the file before any other imports.

def _setup_logging() -> None:
    """
    Configure the root Python logger.

    When LOG_JSON=true (set by docker-compose in production), every log line is
    emitted as a single JSON object, e.g.:
        {"asctime": "2026-01-01 00:00:00", "name": "db.cassandra_client",
         "levelname": "INFO", "message": "Cassandra: connected"}

    JSON logs are easy for tools like Datadog, ELK, or CloudWatch to parse,
    filter, and alert on.  In development (LOG_JSON unset) we keep plain text.
    """
    if os.environ.get('LOG_JSON', '').lower() in ('1', 'true', 'yes'):
        try:
            from pythonjsonlogger import jsonlogger
            handler = logging.StreamHandler()
            handler.setFormatter(
                jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
            )
            # Replace any existing handlers on the root logger.
            logging.root.handlers = [handler]
            logging.root.setLevel(logging.INFO)
            return
        except ImportError:
            pass   # python-json-logger not installed — fall through to plain logging
    logging.basicConfig(level=logging.INFO)


_setup_logging()
log = logging.getLogger(__name__)


# ── Application lifespan ──────────────────────────────────────────────────────
# FastAPI's lifespan is code that runs once when the server starts and once
# when it stops.  It replaces the old @app.on_event("startup") pattern.
# The `yield` in the middle is where the app actually serves HTTP requests.

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    # Cassandra's driver is blocking (not async), so we push the connect call
    # to a thread pool with run_in_threadpool to avoid stalling the event loop.
    from db import cassandra_client as cass
    connected = await run_in_threadpool(cass.connect)
    if connected:
        log.info('Cassandra online — launching background seed')
        loop = asyncio.get_running_loop()
        from db.seeder import seed_all
        # run_in_executor = run a blocking function in a thread without awaiting it.
        # "fire-and-forget" — seeding takes minutes; we don't want startup to block.
        loop.run_in_executor(None, seed_all)
    else:
        log.warning('Cassandra offline — running in CSV-only fallback mode')

    # Start the APScheduler that fires the nightly market data prefetch.
    import scheduler as sched
    await run_in_threadpool(sched.start)

    # Subscribe to stock news and wire the portfolio price-alert monitor.
    from events.news_enricher import setup as setup_enricher
    from events.portfolio_monitor import monitor as portfolio_monitor
    setup_enricher()
    portfolio_monitor.start()

    yield   # ← the app handles HTTP requests from here until shutdown

    # ── Shutdown ──────────────────────────────────────────────────────────────
    # Stop background processes in reverse order so nothing writes after the
    # database connection closes.
    portfolio_monitor.stop()
    import scheduler as sched
    await run_in_threadpool(sched.stop)
    from db import cassandra_client as cass
    await run_in_threadpool(cass.close)


# ── App creation ──────────────────────────────────────────────────────────────
app = FastAPI(title='Stock Screener API', version='1.0.0', lifespan=lifespan)

# ── CORS middleware ───────────────────────────────────────────────────────────
# CORS (Cross-Origin Resource Sharing) is a browser security feature.
# When the React app on http://localhost:5173 calls http://localhost:8000/api,
# the browser first asks "is this backend OK with receiving requests from this
# origin?"  We answer yes by listing allowed origins here.
#
# cfg.CORS_ORIGINS defaults to localhost dev URLs.  In production, set:
#   CORS_ORIGINS='["https://yourapp.com"]'
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],    # allow GET, POST, PUT, DELETE, etc.
    allow_headers=['*'],    # allow any request headers
)

# ── Register routers ──────────────────────────────────────────────────────────
# include_router() mounts all the routes from each file into the main app.
# The URL prefixes (/api/upload, /api/scan, etc.) are set inside each router file.
app.include_router(upload.router)
app.include_router(scan.router)
app.include_router(export.router)
app.include_router(live.router)
app.include_router(sectors.router)
app.include_router(portfolio.router)
app.include_router(cassandra_router)
app.include_router(files_router)
app.include_router(news_router)
app.include_router(alerts_router)
app.include_router(options_router)


# ── Root endpoint ─────────────────────────────────────────────────────────────
@app.get('/')
def root():
    """Quick sanity check — confirms the server is running."""
    return {'status': 'ok', 'docs': '/docs'}


# ── Health check endpoint ─────────────────────────────────────────────────────
@app.get('/healthz')
async def healthz():
    """
    Liveness / readiness probe for Kubernetes and Docker HEALTHCHECK.

    Kubernetes calls this endpoint every 30 seconds.  If it returns anything
    other than a 2xx status, Kubernetes considers the pod unhealthy and
    restarts it.  We return 200 OK even when Cassandra is degraded — the app
    still works in CSV fallback mode, so restarting wouldn't help.
    """
    from db import cassandra_client as cass
    return {
        'status': 'ok',
        'cassandra': 'up' if cass.is_available() else 'degraded',
    }
