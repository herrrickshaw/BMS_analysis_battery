"""
global_tickers.py
=================
Lightweight helper — loads tickers from data/global_universe.json.
Falls back to the curated top-cap lists if the JSON is not built yet.

Usage:
    from global_tickers import all_tickers, tickers_for, market_summary
    syms = tickers_for("US")             # US only
    syms = tickers_for("IN", "JP")       # multi-market
    syms = all_tickers()                 # all markets
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List

_DATA = Path(__file__).parent / "data" / "global_universe.json"

# ── lazy loader ───────────────────────────────────────────────────────────────

_UNIVERSE: Dict[str, dict] | None = None


def _load() -> Dict[str, dict]:
    global _UNIVERSE
    if _UNIVERSE is None:
        if _DATA.exists():
            with open(_DATA) as f:
                _UNIVERSE = json.load(f)
        else:
            # Minimal fallback until universe_builder.py is run
            _UNIVERSE = {}
    return _UNIVERSE


# ── public API ────────────────────────────────────────────────────────────────

def tickers_for(*market_codes: str) -> List[str]:
    """Return yfinance symbols for one or more market codes (e.g. 'US', 'IN')."""
    universe = _load()
    result: List[str] = []
    for code in market_codes:
        m = universe.get(code.upper())
        if not m:
            raise ValueError(f"Unknown market '{code}'. Run universe_builder.py first.")
        result.extend(m["yf_symbols"])
    return result


def all_tickers() -> List[str]:
    """Return all tickers across every market in the universe."""
    universe = _load()
    out = []
    for m in universe.values():
        out.extend(m["yf_symbols"])
    return out


def market_codes() -> List[str]:
    """Return list of available market codes."""
    return list(_load().keys())


def market_summary() -> None:
    """Print a summary table."""
    universe = _load()
    total = 0
    print(f"{'Code':<5} {'Market':<35} {'Exchange':<25} {'Tickers':>8}")
    print("─" * 78)
    for code, m in universe.items():
        n = m["count"]
        total += n
        print(f"{code:<5} {m['name']:<35} {m['exchange']:<25} {n:>8,}")
    print("─" * 78)
    print(f"{'TOTAL':<5} {str(len(universe))+' markets':<35} {'':<25} {total:>8,}")


if __name__ == "__main__":
    market_summary()
    print()
    print("Sample — India (first 5):", tickers_for("IN")[:5])
    print("Sample — US    (first 5):", tickers_for("US")[:5])
    print("Sample — JP    (first 5):", tickers_for("JP")[:5])
