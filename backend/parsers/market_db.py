"""
Market-specific symbol databases and extraction rules.

Each market config provides:
  - load()            → loads/returns {yf_ticker → {name, ...}}
  - by_code           → {raw_code → yf_ticker}  (for code-first markets like JP/KR)
  - pattern           → compiled regex matching native tickers in free text
  - yf_suffix         → exchange suffix appended when building yfinance symbol
"""
from __future__ import annotations

import csv
import os
import re
from difflib import get_close_matches
from typing import Optional

_DATA = os.path.join(os.path.dirname(__file__), '..', '..', 'data')


# ── loaders ───────────────────────────────────────────────────────────────────

def _load_csv(path: str, yf_col: str, name_col: str,
              code_col: Optional[str] = None, extra_cols: list[str] | None = None) -> dict:
    """Generic CSV loader → {yf_ticker: {name, code?, ...}}"""
    out: dict[str, dict] = {}
    by_code: dict[str, str] = {}
    by_name: dict[str, str] = {}
    try:
        with open(path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                yf  = row.get(yf_col, '').strip()
                name = row.get(name_col, '').strip()
                code = row.get(code_col, '').strip() if code_col else ''
                if not yf:
                    continue
                entry = {'yf_ticker': yf, 'name': name}
                if code:
                    entry['code'] = code
                for c in (extra_cols or []):
                    entry[c] = row.get(c, '').strip()
                out[yf] = entry
                if code:
                    by_code[code] = yf
                if name:
                    by_name[name.lower()] = yf
    except FileNotFoundError:
        pass
    return {'by_yf': out, 'by_code': by_code, 'by_name': by_name}


# Module-level cache per market
_CACHE: dict[str, dict] = {}


def _db(market: str) -> dict:
    if market in _CACHE:
        return _CACHE[market]

    if market == 'india':
        # Reuse symbol_db; build a compatible dict here
        from parsers.symbol_db import _load as _nse_load, _BY_SYMBOL, _BY_NAME
        _nse_load()
        by_yf  = {s: {'yf_ticker': s + '.NS', 'name': v['name'], 'code': s}
                  for s, v in _BY_SYMBOL.items()}
        by_code = {s: s + '.NS' for s in _BY_SYMBOL}
        by_name = {n: s + '.NS' for n, s in _BY_NAME.items()}
        result = {'by_yf': by_yf, 'by_code': by_code, 'by_name': by_name}

    elif market == 'us':
        result = _load_csv(
            os.path.join(_DATA, 'sp500_list.csv'),
            yf_col='Symbol', name_col='Security',
            extra_cols=['GICS Sector'],
        )

    elif market == 'europe':
        result = _load_csv(
            os.path.join(_DATA, 'europe_list.csv'),
            yf_col='yf_ticker', name_col='name',
            extra_cols=['sector'],
        )

    elif market == 'japan':
        result = _load_csv(
            os.path.join(_DATA, 'japan_list.csv'),
            yf_col='yf_ticker', name_col='name', code_col='code',
        )

    elif market == 'korea':
        result = _load_csv(
            os.path.join(_DATA, 'korea_list.csv'),
            yf_col='yf_ticker', name_col='name', code_col='code',
            extra_cols=['market'],
        )

    else:
        result = {'by_yf': {}, 'by_code': {}, 'by_name': {}}

    _CACHE[market] = result
    return result


# ── market configs ─────────────────────────────────────────────────────────────

# Regex patterns for recognising native tickers in raw text
_PATTERNS = {
    'india':  re.compile(r'\b([A-Z][A-Z0-9&]{1,14})\b'),
    'us':     re.compile(r'\b([A-Z]{1,5})\b'),
    'europe': re.compile(r'\b([A-Z0-9]{2,8}\.[A-Z]{2})\b'),
    'japan':  re.compile(r'\b(\d{4,5}(?:\.T)?)\b'),
    'korea':  re.compile(r'\b(\d{6}(?:\.KS|\.KQ)?)\b'),
}

# Exchange suffix added to raw code when querying yfinance
_YF_SUFFIX = {
    'india':  '.NS',
    'us':     '',
    'europe': '',       # suffix already embedded in yf_ticker
    'japan':  '.T',
    'korea':  '.KS',
}

_ISIN_PREFIX = {
    'india':  'IN',
    'us':     'US',
    'europe': None,   # multiple country prefixes
    'japan':  'JP',
    'korea':  'KR',
}

_ISIN_RE = re.compile(r'\b([A-Z]{2}[A-Z0-9]{10})\b')


# ── public API ─────────────────────────────────────────────────────────────────

SUPPORTED_MARKETS = ['india', 'us', 'europe', 'japan', 'korea']


def lookup(raw: str, market: str) -> Optional[dict]:
    """
    Resolve a raw ticker/code string to {yf_ticker, name, ...}.
    For India, raw can be the NSE symbol (no suffix needed).
    """
    db = _db(market)
    raw = raw.strip()

    # Try direct yf_ticker match
    if raw in db['by_yf']:
        return db['by_yf'][raw]

    # Try code match (Japan / Korea strip the .T/.KS suffix)
    code = raw.split('.')[0]
    if code in db['by_code']:
        yf = db['by_code'][code]
        return db['by_yf'].get(yf)

    # Build yf symbol with suffix and try again
    suffix = _YF_SUFFIX.get(market, '')
    if suffix and not raw.endswith(suffix):
        yf_candidate = raw + suffix
        if yf_candidate in db['by_yf']:
            return db['by_yf'][yf_candidate]

    return None


def lookup_by_name(name: str, market: str) -> Optional[dict]:
    db = _db(market)
    key = name.lower().strip()
    if key in db['by_name']:
        yf = db['by_name'][key]
        return db['by_yf'].get(yf)
    # fuzzy
    matches = get_close_matches(key, list(db['by_name'].keys()), n=1, cutoff=0.6)
    if matches:
        yf = db['by_name'][matches[0]]
        return db['by_yf'].get(yf)
    return None


def extract_from_text(text: str, market: str) -> list[dict]:
    """Scan raw text for tickers/codes matching the given market's pattern."""
    db = _db(market)
    pattern = _PATTERNS.get(market)
    found: dict[str, dict] = {}

    # ISIN scan first (most reliable)
    isin_prefix = _ISIN_PREFIX.get(market)
    if isin_prefix:
        for isin in _ISIN_RE.findall(text):
            if not isin.startswith(isin_prefix):
                continue
            # For India, delegate to symbol_db ISIN lookup
            if market == 'india':
                from parsers.symbol_db import lookup_by_isin
                info = lookup_by_isin(isin)
                if info:
                    yf = info['symbol'] + '.NS'
                    if yf not in found:
                        found[yf] = {'yf_ticker': yf, 'name': info['name'],
                                     'matched_via': 'ISIN', 'raw': isin}

    if pattern:
        for raw in pattern.findall(text):
            info = lookup(raw, market)
            if info and info['yf_ticker'] not in found:
                found[info['yf_ticker']] = {**info, 'matched_via': 'symbol', 'raw': raw}

    return list(found.values())


def db_size(market: str) -> int:
    return len(_db(market)['by_yf'])
