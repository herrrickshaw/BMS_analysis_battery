#!/usr/bin/env python3
"""
eurex_graphql.py
================
Queries the Eurex FREE public GraphQL API for Eurex derivatives reference data.
No registration required — uses the shared public API key (rate-limited).

For higher throughput: create a dedicated key at https://developer.deutsche-boerse.com

Data available:
  - Products (futures, options, ETP, equity derivatives, fixed income)
  - Contracts + expirations per product
  - Settlement prices
  - Trading hours
  - TES (Trade Entry Service) configuration

Requirements: pip install requests

Run: python3 german_market/eurex_graphql.py [--products] [--contracts PRODUCT_ID]
     python3 german_market/eurex_graphql.py --all-products --out data/eurex_products.csv
"""
import json, csv, time, argparse
from pathlib import Path

try:
    import requests
except ImportError:
    import sys; sys.exit("pip install requests")

# ── Config ────────────────────────────────────────────────────────────────────
GRAPHQL_URL = "https://api.developer.deutsche-boerse.com/eurex-prod-graphql"

# Shared public key (rate-limited; get your own at developer.deutsche-boerse.com)
SHARED_KEY  = "68cdafd2-c5c1-49be-8558-37244ab4f513"

DATA = Path(__file__).parent.parent / "data"

HEADERS = {
    "X-DBP-APIKEY":  SHARED_KEY,
    "Content-Type":  "application/json",
    "Accept":        "application/json",
    "User-Agent":    "python-requests/eurex-analysis",
}

PAGE_SIZE = 100
RATE_DELAY = 0.3   # seconds between paged requests


# ── GraphQL queries ───────────────────────────────────────────────────────────
QUERY_PRODUCTS = """
query Products($first: Int, $after: String) {
  products(first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        productId
        productName
        productType
        productSubType
        marketSegmentId
        currency
        contractMultiplier
        underlyingIsin
        underlyingSymbol
        underlyingDescription
        tickSize
        tickValue
        minimumReservationSize
        tradingModel
        tradingHours {
          preTradingFrom
          preTradingTo
          tradingFrom
          tradingTo
          postTradingFrom
          postTradingTo
        }
      }
    }
  }
}
"""

QUERY_CONTRACTS = """
query Contracts($productId: String!, $first: Int, $after: String) {
  contracts(productId: $productId, first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        contractId
        isin
        expirationDate
        lastTradingDay
        contractSize
        strikePrice
        callPut
        underlyingIsin
        currency
        version
      }
    }
  }
}
"""

QUERY_SETTLEMENT = """
query SettlementPrices($productId: String!, $date: Date!) {
  settlementPrices(productId: $productId, date: $date) {
    edges {
      node {
        contractId
        settlementPrice
        settlementPriceType
        date
      }
    }
  }
}
"""

QUERY_EXPIRATIONS = """
query Expirations($productId: String!, $first: Int) {
  expirations(productId: $productId, first: $first) {
    edges {
      node {
        expirationDate
        expirationStyle
        settlementStyle
        lastTradingDay
      }
    }
  }
}
"""

QUERY_TRADING_HOURS = """
query TradingHours($productId: String) {
  tradingHours(productId: $productId) {
    edges {
      node {
        productId
        preTradingFrom
        preTradingTo
        tradingFrom
        tradingTo
        postTradingFrom
        postTradingTo
      }
    }
  }
}
"""


# ── API wrapper ───────────────────────────────────────────────────────────────
def gql(query: str, variables: dict = None, api_key: str = SHARED_KEY) -> dict:
    """Execute a GraphQL query and return the data dict."""
    h = dict(HEADERS)
    h["X-DBP-APIKEY"] = api_key
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    r = requests.post(GRAPHQL_URL, json=payload, headers=h, timeout=30)
    r.raise_for_status()
    result = r.json()
    if "errors" in result:
        raise RuntimeError(f"GraphQL errors: {result['errors']}")
    return result.get("data", {})


def paginate(query: str, root_key: str, variables: dict = None,
             api_key: str = SHARED_KEY) -> list:
    """Paginate a connection query; return flat list of node dicts."""
    items = []
    cursor = None
    vars_ = dict(variables or {})
    vars_["first"] = PAGE_SIZE

    while True:
        if cursor:
            vars_["after"] = cursor
        data = gql(query, vars_, api_key)
        conn = data.get(root_key, {})
        edges = conn.get("edges", [])
        items.extend(e["node"] for e in edges)

        page_info = conn.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        time.sleep(RATE_DELAY)

    return items


# ── Analysis functions ────────────────────────────────────────────────────────
def fetch_all_products(api_key=SHARED_KEY) -> list[dict]:
    print("[Eurex GraphQL] Fetching all Eurex products...", end="", flush=True)
    products = paginate(QUERY_PRODUCTS, "products", api_key=api_key)
    print(f" {len(products)} products")
    return products


def fetch_contracts(product_id: str, api_key=SHARED_KEY) -> list[dict]:
    return paginate(QUERY_CONTRACTS, "contracts",
                    {"productId": product_id}, api_key=api_key)


def fetch_settlement_prices(product_id: str, date: str, api_key=SHARED_KEY) -> list[dict]:
    """date: YYYY-MM-DD"""
    data = gql(QUERY_SETTLEMENT, {"productId": product_id, "date": date}, api_key)
    return [e["node"] for e in data.get("settlementPrices", {}).get("edges", [])]


