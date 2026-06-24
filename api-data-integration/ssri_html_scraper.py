#!/usr/bin/env python3
"""
SSRI Sandbox HTML Scraper
Extracts retail outlet data from SSRI HTML interface
https://api.ssrinnovationlab.com/api/test/18/
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import re

class SSRIScraper:
    def __init__(self):
        self.url = "https://api.ssrinnovationlab.com/api/test/18/"
        self.outlets = []
        self.stats = {
            'total': 0,
            'states': 0,
            'cities': 0,
            'companies': 0
        }

    def fetch_html(self) -> str:
        """
        Fetch HTML from SSRI sandbox
        """
        print(f"\n📥 Fetching HTML from SSRI sandbox...")
        print(f"   URL: {self.url}")

        try:
            response = requests.get(
                self.url,
                timeout=30,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )

            if response.status_code == 200:
                print(f"   ✓ Successfully fetched HTML ({len(response.text)} bytes)")
                return response.text
            else:
                print(f"   ✗ Failed: Status {response.status_code}")
                return None

        except Exception as e:
            print(f"   ✗ Error: {e}")
            return None

    def parse_html(self, html: str) -> list:
        """
        Parse HTML to extract outlet data
        """
        print(f"\n🔍 Parsing HTML...")

        try:
            soup = BeautifulSoup(html, 'html.parser')

            outlets = []

            # Try to find tables in the HTML
            tables = soup.find_all('table')
            print(f"   Found {len(tables)} tables")

            # Parse each table
            for table_idx, table in enumerate(tables):
                rows = table.find_all('tr')
                print(f"   Table {table_idx + 1}: {len(rows)} rows")

                # Skip header row
                for row in rows[1:]:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        # Extract columns
                        outlet_data = {}

                        # Parse columns (adjust based on actual HTML structure)
                        for i, col in enumerate(cols):
                            text = col.get_text(strip=True)
                            outlet_data[f'col_{i}'] = text

                        outlets.append(outlet_data)

            print(f"   ✓ Extracted {len(outlets)} records from tables")

            # If no tables, try to find divs with data
            if not outlets:
                print(f"   No tables found, trying divs...")
                data_divs = soup.find_all('div', class_=re.compile(r'data|outlet|record'))
                print(f"   Found {len(data_divs)} potential data divs")

                for div in data_divs:
                    text = div.get_text(strip=True)
                    if text:
                        outlets.append({'data': text})

            # If still no data, try paragraphs
            if not outlets:
                print(f"   No divs, trying paragraphs...")
                paragraphs = soup.find_all('p')
                print(f"   Found {len(paragraphs)} paragraphs")

                for p in paragraphs[:100]:  # First 100
                    text = p.get_text(strip=True)
                    if len(text) > 10:  # Only significant text
                        outlets.append({'data': text})

            return outlets

        except Exception as e:
            print(f"   ✗ Parse error: {e}")
            return []

    def extract_state_wise_data(self, outlets: list) -> list:
        """
        Extract state-wise retail outlet information
        """
        print(f"\n📍 Extracting state-wise data...")

        state_wise = {}
        extracted_outlets = []

        # Common Indian states
        states = [
            'Maharashtra', 'Gujarat', 'Karnataka', 'Tamil Nadu', 'Uttar Pradesh',
            'West Bengal', 'Delhi', 'Rajasthan', 'Telangana', 'Andhra Pradesh',
            'Punjab', 'Haryana', 'Madhya Pradesh', 'Odisha', 'Kerala',
            'Jharkhand', 'Chhattisgarh', 'Uttarakhand', 'Himachal Pradesh',
            'Assam', 'Bihar', 'Jammu and Kashmir', 'Ladakh', 'Tripura',
            'Meghalaya', 'Manipur', 'Mizoram', 'Nagaland'
        ]

        companies = ['IOCL', 'BPCL', 'HPCL', 'Shell', 'Nayara']

        # Try to find state and company patterns in data
        for outlet in outlets:
            outlet_text = str(outlet)

            # Check for state mentions
            found_state = None
            for state in states:
                if state.lower() in outlet_text.lower():
                    found_state = state
                    break

            # Check for company mentions
            found_company = None
            for company in companies:
                if company.lower() in outlet_text.lower():
                    found_company = company
                    break

            # Try to extract coordinates (lat, lng patterns)
            lat_match = re.search(r'(\d+\.\d+)[,\s]+latitude', outlet_text, re.IGNORECASE)
            lng_match = re.search(r'(\d+\.\d+)[,\s]+longitude', outlet_text, re.IGNORECASE)

            if found_state or found_company or lat_match:
                extracted = {
                    'raw_data': outlet_text[:100],
                    'state': found_state or 'Unknown',
                    'company': found_company or 'Unknown',
                }

                if found_state:
                    if found_state not in state_wise:
                        state_wise[found_state] = 0
                    state_wise[found_state] += 1

                extracted_outlets.append(extracted)

        print(f"   ✓ Extracted {len(extracted_outlets)} outlets with location info")
        print(f"   ✓ States represented: {len(state_wise)}")
        print(f"\n   State-wise count:")
        for state, count in sorted(state_wise.items(), key=lambda x: x[1], reverse=True):
            print(f"      {state}: {count}")

        return extracted_outlets

    def export_results(self, outlets: list, output_dir: str = "./outlet_data_ssri"):
        """
        Export extracted data
        """
        if not outlets:
            print("✗ No data to export")
            return

        Path(output_dir).mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print(f"\n💾 Exporting to {output_dir}/...")

        try:
            # DataFrame
            df = pd.DataFrame(outlets)

            # CSV
            csv_path = f"{output_dir}/ssri_outlets_{timestamp}.csv"
            df.to_csv(csv_path, index=False)
            print(f"   ✓ CSV: {csv_path}")

            # JSON
            json_path = f"{output_dir}/ssri_outlets_{timestamp}.json"
            with open(json_path, 'w') as f:
                json.dump(outlets, f, indent=2)
            print(f"   ✓ JSON: {json_path}")

            # State summary
            state_summary = {}
            for outlet in outlets:
                state = outlet.get('state', 'Unknown')
                if state not in state_summary:
                    state_summary[state] = {'count': 0, 'companies': set()}
                state_summary[state]['count'] += 1
                if outlet.get('company') != 'Unknown':
                    state_summary[state]['companies'].add(outlet.get('company'))

            # Convert sets to lists for JSON
            for state in state_summary:
                state_summary[state]['companies'] = list(state_summary[state]['companies'])

            summary_path = f"{output_dir}/ssri_state_wise_summary_{timestamp}.json"
            with open(summary_path, 'w') as f:
                json.dump(state_summary, f, indent=2)
            print(f"   ✓ Summary: {summary_path}")

            # Statistics
            stats = {
                'timestamp': timestamp,
                'total_records': len(outlets),
                'unique_states': len(state_summary),
                'states': state_summary
            }

            stats_path = f"{output_dir}/ssri_stats_{timestamp}.json"
            with open(stats_path, 'w') as f:
                json.dump(stats, f, indent=2)
            print(f"   ✓ Statistics: {stats_path}")

            print(f"\n✅ Export complete to {output_dir}/")
            return output_dir

        except Exception as e:
            print(f"   ✗ Export error: {e}")
            return None

    def run(self):
        """
        Execute full scraping pipeline
        """
        print("\n" + "="*70)
        print("🔍 SSRI SANDBOX HTML SCRAPER")
        print("="*70)

        # Fetch HTML
        html = self.fetch_html()
        if not html:
            return

        # Parse HTML
        raw_outlets = self.parse_html(html)
        if not raw_outlets:
            print("❌ No data found in HTML")
            return

        # Extract state-wise data
        extracted = self.extract_state_wise_data(raw_outlets)

        # Export
        if extracted:
            self.export_results(extracted)
            print("\n" + "="*70)
            print(f"✅ SCRAPING COMPLETE")
            print("="*70)
        else:
            print("❌ No structured data could be extracted")


def main():
    """Main execution"""
    scraper = SSRIScraper()
    scraper.run()


if __name__ == "__main__":
    main()
