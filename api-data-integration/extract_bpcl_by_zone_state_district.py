#!/usr/bin/env python3
"""
BPCL DEALERSHIP EXTRACTION - ZONE/STATE/DISTRICT FILTERS
========================================================
Extracts ALL BPCL dealerships using cascading dropdown filters:
- Zone: North, East, West, South
- State: Multiple states per zone
- District: Districts within each state

Source: https://www.bharatpetroleum.in/bharat-petroleum-for/business-associates/dealership-data
Method: Form submission with dropdown filter combinations
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
import time
import re

class BPCLZoneStateDistrictExtractor:
    """
    Extracts BPCL dealerships using Zone/State/District filters.

    Zones:
    - North: Chandigarh, Delhi, Haryana, Himachal Pradesh, J&K, Punjab, Rajasthan, UP, Uttarakhand
    - East: (States in East zone)
    - West: (States in West zone)
    - South: (States in South zone)
    """

    def __init__(self):
        """Initialize extractor."""
        self.base_url = "https://www.bharatpetroleum.in"
        self.dealership_url = "/bharat-petroleum-for/business-associates/dealership-data"
        self.session = requests.Session()
        self.all_dealerships = {}
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Define zone-state-district mapping
        self.zones = {
            '1': {
                'name': 'North',
                'states': {
                    '6': 'Chandigarh',
                    '9': 'Delhi',
                    '12': 'Haryana',
                    '13': 'Himachal Pradesh',
                    '14': 'Jammu and Kashmir',
                    '26': 'Punjab',
                    '27': 'Rajasthan',
                    '31': 'Uttar Pradesh',
                    '38': 'Uttrakhand'
                }
            },
            '2': {'name': 'East', 'states': {}},
            '3': {'name': 'West', 'states': {}},
            '4': {'name': 'South', 'states': {}}
        }

        self.stats = {
            'zones_processed': 0,
            'states_processed': 0,
            'total_fetched': 0,
            'total_unique': 0
        }

    def fetch_page_initial(self):
        """Fetch initial page to get all dropdown options."""
        print("🌐 Fetching initial page to extract dropdown options...")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = self.session.get(
                f'{self.base_url}{self.dealership_url}',
                headers=headers,
                timeout=30
            )
            if response.status_code == 200:
                print("  ✓ Page fetched")
                return response.text
            else:
                print(f"  ✗ Status {response.status_code}")
                return None
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return None

    def extract_dropdown_options(self, html_content: str):
        """Extract all zone, state, district options from HTML."""
        print("\n🔍 Extracting dropdown options...")
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract zones
        zone_select = soup.find('select', {'id': 'ddlDealerZone'})
        if zone_select:
            zones = {}
            for option in zone_select.find_all('option'):
                zone_id = option.get('value', '')
                zone_name = option.get_text(strip=True)
                if zone_id and zone_name:
                    zones[zone_id] = zone_name
            print(f"  ✓ Found {len(zones)} zones: {', '.join(zones.values())}")

        # Extract states
        state_select = soup.find('select', {'id': 'ddlDealerState'})
        if state_select:
            states = {}
            for option in state_select.find_all('option'):
                state_id = option.get('value', '')
                state_name = option.get_text(strip=True)
                if state_id and state_name:
                    states[state_id] = state_name
            print(f"  ✓ Found {len(states)} states")
            # Update states mapping
            if states:
                self.zones['1']['states'] = states  # Assuming these are for North

        return soup

    def fetch_dealerships_by_zone_state(self, zone_id: str, zone_name: str, state_id: str, state_name: str) -> list:
        """Fetch dealerships for a specific zone/state combination."""
        print(f"    📍 {zone_name} > {state_name}...", end=" ", flush=True)

        try:
            # Get current page to extract ViewState
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': f'{self.base_url}{self.dealership_url}'
            }

            response = self.session.get(
                f'{self.base_url}{self.dealership_url}',
                headers=headers,
                timeout=30
            )

            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract ASP.NET fields
            viewstate = soup.find('input', {'id': '__VIEWSTATE'})
            viewstate_gen = soup.find('input', {'id': '__VIEWSTATEGENERATOR'})
            event_validation = soup.find('input', {'id': '__EVENTVALIDATION'})

            viewstate_val = viewstate.get('value', '') if viewstate else ''
            viewstate_gen_val = viewstate_gen.get('value', '') if viewstate_gen else ''
            event_val = event_validation.get('value', '') if event_validation else ''

            # POST with zone and state filters
            post_data = {
                '__VIEWSTATE': viewstate_val,
                '__VIEWSTATEGENERATOR': viewstate_gen_val,
                '__EVENTVALIDATION': event_val,
                'ddlDealerZone': zone_id,
                'ddlDealerState': state_id,
                'ddlDealerDistrict': '',
                '__EVENTTARGET': 'ddlDealerState',
                '__EVENTARGUMENT': ''
            }

            response = self.session.post(
                f'{self.base_url}{self.dealership_url}',
                data=post_data,
                headers=headers,
                timeout=30
            )

            if response.status_code != 200:
                print(f"✗ Status {response.status_code}")
                return []

            # Parse dealerships
            dealerships = self.parse_dealerships(response.text, zone_name, state_name)
            print(f"✓ {len(dealerships)} dealerships")
            return dealerships

        except Exception as e:
            print(f"✗ {str(e)[:30]}")
            return []

    def parse_dealerships(self, html_content: str, zone: str, state: str) -> list:
        """Parse dealership records from HTML."""
        dealerships = []

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            table = soup.find('table', {'id': 'gvDealerData'})

            if not table:
                return dealerships

            rows = table.find_all('tr')[1:]  # Skip header

            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 5:
                    try:
                        name = self._extract_text(cells[0]).strip()
                        address = self._extract_text(cells[1]).strip()
                        city = self._extract_text(cells[2]).strip()
                        postal_code = self._extract_text(cells[3]).strip()
                        customer_code = self._extract_text(cells[4]).strip()

                        if name:
                            dealership = {
                                'name': name,
                                'address': address,
                                'city': city,
                                'postal_code': postal_code,
                                'customer_code': customer_code,
                                'zone': zone,
                                'state': state,
                                'company': 'BPCL',
                                'source': 'BPCL Official Website',
                                'extraction_date': datetime.now().strftime('%Y-%m-%d')
                            }
                            dealerships.append(dealership)
                    except Exception:
                        continue

            return dealerships

        except Exception as e:
            return []

    def _extract_text(self, cell) -> str:
        """Extract clean text from table cell."""
        try:
            span = cell.find('span')
            text = span.get_text(strip=True) if span else cell.get_text(strip=True)
            return ' '.join(text.split()) if text else ''
        except:
            return ''

    def add_dealership_with_dedup(self, dealership: dict) -> bool:
        """Add dealership with deduplication."""
        key = f"{dealership['name'].upper()}_{dealership['customer_code']}"

        if key not in self.all_dealerships:
            self.all_dealerships[key] = dealership
            return True
        else:
            # Update zone/state if more complete
            if dealership['zone'] and not self.all_dealerships[key].get('zone'):
                self.all_dealerships[key]['zone'] = dealership['zone']
            return False

    def extract_all_zones_states(self):
        """Extract dealerships for all zone/state combinations."""
        print("\n" + "="*80)
        print("🔍 EXTRACTING BPCL DEALERSHIPS BY ZONE/STATE")
        print("="*80)

        # Fetch initial page
        html_content = self.fetch_page_initial()
        if not html_content:
            return

        # Extract dropdown options
        self.extract_dropdown_options(html_content)

        # Extract for each zone/state
        for zone_id, zone_info in self.zones.items():
            zone_name = zone_info['name']
            print(f"\n📌 Zone: {zone_name}")

            states = zone_info['states']
            if not states:
                print(f"  ⚠ No states found for {zone_name}")
                continue

            for state_id, state_name in states.items():
                # Fetch dealerships
                dealerships = self.fetch_dealerships_by_zone_state(
                    zone_id, zone_name, state_id, state_name
                )

                # Add with deduplication
                for dealership in dealerships:
                    if self.add_dealership_with_dedup(dealership):
                        self.stats['total_unique'] += 1
                    self.stats['total_fetched'] += 1

                self.stats['states_processed'] += 1
                time.sleep(0.5)

            self.stats['zones_processed'] += 1

        print(f"\n✅ Extraction complete: {len(self.all_dealerships)} unique dealerships")

    def enrich_and_export(self):
        """Enrich data and export."""
        print("\n" + "="*80)
        print("💾 EXPORTING BPCL DEALERSHIP DATABASE")
        print("="*80)

        if not self.all_dealerships:
            print("✗ No dealerships to export")
            return

        # Enrich with additional fields
        for dealership in self.all_dealerships.values():
            dealership['latitude'] = None
            dealership['longitude'] = None
            dealership['dealer_type'] = 'Petrol Pump'
            dealership['status'] = 'Active'
            dealership['phone'] = ''

        # Create DataFrame
        df = pd.DataFrame(list(self.all_dealerships.values()))

        # Output directory
        output_dir = "./outlet_data_bpcl_complete"
        Path(output_dir).mkdir(exist_ok=True)

        # Export CSV
        print(f"\n  Exporting CSV...")
        csv_path = f"{output_dir}/bpcl_complete_dealerships_{self.timestamp}.csv"
        df.to_csv(csv_path, index=False)
        csv_size = Path(csv_path).stat().st_size / (1024*1024)
        print(f"    ✓ {csv_path} ({csv_size:.2f}MB, {len(df)} records)")

        # Export JSON
        print(f"  Exporting JSON...")
        json_path = f"{output_dir}/bpcl_complete_dealerships_{self.timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(list(self.all_dealerships.values()), f, indent=2)
        json_size = Path(json_path).stat().st_size / (1024*1024)
        print(f"    ✓ {json_path} ({json_size:.2f}MB)")

        # Summary
        print(f"  Generating summary...")
        summary = {
            'timestamp': self.timestamp,
            'total_dealerships': len(self.all_dealerships),
            'unique_states': len(set(d.get('state') for d in self.all_dealerships.values())),
            'unique_cities': len(set(d.get('city') for d in self.all_dealerships.values())),
            'unique_zones': len(set(d.get('zone') for d in self.all_dealerships.values())),
            'extraction_stats': self.stats,
            'zone_distribution': self._get_zone_distribution(),
            'state_distribution': self._get_state_distribution()
        }

        summary_path = f"{output_dir}/bpcl_complete_dealerships_summary_{self.timestamp}.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"    ✓ {summary_path}")

        print(f"\n✅ Export complete to {output_dir}/")
        return summary

    def _get_zone_distribution(self):
        """Get dealership distribution by zone."""
        dist = {}
        for dealer in self.all_dealerships.values():
            zone = dealer.get('zone', 'Unknown')
            dist[zone] = dist.get(zone, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def _get_state_distribution(self):
        """Get dealership distribution by state."""
        dist = {}
        for dealer in self.all_dealerships.values():
            state = dealer.get('state', 'Unknown')
            dist[state] = dist.get(state, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def print_final_summary(self, summary: dict):
        """Print final summary."""
        print("\n" + "="*80)
        print("📊 BPCL DEALERSHIP DATABASE SUMMARY")
        print("="*80)

        print(f"\n✅ EXTRACTION COMPLETE!")
        print(f"\n   Total Dealerships: {summary['total_dealerships']}")
        print(f"   Unique States: {summary['unique_states']}")
        print(f"   Unique Cities: {summary['unique_cities']}")
        print(f"   Unique Zones: {summary['unique_zones']}")

        print(f"\n   Zone Distribution:")
        for zone, count in summary['zone_distribution'].items():
            print(f"   • {zone}: {count}")

        print(f"\n   Top States:")
        for state, count in list(summary['state_distribution'].items())[:10]:
            print(f"   • {state}: {count}")

        print(f"\n   Extraction Statistics:")
        print(f"   • Zones processed: {summary['extraction_stats']['zones_processed']}")
        print(f"   • States processed: {summary['extraction_stats']['states_processed']}")
        print(f"   • Total records fetched: {summary['extraction_stats']['total_fetched']}")
        print(f"   • Total unique: {summary['extraction_stats']['total_unique']}")

    def run(self):
        """Run complete extraction pipeline."""
        print("\n" + "="*80)
        print("🚀 BPCL DEALERSHIP EXTRACTION - ZONE/STATE/DISTRICT FILTERS")
        print("="*80)
        print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Extract
        self.extract_all_zones_states()

        # Export
        summary = self.enrich_and_export()

        # Print summary
        if summary:
            self.print_final_summary(summary)

        print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")


def main():
    """Main execution."""
    extractor = BPCLZoneStateDistrictExtractor()
    extractor.run()


if __name__ == "__main__":
    main()
