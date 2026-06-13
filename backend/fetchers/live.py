"""
Live data fetcher: NSE archive CSVs for symbol lists, yfinance for fundamentals.

Exchange suffix conventions (yfinance):
  NSE     → {ticker}.NS   (e.g. TCS.NS)
  BSE     → {ticker}.BO   (e.g. 500325.BO)
  NASDAQ  → {ticker}      (e.g. INFY)

Unit notes from yfinance:
  Percent fields (ROE, OPM, margins, ROA) → returned as decimals (0.25 = 25%) → ×100
  Debt/Equity   → returned as a raw number (not divided by 100)
  Market cap    → INR absolute for .NS/.BO → divide by 1e7 to get Crore
                  USD absolute for US tickers → divide by 1e6 to get USD M
"""
from __future__ import annotations

import io
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pandas as pd
import requests

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

# ── NSE index symbol lists ────────────────────────────────────────────────────

_NSE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36'
    )
}

NSE_INDEX_URLS: dict[str, str] = {
    'nifty50':      'https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv',
    'nifty100':     'https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv',
    'nifty200':     'https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv',
    'nifty500':     'https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv',
    'niftymidcap':  'https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv',
    'niftysmallcap':'https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv',
}

BSE_EQUITY_URL = (
    'https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w'
    '?Group=&Scripcode=&industry=&segment=Equity&status=Active'
)


def get_nse_index_symbols(index_key: str) -> list[str]:
    """Download NSE index constituent list from NSE archives."""
    url = NSE_INDEX_URLS.get(index_key.lower())
    if not url:
        return []
    try:
        r = requests.get(url, headers=_NSE_HEADERS, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        col = next((c for c in df.columns if 'symbol' in c.lower()), None)
        return df[col].dropna().str.strip().tolist() if col else []
    except Exception:
        return []


def get_bse_symbols(limit: int = 500) -> list[str]:
    """Return BSE Scripcode list (numeric) for active equities."""
    try:
        r = requests.get(BSE_EQUITY_URL, timeout=20)
        data = r.json()
        codes = [str(item.get('SCRIP_CD', '')) for item in data if item.get('SCRIP_CD')]
        return codes[:limit]
    except Exception:
        return []


# ── yfinance field extraction ─────────────────────────────────────────────────

EXCHANGE_SUFFIX = {'NSE': '.NS', 'BSE': '.BO', 'NASDAQ': '', 'NYSE': ''}

# Fields returned as decimals (× 100 to get %)
_PERCENT_FIELDS: dict[str, str] = {
    'returnOnEquity':    'roe',
    'returnOnAssets':    'roa',
    'operatingMargins':  'opm',
    'profitMargins':     'net_profit_margin',
    'grossMargins':      'gross_margin',
    'revenueGrowth':     'sales_growth_ttm',
    'earningsGrowth':    'profit_growth_ttm',
    'heldPercentInsiders': 'promoter_holding',
    'dividendYield':     'dividend_yield',
}

# Fields returned as raw ratios (no unit conversion)
_RATIO_FIELDS: dict[str, str] = {
    'trailingPE':    'pe',
    'forwardPE':     'pe_forward',
    'priceToBook':   'pb',
    'debtToEquity':  'debt_to_equity',
    'currentRatio':  'current_ratio',
    'fiftyTwoWeekHigh': 'high_52w',
    'fiftyTwoWeekLow':  'low_52w',
    'volume':           'volume',
    'averageVolume':    'volume_30d_avg',
}

# Fields that are INR/USD absolute amounts — convert to Cr/USD M
_MONEY_FIELDS: dict[str, str] = {
    'totalRevenue':      'revenue',
    'netIncomeToCommon': 'net_profit',
    'totalAssets':       'total_assets',
    'operatingCashflow': 'ocf',
}


def _extract_info(info: dict, ticker: str, is_inr: bool) -> dict:
    row: dict[str, object] = {
        'ticker': ticker,
        'name':   info.get('longName') or info.get('shortName') or ticker,
        'sector': info.get('sector', ''),
        '_source': 'yfinance',
    }

    # Price
    row['cmp'] = info.get('currentPrice') or info.get('regularMarketPrice')

    # Market cap
    mc = info.get('marketCap')
    if mc:
        row['market_cap'] = round(mc / 1e7, 2) if is_inr else round(mc / 1e6, 2)

    for yf_key, canon in _PERCENT_FIELDS.items():
        v = info.get(yf_key)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            row[canon] = round(float(v) * 100, 2)

    for yf_key, canon in _RATIO_FIELDS.items():
        v = info.get(yf_key)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            row[canon] = v

    divisor = 1e7 if is_inr else 1e6
    for yf_key, canon in _MONEY_FIELDS.items():
        v = info.get(yf_key)
        if v:
            row[canon] = round(float(v) / divisor, 2)

    return row


def _fetch_one(symbol: str, suffix: str, is_inr: bool) -> dict:
    yf_sym = f'{symbol}{suffix}'
    try:
        info = yf.Ticker(yf_sym).info
        if not info or not info.get('regularMarketPrice'):
            # Try .NS fallback for BSE numeric codes
            if suffix == '.BO':
                fallback = yf.Ticker(f'{symbol}.NS').info
                if fallback and fallback.get('regularMarketPrice'):
                    return _extract_info(fallback, symbol, is_inr)
            return {'ticker': symbol, '_error': 'no price data', '_source': 'yfinance'}
        return _extract_info(info, symbol, is_inr)
    except Exception as exc:
        return {'ticker': symbol, '_error': str(exc)[:120], '_source': 'yfinance'}


def fetch_live(
    symbols: list[str],
    exchange: str = 'NSE',
    max_workers: int = 12,
) -> pd.DataFrame:
    """
    Fetch financial data from yfinance for a list of tickers in parallel.
    Returns a DataFrame with canonical column names.
    """
    if not HAS_YF:
        raise RuntimeError('yfinance is not installed. Run: pip install yfinance')

    suffix = EXCHANGE_SUFFIX.get(exchange.upper(), '.NS')
    is_inr = exchange.upper() in ('NSE', 'BSE')

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, sym, suffix, is_inr): sym for sym in symbols}
        for fut in as_completed(futures, timeout=240):
            try:
                results.append(fut.result())
            except Exception:
                pass

    return pd.DataFrame(results) if results else pd.DataFrame()


