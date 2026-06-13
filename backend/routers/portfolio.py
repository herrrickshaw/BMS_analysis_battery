from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, Query

from parsers.excel_parser import parse_excel
from parsers.pdf_parser   import parse_pdf
from parsers.market_db    import SUPPORTED_MARKETS, db_size

router = APIRouter()

ALLOWED_EXTENSIONS = {'xlsx': parse_excel, 'xls': parse_excel, 'pdf': parse_pdf}
MAX_SIZE_MB = 20


@router.post('/api/portfolio/parse')
async def parse_portfolio(
    file: UploadFile = File(...),
    market: str = Query('india', description='Market: india | us | europe | japan | korea'),
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

    return {
        'filename':  file.filename,
        'file_type': ext,
        'market':    market,
        'stocks':    result.get('stocks', []),
        'warnings':  result.get('warnings', []),
        'meta': {
            'sheets_scanned': result.get('sheets_scanned', []),
            'pages_scanned':  result.get('pages_scanned', 0),
            'total_found':    len(result.get('stocks', [])),
            'db_size':        db_size(market),
        },
    }


@router.get('/api/portfolio/markets')
def list_markets():
    """Return supported markets with their symbol DB sizes."""
    return [
        {'id': 'india',  'label': 'India (NSE / BSE)',       'exchange': 'NSE/BSE', 'yf_suffix': '.NS / .BO'},
        {'id': 'us',     'label': 'United States (S&P 500)', 'exchange': 'NYSE/NASDAQ', 'yf_suffix': ''},
        {'id': 'europe', 'label': 'Europe (Euronext / Xetra)','exchange': 'Multi', 'yf_suffix': '.PA / .DE / .AS …'},
        {'id': 'japan',  'label': 'Japan (TSE)',              'exchange': 'TSE',    'yf_suffix': '.T'},
        {'id': 'korea',  'label': 'Korea (KRX)',              'exchange': 'KRX',    'yf_suffix': '.KS / .KQ'},
    ]
