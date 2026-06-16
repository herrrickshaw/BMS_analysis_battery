from __future__ import annotations
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool


def _setup_logging() -> None:
    """Configure JSON logging when LOG_JSON=true, plain otherwise."""
    if os.environ.get('LOG_JSON', '').lower() in ('1', 'true', 'yes'):
        try:
            from pythonjsonlogger import jsonlogger
            handler = logging.StreamHandler()
            handler.setFormatter(
                jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
            )
            logging.root.handlers = [handler]
            logging.root.setLevel(logging.INFO)
            return
        except ImportError:
            pass
    logging.basicConfig(level=logging.INFO)


_setup_logging()
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    from db import cassandra_client as cass
    connected = await run_in_threadpool(cass.connect)
    if connected:
        log.info('Cassandra online — launching background seed')
        loop = asyncio.get_running_loop()
        from db.seeder import seed_all
        loop.run_in_executor(None, seed_all)   # fire-and-forget; doesn't delay startup
    else:
        log.warning('Cassandra offline — running in CSV-only fallback mode')

    # Start the daily pre-compute scheduler
    import scheduler as sched
    await run_in_threadpool(sched.start)

    # Wire event-driven news pipeline
    from events.news_enricher import setup as setup_enricher
    from events.portfolio_monitor import monitor as portfolio_monitor
    setup_enricher()
    portfolio_monitor.start()

    yield   # ← app serves requests here

    # ── Shutdown ─────────────────────────────────────────────────────────────
    portfolio_monitor.stop()
    import scheduler as sched
    await run_in_threadpool(sched.stop)
    from db import cassandra_client as cass
    await run_in_threadpool(cass.close)


from routers import upload, scan, export, live, sectors, portfolio
from routers.cassandra_router import router as cassandra_router
from routers.files import router as files_router
from routers.news import router as news_router
from routers.alerts import router as alerts_router
from config.providers import cfg

app = FastAPI(title='Stock Screener API', version='1.0.0', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

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


@app.get('/')
def root():
    return {'status': 'ok', 'docs': '/docs'}


@app.get('/healthz')
async def healthz():
    """Kubernetes liveness / readiness probe."""
    from db import cassandra_client as cass
    return {
        'status': 'ok',
        'cassandra': 'up' if cass.is_available() else 'degraded',
    }
