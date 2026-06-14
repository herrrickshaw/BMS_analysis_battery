"""
Bulk live-quote fetcher for all instruments in Cassandra.

Two-phase approach to stay within Yahoo Finance rate limits:
  Phase 1 — yf.download(batch_of_50, period='1y')
             One API call per 50 tickers: price, volume, 52W hi/lo, RSI, EMA
             Handles ~16K tickers with minimal requests.
  Phase 2 — individual yf.Ticker().info (throttled to 30/min)
             Fundamentals: PE, PB, ROE, OPM, market cap, D/E.
             Optional; can run after Phase 1.

Suffix strategy (per Cassandra instruments inspection):
  india  — bare NSE symbols (20MICRONS) → appends .NS
  us     — bare symbols (AAPL)          → no suffix
  europe — pre-suffixed (1COV.DE …)     → no suffix
  japan  — pre-suffixed (1301.T …)      → no suffix
  korea  — pre-suffixed (000020.KS …)   → no suffix
"""
from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pandas as pd

from db import cassandra_client as cass
from db.quote_updater import upsert_quotes

log = logging.getLogger(__name__)

MARKETS = ['india', 'us', 'europe', 'japan', 'korea', 'china']

_MARKET_CFG: dict[str, dict] = {
    'india':  {'suffix': '.NS', 'is_inr': True},
    'us':     {'suffix': '',    'is_inr': False},
    'europe': {'suffix': '',    'is_inr': False},
    'japan':  {'suffix': '',    'is_inr': False},
    'korea':  {'suffix': '',    'is_inr': False},
    'china':  {'suffix': '',    'is_inr': False},
}

_progress: dict[str, dict] = {}
_lock     = threading.Lock()
_cancel   = threading.Event()


# ── progress helpers ──────────────────────────────────────────────────────────

def get_progress() -> dict:
    with _lock:
        return dict(_progress)


def cancel():
    _cancel.set()


# ── Cassandra helpers ─────────────────────────────────────────────────────────

def _get_tickers(market: str) -> list[str]:
    s = cass.session()
    if s is None:
        return []
    try:
        rows = s.execute(
            f"SELECT yf_ticker FROM {cass.KEYSPACE}.instruments WHERE market = %s",
            (market,),
        )
        return [r.yf_ticker for r in rows if r.yf_ticker]
    except Exception as exc:
        log.error('bulk_fetcher._get_tickers(%s): %s', market, exc)
        return []


def _yf_sym(ticker: str, suffix: str) -> str:
    """Add suffix only when the ticker doesn't already carry one."""
    if not suffix:
        return ticker
    return ticker if ticker.upper().endswith(suffix.upper()) else f'{ticker}{suffix}'


# ── Phase 1: bulk OHLCV via yf.download ──────────────────────────────────────

def _compute_rsi(closes: pd.Series, period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    delta  = closes.diff().dropna()
    gains  = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    ag = gains.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    al = losses.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 2)


_RATE_LIMIT_BACKOFF = [90, 180, 300]   # seconds to wait on successive rate-limit hits


