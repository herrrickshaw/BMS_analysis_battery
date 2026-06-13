"""
Extract stock names and tickers from uploaded PDF files.

Strategy:
1. Use pdfplumber to extract tables — these preserve column structure and are
   the most reliable source in brokerage statements / portfolio reports.
2. Fall back to raw page text when no tables are found.
3. Resolve each candidate via ISIN → NSE symbol → company name fuzzy match.
"""
from __future__ import annotations

import io
import re
from parsers.symbol_db import (
    lookup_by_symbol, lookup_by_isin, lookup_by_name,
    extract_symbols_from_text,
)

_ISIN_RE   = re.compile(r'\b(INE[A-Z0-9]{9})\b')
_SYMBOL_RE = re.compile(r'\b([A-Z][A-Z0-9&]{1,14})\b')

# Headers that indicate a ticker / ISIN column in a PDF table
_TICKER_HEADERS = {'symbol', 'ticker', 'scrip', 'script', 'nse symbol',
                   'nse code', 'trading symbol', 'instrument', 'stock'}
_NAME_HEADERS   = {'name', 'company', 'company name', 'scrip name',
                   'instrument name', 'security name', 'stock name', 'issuer'}
_ISIN_HEADERS   = {'isin', 'isin number', 'isin no', 'isin code'}


def _col_role(header: str):
    h = header.lower().strip().rstrip('.')
    if h in _TICKER_HEADERS:
        return 'ticker'
    if h in _NAME_HEADERS:
        return 'name'
    if h in _ISIN_HEADERS:
        return 'isin'
    return None


def _resolve(raw_ticker='', raw_name='', raw_isin='', sheet='') -> dict | None:
    """Try to resolve a row to an NSE symbol."""
    info = None
    matched_via = ''

    if raw_ticker:
        sym = re.sub(r'[-/].*$', '', raw_ticker.upper().strip())
        info = lookup_by_symbol(sym)
        if info:
            matched_via = 'symbol'

    if not info and raw_isin and raw_isin.startswith('INE'):
        info = lookup_by_isin(raw_isin)
        if info:
            matched_via = 'ISIN'

    if not info and raw_name:
        info = lookup_by_name(raw_name)
        if info:
            matched_via = 'name (fuzzy)'

    if not info:
        return None

    return {
        'symbol':      info['symbol'],
        'name':        info.get('name') or raw_name,
        'isin':        info.get('isin') or raw_isin,
        'sheet':       sheet,
        'matched_via': matched_via,
    }


def _parse_table(table: list[list], page_label: str) -> list[dict]:
    """Extract stocks from a pdfplumber table (list of rows, first row = header)."""
    if not table or len(table) < 2:
        return []

    # Detect column roles from header row
    header = [str(c or '').strip() for c in table[0]]
    role_map: dict[str, int] = {}
    for i, h in enumerate(header):
        role = _col_role(h)
        if role and role not in role_map:
            role_map[role] = i

    if not role_map:
        return []

    results = []
    for row in table[1:]:
        if not row:
            continue
        def cell(key):
            idx = role_map.get(key)
            return str(row[idx] or '').strip() if idx is not None and idx < len(row) else ''

        rec = _resolve(
            raw_ticker=cell('ticker'),
            raw_name=cell('name'),
            raw_isin=cell('isin'),
            sheet=page_label,
        )
        if rec:
            results.append(rec)

    return results


def parse_pdf(file_bytes: bytes) -> dict:
    """
    Parse a PDF and return extracted stocks.
    Returns {stocks: [...], warnings: [], pages_scanned: int}.
    """
    import pdfplumber

    stocks: dict[str, dict] = {}
    warnings: list[str] = []
    pages_scanned = 0
    table_hits = 0

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages_scanned = len(pdf.pages)

        for page in pdf.pages:
            label = f'p{page.page_number}'

            # --- Try structured tables first ---
            tables = page.extract_tables()
            for table in tables:
                for rec in _parse_table(table, label):
                    sym = rec['symbol']
                    if sym not in stocks:
                        stocks[sym] = rec
                        table_hits += 1

            # --- Fall back: raw text scan on every page ---
            text = page.extract_text() or ''
            for rec in extract_symbols_from_text(text):
                sym = rec['symbol']
                if sym not in stocks:
                    stocks[sym] = {**rec, 'sheet': label}

    if not stocks:
        warnings.append(
            'No NSE symbols could be extracted. '
            'The PDF may be scanned (image-only) or use a non-standard format.'
        )
    elif table_hits == 0:
        warnings.append(
            'No structured tables detected — symbols were matched from raw text. '
            'Review the list carefully for false positives.'
        )

    return {
        'stocks':        list(stocks.values()),
        'warnings':      warnings,
        'pages_scanned': pages_scanned,
    }
