"""
Extract stock names and tickers from uploaded Excel files.

Strategy (in order):
1. Find columns whose headers match known ticker/name/ISIN aliases.
2. For each row, resolve ticker via: direct symbol → ISIN → company name fuzzy match.
3. Return a deduplicated list of {symbol, name, isin, sheet, row, matched_via}.
"""
from __future__ import annotations

import re
from typing import Optional
import openpyxl
from parsers.symbol_db import (
    lookup_by_symbol, lookup_by_isin, lookup_by_name,
    extract_symbols_from_text, is_valid_nse_symbol,
)

# Column header → canonical role
_TICKER_ALIASES = {
    'symbol', 'ticker', 'nse code', 'nse symbol', 'bse code', 'scrip',
    'scrip code', 'trading symbol', 'stock symbol', 'nse ticker',
    'instrument', 'stock', 'script', 'equity',
}
_NAME_ALIASES = {
    'name', 'company', 'company name', 'stock name', 'scrip name',
    'instrument name', 'security name', 'issuer', 'issuer name',
}
_ISIN_ALIASES = {'isin', 'isin number', 'isin code', 'isin no'}


def _header_role(header: str) -> Optional[str]:
    h = header.lower().strip().rstrip('.')
    if h in _TICKER_ALIASES:
        return 'ticker'
    if h in _NAME_ALIASES:
        return 'name'
    if h in _ISIN_ALIASES:
        return 'isin'
    return None


def _find_header_row(ws, max_scan: int = 20) -> Optional[tuple[int, dict[str, int]]]:
    """Find the first row that has recognisable ticker/name/ISIN headers."""
    for r in range(1, min(max_scan + 1, ws.max_row + 1)):
        role_map: dict[str, int] = {}
        for c in range(1, ws.max_column + 1):
            val = ws.cell(r, c).value
            if val is None:
                continue
            role = _header_role(str(val))
            if role and role not in role_map:
                role_map[role] = c
        if role_map:
            return r, role_map
    return None


def parse_excel(file_bytes: bytes) -> dict:
    """
    Parse an Excel workbook and return extracted stocks.
    Returns {stocks: [...], warnings: [], sheets_scanned: [...]}.
    """
    import io
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)

    stocks: dict[str, dict] = {}  # keyed by NSE symbol to deduplicate
    warnings: list[str] = []
    sheets_scanned: list[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        result = _find_header_row(ws)
        if result is None:
            # No structured headers — try extracting text from whole sheet
            text_parts = []
            for row in ws.iter_rows(max_row=500, values_only=True):
                for cell in row:
                    if cell:
                        text_parts.append(str(cell))
            found = extract_symbols_from_text(' '.join(text_parts))
            if found:
                sheets_scanned.append(sheet_name)
                for s in found:
                    sym = s['symbol']
                    if sym not in stocks:
                        stocks[sym] = {**s, 'sheet': sheet_name}
            continue

        header_row, role_map = result
        sheets_scanned.append(sheet_name)
        ticker_col = role_map.get('ticker')
        name_col   = role_map.get('name')
        isin_col   = role_map.get('isin')

        unresolved_names: list[str] = []

        for row in ws.iter_rows(min_row=header_row + 1, max_row=500, values_only=True):
            raw_ticker = str(row[ticker_col - 1]).strip() if ticker_col and row[ticker_col - 1] else ''
            raw_name   = str(row[name_col   - 1]).strip() if name_col   and row[name_col   - 1] else ''
            raw_isin   = str(row[isin_col   - 1]).strip() if isin_col   and row[isin_col   - 1] else ''

            if not any([raw_ticker, raw_name, raw_isin]):
                continue

            info = None
            matched_via = ''

            # Try in priority order: symbol → ISIN → name
            if raw_ticker:
                sym = re.sub(r'\s*[-/].*$', '', raw_ticker.upper())  # strip "-EQ", "/NSE" suffixes
                info = lookup_by_symbol(sym)
                if info:
                    matched_via = 'symbol'
                elif is_valid_nse_symbol(sym):
                    info = {'symbol': sym, 'name': raw_name or sym, 'isin': raw_isin}
                    matched_via = 'symbol (unverified)'

            if not info and raw_isin and raw_isin.startswith('INE'):
                info = lookup_by_isin(raw_isin)
                if info:
                    matched_via = 'ISIN'

            if not info and raw_name:
                info = lookup_by_name(raw_name)
                if info:
                    matched_via = 'name (fuzzy)'
                else:
                    unresolved_names.append(raw_name)

            if info:
                sym = info['symbol']
                if sym not in stocks:
                    stocks[sym] = {
                        'symbol': sym,
                        'name':   info.get('name') or raw_name,
                        'isin':   info.get('isin') or raw_isin,
                        'sheet':  sheet_name,
                        'matched_via': matched_via,
                    }

        if unresolved_names:
            sample = unresolved_names[:5]
            warnings.append(
                f"Sheet '{sheet_name}': {len(unresolved_names)} names could not be matched "
                f"to NSE symbols (e.g. {', '.join(sample)})"
            )

    return {
        'stocks': list(stocks.values()),
        'warnings': warnings,
        'sheets_scanned': sheets_scanned,
    }
