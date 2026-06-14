"""
Daily momentum scanner — vectorized for Cassandra Phase-1 data.
No fundamentals required; uses them when available.

Darvas / Buffett  (0–12 max with all data):
  D1  CMP within 15% of 52W high        → +2   (Darvas box ceiling)
  D2  CMP > EMA-50                       → +2   (uptrend)
  D3  Price in top 40% of 52W range      → +1   (range strength)
  D4  RSI 40–68                          → +1   (healthy momentum)
  D5  ROE > 12%       [if available]     → +1   (Buffett quality)
  D6  PE 5–30         [if available]     → +1   (Buffett value)
  D7  D/E < 1         [if available]     → +1   (Buffett safety)
  D8  CMP > EMA-200   [if available]     → +1   (secular uptrend)
  D9  MACD > signal   [if available]     → +1   (momentum confirmed)
  D10 Volume ratio > 1.5 [if available]  → +1   (volume confirms move)
  BUY ≥ 5 · WATCH ≥ 3 · AVOID < 3

Piotroski (0–8 max with all data):
  F1  ROE > 0         [if available]     → +1
  F5  D/E < 0.5       [if available]     → +1
  F8  OPM > 15%       [if available]     → +1
  F9  Revenue growth > 0 [if available]  → +1
  FX1 CMP > EMA-50                       → +1
  FX2 RSI 40–70                          → +1
  FX3 CMP within 20% of 52W high         → +1
  FX4 Current ratio > 1.5 [if available] → +1
  BUY ≥ ceil(max×0.65) · WATCH ≥ ceil(max×0.40)
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


# ── helpers ───────────────────────────────────────────────────────────────────

def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """Return column or a NaN series if missing."""
    return pd.to_numeric(df[name], errors='coerce') if name in df.columns \
        else pd.Series(np.nan, index=df.index)


def _vcrit(passes: pd.Series, valid: pd.Series) -> pd.Series:
    """Boolean criterion as object Series: True/False where valid, None elsewhere."""
    out = pd.Series(None, index=passes.index, dtype=object)
    out[valid] = passes[valid]
    return out


def _pts(crit: pd.Series, weight: int = 1) -> pd.Series:
    """Score contribution — weight where True, 0 where False or None."""
    return (crit == True).astype(int) * weight   # noqa: E712


def _r(v) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) else round(f, 2)
    except (TypeError, ValueError):
        return None


# ── Darvas / Buffett ──────────────────────────────────────────────────────────

def scan_darvas(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []

    d = df.reset_index(drop=True)
    cmp  = _col(d, 'cmp')
    h52  = _col(d, 'high_52w')
    l52  = _col(d, 'low_52w')
    e50  = _col(d, 'ema_50')
    e200 = _col(d, 'ema_200')
    rsi  = _col(d, 'rsi')
    roe  = _col(d, 'roe')
    pe   = _col(d, 'pe')
    de   = _col(d, 'debt_to_equity')
    macd = _col(d, 'macd')
    msig = _col(d, 'macd_signal')
    vr   = _col(d, 'volume_ratio')

    # ── criteria ──────────────────────────────────────────────────────────────
    h52s = h52.where(h52 > 0)  # guard div/0

    v_d1  = cmp.notna() & h52.gt(0) & h52.notna()
    v_d2  = cmp.notna() & e50.notna()
    v_d3  = cmp.notna() & h52.notna() & l52.notna() & (h52 - l52).gt(0)
    v_d4  = rsi.notna()
    v_d5  = roe.notna()
    v_d6  = pe.notna()
    v_d7  = de.notna()
    v_d8  = cmp.notna() & e200.notna()
    v_d9  = macd.notna() & msig.notna()
    v_d10 = vr.notna()

    c_near_high    = _vcrit((h52 - cmp) / h52s <= 0.15,        v_d1)
    c_above_e50    = _vcrit(cmp > e50,                          v_d2)
    c_range_str    = _vcrit((cmp - l52) / (h52 - l52) >= 0.60, v_d3)
    c_rsi_health   = _vcrit(rsi.between(40, 68),                v_d4)
    c_roe          = _vcrit(roe > 12,                           v_d5)
    c_pe           = _vcrit(pe.between(5, 30),                  v_d6)
    c_de           = _vcrit(de < 1.0,                           v_d7)
    c_above_e200   = _vcrit(cmp > e200,                         v_d8)
    c_macd_bull    = _vcrit(macd > msig,                        v_d9)
    c_vol_surge    = _vcrit(vr > 1.5,                           v_d10)

    score = (
        _pts(c_near_high, 2) + _pts(c_above_e50, 2) + _pts(c_range_str) +
        _pts(c_rsi_health) + _pts(c_roe) + _pts(c_pe) + _pts(c_de) +
        _pts(c_above_e200) + _pts(c_macd_bull) + _pts(c_vol_surge)
    )

    # base 6 always; +1 per optional criterion where data is available
    max_score = 6 + v_d5.astype(int) + v_d6.astype(int) + v_d7.astype(int) + \
                    v_d8.astype(int) + v_d9.astype(int) + v_d10.astype(int)

    signal = np.where(score >= 5, 'BUY', np.where(score >= 3, 'WATCH', 'AVOID'))

    n_avail = (v_d1.astype(int) + v_d2.astype(int) + v_d3.astype(int) + v_d4.astype(int) +
               v_d5.astype(int) + v_d6.astype(int) + v_d7.astype(int) + v_d8.astype(int) +
               v_d9.astype(int) + v_d10.astype(int))
    completeness = (n_avail / 10 * 100).round().astype(int)

    results = []
    for i in range(len(d)):
        row = d.iloc[i]
        results.append({
            'ticker':         str(row.get('ticker', '')),
            'name':           str(row.get('name', '')),
            'cmp':            _r(cmp.iat[i]),
            'high_52w':       _r(h52.iat[i]),
            'low_52w':        _r(l52.iat[i]),
            'ema_50':         _r(e50.iat[i]),
            'ema_200':        _r(e200.iat[i]),
            'rsi':            _r(rsi.iat[i]),
            'macd':           _r(macd.iat[i]),
            'macd_signal':    _r(msig.iat[i]),
            'volume_ratio':   _r(vr.iat[i]),
            'rsi_signal':     str(row.get('rsi_signal', 'HOLD') or 'HOLD'),
            'roe':            _r(roe.iat[i]),
            'pe':             _r(pe.iat[i]),
            'pb':             _r(_col(d, 'pb').iat[i]),
            'opm':            _r(_col(d, 'opm').iat[i]),
            'debt_to_equity': _r(de.iat[i]),
            'market_cap':     _r(_col(d, 'market_cap').iat[i]),
            'volume':         row.get('volume'),
            'beta':           _r(_col(d, 'beta').iat[i]),
            'current_ratio':  _r(_col(d, 'current_ratio').iat[i]),
            'revenue_growth': _r(_col(d, 'revenue_growth').iat[i]),
            'eps':            _r(_col(d, 'eps').iat[i]),
            'dividend_yield': _r(_col(d, 'dividend_yield').iat[i]),
            'ret_1d':         _r(_col(d, 'ret_1d').iat[i]),
            'ret_1w':         _r(_col(d, 'ret_1w').iat[i]),
            'ret_1m':         _r(_col(d, 'ret_1m').iat[i]),
            'ret_3m':         _r(_col(d, 'ret_3m').iat[i]),
            'ret_6m':         _r(_col(d, 'ret_6m').iat[i]),
            'ret_1y':         _r(_col(d, 'ret_1y').iat[i]),
            'score':          int(score.iat[i]),
            'max_score':      int(max_score.iat[i]),
            'signal':         str(signal[i]),
            'completeness':   int(completeness.iat[i]),
            'criteria': {
                'near_52w_high': c_near_high.iat[i],
                'above_ema50':   c_above_e50.iat[i],
                'range_strength': c_range_str.iat[i],
                'rsi_healthy':   c_rsi_health.iat[i],
                'buffett_roe':   c_roe.iat[i],
                'buffett_pe':    c_pe.iat[i],
                'buffett_de':    c_de.iat[i],
                'above_ema200':  c_above_e200.iat[i],
                'macd_bull':     c_macd_bull.iat[i],
                'volume_surge':  c_vol_surge.iat[i],
            },
            '_exchange': str(row.get('_exchange', '')),
        })
    return results


# ── Piotroski (simplified) ────────────────────────────────────────────────────

def scan_piotroski(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []

    d = df.reset_index(drop=True)
    cmp  = _col(d, 'cmp')
    h52  = _col(d, 'high_52w')
    e50  = _col(d, 'ema_50')
    rsi  = _col(d, 'rsi')
    roe  = _col(d, 'roe')
    opm  = _col(d, 'opm')
    de   = _col(d, 'debt_to_equity')
    cr   = _col(d, 'current_ratio')
    rg   = _col(d, 'revenue_growth')

    v_f1  = roe.notna()
    v_f5  = de.notna()
    v_f8  = opm.notna()
    v_f9  = rg.notna()
    v_fx1 = cmp.notna() & e50.notna()
    v_fx2 = rsi.notna()
    v_fx3 = cmp.notna() & h52.gt(0) & h52.notna()
    v_fx4 = cr.notna()

    h52s = h52.where(h52 > 0)

    c_f1  = _vcrit(roe > 0,                            v_f1)
    c_f5  = _vcrit(de < 0.5,                           v_f5)
    c_f8  = _vcrit(opm > 15,                           v_f8)
    c_f9  = _vcrit(rg > 0,                             v_f9)
    c_fx1 = _vcrit(cmp > e50,                          v_fx1)
    c_fx2 = _vcrit(rsi.between(40, 70),                v_fx2)
    c_fx3 = _vcrit((h52 - cmp) / h52s <= 0.20,        v_fx3)
    c_fx4 = _vcrit(cr > 1.5,                           v_fx4)

    score = (_pts(c_f1) + _pts(c_f5) + _pts(c_f8) + _pts(c_f9) +
             _pts(c_fx1) + _pts(c_fx2) + _pts(c_fx3) + _pts(c_fx4))

    max_score = (v_f1.astype(int) + v_f5.astype(int) + v_f8.astype(int) + v_f9.astype(int) +
                 v_fx1.astype(int) + v_fx2.astype(int) + v_fx3.astype(int) + v_fx4.astype(int))
    max_score = max_score.clip(lower=1)  # avoid div/0 on completely empty rows

    buy_thresh   = (max_score * 0.65).apply(math.ceil)
    watch_thresh = (max_score * 0.40).apply(math.ceil)
    signal = np.where(score >= buy_thresh, 'BUY',
             np.where(score >= watch_thresh, 'WATCH', 'AVOID'))

    n_avail = (v_f1.astype(int) + v_f5.astype(int) + v_f8.astype(int) + v_f9.astype(int) +
               v_fx1.astype(int) + v_fx2.astype(int) + v_fx3.astype(int) + v_fx4.astype(int))
    completeness = (n_avail / 8 * 100).round().astype(int)

    results = []
    for i in range(len(d)):
        row = d.iloc[i]
        ms  = int(max_score.iat[i])
        results.append({
            'ticker':         str(row.get('ticker', '')),
            'name':           str(row.get('name', '')),
            'cmp':            _r(cmp.iat[i]),
            'high_52w':       _r(h52.iat[i]),
            'ema_50':         _r(e50.iat[i]),
            'ema_200':        _r(_col(d, 'ema_200').iat[i]),
            'rsi':            _r(rsi.iat[i]),
            'rsi_signal':     str(row.get('rsi_signal', 'HOLD') or 'HOLD'),
            'roe':            _r(roe.iat[i]),
            'opm':            _r(opm.iat[i]),
            'debt_to_equity': _r(de.iat[i]),
            'current_ratio':  _r(cr.iat[i]),
            'revenue_growth': _r(rg.iat[i]),
            'market_cap':     _r(_col(d, 'market_cap').iat[i]),
            'beta':           _r(_col(d, 'beta').iat[i]),
            'eps':            _r(_col(d, 'eps').iat[i]),
            'dividend_yield': _r(_col(d, 'dividend_yield').iat[i]),
            'ret_1d':         _r(_col(d, 'ret_1d').iat[i]),
            'ret_1w':         _r(_col(d, 'ret_1w').iat[i]),
            'ret_1m':         _r(_col(d, 'ret_1m').iat[i]),
            'ret_3m':         _r(_col(d, 'ret_3m').iat[i]),
            'ret_6m':         _r(_col(d, 'ret_6m').iat[i]),
            'ret_1y':         _r(_col(d, 'ret_1y').iat[i]),
            'score':          int(score.iat[i]),
            'max_score':      ms,
            'signal':         str(signal[i]),
            'completeness':   int(completeness.iat[i]),
            'criteria': {
                'F1_roe_positive':   c_f1.iat[i],
                'F5_low_leverage':   c_f5.iat[i],
                'F8_op_margin':      c_f8.iat[i],
                'F9_rev_growth':     c_f9.iat[i],
                'FX1_above_ema50':   c_fx1.iat[i],
                'FX2_rsi_range':     c_fx2.iat[i],
                'FX3_near_high':     c_fx3.iat[i],
                'FX4_current_ratio': c_fx4.iat[i],
            },
            '_exchange': str(row.get('_exchange', '')),
        })
    return results
