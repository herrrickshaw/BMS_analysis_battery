"""
Damodaran sector benchmark data loader.
Source: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html
Datasets: peIndia, marginIndia, roeIndia, dbtfundIndia, histgrIndia
          pedata, margin, roe (US)
          peEurope, marginEurope, roeEurope (Europe)
"""
from __future__ import annotations

import math
import os
from difflib import get_close_matches
from typing import Optional

import xlrd

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'damodaran')
_HEADER_ROW = 8  # row index (0-based) where industry data starts in all Damodaran xls

# Maps region key → file suffixes
_REGION_SUFFIX = {
    'india':  'India',
    'us':     '',
    'europe': 'Europe',
}

# Screener.in / yfinance sector names → Damodaran industry names
_SECTOR_MAP: dict[str, str] = {
    # IT / Technology
    'it':                          'Software (System & Application)',
    'technology':                  'Software (System & Application)',
    'software':                    'Software (System & Application)',
    'computer services':           'Computer Services',
    'information technology':      'Software (System & Application)',
    # Banking / Finance
    'banking':                     'Banks (Regional)',
    'bank':                        'Banks (Regional)',
    'banks':                       'Banks (Regional)',
    'financial services':          'Financial Svcs. (Non-bank & Insurance)',
    'nbfc':                        'Financial Svcs. (Non-bank & Insurance)',
    'brokerage':                   'Brokerage & Investment Banking',
    'insurance':                   'Insurance (General)',
    'insurance (life)':            'Insurance (Life)',
    # Pharma / Healthcare
    'pharmaceuticals':             'Drugs (Pharmaceutical)',
    'pharmaceuticals & biotechnology': 'Drugs (Pharmaceutical)',
    'pharma':                      'Drugs (Pharmaceutical)',
    'healthcare':                  'Healthcare Products',
    'healthcare products':         'Healthcare Products',
    'healthcare services':         'Hospitals/Healthcare Facilities',
    'hospitals':                   'Hospitals/Healthcare Facilities',
    'biotech':                     'Drugs (Biotechnology)',
    # Auto
    'automobiles':                 'Auto & Truck',
    'auto':                        'Auto & Truck',
    'automobile':                  'Auto & Truck',
    'auto ancillaries':            'Auto Parts',
    'auto parts':                  'Auto Parts',
    # Metals
    'metals - ferrous':            'Steel',
    'steel':                       'Steel',
    'metals & mining':             'Metals & Mining',
    'metals':                      'Metals & Mining',
    'mining':                      'Metals & Mining',
    # Energy
    'oil & gas':                   'Oil/Gas (Integrated)',
    'oil gas':                     'Oil/Gas (Integrated)',
    'power':                       'Power',
    'utilities':                   'Utility (General)',
    'utility':                     'Utility (General)',
    'coal':                        'Coal & Related Energy',
    'renewable energy':            'Green & Renewable Energy',
    # Consumer
    'fmcg':                        'Household Products',
    'consumer goods':              'Household Products',
    'consumer staples':            'Household Products',
    'food & beverages':            'Food Processing',
    'food processing':             'Food Processing',
    'beverages':                   'Beverage (Soft)',
    'alcohol':                     'Beverage (Alcoholic)',
    'tobacco':                     'Tobacco',
    'retail':                      'Retail (General)',
    'retailing':                   'Retail (General)',
    # Infrastructure / Construction
    'construction':                'Engineering/Construction',
    'engineering':                 'Engineering/Construction',
    'infrastructure':              'Engineering/Construction',
    'cement':                      'Building Materials',
    'building materials':          'Building Materials',
    'real estate':                 'Real Estate (Development)',
    'realty':                      'Real Estate (Development)',
    # Telecom / Media
    'telecom':                     'Telecom. Services',
    'telecommunications':          'Telecom. Services',
    'media':                       'Publishing & Newspapers',
    'broadcasting':                'Broadcasting',
    'entertainment':               'Entertainment',
    # Capital Goods / Industrial
    'capital goods':               'Machinery',
    'machinery':                   'Machinery',
    'industrial':                  'Machinery',
    'electrical equipment':        'Electrical Equipment',
    'electronics':                 'Electronics (General)',
    'packaging':                   'Packaging & Container',
    'paper':                       'Paper/Forest Products',
    'chemicals':                   'Chemical (Specialty)',
    'fertilisers':                 'Chemical (Basic)',
    'textiles':                    'Apparel',
    'transport':                   'Transportation',
    'logistics':                   'Transportation',
    'shipping':                    'Shipbuilding & Marine',
    'hospitality':                 'Hotel/Gaming',
    'hotels':                      'Hotel/Gaming',
    'education':                   'Education',
    'agriculture':                 'Farming/Agriculture',
    # European / US
    'consumer cyclical':           'Retail (General)',
    'consumer defensive':          'Household Products',
    'industrials':                 'Machinery',
    'basic materials':             'Chemical (Basic)',
    'communication services':      'Telecom. Services',
}


