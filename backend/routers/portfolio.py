"""
POST /api/portfolio/parse  — upload Excel or PDF, get back extracted NSE tickers.
POST /api/portfolio/fetch  — fetch live yfinance data for a given symbol list.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List

from parsers.excel_parser import parse_excel
from parsers.pdf_parser   import parse_pdf

router = APIRouter()

ALLOWED_EXTENSIONS = {
    'xlsx': parse_excel,
    'xls':  parse_excel,
    'pdf':  parse_pdf,
}
MAX_SIZE_MB = 20


@router.post('/api/portfolio/parse')
async def parse_portfolio(file: UploadFile = File(...)):
    ext = (file.filename or '').rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f'Unsupported file type ".{ext}". Upload .xlsx, .xls, or .pdf.',
        )

    raw = await file.read()
    if len(raw) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f'File exceeds {MAX_SIZE_MB} MB limit.')

    parser = ALLOWED_EXTENSIONS[ext]
    try:
        result = parser(raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f'Could not parse file: {e}')

    return {
        'filename':  file.filename,
        'file_type': ext,
        'stocks':    result.get('stocks', []),
        'warnings':  result.get('warnings', []),
        'meta': {
            'sheets_scanned': result.get('sheets_scanned', []),
            'pages_scanned':  result.get('pages_scanned', 0),
            'total_found':    len(result.get('stocks', [])),
        },
    }
