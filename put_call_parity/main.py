"""
main.py
=======
Entry point for the put-call parity arbitrage strategy.

Usage:
    python -m put_call_parity.main                # live trading
    python -m put_call_parity.main --backtest     # offline parity analysis (no orders)
    python -m put_call_parity.main --broker kite  # broker override

Environment variables (required before running live):
    KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN
  or
    UPSTOX_ACCESS_TOKEN
  or
    ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET
"""

import argparse
import logging
import os
import sys


def _parse_args():
    p = argparse.ArgumentParser(description="Put-Call Parity Arbitrage Trader")
    p.add_argument("--broker", choices=["kite", "upstox", "angel"], default="kite")
    p.add_argument("--backtest", action="store_true",
                   help="Run in analysis-only mode (no real orders)")
    p.add_argument("--instrument", nargs="+",
                   choices=["BANKNIFTY", "CRUDEOIL", "SILVER"],
                   help="Restrict to specific instruments (default: all)")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    # ── Strategy mode (Sensibull-style) ────────────────────────────────────
    p.add_argument("--strategy", action="store_true",
                   help="Run strategy builder / analyser (no broker required)")
    p.add_argument("--symbol", default="BANKNIFTY",
                   help="Symbol to analyse in strategy mode (default: BANKNIFTY)")
    p.add_argument("--outlook", default="neutral",
                   choices=["bullish", "bearish", "neutral", "volatile"],
                   help="Market outlook for strategy recommendations")
    p.add_argument("--lots", type=int, default=1,
                   help="Contracts per leg (default: 1)")
    p.add_argument("--expiry", default=None,
                   help="Expiry date YYYY-MM-DD (default: nearest available)")
    p.add_argument("--otm-pct", type=float, default=0.02,
                   help="OTM %% for spread/strangle wings, e.g. 0.02 = 2%% (default: 0.02)")
    return p.parse_args()


def main():
    args = _parse_args()
    logging.getLogger().setLevel(args.log_level)

    if args.backtest:
        _run_backtest(args)
        return

    if args.strategy:
        _run_strategy(args)
        return

    # Live trading
    import put_call_parity.config as cfg_module

    from .broker import get_broker
    from .strategy import Strategy

    if args.instrument:
        # Restrict the INSTRUMENTS dict in place
        keep = {k: v for k, v in cfg_module.INSTRUMENTS.items() if k in args.instrument}
        cfg_module.INSTRUMENTS.clear()
        cfg_module.INSTRUMENTS.update(keep)

    broker = get_broker(args.broker)
    strategy = Strategy(broker=broker)
    strategy.run()


# ---------------------------------------------------------------------------
# Strategy builder mode (Sensibull-style)
# ---------------------------------------------------------------------------
def _run_strategy(args):
    """
    Interactive options strategy analysis — no broker or API key required.

    Fetches the option chain via yfinance (or uses a synthetic Black-Scholes
    chain for Indian instruments that yfinance doesn't cover), then prints
    recommended strategies plus full payoff metrics for every strategy.

    Examples:
        python -m put_call_parity.main --strategy --symbol BANKNIFTY --outlook neutral
        python -m put_call_parity.main --strategy --symbol AAPL --outlook bullish --lots 2
        python -m put_call_parity.main --strategy --symbol NIFTY --outlook volatile --otm-pct 0.025
    """
    from .strategy_scanner import run_strategy_scan

    symbol  = args.symbol.upper()
    outlook = args.outlook
    lots    = args.lots
    otm_pct = args.otm_pct

    print(f"\n{'='*72}")
    print("  SENSIBULL-STYLE STRATEGY ANALYSIS")
    print(f"  Symbol: {symbol}  |  Outlook: {outlook.upper()}  |  Lots: {lots}")
    print(f"{'='*72}")
    print("  Fetching option chain …")

    result = run_strategy_scan(symbol, outlook, lots, args.expiry, otm_pct)

    print(f"\n  Spot:     {result['spot']:,.2f}")
    print(f"  Expiry:   {result['expiry']}  ({result['T_days']} days)")
    print(f"  ATM IV:   {result['atm_iv_pct']:.1f}%")
    print(f"  IV Rank:  {result['iv_rank']:.0f}/100  "
          f"({'HIGH — favour selling' if result['iv_rank'] > 60 else 'LOW — favour buying' if result['iv_rank'] < 40 else 'NEUTRAL'})")
    print(f"  Data:     {result['data_source']}")

    # ── Recommended strategies ──────────────────────────────────────────────
    print(f"\n{'─'*72}")
    print(f"  RECOMMENDED FOR {outlook.upper()} VIEW")
    print(f"{'─'*72}")
    for strat in result['recommended']:
        _print_strategy(strat)

    # ── Full catalogue ──────────────────────────────────────────────────────
    print(f"\n{'─'*72}")
    print("  ALL 14 STRATEGIES (summary)")
    print(f"{'─'*72}")
    hdr = f"  {'Strategy':<25} {'Outlook':<10} {'Net Prem':>10} {'Max Profit':>12} {'Max Loss':>10} {'Breakevens'}"
    print(hdr)
    print(f"  {'-'*24} {'-'*9} {'-'*10} {'-'*12} {'-'*10} {'-'*20}")
    for key, s in result['strategies'].items():
        mp  = f"{s['max_profit']:>12,.0f}" if isinstance(s['max_profit'], (int, float)) else f"{'unlimited':>12}"
        ml  = f"{s['max_loss']:>10,.0f}"   if isinstance(s['max_loss'],   (int, float)) else f"{'unlimited':>10}"
        bes = ', '.join(f"{b:,.0f}" for b in s['breakevens'][:2]) or '—'
        print(f"  {s['name']:<25} {s['outlook']:<10} {s['net_premium']:>10,.0f} {mp} {ml} {bes}")

    print(f"\n{'='*72}\n")