def _fetch_ohlcv_batch(
    tickers: list[str],
    suffix: str,
    is_inr: bool,
) -> list[dict]:
    """
    Download 1-year OHLCV for up to ~100 tickers in one yf.download() call,
    compute RSI-14, EMA-50, CMP, volume, 52W hi/lo per ticker.
    Retries with exponential backoff on YFRateLimitError.
    Returns a list of row dicts (without fundamentals).
    """
    try:
        import yfinance as yf
    except ImportError:
        return []

    yf_syms  = [_yf_sym(t, suffix) for t in tickers]
    sym_back = dict(zip(yf_syms, tickers))   # yf_sym → original DB ticker

    raw = None
    for attempt, backoff in enumerate([0] + _RATE_LIMIT_BACKOFF):
        if backoff:
            log.warning('_fetch_ohlcv_batch: rate-limited, sleeping %ds (attempt %d)', backoff, attempt)
            time.sleep(backoff)
        try:
            raw = yf.download(
                yf_syms,
                period='1y',
                auto_adjust=True,
                progress=False,
                threads=False,   # avoid nested thread issues
            )
            break
        except Exception as exc:
            if 'rate' in str(exc).lower() or '429' in str(exc):
                continue
            log.warning('_fetch_ohlcv_batch: download error: %s', exc)
            return []

    if raw is None or raw.empty:
        return []

    # yf.download with >1 ticker returns MultiIndex columns (field, yf_sym)
    # With 1 ticker it returns flat (field) columns.
    multi = isinstance(raw.columns, pd.MultiIndex)

    rows: list[dict] = []
    for yf_sym, orig in sym_back.items():
        try:
            if multi:
                close_col = ('Close', yf_sym)
                vol_col   = ('Volume', yf_sym)
                if close_col not in raw.columns:
                    continue
                closes  = raw[close_col].dropna()
                volumes = raw[vol_col].dropna() if vol_col in raw.columns else pd.Series(dtype=float)
            else:
                closes  = raw['Close'].dropna()
                volumes = raw['Volume'].dropna() if 'Volume' in raw.columns else pd.Series(dtype=float)

            if len(closes) < 15:
                continue

            cmp   = float(closes.iloc[-1])
            rsi   = _compute_rsi(closes)
            ema50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
            h52   = float(closes.rolling(window=min(252, len(closes))).max().iloc[-1])
            l52   = float(closes.rolling(window=min(252, len(closes))).min().iloc[-1])
            vol   = int(volumes.iloc[-1]) if not volumes.empty else None

            if math.isnan(cmp):
                continue

            # EMA-200 (long-term trend)
            ema200 = round(float(closes.ewm(span=200, adjust=False).mean().iloc[-1]), 2) \
                     if len(closes) >= 50 else None

            # MACD = EMA-12 minus EMA-26; signal = EMA-9 of MACD
            macd_val = macd_sig = None
            if len(closes) >= 26:
                ema12     = closes.ewm(span=12, adjust=False).mean()
                ema26     = closes.ewm(span=26, adjust=False).mean()
                macd_line = ema12 - ema26
                macd_val  = round(float(macd_line.iloc[-1]), 4)
                if len(macd_line) >= 9:
                    macd_sig = round(float(macd_line.ewm(span=9, adjust=False).mean().iloc[-1]), 4)

            # 20-day average volume and today's volume ratio
            vol_avg = vol_ratio = None
            if not volumes.empty and len(volumes) >= 5:
                window      = min(20, len(volumes))
                vol_avg     = int(volumes.iloc[-window:].mean())
                vol_ratio   = round(float(volumes.iloc[-1]) / vol_avg, 2) if vol_avg > 0 else None

            # Period returns — all derived from existing close series, no extra calls
            def _ret(n_back: int):
                if len(closes) <= n_back:
                    return None
                prev = float(closes.iloc[-(n_back + 1)])
                if math.isnan(prev) or prev <= 0:
                    return None
                return round((cmp - prev) / prev * 100, 2)

            ret_1d = _ret(1)
            ret_1w = _ret(5)
            ret_1m = _ret(21)
            ret_3m = _ret(63)
            ret_6m = _ret(126)
            # 1y: first available close in the downloaded window vs today
            first = float(closes.iloc[0])
            ret_1y = round((cmp - first) / first * 100, 2) \
                     if not math.isnan(first) and first > 0 else None

            if rsi is None:
                signal = 'HOLD'
            elif rsi < 30 and cmp > ema50:
                signal = 'BUY'
            elif rsi > 70 and cmp < ema50:
                signal = 'SELL'
            else:
                signal = 'HOLD'

            rows.append({
                'ticker':         orig,
                'cmp':            round(cmp,   2),
                'rsi':            rsi,
                'ema_50':         round(ema50, 2),
                'ema_200':        ema200,
                'macd':           macd_val,
                'macd_signal':    macd_sig,
                'rsi_signal':     signal,
                'high_52w':       round(h52, 2),
                'low_52w':        round(l52, 2),
                'volume':         vol,
                'volume_20d_avg': vol_avg,
                'volume_ratio':   vol_ratio,
                'ret_1d':         ret_1d,
                'ret_1w':         ret_1w,
                'ret_1m':         ret_1m,
                'ret_3m':         ret_3m,
                'ret_6m':         ret_6m,
                'ret_1y':         ret_1y,
                '_source':        'yfinance_bulk',
            })
        except Exception as exc:
            log.debug('_fetch_ohlcv_batch[%s]: %s', yf_sym, exc)

    return rows


# ── Phase 2: individual .info for fundamentals (throttled) ───────────────────

def _fetch_info_one(ticker: str, suffix: str, is_inr: bool) -> dict:
    """Fetch fundamentals for one ticker with rate-limit retry."""
    try:
        import yfinance as yf
        yf_sym = _yf_sym(ticker, suffix)
        for attempt in range(3):
            try:
                info = yf.Ticker(yf_sym).info
                if not info:
                    return {}
                mc = info.get('marketCap')

                def pct(k):
                    v = info.get(k)
                    return round(float(v) * 100, 2) if v and not math.isnan(float(v)) else None

                def rat(k):
                    v = info.get(k)
                    try:
                        f = float(v)
                        return None if math.isnan(f) else f
                    except (TypeError, ValueError):
                        return None

                return {
                    'pe':             rat('trailingPE'),
                    'pb':             rat('priceToBook'),
                    'roe':            pct('returnOnEquity'),
                    'opm':            pct('operatingMargins'),
                    'market_cap':     round(mc / (1e7 if is_inr else 1e6), 2) if mc else None,
                    'debt_to_equity': rat('debtToEquity'),
                    'beta':           rat('beta'),
                    'current_ratio':  rat('currentRatio'),
                    'revenue_growth': pct('revenueGrowth'),
                    'eps':            rat('trailingEps'),
                    'dividend_yield': pct('dividendYield'),
                }
            except Exception as exc:
                if 'rate' in str(exc).lower() or '429' in str(exc):
                    time.sleep(60 * (attempt + 1))
                else:
                    return {}
        return {}
    except Exception:
        return {}


