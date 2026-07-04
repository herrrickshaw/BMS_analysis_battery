#!/usr/bin/env python3
"""
eurex_graphql.py
================
Queries the Eurex FREE public GraphQL API for T7 reference data.
No registration required — uses the shared public API key (rate-limited).

Official endpoint (v2.0.0, GCP — AWS v1.1.0 decommissioned Jan 2026):
  https://api.developer.deutsche-boerse.com/eurex-prod-graphql/
Shared key: 68cdafd2-c5c1-49be-8558-37244ab4f513

Available data:
  ProductInfos  — all Eurex products (futures, options) with ISIN, type, line
  Contracts     — active contracts per product with settlement price
  TradingHours  — pre/continuous/post trading session times
  TradingHolidays — exchange holiday calendar

Requirements: pip install requests pandas

Usage:
  python3 german_market/eurex_graphql.py --products
  python3 german_market/eurex_graphql.py --products --filter DAX
  python3 german_market/eurex_graphql.py --contracts ODAX
  python3 german_market/eurex_graphql.py --contracts FEU3
  python3 german_market/eurex_graphql.py --trading-hours FDAX
  python3 german_market/eurex_graphql.py --holidays
  python3 german_market/eurex_graphql.py --all-products --out data/eurex_products.csv
"""
import json, csv, argparse, sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

# ── Config ────────────────────────────────────────────────────────────────────
# v2.0.0 GCP endpoint (AWS v1.1.0 decommissioned ~Jan 2026)
GRAPHQL_URL = "https://api.developer.deutsche-boerse.com/eurex-prod-graphql/"
SHARED_KEY  = "68cdafd2-c5c1-49be-8558-37244ab4f513"

DATA = Path(__file__).parent.parent / "data"

# ── API call ──────────────────────────────────────────────────────────────────
def gql(query: str, api_key: str = SHARED_KEY) -> dict:
    """POST a GraphQL query; return the full response dict."""
    r = requests.post(
        GRAPHQL_URL,
        headers={"X-DBP-APIKEY": api_key, "Content-Type": "application/json"},
        json={"query": query},
        timeout=30,
    )
    r.raise_for_status()
    result = r.json()
    if "errors" in result:
        raise RuntimeError(f"GraphQL errors: {result['errors']}")
    return result.get("data", {})


# ── Queries ───────────────────────────────────────────────────────────────────
def product_infos(name_filter: str = None, api_key: str = SHARED_KEY) -> list[dict]:
    """All Eurex products, optionally filtered by name substring."""
    if name_filter:
        q = f'''query {{
  ProductInfos(filter: {{ Name: {{ contains: "{name_filter}" }} }}) {{
    date
    data {{ Product Name ProductISIN ProductLine ProductType }}
  }}
}}'''
    else:
        q = '''query {
  ProductInfos {
    date
    data { Product Name ProductISIN ProductLine ProductType }
  }
}'''
    data = gql(q, api_key)
    return data.get("ProductInfos", {}).get("data", [])


def contracts(product_id: str, api_key: str = SHARED_KEY) -> list[dict]:
    """All active contracts for a product (e.g. ODAX, FGBL, FEU3)."""
    q = f'''query {{
  Contracts(filter: {{ Product: {{ eq: "{product_id}" }} }}) {{
    date
    data {{ Product Contract PreviousDaySettlementPrice }}
  }}
}}'''
    data = gql(q, api_key)
    return data.get("Contracts", {}).get("data", [])


def trading_hours(product_id: str = None, api_key: str = SHARED_KEY) -> list[dict]:
    """Trading session times for one or all products."""
    if product_id:
        q = f'''query {{
  TradingHours(filter: {{ Product: {{ eq: "{product_id}" }} }}) {{
    date
    data {{
      Product
      StartContinuousTrading
      EndOpeningAuction
      EndContinuousTrading
      EndClosingAuction
      StartTES
      EndTES
      LTDBook
      LTDTES
    }}
  }}
}}'''
    else:
        q = '''query {
  TradingHours {
    date
    data {
      Product
      StartContinuousTrading
      EndOpeningAuction
      EndContinuousTrading
      EndClosingAuction
      StartTES
      EndTES
      LTDBook
      LTDTES
    }
  }
}'''
    data = gql(q, api_key)
    return data.get("TradingHours", {}).get("data", [])


def trading_holidays(api_key: str = SHARED_KEY) -> list[dict]:
    """Exchange holiday calendar (v2.0.0: query is Holidays, fields: Holiday, ExchangeHoliday)."""
    q = '''query {
  Holidays {
    date
    data { Product Holiday ExchangeHoliday }
  }
}'''
    data = gql(q, api_key)
    return data.get("Holidays", {}).get("data", [])


