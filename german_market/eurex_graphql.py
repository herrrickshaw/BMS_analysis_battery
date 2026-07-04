#!/usr/bin/env python3
"""
Eurex GraphQL API - Free Public Endpoint
Query: Products, contracts, reference data, settlement info
No authentication required - public API
"""

import requests
import json
import csv
from datetime import datetime
from pathlib import Path
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

EUREX_GRAPHQL_ENDPOINT = "https://console.developer.deutsche-boerse.com/graphql"

class EurexGraphQLClient:
    def __init__(self):
        self.endpoint = EUREX_GRAPHQL_ENDPOINT
        self.session = requests.Session()
        self.output_dir = Path.home() / "eurex_data"
        self.output_dir.mkdir(exist_ok=True)
    
    def query(self, query_string):
        """Execute GraphQL query"""
        try:
            response = self.session.post(
                self.endpoint,
                json={"query": query_string},
                timeout=30,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                logger.error(f"GraphQL error: {data['errors']}")
                return None
            
            return data.get("data", {})
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return None
    
    def get_all_products(self, market="XEUR"):
        """Get all Eurex products"""
        query = f"""
        query {{
          products(first: 1000, market: "{market}") {{
            edges {{
              node {{
                productId
                isin
                shortName
                longName
                description
                market
                marketSegment
                state
                currency
                issuer
                strikePrice
                expiryDate
                optionType
              }}
            }}
            pageInfo {{
              hasNextPage
              endCursor
            }}
          }}
        }}
        """
        
        logger.info(f"Fetching all products from market {market}...")
        data = self.query(query)
        
        if not data:
            return []
        
        products = []
        edges = data.get("products", {}).get("edges", [])
        
        for edge in edges:
            node = edge.get("node", {})
            products.append(node)
        
        logger.info(f"✓ Retrieved {len(products)} products")
        return products
    
    def get_dax_options(self):
        """Get DAX options chain"""
        query = """
        query {
          products(first: 500, market: "XEUR", filter: {contractType: OPTION, underlying: "ODAX"}) {
            edges {
              node {
                productId
                shortName
                strikePrice
                expiryDate
                optionType
                lastPrice
                bidPrice
                askPrice
                volume
                openInterest
              }
            }
          }
        }
        """
        
        logger.info("Fetching DAX options...")
        data = self.query(query)
        
        if not data:
            return []
        
        options = []
        edges = data.get("products", {}).get("edges", [])
        
        for edge in edges:
            options.append(edge.get("node", {}))
        
        logger.info(f"✓ Retrieved {len(options)} DAX options")
        return options
    
    def get_settlement_info(self, isin, date=None):
        """Get settlement information for contract"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        query = f"""
        query {{
          settlements(isin: "{isin}", date: "{date}") {{
            isin
            date
            settlementPrice
            openInterest
            volume
            highPrice
            lowPrice
          }}
        }}
        """
        
        logger.info(f"Fetching settlement info for {isin}...")
        data = self.query(query)
        return data
    
    def export_products_csv(self, products):
        """Export products to CSV"""
        if not products:
            logger.warning("No products to export")
            return
        
        output_file = self.output_dir / f"eurex_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            keys = set()
            for p in products:
                keys.update(p.keys())
            
            with open(output_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=sorted(keys))
                writer.writeheader()
                writer.writerows(products)
            
            logger.info(f"✓ Exported {len(products)} products to {output_file}")
        except Exception as e:
            logger.error(f"Export failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Eurex GraphQL API Client")
    parser.add_argument("--products", action="store_true", help="Get all products")
    parser.add_argument("--contracts", type=str, help="Get contracts for underlying (e.g., ODAX)")
    parser.add_argument("--dax-options", action="store_true", help="Get DAX options chain")
    parser.add_argument("--settlement", type=str, help="Get settlement info (ISIN)")
    parser.add_argument("--date", type=str, help="Settlement date (YYYY-MM-DD)")
    parser.add_argument("--all-products", action="store_true", help="Download all products to CSV")
    
    args = parser.parse_args()
    
    client = EurexGraphQLClient()
    
    if args.products or args.all_products:
        products = client.get_all_products()
        print(f"\n✓ Found {len(products)} Eurex products")
        if products:
            print("\nFirst 5 products:")
            for p in products[:5]:
                print(f"  - {p.get('shortName', 'N/A')} ({p.get('isin', 'N/A')})")
        
        if args.all_products:
            client.export_products_csv(products)
    
    elif args.dax_options:
        options = client.get_dax_options()
        print(f"\n✓ Found {len(options)} DAX options")
        if options:
            print("\nSample options:")
            for opt in options[:5]:
                print(f"  - {opt.get('shortName')} Strike: {opt.get('strikePrice')} Type: {opt.get('optionType')}")
    
    elif args.settlement:
        settlement = client.get_settlement_info(args.settlement, args.date)
        print(f"\n✓ Settlement info for {args.settlement}:")
        print(json.dumps(settlement, indent=2))
    
    else:
        print("✓ Eurex GraphQL API client ready")
        print("  Run with --products to fetch all Eurex products")
        print("  Run with --dax-options to get DAX options chain")
        print("  Run with --all-products to export all products to CSV")

if __name__ == "__main__":
    main()