def fetch_expirations(product_id: str, api_key=SHARED_KEY) -> list[dict]:
    return paginate(QUERY_EXPIRATIONS, "expirations",
                    {"productId": product_id, "first": 50}, api_key=api_key)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key",       default=SHARED_KEY,
                        help="Your personal DBP API key (optional)")
    parser.add_argument("--products",      action="store_true",
                        help="List all Eurex products")
    parser.add_argument("--contracts",     metavar="PRODUCT_ID",
                        help="List all contracts for a product (e.g. ODAX, FGBL)")
    parser.add_argument("--settlement",    metavar="PRODUCT_ID",
                        help="Get settlement prices for product (with --date)")
    parser.add_argument("--date",          default="2025-01-10",
                        help="Date for settlement prices YYYY-MM-DD")
    parser.add_argument("--all-products",  action="store_true",
                        help="Download all products + contracts + expirations to CSVs")
    parser.add_argument("--product-type",  default=None,
                        help="Filter by type: OPTION, FUTURE, ETP, ...")
    parser.add_argument("--out",           default=None,
                        help="Output CSV path")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    key = args.api_key

    # ── products ───────────────────────────────────────────────────────────────
    if args.products or args.all_products:
        products = fetch_all_products(key)

        if args.product_type:
            products = [p for p in products
                        if p.get("productType", "").upper() == args.product_type.upper()]
            print(f"  Filtered to {args.product_type}: {len(products)}")

        # Print summary table
        print(f"\n{'ProductID':<12} {'Type':<10} {'SubType':<14} {'Currency':<5} {'Name'}")
        print("─" * 80)
        for p in products[:30]:
            print(f"{p.get('productId',''):<12} {p.get('productType',''):<10} "
                  f"{p.get('productSubType',''):<14} {p.get('currency',''):<5} "
                  f"{p.get('productName','')[:40]}")
        if len(products) > 30:
            print(f"  ... (+{len(products)-30} more)")

        # Breakdown by type
        from collections import Counter
        counts = Counter(p.get("productType") for p in products)
        print(f"\nProduct type breakdown: {dict(counts)}")

        # Save CSV
        out = Path(args.out) if args.out else DATA / "eurex_products.csv"
        if products:
            flat = []
            for p in products:
                row = {k: v for k, v in p.items() if k != "tradingHours"}
                th = p.get("tradingHours") or {}
                row["trading_from"]       = th.get("tradingFrom", "")
                row["trading_to"]         = th.get("tradingTo", "")
                row["pre_trading_from"]   = th.get("preTradingFrom", "")
                row["post_trading_to"]    = th.get("postTradingTo", "")
                flat.append(row)
            keys = list(flat[0].keys()) if flat else []
            with open(out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader(); w.writerows(flat)
            print(f"\nSaved: {out}")

    # ── contracts for one product ──────────────────────────────────────────────
    if args.contracts:
        pid = args.contracts.upper()
        print(f"\n[Eurex GraphQL] Fetching contracts for {pid}...")
        contracts = fetch_contracts(pid, key)
        print(f"  {len(contracts)} contracts")
        print(f"\n{'ContractID':<20} {'ISIN':<14} {'Expiry':<12} {'Strike':>12} "
              f"{'C/P':<4} {'Currency'}")
        print("─" * 75)
        for c in contracts[:25]:
            print(f"{c.get('contractId',''):<20} {c.get('isin',''):<14} "
                  f"{c.get('expirationDate',''):<12} "
                  f"{str(c.get('strikePrice','') or ''):>12} "
                  f"{c.get('callPut',''):<4} {c.get('currency','')}")
        if len(contracts) > 25:
            print(f"  ... (+{len(contracts)-25} more)")

        out = DATA / f"eurex_{pid}_contracts.csv"
        if contracts:
            keys = list(contracts[0].keys())
            with open(out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader(); w.writerows(contracts)
            print(f"\nSaved: {out}")

    # ── settlement prices ──────────────────────────────────────────────────────
    if args.settlement:
        pid = args.settlement.upper()
        print(f"\n[Eurex GraphQL] Settlement prices for {pid} on {args.date}...")
        prices = fetch_settlement_prices(pid, args.date, key)
        print(f"  {len(prices)} records")
        for p in prices[:15]:
            print(f"  {p.get('contractId',''):<20} {p.get('settlementPrice',''):>12} "
                  f"  {p.get('settlementPriceType','')}")

    # ── full download ──────────────────────────────────────────────────────────
    if args.all_products:
        products = fetch_all_products(key)
        print(f"\n[Eurex GraphQL] Downloading contracts for all {len(products)} products...")
        all_contracts = []
        for i, p in enumerate(products):
            pid = p["productId"]
            try:
                contracts = fetch_contracts(pid, key)
                for c in contracts:
                    c["productId"]   = pid
                    c["productName"] = p.get("productName", "")
                    c["productType"] = p.get("productType", "")
                all_contracts.extend(contracts)
                print(f"  [{i+1}/{len(products)}] {pid}: {len(contracts)} contracts "
                      f"(total {len(all_contracts):,})", flush=True)
            except Exception as e:
                print(f"  [{i+1}/{len(products)}] {pid}: ERROR {e}")
            time.sleep(RATE_DELAY)

        out = DATA / "eurex_all_contracts.csv"
        if all_contracts:
            keys = list(all_contracts[0].keys())
            with open(out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                w.writeheader(); w.writerows(all_contracts)
            print(f"\nSaved {len(all_contracts):,} contracts → {out}")


if __name__ == "__main__":
    main()