def introspect(api_key: str = SHARED_KEY) -> dict:
    """GraphQL schema introspection — lists all available query types and fields."""
    q = '''query {
  __schema {
    queryType { fields { name description args { name type { name kind ofType { name } } } } }
  }
}'''
    return gql(q, api_key)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key",       default=SHARED_KEY)
    parser.add_argument("--products",      action="store_true", help="List all products")
    parser.add_argument("--filter",        default=None,        help="Name filter for products")
    parser.add_argument("--contracts",     metavar="PRODUCT",   help="Contracts for product e.g. ODAX")
    parser.add_argument("--trading-hours", metavar="PRODUCT",   nargs="?", const="",
                        help="Trading hours (all if no PRODUCT given)")
    parser.add_argument("--holidays",      action="store_true", help="Trading holiday calendar")
    parser.add_argument("--introspect",    action="store_true", help="Show available API fields")
    parser.add_argument("--all-products",  action="store_true", help="Download all products to CSV")
    parser.add_argument("--out",           default=None)
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    key = args.api_key

    # ── Products ───────────────────────────────────────────────────────────────
    if args.products or args.all_products:
        print(f"[Eurex GraphQL] Fetching products{f' (filter: {args.filter})' if args.filter else ''}...")
        prods = product_infos(args.filter, key)
        print(f"  {len(prods)} products returned\n")

        from collections import Counter
        by_type = Counter(p.get("ProductType") for p in prods)
        print(f"  {'Type':<20} {'Count':>6}")
        print("  " + "─" * 28)
        for t, c in by_type.most_common():
            print(f"  {t or 'N/A':<20} {c:>6}")
        print()

        print(f"  {'Product':<12} {'Type':<10} {'Line':<20} {'Name'}")
        print("  " + "─" * 70)
        for p in prods[:40]:
            print(f"  {p.get('Product',''):<12} {p.get('ProductType',''):<10} "
                  f"{p.get('ProductLine',''):<20} {p.get('Name','')[:35]}")
        if len(prods) > 40:
            print(f"  ... (+{len(prods) - 40} more)")

        out = Path(args.out) if args.out else DATA / "eurex_products.csv"
        if prods:
            keys = list(prods[0].keys())
            with open(out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader(); w.writerows(prods)
            print(f"\n  Saved: {out}")

    # ── Contracts ──────────────────────────────────────────────────────────────
    if args.contracts:
        pid = args.contracts.upper()
        print(f"[Eurex GraphQL] Contracts for {pid}...")
        ctrs = contracts(pid, key)
        print(f"  {len(ctrs)} contracts\n")
        print(f"  {'Contract':<25} {'Settlement':>15}")
        print("  " + "─" * 42)
        for c in ctrs:
            print(f"  {c.get('Contract',''):<25} "
                  f"{str(c.get('PreviousDaySettlementPrice','') or ''):>15}")

        out = Path(args.out) if args.out else DATA / f"eurex_{pid}_contracts.csv"
        if ctrs:
            keys = list(ctrs[0].keys())
            with open(out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader(); w.writerows(ctrs)
            print(f"\n  Saved: {out}")

    # ── Trading hours ──────────────────────────────────────────────────────────
    if args.trading_hours is not None:
        pid = args.trading_hours.upper() if args.trading_hours else None
        label = pid or "all products"
        print(f"[Eurex GraphQL] Trading hours for {label}...")
        hours = trading_hours(pid, key)
        print(f"  {len(hours)} records\n")
        print(f"  {'Product':<12} {'PreTrade Start':<20} {'Cont. Open':>12} {'Cont. Close':>13}")
        print("  " + "─" * 60)
        for h in hours[:20]:
            print(f"  {h.get('Product',''):<12} "
                  f"{str(h.get('StartContinuousTrading','')):<20} "
                  f"{str(h.get('EndOpeningAuction','') or ''):>12} "
                  f"{str(h.get('EndContinuousTrading','') or ''):>13}")

        out = Path(args.out) if args.out else DATA / "eurex_trading_hours.csv"
        if hours:
            keys = list(hours[0].keys())
            with open(out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader(); w.writerows(hours)
            print(f"\n  Saved: {out}")

    # ── Holidays ───────────────────────────────────────────────────────────────
    if args.holidays:
        print("[Eurex GraphQL] Trading holiday calendar...")
        hols = trading_holidays(key)
        print(f"  {len(hols)} holiday records\n")
        for h in hols:
            print(f"  {h.get('Holiday',''):<15} {h.get('ExchangeHoliday','')}")

        out = Path(args.out) if args.out else DATA / "eurex_holidays.csv"
        if hols:
            keys = list(hols[0].keys())
            with open(out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader(); w.writerows(hols)
            print(f"\n  Saved: {out}")

    # ── Schema introspection ───────────────────────────────────────────────────
    if args.introspect:
        print("[Eurex GraphQL] Available API fields (introspection)...")
        schema = introspect(key)
        fields = (schema.get("__schema", {})
                       .get("queryType", {})
                       .get("fields", []))
        print(f"\n  {'Query':<30} Description")
        print("  " + "─" * 60)
        for f in fields:
            print(f"  {f['name']:<30} {f.get('description','')[:40]}")

    if not any([args.products, args.all_products, args.contracts,
                args.trading_hours is not None, args.holidays, args.introspect]):
        parser.print_help()
        print("""
Examples:
  python3 german_market/eurex_graphql.py --products
  python3 german_market/eurex_graphql.py --products --filter DAX
  python3 german_market/eurex_graphql.py --contracts ODAX
  python3 german_market/eurex_graphql.py --contracts FGBL
  python3 german_market/eurex_graphql.py --trading-hours FDAX
  python3 german_market/eurex_graphql.py --trading-hours        # all products
  python3 german_market/eurex_graphql.py --holidays
  python3 german_market/eurex_graphql.py --introspect           # show all API fields
  python3 german_market/eurex_graphql.py --all-products --out data/eurex_products.csv
""")


if __name__ == "__main__":
    main()
