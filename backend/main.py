from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

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
from routers.options_strategies import router as options_strategies_router

app = FastAPI(title='Stock Screener API', version='1.0.0', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://localhost:3000'],
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
app.include_router(options_strategies_router)


@app.get('/')
def root():
    return {'status': 'ok', 'docs': '/docs'}
