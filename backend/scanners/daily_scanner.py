"""
Daily momentum scanner — designed for Cassandra Phase-1 data (OHLCV + RSI + EMA50).
No fundamentals required; enriches results when pe/roe/de are available.

Darvas / Buffett  (0–7):
  D1  CMP within 15% of 52W high        → +2   (Darvas box ceiling)
  D2  CMP > EMA-50                       → +2   (uptrend)
  D3  Price in top 40% of 52W range      → +1   (range strength)
  D4  RSI 40–68, healthy momentum        → +1   (not overbought)
  D5  ROE > 12%  [if available]          → +1   (Buffett quality)
  D6  PE < 30    [if available]          → +1   (Buffett value)
  D7  D/E < 1    [if available]          → +1   (Buffett safety)
  BUY ≥ 5 · WATCH ≥ 3 · AVOID < 3

Piotroski (0–6):
  F1  ROE > 0    [if available]          → +1
  F5  D/E < 0.5  [if available]          → +1
  F8  OPM > 15%  [if available]          → +1
  FX1 CMP > EMA-50                       → +1   (trend proxy)
  FX2 RSI 40–70 (not extreme)            → +1   (momentum proxy)
  FX3 CMP within 20% of 52W high        → +1   (relative strength)
  BUY ≥ 4 · WATCH ≥ 2 · AVOID < 2
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd


def _f(row: pd.Series, key: str) -> Optional[float]:
    try:
        v = float(row.get(key))
        return None if (isinstance(v, float) and math.isnan(v)) else v
    except (TypeError, ValueError):
        return None


def _bool(val) -> Optional[bool]:
    if val is None:
        return None
    return bool(val)


# ── Darvas / Buffett ──────────────────────────────────────────────────────────

def _darvas_score(row: pd.Series) -> dict:
    cmp   = _f(row, 'cmp')
    h52   = _f(row, 'high_52w')
    l52   = _f(row, 'low_52w')
    ema50 = _f(row, 'ema_50')
    rsi   = _f(row, 'rsi')
    roe   = _f(row, 'roe')
    pe    = _f(row, 'pe')
    de    = _f(row, 'debt_to_equity')

    c: dict = {}
    score = 0

    # D1: within 15% of 52W high
    if cmp is not None and h52 and h52 > 0:
        c['near_52w_high'] = (h52 - cmp) / h52 <= 0.15
    else:
        c['near_52w_high'] = None
    if c['near_52w_high']:
        score += 2

    # D2: above EMA50
    if cmp is not None and ema50:
        c['above_ema50'] = cmp > ema50
    else:
        c['above_ema50'] = None
    if c['above_ema50']:
        score += 2

    # D3: top 40% of 52W range
    if cmp is not None and h52 and l52 is not None and (h52 - l52) > 0:
        c['range_strength'] = (cmp - l52) / (h52 - l52) >= 0.60
    else:
        c['range_strength'] = None
    if c['range_strength']:
        score += 1

    # D4: RSI 40-68
    if rsi is not None:
        c['rsi_healthy'] = 40 <= rsi <= 68
    else:
        c['rsi_healthy'] = None
    if c['rsi_healthy']:
        score += 1

    # D5-D7: Buffett overlay (optional)
    if roe is not None:
        c['buffett_roe'] = roe > 12
        if c['buffett_roe']:
            score += 1
    if pe is not None:
        c['buffett_pe'] = pe < 30
        if c['buffett_pe']:
            score += 1
    if de is not None:
        c['buffett_de'] = de < 1.0
        if c['buffett_de']:
            score += 1

    max_score = 6 + sum(1 for k in ('buffett_roe', 'buffett_pe', 'buffett_de') if k in c)

    signal = 'BUY' if score >= 5 else ('WATCH' if score >= 3 else 'AVOID')

    avail  = sum(1 for v in c.values() if v is not None)
    total  = len(c)
    compl  = round(avail / total * 100) if total else 0

    return {
        'ticker':        str(row.get('ticker', '')),
        'name':          str(row.get('name', '')),
        'cmp':           round(cmp, 2) if cmp else None,
        'high_52w':      round(h52, 2) if h52 else None,
        'low_52w':       round(l52, 2) if l52 else None,
        'ema_50':        round(ema50, 2) if ema50 else None,
        'rsi':           round(rsi, 2) if rsi else None,
        'rsi_signal':    str(row.get('rsi_signal', 'HOLD') or 'HOLD'),
        'roe':           round(roe, 2) if roe else None,
        'pe':            round(pe, 2) if pe else None,
        'pb':            _f(row, 'pb'),
        'opm':           _f(row, 'opm'),
        'debt_to_equity': round(de, 2) if de else None,
        'market_cap':    _f(row, 'market_cap'),
        'volume':        row.get('volume'),
        'score':         score,
        'max_score':     max_score,
        'signal':        signal,
        'completeness':  compl,
        'criteria':      c,
        '_exchange':     str(row.get('_exchange', '')),
    }


def scan_darvas(df: pd.DataFrame) -> list[dict]:
    return [_darvas_score(row) for _, row in df.iterrows()]


# ── Piotroski (simplified) ────────────────────────────────────────────────────

def _piotroski_score(row: pd.Series) -> dict:
    cmp   = _f(row, 'cmp')
    h52   = _f(row, 'high_52w')
    ema50 = _f(row, 'ema_50')
    rsi   = _f(row, 'rsi')
    roe   = _f(row, 'roe')
    opm   = _f(row, 'opm')
    de    = _f(row, 'debt_to_equity')

    f: dict = {}
    score = 0

    # Fundamental signals (when available)
    if roe is not None:
        f['F1_roa_positive'] = roe > 0
        if f['F1_roa_positive']:
            score += 1
    if de is not None:
        f['F5_low_leverage'] = de < 0.5
        if f['F5_low_leverage']:
            score += 1
    if opm is not None:
        f['F8_operating_margin'] = opm > 15
        if f['F8_operating_margin']:
            score += 1

    # Price/momentum proxies (always computable)
    if cmp is not None and ema50:
        f['FX_above_ema50'] = cmp > ema50
        if f['FX_above_ema50']:
            score += 1

    if rsi is not None:
        f['FX_rsi_range'] = 40 <= rsi <= 70
        if f['FX_rsi_range']:
            score += 1

    if cmp is not None and h52 and h52 > 0:
        f['FX_near_high'] = (h52 - cmp) / h52 <= 0.20
        if f['FX_near_high']:
            score += 1

    max_score = len(f)
    # Scale thresholds to available criteria so sparse data still produces signals
    buy_thresh   = max(3, round(max_score * 0.65))
    watch_thresh = max(2, round(max_score * 0.40))
    signal = 'BUY' if score >= buy_thresh else ('WATCH' if score >= watch_thresh else 'AVOID')

    avail = sum(1 for v in f.values() if v is not None)
    compl = round(avail / max_score * 100) if max_score else 0

    return {
        'ticker':        str(row.get('ticker', '')),
        'name':          str(row.get('name', '')),
        'cmp':           round(cmp, 2) if cmp else None,
        'high_52w':      round(h52, 2) if h52 else None,
        'ema_50':        round(ema50, 2) if ema50 else None,
        'rsi':           round(rsi, 2) if rsi else None,
        'rsi_signal':    str(row.get('rsi_signal', 'HOLD') or 'HOLD'),
        'roe':           round(roe, 2) if roe else None,
        'opm':           round(opm, 2) if opm else None,
        'debt_to_equity': round(de, 2) if de else None,
        'market_cap':    _f(row, 'market_cap'),
        'score':         score,
        'max_score':     max_score,
        'signal':        signal,
        'completeness':  compl,
        'criteria':      f,
        '_exchange':     str(row.get('_exchange', '')),
    }


def scan_piotroski(df: pd.DataFrame) -> list[dict]:
    return [_piotroski_score(row) for _, row in df.iterrows()]