def _safe_float(v) -> Optional[float]:
    if v == '' or v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def _load_sheet(path: str) -> list[dict]:
    """Load rows from 'Industry Averages' sheet.

    Damodaran sheets have 7–8 metadata rows before data.  The column-name row
    is the first row whose first cell equals 'Industry Name'.
    """
    wb = xlrd.open_workbook(path)
    ws = wb.sheet_by_name('Industry Averages')

    # Find the header row (first cell == 'Industry Name')
    header_idx = None
    for r in range(ws.nrows):
        if str(ws.cell_value(r, 0)).strip() == 'Industry Name':
            header_idx = r
            break
    if header_idx is None:
        return []

    col_headers = [str(ws.cell_value(header_idx, c)).strip() for c in range(ws.ncols)]
    rows = []
    for r in range(header_idx + 1, ws.nrows):
        name = ws.cell_value(r, 0)
        if not name or not isinstance(name, str):
            continue
        row = {'Industry Name': name.strip()}
        for c in range(1, ws.ncols):
            row[col_headers[c]] = ws.cell_value(r, c)
        rows.append(row)
    return rows


def _build_benchmarks(region: str) -> dict[str, dict]:
    suffix = _REGION_SUFFIX.get(region, 'India')

    # US files use different base names (pedata, margin, roe)
    _PE_BASE     = 'pedata'  if region == 'us' else 'pe'
    _MARGIN_BASE = 'margin'
    _ROE_BASE    = 'roe'

    def path(base: str) -> str:
        return os.path.join(DATA_DIR, f'{base}{suffix}.xls')

    pe_rows     = _load_sheet(path(_PE_BASE))
    margin_rows = _load_sheet(path(_MARGIN_BASE))
    roe_rows    = _load_sheet(path(_ROE_BASE))

    # D/E and historical growth only downloaded for India
    de_rows = histgr_rows = []
    if region == 'india':
        try:
            de_rows     = _load_sheet(os.path.join(DATA_DIR, 'dbtfundIndia.xls'))
            histgr_rows = _load_sheet(os.path.join(DATA_DIR, 'histgrIndia.xls'))
        except Exception:
            pass

    benchmarks: dict[str, dict] = {}

    def ensure(ind):
        if ind not in benchmarks:
            benchmarks[ind] = {'industry': ind}
        return benchmarks[ind]

    for r in pe_rows:
        ind = r['Industry Name']
        b = ensure(ind)
        b['num_firms']    = _safe_float(r.get('Number of firms'))
        b['trailing_pe']  = _safe_float(r.get('Trailing PE'))
        b['current_pe']   = _safe_float(r.get('Current PE'))
        b['forward_pe']   = _safe_float(r.get('Forward PE'))
        b['peg']          = _safe_float(r.get('PEG Ratio'))
        b['exp_growth_5y']= _safe_float(r.get('Expected growth - next 5 years'))

    for r in margin_rows:
        ind = r['Industry Name']
        b = ensure(ind)
        b['gross_margin'] = _safe_float(r.get('Gross Margin'))
        b['net_margin']   = _safe_float(r.get('Net Margin'))
        # Pre-tax operating margin column label varies
        for key in ('Pre-tax, Pre-stock compensation Operating Margin',
                    'Pre-tax Unadjusted Operating Margin',
                    'Operating Margin'):
            v = _safe_float(r.get(key))
            if v is not None:
                b['opm'] = v
                break

    for r in roe_rows:
        ind = r['Industry Name']
        b = ensure(ind)
        b['roe'] = _safe_float(r.get('ROE (unadjusted)'))

    for r in de_rows:
        ind = r['Industry Name']
        b = ensure(ind)
        b['market_de'] = _safe_float(r.get('Market D/E (unadjusted)'))

    for r in histgr_rows:
        ind = r['Industry Name']
        b = ensure(ind)
        b['rev_cagr_5y'] = _safe_float(r.get('CAGR in Revenues- Last 5 years'))
        b['ni_cagr_5y']  = _safe_float(r.get('CAGR in Net Income- Last 5 years'))

    return benchmarks


# Module-level cache: region → {industry_name → benchmark_dict}
_CACHE: dict[str, dict[str, dict]] = {}


def _get_cache(region: str) -> dict[str, dict]:
    if region not in _CACHE:
        _CACHE[region] = _build_benchmarks(region)
    return _CACHE[region]


def lookup_industry(sector: str, region: str = 'india') -> Optional[str]:
    """Map a Screener.in / yfinance sector name to a Damodaran industry name."""
    if not sector:
        return None
    key = sector.lower().strip()
    # Direct map
    if key in _SECTOR_MAP:
        return _SECTOR_MAP[key]
    # Fuzzy match against known industry names
    cache = _get_cache(region)
    industries = list(cache.keys())
    matches = get_close_matches(sector, industries, n=1, cutoff=0.5)
    return matches[0] if matches else None


def get_sector_benchmarks(sector: str, region: str = 'india') -> Optional[dict]:
    """Return the Damodaran benchmark dict for a given sector, or None if not found."""
    industry = lookup_industry(sector, region)
    if not industry:
        return None
    return _get_cache(region).get(industry)


def get_all_benchmarks(region: str = 'india') -> list[dict]:
    """Return all industry benchmarks as a list, sorted by industry name."""
    cache = _get_cache(region)
    return sorted(cache.values(), key=lambda b: b.get('industry', ''))


def get_sector_pe(sector: str, region: str = 'india') -> Optional[float]:
    b = get_sector_benchmarks(sector, region)
    return b.get('trailing_pe') if b else None


def get_sector_roe(sector: str, region: str = 'india') -> Optional[float]:
    b = get_sector_benchmarks(sector, region)
    return b.get('roe') if b else None
