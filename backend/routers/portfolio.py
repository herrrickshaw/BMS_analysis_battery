from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, field_validator

from parsers.excel_parser import parse_excel
from parsers.market_db import SUPPORTED_MARKETS, db_size
from parsers.pdf_parser import parse_pdf

router = APIRouter()


# ── request models ────────────────────────────────────────────────────────────

class HoldingInput(BaseModel):
    yf_ticker:      str
    name:           Optional[str]   = None
    purchase_date:  Optional[str]   = None   # ISO date YYYY-MM-DD or common formats
    purchase_price: Optional[float] = None
    quantity:       Optional[float] = None

    @field_validator('purchase_date', mode='before')
    @classmethod
    def coerce_date(cls, v):
        if v is None:
            return None
        from fetchers.history import parse_date
        d = parse_date(v)
        return d.isoformat() if d else str(v)


class HistoryRequest(BaseModel):
    market:   str = 'india'
    holdings: list[HoldingInput]

ALLOWED_EXTENSIONS = {'xlsx': parse_excel, 'xls': parse_excel, 'pdf': parse_pdf}
MAX_SIZE_MB = 20


@router.post('/api/portfolio/parse')
async def parse_portfolio(
    file: UploadFile = File(...),
    market: str = Query('india', description='Market: india | us | europe | japan | korea | china'),
):
    if market not in SUPPORTED_MARKETS:
        raise HTTPException(status_code=400, detail=f'Unknown market "{market}". '
                            f'Choose from: {", ".join(SUPPORTED_MARKETS)}')

    ext = (file.filename or '').rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415,
                            detail=f'Unsupported type ".{ext}". Upload .xlsx, .xls, or .pdf.')

    raw = await file.read()
    if len(raw) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f'File exceeds {MAX_SIZE_MB} MB.')

    parser = ALLOWED_EXTENSIONS[ext]
    try:
        result = parser(raw, market=market)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f'Could not parse file: {e}')

    stocks = result.get('stocks', [])

    # Enrich matched stocks with cached Cassandra quotes (RSI, price, signal)
    quotes_enriched = 0
    from db import cassandra_client as cass
    if stocks and cass.is_available():
        from db.quote_updater import get_quotes
        tickers = [s.get('yf_ticker') or s.get('symbol') for s in stocks
                   if s.get('yf_ticker') or s.get('symbol')]
        quotes = await run_in_threadpool(get_quotes, market, tickers)
        if quotes:
            for s in stocks:
                tk = s.get('yf_ticker') or s.get('symbol')
                if tk and tk in quotes:
                    s['quote'] = quotes[tk]
                    quotes_enriched += 1

    return {
        'filename':  file.filename,
        'file_type': ext,
        'market':    market,
        'stocks':    stocks,
        'warnings':  result.get('warnings', []),
        'meta': {
            'sheets_scanned':  result.get('sheets_scanned', []),
            'pages_scanned':   result.get('pages_scanned', 0),
            'total_found':     len(stocks),
            'db_size':         db_size(market),
            'quotes_enriched': quotes_enriched,
            'cassandra':       'online' if cass.is_available() else 'offline',
        },
    }


@router.post('/api/portfolio/history')
async def portfolio_history(req: HistoryRequest):
    """
    For each holding, retrieve:
      - Closing price on the purchase date (yfinance / Cassandra cache)
      - Current price + RSI signal (Cassandra / yfinance fallback)
      - Cost basis, current value, unrealised P&L

    Purchase date must be supplied per holding (ISO or common formats).
    Holdings without a purchase_date still get current price + RSI signal.
    """
    if req.market not in SUPPORTED_MARKETS:
        raise HTTPException(400, f'Unknown market "{req.market}"')
    if not req.holdings:
        raise HTTPException(400, 'holdings list is empty')

    holdings_input = [h.model_dump() for h in req.holdings]

    from fetchers.history import fetch_holdings_history
    result = await run_in_threadpool(fetch_holdings_history, holdings_input)
    return {'market': req.market, **result}


@router.get('/api/portfolio/markets')
def list_markets():
    """Return supported markets with their symbol DB sizes."""
    return [
        {'id': 'india',  'label': 'India (NSE / BSE)',        'exchange': 'NSE/BSE',    'yf_suffix': '.NS / .BO'},
        {'id': 'us',     'label': 'United States (S&P 500)',  'exchange': 'NYSE/NASDAQ', 'yf_suffix': ''},
        {'id': 'europe', 'label': 'Europe (Euronext / Xetra)','exchange': 'Multi',       'yf_suffix': '.PA / .DE / .AS …'},
        {'id': 'japan',  'label': 'Japan (TSE)',               'exchange': 'TSE',         'yf_suffix': '.T'},
        {'id': 'korea',  'label': 'Korea (KRX)',               'exchange': 'KRX',         'yf_suffix': '.KS / .KQ'},
        {'id': 'china',  'label': 'China (SSE / SZSE)',        'exchange': 'SSE/SZSE',    'yf_suffix': '.SS / .SZ'},
    ]
