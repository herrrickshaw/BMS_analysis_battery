"""
NSE symbol lookup built from the NSE equity list CSV.
Provides company-name → NSE symbol fuzzy matching and ISIN lookup.
"""
from __future__ import annotations

import csv
import os
import re
from difflib import get_close_matches
from typing import Optional

_CSV = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'nse_equity_list.csv')

# symbol → {name, isin}
_BY_SYMBOL: dict[str, dict] = {}
# isin → symbol
_BY_ISIN: dict[str, str] = {}
# lower-stripped name → symbol
_BY_NAME: dict[str, str] = {}
# list of all company names for fuzzy matching
_ALL_NAMES: list[str] = []


def _load():
    if _BY_SYMBOL:
        return
    try:
        with open(_CSV, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym  = row.get('SYMBOL', '').strip()
                name = row.get('NAME OF COMPANY', '').strip()
                isin = row.get('ISIN NUMBER', '').strip()
                if not sym:
                    continue
                _BY_SYMBOL[sym] = {'name': name, 'isin': isin, 'symbol': sym}
                if isin:
                    _BY_ISIN[isin] = sym
                if name:
                    _BY_NAME[name.lower()] = sym
                    _ALL_NAMES.append(name)
    except FileNotFoundError:
        pass


def lookup_by_symbol(sym: str) -> Optional[dict]:
    _load()
    return _BY_SYMBOL.get(sym.upper().strip())


def lookup_by_isin(isin: str) -> Optional[dict]:
    _load()
    sym = _BY_ISIN.get(isin.strip())
    return _BY_SYMBOL.get(sym) if sym else None


def lookup_by_name(name: str, cutoff: float = 0.6) -> Optional[dict]:
    _load()
    key = name.lower().strip()
    # exact match first
    if key in _BY_NAME:
        return _BY_SYMBOL[_BY_NAME[key]]
    # fuzzy
    matches = get_close_matches(key, list(_BY_NAME.keys()), n=1, cutoff=cutoff)
    if matches:
        return _BY_SYMBOL[_BY_NAME[matches[0]]]
    return None


def is_valid_nse_symbol(sym: str) -> bool:
    """True if sym is in the NSE equity list."""
    _load()
    return sym.upper().strip() in _BY_SYMBOL


# NSE ticker regex: 1-15 uppercase letters/digits/& (no spaces)
_NSE_PATTERN = re.compile(r'\b([A-Z][A-Z0-9&]{1,14})\b')
# ISIN regex: INE followed by 9 alphanumeric chars
_ISIN_PATTERN = re.compile(r'\b(INE[A-Z0-9]{9})\b')


def extract_symbols_from_text(text: str) -> list[dict]:
    """Scan raw text for ISIN codes and NSE ticker patterns."""
    _load()
    found: dict[str, dict] = {}

    # ISINs first — most reliable
    for isin in _ISIN_PATTERN.findall(text):
        info = lookup_by_isin(isin)
        if info and info['symbol'] not in found:
            found[info['symbol']] = {**info, 'matched_via': 'ISIN', 'raw': isin}

    # NSE symbol patterns
    for sym in _NSE_PATTERN.findall(text):
        if sym in found:
            continue
        info = lookup_by_symbol(sym)
        if info:
            found[sym] = {**info, 'matched_via': 'symbol', 'raw': sym}

    return list(found.values())
