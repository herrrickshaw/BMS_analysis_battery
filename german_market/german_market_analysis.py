#!/usr/bin/env python3
"""
german_market_analysis.py
=========================
Unified German market analysis combining all three Deutsche Börse data sources:
  1. Eurex GraphQL API  — derivatives reference data (free, no auth)
  2. A7 REST API        — Xetra equity reference + order book data (needs A7 token)
  3. Xetra PDS / S3    — 1-minute OHLCV historical data (needs AWS creds)

Run each module independently, or chain them here.

Requirements: pip install requests boto3 pandas tabulate

Usage:
  # Quick summary (Eurex only, no auth needed)
  python3 german_market/german_market_analysis.py --eurex-summary

  # Full market snapshot (needs A7 token + AWS creds)
  export A7_TOKEN="your-token"
  export AWS_ACCESS_KEY_ID="..."
  export AWS_SECRET_ACCESS_KEY="..."
  python3 german_market/german_market_analysis.py --full --date 2025-01-10

  # Generate a market report (HTML)
  python3 german_market/german_market_analysis.py --report --date 2025-01-10
"""
import os, sys, csv, json, argparse
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict

DATA = Path(__file__).parent.parent / "data"

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


# ── Import sub-modules ────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from eurex_graphql      import fetch_all_products, fetch_contracts, gql, QUERY_EXPIRATIONS
from a7_xetra_reference import (session as a7_session, fetch_all_xetra_instruments,
                                 aggregate_day, day_key, flatten_instrument)


# ── 1. Eurex summary (free, no auth) ─────────────────────────────────────────
def eurex_summary(api_key: str = None) -> dict:
    """Pull Eurex product breakdown — no auth needed."""
    from eurex_graphql import SHARED_KEY
    key = api_key or SHARED_KEY

    products = fetch_all_products(key)

    by_type: dict[str, list] = defaultdict(list)
    by_underlying: dict[str, int] = defaultdict(int)
    equity_products = []

    for p in products:
        ptype = p.get("productType", "UNKNOWN")
        by_type[ptype].append(p)
        ul = p.get("underlyingSymbol") or p.get("underlyingDescription") or ""
        if ul:
            by_underlying[ul] += 1
        if ptype in ("OPTION", "FUTURE") and p.get("underlyingIsin", "").startswith("DE"):
            equity_products.append(p)

    print("\n── Eurex Product Summary ──────────────────────────────────────")
    print(f"{'Type':<20} {'Count':>8}")
    print("─" * 30)
    for ptype, plist in sorted(by_type.items(), key=lambda x: -len(x[1])):
        print(f"{ptype:<20} {len(plist):>8,}")
    print(f"{'TOTAL':<20} {len(products):>8,}")

    print(f"\n── German Equity Derivatives ({len(equity_products)} products) ──")
    for p in sorted(equity_products, key=lambda x: x.get("productId", ""))[:20]:
        print(f"  {p['productId']:<12} {p['productType']:<8} {p['productName'][:50]}")

    print(f"\n── Top 10 Underlying Symbols ──")
    for sym, cnt in sorted(by_underlying.items(), key=lambda x: -x[1])[:10]:
        print(f"  {sym:<20} {cnt:>5} products")

    return {
        "total_products":    len(products),
        "by_type":           {k: len(v) for k, v in by_type.items()},
        "equity_derivatives": len(equity_products),
        "products":          products,
    }


# ── 2. Xetra reference snapshot (needs A7 token) ─────────────────────────────
def xetra_reference_snapshot(token: str, date_str: str) -> dict:
    """Fetch all Xetra listed instruments for a date via A7 RDI."""
    sess = a7_session(token)
    date_nodash = date_str.replace("-", "")

    print(f"\n── Xetra Reference Data ({date_str}) ──────────────────────────")
    instruments = fetch_all_xetra_instruments(sess, date_nodash)

    if not instruments:
        print("  No data returned (check A7 token and date)")
        return {}

    # Categorize
    by_type: dict[str, int] = defaultdict(int)
    isins: set[str] = set()
    equities: list[dict] = []

    for inst in instruments:
        itype = (inst.get("InstrumentType") or inst.get("instrumentType") or
                 inst.get("SecurityType") or "UNKNOWN")
        by_type[itype] += 1
        isin = inst.get("ISIN") or inst.get("isin") or ""
        if isin:
            isins.add(isin)
        if "EQUITY" in itype.upper() or "AKTIE" in itype.upper():
            equities.append(inst)

    print(f"  Total instruments : {len(instruments):,}")
    print(f"  Unique ISINs      : {len(isins):,}")
    print(f"\n  {'Type':<30} {'Count':>8}")
    print("  " + "─" * 40)
    for t, c in sorted(by_type.items(), key=lambda x: -x[1])[:15]:
        print(f"  {t:<30} {c:>8,}")

    print(f"\n  Sample Equities:")
    for inst in equities[:10]:
        isin = inst.get("ISIN") or inst.get("isin") or ""
        name = (inst.get("InstrumentLongName") or inst.get("SecurityDescription") or
                inst.get("SecurityDesc") or "")
        mnem = (inst.get("Mnemonic") or inst.get("InstrumentSymbol") or "")
        curr = inst.get("Currency") or inst.get("currency") or ""
        print(f"    {isin:<14} {mnem:<8} {curr:<5} {name[:40]}")

    # Save
    out = DATA / f"xetra_reference_{date_str}.csv"
    flat = [flatten_instrument(i) for i in instruments]
    if flat:
        all_keys = list(dict.fromkeys(k for row in flat for k in row))
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            w.writeheader()
            for row in flat:
                w.writerow({k: row.get(k, "") for k in all_keys})
        print(f"\n  Saved: {out}")

    return {"instruments": instruments, "equities": equities, "isins": isins}


