#!/usr/bin/env python3
"""
BPCL DEALERSHIP DATA EXTRACTION
================================
Extracts comprehensive dealership information from BPCL official website
and integrates with existing SSRI petrol pump database for complete coverage.

Source: https://www.bharatpetroleum.in/bharat-petroleum-for/business-associates/dealership-data
Data Format: HTML table with dealership details
Fields: Name, Address, City, Postal Code, Customer Code
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
import re

class BPCLDealershipExtractor:
    """
    Extracts BPCL dealership data from official website.
    Integrates with SSRI database for comprehensive petrol pump coverage.
    """

    def __init__(self):
        """Initialize BPCL extractor with configuration."""
        self.url = "https://www.bharatpetroleum.in/bharat-petroleum-for/business-associates/dealership-data"
        self.dealerships = []
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def fetch_page(self):
        """
        Fetch BPCL dealership data page from official website.

        Returns:
            str: HTML content of the page

        Handles:
        - HTTP requests with proper headers
        - Timeout handling
        - Error reporting
        """
        print("🌐 Fetching BPCL dealership data page...")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.url, headers=headers, timeout=30)
            response.raise_for_status()
            print(f"  ✓ Page fetched successfully (Status: {response.status_code})")
            return response.text
        except Exception as e:
            print(f"  ✗ Error fetching page: {e}")
            return None

    def parse_dealership_data(self, html_content):
        """
        Parse dealership data from HTML table.

        Extracts:
        - Dealership Name
        - Address
        - City
        - Postal Code
        - Customer Code (Identifier)

        Args:
            html_content (str): HTML content of the page

        Returns:
            list: List of dealership dictionaries
        """
        print("📊 Parsing dealership data from HTML...")

        if not html_content:
            return []

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # Find the table with dealership data
            table = soup.find('table', {'id': 'gvDealerData'})

            if not table:
                print("  ⚠ Could not find dealership data table")
                return []

            # Find all rows in the table
            rows = table.find_all('tr')
            dealerships = []

            print(f"  📋 Found {len(rows)} rows in table")

            for row_idx, row in enumerate(rows):
                try:
                    # Extract cells from the row
                    cells = row.find_all('td')

                    if len(cells) >= 5:
                        # Parse dealership data from table cells
                        name = self._extract_text(cells[0])
                        address = self._extract_text(cells[1])
                        city = self._extract_text(cells[2])
                        postal_code = self._extract_text(cells[3])
                        customer_code = self._extract_text(cells[4])

                        if name:  # Only add if we have a name
                            dealership = {
                                'name': name,
                                'address': address,
                                'city': city,
                                'postal_code': postal_code,
                                'customer_code': customer_code,
                                'company': 'BPCL',
                                'source': 'BPCL Official Website',
                                'extraction_date': datetime.now().strftime('%Y-%m-%d')
                            }
                            dealerships.append(dealership)
                except Exception as e:
                    print(f"    ⚠ Error parsing row {row_idx}: {str(e)[:50]}")
                    continue

            print(f"  ✓ Successfully parsed {len(dealerships)} dealerships")
            return dealerships

        except Exception as e:
            print(f"  ✗ Error parsing HTML: {e}")
            return []

    def _extract_text(self, cell):
        """
        Extract clean text from HTML table cell.

        Handles:
        - Nested elements
        - Whitespace normalization
        - Empty cells

        Args:
            cell: BeautifulSoup element (td)

        Returns:
            str: Extracted and cleaned text
        """
        try:
            # Try to find span elements first (common in ASP.NET tables)
            span = cell.find('span')
            if span:
                text = span.get_text(strip=True)
            else:
                text = cell.get_text(strip=True)

            # Normalize whitespace
            text = ' '.join(text.split())

            return text if text else ''
        except:
            return ''

    def extract_alternative_method(self, html_content):
        """
        Alternative extraction method using regex and direct HTML parsing.
        Useful if table-based extraction fails.

        Args:
            html_content (str): HTML content

        Returns:
            list: List of dealership dictionaries
        """
        print("📊 Attempting alternative extraction method...")

        dealerships = []

        # Look for label elements with dealership data
        # Pattern: id="gvDealerData_lblDealershipName_0", etc.
        soup = BeautifulSoup(html_content, 'html.parser')

        # Find all span elements containing dealership data
        spans = soup.find_all('span', {'id': re.compile(r'gvDealerData_lbl.*')})

        if not spans:
            print("  ⚠ No dealership data found via alternative method")
            return []

        # Group spans by dealership (every 5 spans = 1 dealership)
        dealerships_list = []
        dealership_dict = {}

        for span in spans:
            span_id = span.get('id', '')
            text = span.get_text(strip=True)

            # Extract field type from span ID
            if 'lblDealershipName' in span_id:
                dealership_dict['name'] = text
            elif 'lblAddress' in span_id:
                dealership_dict['address'] = text
            elif 'lblCity' in span_id:
                dealership_dict['city'] = text
            elif 'lblPostalCode' in span_id:
                dealership_dict['postal_code'] = text
            elif 'lblCustomerCode' in span_id:
                dealership_dict['customer_code'] = text
                # When we have all fields, add to list
                if 'name' in dealership_dict:
                    dealership_dict['company'] = 'BPCL'
                    dealership_dict['source'] = 'BPCL Official Website'
                    dealership_dict['extraction_date'] = datetime.now().strftime('%Y-%m-%d')
                    dealerships_list.append(dealership_dict)
                dealership_dict = {}

        print(f"  ✓ Alternative method found {len(dealerships_list)} dealerships")
        return dealerships_list

    def enrich_dealership_data(self):
        """
        Enrich dealership data with additional fields.

        Adds:
        - State extraction from postal code or city
        - Dealer type classification
        - Status (Active assumed)
        """
        print("🔍 Enriching dealership data...")

        # State mapping (postal code prefixes)
        state_map = {
            '16': 'Chandigarh', '17': 'Himachal Pradesh', '18': 'Haryana',
            '19': 'Punjab', '20': 'Delhi', '21': 'Uttar Pradesh', '22': 'Uttar Pradesh',
            '23': 'Rajasthan', '24': 'Gujarat', '25': 'Gujarat', '26': 'Madhya Pradesh',
            '27': 'Madhya Pradesh', '28': 'Maharashtra', '29': 'Maharashtra',
            '30': 'Andhra Pradesh', '31': 'Karnataka', '32': 'Tamil Nadu',
            '33': 'Kerala', '34': 'West Bengal', '35': 'Odisha', '36': 'Jharkhand',
            '37': 'Chhattisgarh', '38': 'Assam', '39': 'Northeast India', '50': 'Bihar',
            '80': 'Goa', '90': 'Jammu & Kashmir'
        }

        for dealership in self.dealerships:
            # Extract state from postal code
            postal = dealership.get('postal_code', '')[:2]
            dealership['state'] = state_map.get(postal, 'Unknown')

            # Add latitude/longitude placeholder (would need geocoding service)
            dealership['latitude'] = None
            dealership['longitude'] = None

            # Add dealer type
            dealership['dealer_type'] = 'Petrol Pump'

            # Add status
            dealership['status'] = 'Active'

        print(f"  ✓ Data enrichment complete")

    def export_data(self, output_dir: str = "./outlet_data_bpcl"):
        """
        Export BPCL dealership data in multiple formats.

        Formats:
        - CSV: Database import, Excel analysis
        - JSON: API ready, structured data
        - GeoJSON: Map integration (coordinates null until geocoded)

        Args:
            output_dir (str): Output directory path
        """
        print("\n" + "="*80)
        print("💾 EXPORTING BPCL DEALERSHIP DATA")
        print("="*80)

        Path(output_dir).mkdir(exist_ok=True)

        if not self.dealerships:
            print("✗ No data to export")
            return

        # Create DataFrame
        df = pd.DataFrame(self.dealerships)

        # Export CSV
        print(f"\n  Exporting CSV...")
        csv_path = f"{output_dir}/bpcl_dealerships_{self.timestamp}.csv"
        df.to_csv(csv_path, index=False)
        csv_size = Path(csv_path).stat().st_size / (1024*1024)
        print(f"    ✓ {csv_path} ({csv_size:.2f}MB)")

        # Export JSON
        print(f"  Exporting JSON...")
        json_path = f"{output_dir}/bpcl_dealerships_{self.timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(self.dealerships, f, indent=2)
        json_size = Path(json_path).stat().st_size / (1024*1024)
        print(f"    ✓ {json_path} ({json_size:.2f}MB)")

        # Export GeoJSON (without coordinates for now)
        print(f"  Exporting GeoJSON...")
        geojson = {"type": "FeatureCollection", "features": []}

        for dealer in self.dealerships:
            # Note: coordinates are null - would need geocoding service
            if dealer.get('latitude') and dealer.get('longitude'):
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [dealer['longitude'], dealer['latitude']]
                    },
                    "properties": {
                        "name": dealer['name'],
                        "address": dealer['address'],
                        "city": dealer['city'],
                        "company": dealer['company']
                    }
                }
                geojson["features"].append(feature)

        geojson_path = f"{output_dir}/bpcl_dealerships_{self.timestamp}.geojson"
        with open(geojson_path, 'w') as f:
            json.dump(geojson, f)
        geojson_size = Path(geojson_path).stat().st_size / (1024*1024)
        print(f"    ✓ {geojson_path} ({geojson_size:.2f}MB, {len(geojson['features'])} features)")

        # Export summary
        print(f"  Generating summary...")
        summary = {
            'timestamp': self.timestamp,
            'total_dealerships': len(self.dealerships),
            'unique_cities': len(set(d.get('city', 'Unknown') for d in self.dealerships)),
            'unique_states': len(set(d.get('state', 'Unknown') for d in self.dealerships)),
            'source': 'BPCL Official Website',
            'data_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'city_distribution': self._get_city_distribution(),
            'state_distribution': self._get_state_distribution()
        }

        summary_path = f"{output_dir}/bpcl_dealerships_summary_{self.timestamp}.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"    ✓ {summary_path}")

        print(f"\n✅ Export complete to {output_dir}/")

    def _get_city_distribution(self):
        """Get dealership distribution by city."""
        city_counts = {}
        for dealer in self.dealerships:
            city = dealer.get('city', 'Unknown')
            city_counts[city] = city_counts.get(city, 0) + 1
        return dict(sorted(city_counts.items(), key=lambda x: x[1], reverse=True))

    def _get_state_distribution(self):
        """Get dealership distribution by state."""
        state_counts = {}
        for dealer in self.dealerships:
            state = dealer.get('state', 'Unknown')
            state_counts[state] = state_counts.get(state, 0) + 1
        return dict(sorted(state_counts.items(), key=lambda x: x[1], reverse=True))

    def run_extraction(self):
        """Run complete BPCL dealership extraction pipeline."""
        print("\n" + "="*80)
        print("🚀 BPCL DEALERSHIP DATA EXTRACTION")
        print("="*80)
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Fetch page
        html_content = self.fetch_page()
        if not html_content:
            print("✗ Failed to fetch page")
            return False

        # Try primary parsing method
        self.dealerships = self.parse_dealership_data(html_content)

        # If primary method fails, try alternative
        if not self.dealerships:
            print("\n⚠ Primary parsing failed, trying alternative method...")
            self.dealerships = self.extract_alternative_method(html_content)

        if not self.dealerships:
            print("✗ All parsing methods failed")
            return False

        # Enrich data
        self.enrich_dealership_data()

        # Export data
        self.export_data()

        # Print summary
        self._print_summary()

        print(f"\nEnd time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")

        return True

    def _print_summary(self):
        """Print extraction summary."""
        print("\n" + "="*80)
        print("📊 EXTRACTION SUMMARY")
        print("="*80)

        if not self.dealerships:
            print("✗ No dealerships extracted")
            return

        print(f"\n✅ EXTRACTION COMPLETE!")
        print(f"\n   Total Dealerships: {len(self.dealerships)}")

        city_dist = self._get_city_distribution()
        state_dist = self._get_state_distribution()

        print(f"   Unique Cities: {len(city_dist)}")
        print(f"   Unique States: {len(state_dist)}")

        print(f"\n   Top Cities:")
        for city, count in list(city_dist.items())[:5]:
            print(f"   • {city}: {count}")

        print(f"\n   Top States:")
        for state, count in list(state_dist.items())[:5]:
            print(f"   • {state}: {count}")

        print("\n   Data Completeness:")
        print(f"   • Names: {sum(1 for d in self.dealerships if d.get('name'))} / {len(self.dealerships)}")
        print(f"   • Addresses: {sum(1 for d in self.dealerships if d.get('address'))} / {len(self.dealerships)}")
        print(f"   • Cities: {sum(1 for d in self.dealerships if d.get('city'))} / {len(self.dealerships)}")
        print(f"   • Postal Codes: {sum(1 for d in self.dealerships if d.get('postal_code'))} / {len(self.dealerships)}")


def main():
    """Main execution."""
    extractor = BPCLDealershipExtractor()
    extractor.run_extraction()


if __name__ == "__main__":
    main()
