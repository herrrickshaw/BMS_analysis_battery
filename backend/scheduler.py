"""
APScheduler-based daily pre-compute for all market quotes.

The scheduler runs fetch_all_quotes() once per day (default: midnight server
time, configurable via PREFETCH_HOUR env var).  Results land in Cassandra
stock_quotes so every /api/portfolio and /api/live/scan response is served
from cached data — no live yfinance call on the hot path.

Lifecycle:
  start()  — called from FastAPI lifespan startup
  stop()   — called from FastAPI lifespan shutdown
  trigger() — kick off an immediate run (skips schedule, still background)
  status() — returns next_run, last_run, last_result dict
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ── state ─────────────────────────────────────────────────────────────────────

_state: dict = {
    'next_run':    None,   # ISO string
    'last_run':    None,   # ISO string
    'last_status': None,   # 'success' | 'error' | 'running' | 'never'
    'last_result': None,   # list[dict] from fetch_all_quotes
    'last_elapsed_s': None,
    'total_written': None,
}
_state_lock = threading.Lock()

_scheduler = None
_running   = threading.Event()   # set while a fetch job is active


# ── job ───────────────────────────────────────────────────────────────────────

def _run_prefetch():
    """The actual job executed by APScheduler."""
    if _running.is_set():
        log.warning('scheduler: prefetch already running — skipping this fire')
        return

    _running.set()
    started = time.time()
    with _state_lock:
        _state['last_run']    = datetime.now(timezone.utc).isoformat()
        _state['last_status'] = 'running'

    log.info('scheduler: daily prefetch starting')
    try:
        from db.bulk_fetcher import fetch_all_quotes
        results = fetch_all_quotes(with_fundamentals=False)

        total_written = sum(r.get('written', 0) for r in results)
        elapsed = round(time.time() - started, 1)

        with _state_lock:
            _state['last_status']   = 'success'
            _state['last_result']   = results
            _state['last_elapsed_s'] = elapsed
            _state['total_written'] = total_written

        log.info('scheduler: prefetch done — %d quotes written in %.0fs',
                 total_written, elapsed)
    except Exception as exc:
        elapsed = round(time.time() - started, 1)
        with _state_lock:
            _state['last_status']   = 'error'
            _state['last_result']   = [{'error': str(exc)}]
            _state['last_elapsed_s'] = elapsed
        log.error('scheduler: prefetch failed after %.0fs: %s', elapsed, exc)
    finally:
        _running.clear()


# ── public API ────────────────────────────────────────────────────────────────

def start():
    """
    Create and start the APScheduler.  Call from FastAPI lifespan startup.
    Schedule: daily at PREFETCH_HOUR:PREFETCH_MINUTE (default 00:00 local time).
    """
    global _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.warning('scheduler: apscheduler not installed — daily prefetch disabled')
        return

    from config.providers import cfg
    hour   = cfg.PREFETCH_HOUR
    minute = cfg.PREFETCH_MINUTE

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _run_prefetch,
        trigger=CronTrigger(hour=hour, minute=minute),
        id='daily_prefetch',
        name='Daily market data prefetch',
        max_instances=1,
        misfire_grace_time=3600,   # still runs if server was down at midnight
        replace_existing=True,
    )
    _scheduler.start()

    next_job = _scheduler.get_job('daily_prefetch')
    next_run = next_job.next_run_time.isoformat() if next_job and next_job.next_run_time else None
    with _state_lock:
        _state['next_run']    = next_run
        _state['last_status'] = 'never'

    log.info('scheduler: started — daily prefetch at %02d:%02d, next run: %s',
             hour, minute, next_run)


def stop():
    """Shut down APScheduler gracefully. Call from FastAPI lifespan teardown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info('scheduler: stopped')
    _scheduler = None


def trigger():
    """
    Fire an immediate prefetch in a background thread (non-blocking).
    Returns False if a run is already in progress.
    """
    if _running.is_set():
        return False
    t = threading.Thread(target=_run_prefetch, daemon=True, name='manual_prefetch')
    t.start()
    return True


def status() -> dict:
    """Return current scheduler state."""
    with _state_lock:
        snap = dict(_state)

    # Refresh next_run from the live scheduler
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job('daily_prefetch')
        if job and job.next_run_time:
            snap['next_run'] = job.next_run_time.isoformat()

    snap['is_running'] = _running.is_set()
    snap['scheduler_active'] = bool(_scheduler and _scheduler.running)
    return snap


def pause():
    if _scheduler and _scheduler.running:
        _scheduler.pause_job('daily_prefetch')


def resume():
    if _scheduler and _scheduler.running:
        _scheduler.resume_job('daily_prefetch')
