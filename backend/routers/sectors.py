from __future__ import annotations

from fastapi import APIRouter
from damodaran import get_all_benchmarks, _REGION_SUFFIX

router = APIRouter()

VALID_REGIONS = list(_REGION_SUFFIX.keys())  # india, us, europe


def _pct(v):
    """Convert Damodaran decimal fractions to percentage strings where needed."""
    return v


def _format_row(b: dict) -> dict:
    """Convert raw Damodaran floats: margins/ROE stored as 0-1 fractions → multiply by 100."""
    def pct(k):
        v = b.get(k)
        return round(v * 100, 1) if v is not None else None

    return {
        'industry':      b.get('industry'),
        'num_firms':     int(b['num_firms']) if b.get('num_firms') else None,
        'trailing_pe':   round(b['trailing_pe'], 1) if b.get('trailing_pe') else None,
        'forward_pe':    round(b['forward_pe'], 1)  if b.get('forward_pe')  else None,
        'peg':           round(b['peg'], 2)          if b.get('peg')         else None,
        'roe_pct':       pct('roe'),
        'opm_pct':       pct('opm'),
        'net_margin_pct':pct('net_margin'),
        'gross_margin_pct': pct('gross_margin'),
        'market_de':     round(b['market_de'], 2)   if b.get('market_de')   else None,
        'rev_cagr_5y_pct': pct('rev_cagr_5y'),
        'ni_cagr_5y_pct':  pct('ni_cagr_5y'),
        'exp_growth_5y_pct': pct('exp_growth_5y'),
    }


@router.get('/api/sectors')
def list_sectors(region: str = 'india'):
    if region not in VALID_REGIONS:
        region = 'india'
    rows = get_all_benchmarks(region)
    return {
        'region': region,
        'source': 'Aswath Damodaran — NYU Stern (https://pages.stern.nyu.edu/~adamodar/)',
        'sectors': [_format_row(b) for b in rows],
    }