def _print_strategy(s: dict) -> None:
    """Pretty-print a single strategy with its legs and key metrics."""
    mp  = f"{s['max_profit']:,.0f}" if isinstance(s['max_profit'], (int, float)) else 'unlimited'
    ml  = f"{s['max_loss']:,.0f}"   if isinstance(s['max_loss'],   (int, float)) else 'unlimited'
    bes = ', '.join(f"{b:,.0f}" for b in s['breakevens']) or '—'

    print(f"\n  ▶ {s['name']}")
    print(f"    {s['description']}")
    print(f"    Net premium  : {'DEBIT ' if s['net_premium'] > 0 else 'CREDIT'} ₹{abs(s['net_premium']):,.0f}")
    print(f"    Max profit   : ₹{mp}")
    print(f"    Max loss     : ₹{ml}")
    print(f"    Breakeven(s) : {bes}")
    g = s['combined_greeks']
    print(f"    Greeks       : Δ {g['delta']:+.3f}  Γ {g['gamma']:.5f}  "
          f"Θ {g['theta']:+.2f}/day  ν {g['vega']:+.2f}/1%IV")
    print("    Legs:")
    for leg in s['legs']:
        iv_str = f"IV {leg['iv_pct']:.1f}%" if leg.get('iv_pct') else ""
        print(f"      {leg['action']:<5} {leg['option_type']}  K={leg['strike']:>8,.0f}  "
              f"₹{leg['premium']:>8,.2f}  {iv_str}")


# ---------------------------------------------------------------------------
# Backtest / analysis mode
# ---------------------------------------------------------------------------
def _run_backtest(args):
    """
    Offline analysis: reads a JSON option-chain snapshot and prints
    parity deviations without placing any orders.

    Snapshot format (option_chain_snapshot.json):
    [
      {
        "instrument": "BANKNIFTY",
        "expiry": "2024-01-25",
        "futures_price": 47500.0,
        "futures_symbol": "BANKNIFTY24JAN47500FUT",
        "chain": [
          {"strike": 47000, "instrument_type": "CE", "bid": 600, "ask": 605, "oi": 8000, "tradingsymbol": "BANKNIFTY24JAN47000CE"},
          {"strike": 47000, "instrument_type": "PE", "bid": 95,  "ask": 100, "oi": 7500, "tradingsymbol": "BANKNIFTY24JAN47000PE"},
          ...
        ]
      }
    ]
    """
    import json
    from pathlib import Path

    from .config import INSTRUMENTS
    from .parity_engine import ParityEngine

    snapshot_path = Path("option_chain_snapshot.json")
    if not snapshot_path.exists():
        print("[backtest] option_chain_snapshot.json not found.")
        print("           Create a snapshot file or fetch live data first.")
        _print_sample_snapshot()
        return

    with open(snapshot_path) as f:
        snapshots = json.load(f)

    engine = ParityEngine()
    for snap in snapshots:
        inst_key = snap["instrument"]
        if inst_key not in INSTRUMENTS:
            continue
        if args.instrument and inst_key not in args.instrument:
            continue

        signals = engine.scan(
            instrument_key=inst_key,
            option_chain=snap["chain"],
            futures_price=snap["futures_price"],
            futures_symbol=snap["futures_symbol"],
            expiry=snap["expiry"],
            min_oi=0,   # relax OI filter for backtest
        )

        print(f"\n{'='*70}")
        print(f"  {inst_key}  |  Expiry: {snap['expiry']}  |  Futures: {snap['futures_price']:.2f}")
        print(f"{'='*70}")
        if not signals:
            print("  No actionable deviations found.")
            continue

        print(f"  {'Strike':>10}  {'Direction':<25}  {'RawDev':>8}  {'TxnCost':>8}  {'NetDev':>8}  {'Lots':>5}")
        print(f"  {'-'*10}  {'-'*25}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*5}")
        for s in signals:
            print(
                f"  {s.strike:>10.0f}  {s.direction:<25}  "
                f"{s.raw_deviation:>8.2f}  {s.transaction_cost:>8.2f}  "
                f"{s.net_deviation:>8.2f}  {s.lots:>5}"
            )


def _print_sample_snapshot():
    sample = [
        {
            "instrument": "BANKNIFTY",
            "expiry": "2024-01-25",
            "futures_price": 47500.0,
            "futures_symbol": "BANKNIFTY24JANFUT",
            "chain": [
                {"strike": 47000, "instrument_type": "CE", "bid": 600.0, "ask": 605.0,
                 "oi": 8000, "tradingsymbol": "BANKNIFTY24JAN47000CE", "last_price": 602.5, "volume": 1000},
                {"strike": 47000, "instrument_type": "PE", "bid": 80.0, "ask": 85.0,
                 "oi": 7500, "tradingsymbol": "BANKNIFTY24JAN47000PE", "last_price": 82.5, "volume": 900},
                {"strike": 47500, "instrument_type": "CE", "bid": 300.0, "ask": 305.0,
                 "oi": 12000, "tradingsymbol": "BANKNIFTY24JAN47500CE", "last_price": 302.5, "volume": 2000},
                {"strike": 47500, "instrument_type": "PE", "bid": 295.0, "ask": 300.0,
                 "oi": 11000, "tradingsymbol": "BANKNIFTY24JAN47500PE", "last_price": 297.5, "volume": 1800},
            ]
        }
    ]
    import json
    print("\nSample option_chain_snapshot.json content:")
    print(json.dumps(sample, indent=2))


if __name__ == "__main__":
    main()