# ── 3. PDS market data (needs AWS creds) ─────────────────────────────────────
def xetra_market_data(date_str: str, isin_filter: set = None) -> dict:
    """Download Xetra PDS 1-minute data and compute daily stats."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print("  boto3 not installed — skipping PDS download")
        return {}

    from xetra_pds import s3_client, download_hour_csv, day_key, aggregate_day, market_stats, XETRA_HOURS

    print(f"\n── Xetra PDS Market Data ({date_str}) ─────────────────────────")
    client = s3_client()
    all_records = []

    for hour in XETRA_HOURS:
        key = day_key(date_str, hour)
        records = download_hour_csv(client, key)
        if records:
            all_records.extend(records)
            print(f"  {hour:02d}:00  {len(records):>6,} records", flush=True)

    if not all_records:
        print("  No PDS data available (check AWS creds + date)")
        return {}

    daily = aggregate_day(all_records, isin_filter)
    stats = market_stats(daily)

    print(f"\n  ── {date_str} Market Summary ──────────────")
    print(f"  Instruments     : {stats['total_instruments']:,}")
    print(f"  Total volume    : {stats['total_volume']:,.0f} shares")
    print(f"  Total trades    : {stats['total_trades']:,}")
    print(f"  Advancers       : {stats['advancers']}")
    print(f"  Decliners       : {stats['decliners']}")
    if stats["total_instruments"] > 0:
        pct_up = 100 * stats["advancers"] / stats["total_instruments"]
        print(f"  Breadth         : {pct_up:.1f}% advancing")

    print(f"\n  Top 10 by Volume:")
    print(f"  {'ISIN':<14} {'Mnem':<8} {'Close':>10} {'Volume':>15} {'Trades':>8} {'Ret%':>7}")
    print("  " + "─" * 65)
    for isin, d in stats["top_by_volume"]:
        ret = ((d["close"] / d["open"] - 1) * 100
               if d.get("close") and d.get("open") and d["open"] > 0 else 0)
        print(f"  {isin:<14} {d['mnemonic']:<8} "
              f"{d.get('close', 0):>10.2f} "
              f"{d.get('volume', 0):>15,.0f} "
              f"{d.get('trades', 0):>8,} "
              f"{ret:>+7.2f}%")

    return {"daily": daily, "stats": stats}


# ── 4. Cross-reference with our validated universe ───────────────────────────
def merge_with_universe(instruments: list[dict], pds_daily: dict) -> list[dict]:
    """
    Join A7 reference data + PDS market data with our validated universe.
    Returns enriched rows for all DE tickers.
    """
    universe_file = DATA / "validated_universe_flat.csv"
    if not universe_file.exists():
        universe_file = DATA / "global_universe_flat.csv"
    if not universe_file.exists():
        print("  Universe CSV not found — skipping merge")
        return []

    de_rows = [r for r in csv.DictReader(open(universe_file))
               if r["market_code"] == "DE"]
    print(f"\n── Universe Merge ─────────────────────────────────────────────")
    print(f"  DE tickers in universe: {len(de_rows):,}")

    # Build ISIN → A7 instrument lookup
    isin_to_a7: dict[str, dict] = {}
    mnem_to_a7: dict[str, dict] = {}
    for inst in instruments:
        isin = inst.get("ISIN") or inst.get("isin") or ""
        mnem = (inst.get("Mnemonic") or inst.get("mnemonic") or
                inst.get("InstrumentSymbol") or "").strip()
        if isin:
            isin_to_a7[isin] = inst
        if mnem:
            mnem_to_a7[mnem] = inst

    enriched = []
    matched_a7 = 0
    matched_pds = 0

    for r in de_rows:
        sym_bare = r["yf_symbol"].replace(".DE", "").replace(".F", "").upper()
        row = dict(r)

        # Try A7 match by mnemonic
        a7 = mnem_to_a7.get(sym_bare)
        if a7:
            matched_a7 += 1
            isin = a7.get("ISIN") or a7.get("isin") or ""
            row["isin"]       = isin
            row["a7_name"]    = (a7.get("InstrumentLongName") or
                                  a7.get("SecurityDescription") or "")
            row["a7_type"]    = (a7.get("InstrumentType") or
                                  a7.get("SecurityType") or "")
            row["tick_size"]  = a7.get("TickSize") or a7.get("tickSize") or ""
            row["currency"]   = a7.get("Currency") or a7.get("currency") or ""

            # Try PDS match by ISIN
            if isin and isin in pds_daily:
                matched_pds += 1
                pds = pds_daily[isin]
                row["pds_open"]   = pds.get("open", "")
                row["pds_high"]   = pds.get("high", "")
                row["pds_low"]    = pds.get("low", "")
                row["pds_close"]  = pds.get("close", "")
                row["pds_volume"] = pds.get("volume", "")
                row["pds_trades"] = pds.get("trades", "")

        enriched.append(row)

    print(f"  Matched to A7 reference : {matched_a7}/{len(de_rows)} "
          f"({100*matched_a7/max(1,len(de_rows)):.1f}%)")
    print(f"  Matched to PDS data     : {matched_pds}/{len(de_rows)} "
          f"({100*matched_pds/max(1,len(de_rows)):.1f}%)")

    # Save merged
    if enriched:
        out = DATA / "de_universe_enriched.csv"
        all_keys = list(dict.fromkeys(k for row in enriched for k in row))
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            w.writeheader()
            for row in enriched:
                w.writerow({k: row.get(k, "") for k in all_keys})
        print(f"  Saved: {out}")

    return enriched


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--eurex-summary",   action="store_true",
                        help="Eurex product summary (no auth needed)")
    parser.add_argument("--xetra-reference", action="store_true",
                        help="Xetra reference data via A7 (needs A7_TOKEN)")
    parser.add_argument("--xetra-market",    action="store_true",
                        help="Xetra market data via PDS S3 (needs AWS creds)")
    parser.add_argument("--full",            action="store_true",
                        help="All three data sources + merge")
    parser.add_argument("--date",            default=str(date.today() - timedelta(days=3)),
                        help="Date YYYY-MM-DD")
    parser.add_argument("--api-key",         default=None,
                        help="Eurex GraphQL API key (optional — uses shared key)")
    parser.add_argument("--a7-token",        default=None,
                        help="A7 API token (or set A7_TOKEN env)")
    parser.add_argument("--isins",           default=None,
                        help="Comma-separated ISIN filter for PDS")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)

    isin_filter = None
    if args.isins:
        isin_filter = set(i.strip() for i in args.isins.split(","))

    instruments: list[dict] = []
    pds_daily:   dict        = {}

    if args.eurex_summary or args.full:
        if not HAS_REQUESTS:
            print("WARNING: pip install requests  (needed for Eurex GraphQL)")
        else:
            eurex_summary(args.api_key)

    if args.xetra_reference or args.full:
        token = args.a7_token or os.environ.get("A7_TOKEN", "")
        if not token:
            print("WARNING: A7_TOKEN not set — skipping Xetra reference data")
            print("  Get a free token at: https://a7.deutsche-boerse.com")
        else:
            result = xetra_reference_snapshot(token, args.date)
            instruments = result.get("instruments", [])

    if args.xetra_market or args.full:
        result = xetra_market_data(args.date, isin_filter)
        pds_daily = result.get("daily", {})

    if args.full and (instruments or pds_daily):
        merge_with_universe(instruments, pds_daily)

    if not any([args.eurex_summary, args.xetra_reference,
                args.xetra_market, args.full]):
        parser.print_help()
        print("""
Quick start:
  # No auth needed:
  python3 german_market/german_market_analysis.py --eurex-summary

  # With A7 token (free, register at https://a7.deutsche-boerse.com):
  export A7_TOKEN="your-token"
  python3 german_market/german_market_analysis.py --xetra-reference --date 2025-01-10

  # With AWS credentials (for Xetra PDS historical data):
  export AWS_ACCESS_KEY_ID="..."  AWS_SECRET_ACCESS_KEY="..."
  python3 german_market/german_market_analysis.py --xetra-market --date 2024-12-20

  # Everything at once:
  python3 german_market/german_market_analysis.py --full --date 2025-01-10
""")


if __name__ == "__main__":
    main()