# ── Screener vs Live comparison ───────────────────────────────────────────────

COMPARE_FIELDS: list[tuple[str, str]] = [
    ('cmp',            'CMP'),
    ('pe',             'P/E'),
    ('pb',             'P/B'),
    ('roe',            'ROE %'),
    ('opm',            'OPM %'),
    ('debt_to_equity', 'D/E'),
    ('current_ratio',  'Curr Ratio'),
    ('market_cap',     'Mkt Cap'),
    ('high_52w',       '52W High'),
    ('low_52w',        '52W Low'),
]

# D/E comparison is excluded by default because yfinance uses total liabilities
# while Screener uses financial debt only — comparison is misleading.
_NOISY_FIELDS = {'debt_to_equity', 'promoter_holding'}


def compare_dataframes(
    screener_df: pd.DataFrame,
    live_df: pd.DataFrame,
) -> list[dict]:
    """
    Match stocks by ticker, compute per-field delta between Screener and live data.
    Returns list sorted by max delta (most discrepant first).
    """
    if 'ticker' not in screener_df.columns or live_df.empty:
        return []

    live_upper = live_df.copy()
    live_upper['_ticker_upper'] = live_upper['ticker'].str.strip().str.upper()

    records: list[dict] = []
    for _, scr in screener_df.iterrows():
        ticker = str(scr.get('ticker') or '').strip().upper()
        if not ticker:
            continue

        match = live_upper[live_upper['_ticker_upper'] == ticker]
        if match.empty:
            continue
        live = match.iloc[0]

        fields_data: list[dict] = []
        for field_key, field_label in COMPARE_FIELDS:
            scr_val = _to_float(scr.get(field_key))
            live_val = _to_float(live.get(field_key))
            dpct = _delta_pct(scr_val, live_val)
            fields_data.append({
                'field':      field_key,
                'label':      field_label,
                'screener':   scr_val,
                'live':       live_val,
                'delta_pct':  round(dpct, 1) if dpct is not None else None,
                'flag':       _flag(dpct),
                'noisy':      field_key in _NOISY_FIELDS,
            })

        non_noisy = [f['delta_pct'] for f in fields_data
                     if f['delta_pct'] is not None and not f['noisy']]
        max_delta = max(non_noisy, default=0.0)

        records.append({
            'ticker':       ticker,
            'name':         scr.get('name') or live.get('name') or ticker,
            'sector':       scr.get('sector') or live.get('sector') or '',
            'fields':       fields_data,
            'max_delta':    round(max_delta, 1),
            'overall_flag': _flag(max_delta),
        })

    records.sort(key=lambda x: x['max_delta'], reverse=True)
    return records


def _to_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if math.isnan(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def _delta_pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    if a == 0 and b == 0:
        return 0.0
    denom = abs(a) if a != 0 else abs(b)
    return abs(a - b) / denom * 100


def _flag(dpct: Optional[float]) -> str:
    if dpct is None:
        return 'na'
    if dpct < 5:
        return 'green'
    if dpct < 20:
        return 'amber'
    return 'red'