# ── Main fetch functions ──────────────────────────────────────────────────────

def fetch_market_quotes(
    market: str,
    batch_size: int = 100,
    max_workers: int = 6,
    with_fundamentals: bool = True,
    inter_batch_delay: float = 0.5,
) -> dict:
    """
    Fetch live quotes for every instrument in one market and persist to Cassandra.
    Blocking — must be called from a background thread.
    """
    cfg    = _MARKET_CFG.get(market, {'suffix': '', 'is_inr': False})
    suffix = cfg['suffix']
    is_inr = cfg['is_inr']

    tickers = _get_tickers(market)
    if not tickers:
        result = {'market': market, 'total': 0, 'done': 0, 'errors': 0,
                  'written': 0, 'status': 'no_instruments', 'elapsed_s': 0}
        with _lock:
            _progress[market] = result
        return result

    total   = len(tickers)
    done    = errors = written = 0
    started = time.time()

    with _lock:
        _progress[market] = {
            'status': 'running', 'total': total,
            'done': 0, 'errors': 0, 'written': 0,
            'elapsed_s': 0, 'rate_per_min': 0, 'phase': 1,
        }

    log.info('bulk_fetcher: [%s] phase 1 (OHLCV) — %d tickers, batch=%d', market, total, batch_size)

    # ── Phase 1: OHLCV batches ────────────────────────────────────────────────
    phase1_rows: dict[str, dict] = {}  # ticker → partial row

    for i in range(0, total, batch_size):
        if _cancel.is_set():
            break
        batch = tickers[i:i + batch_size]
        batch_rows = _fetch_ohlcv_batch(batch, suffix, is_inr)

        for row in batch_rows:
            phase1_rows[row['ticker']] = row

        batch_done = len(batch_rows)
        batch_err  = len(batch) - batch_done
        done   += batch_done
        errors += batch_err

        elapsed = time.time() - started
        rate    = round((done + errors) / elapsed * 60, 1) if elapsed > 0 else 0
        with _lock:
            _progress[market].update({
                'done': done + errors, 'errors': errors,
                'elapsed_s': round(elapsed, 1), 'rate_per_min': rate,
            })

        if inter_batch_delay > 0:
            time.sleep(inter_batch_delay)

    # ── Phase 2: fundamentals (throttled) ─────────────────────────────────────
    if with_fundamentals and phase1_rows and not _cancel.is_set():
        with _lock:
            _progress[market]['phase'] = 2

        log.info('bulk_fetcher: [%s] phase 2 (fundamentals) — %d tickers', market, len(phase1_rows))

        fund_tickers = list(phase1_rows.keys())
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {
                pool.submit(_fetch_info_one, t, suffix, is_inr): t
                for t in fund_tickers
            }
            for fut in as_completed(futs, timeout=600):
                t = futs[fut]
                try:
                    extras = fut.result()
                    if extras:
                        phase1_rows[t].update(extras)
                except Exception:
                    pass

        elapsed = time.time() - started
        with _lock:
            _progress[market].update({'elapsed_s': round(elapsed, 1)})

    # ── Write to Cassandra ────────────────────────────────────────────────────
    if phase1_rows:
        df     = pd.DataFrame(list(phase1_rows.values()))
        written = upsert_quotes(market, df)

    elapsed = time.time() - started
    result = {
        'market': market, 'total': total, 'done': done, 'errors': errors,
        'written': written, 'elapsed_s': round(elapsed, 1),
        'status': 'cancelled' if _cancel.is_set() else 'done',
        'rate_per_min': round(total / elapsed * 60, 1) if elapsed > 0 else 0,
    }
    with _lock:
        _progress[market] = result

    log.info('bulk_fetcher: [%s] %s — %d written in %.0fs',
             market, result['status'], written, elapsed)
    return result


def fetch_all_quotes(
    markets: Optional[list[str]] = None,
    batch_size: int = 100,
    max_workers: int = 6,
    with_fundamentals: bool = True,
) -> list[dict]:
    """Fetch quotes for all markets sequentially to respect rate limits."""
    _cancel.clear()
    targets = [m for m in (markets or MARKETS) if m in _MARKET_CFG]
    results = []
    for m in targets:
        if _cancel.is_set():
            break
        results.append(fetch_market_quotes(
            m,
            batch_size=batch_size,
            max_workers=max_workers,
            with_fundamentals=with_fundamentals,
        ))
    return results
