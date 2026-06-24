#!/usr/bin/env python3
"""
SSRI Petrol Pumps API Client
Access actual petrol pump data from SSR Innovation Lab
Endpoints discovered from https://api.ssrinnovationlab.com/api/test/18/
"""

import requests
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict

class SSRIPetrolPumpsAPI:
    def __init__(self):
        self.base_url = "https://api.ssrinnovationlab.com"
        self.api_path = "/api/petrol-pumps/pumps"
        self.pumps = []
        self.stats = {
            'total': 0,
            'states': {},
            'companies': {},
            'cities': {}
        }

    def fetch_all_pumps(self, limit: int = 1000, page: int = 1) -> List[Dict]:
        """
        Fetch all petrol pumps from API

        Parameters:
        - limit: Number of records per page (default 1000)
        - page: Page number (default 1)
        """
        print(f"\n📥 Fetching petrol pumps from SSR API...")
        print(f"   Endpoint: {self.base_url}{self.api_path}/")
        print(f"   Parameters: limit={limit}, page={page}")

        try:
            params = {
                'limit': limit,
                'page': page
            }

            response = requests.get(
                f"{self.base_url}{self.api_path}/",
                params=params,
                timeout=30,
                headers={'Accept': 'application/json'}
            )

            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()

                    # Handle different response formats
                    if isinstance(data, list):
                        pumps = data
                    elif isinstance(data, dict):
                        pumps = data.get('results', data.get('data', data.get('pumps', [])))
                    else:
                        pumps = []

                    print(f"   ✓ Fetched {len(pumps)} pumps")
                    return pumps

                except json.JSONDecodeError as e:
                    print(f"   ✗ Invalid JSON: {e}")
                    return []
            else:
                print(f"   ✗ API Error: {response.status_code}")
                return []

        except Exception as e:
            print(f"   ✗ Request failed: {e}")
            return []

    def fetch_by_city(self, city: str) -> List[Dict]:
        """Fetch pumps by city"""
        print(f"\n📥 Fetching pumps in {city}...")

        try:
            response = requests.get(
                f"{self.base_url}{self.api_path}/by-city/",
                params={'city': city},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                pumps = data if isinstance(data, list) else data.get('results', [])
                print(f"   ✓ Found {len(pumps)} pumps in {city}")
                return pumps
            else:
                print(f"   ⚠ Status {response.status_code}")
                return []

        except Exception as e:
            print(f"   ✗ Error: {e}")
            return []

    def fetch_by_company(self, company: str) -> List[Dict]:
        """Fetch pumps by company (IOCL, BPCL, HPCL, Shell, etc.)"""
        print(f"\n📥 Fetching {company} pumps...")

        try:
            response = requests.get(
                f"{self.base_url}{self.api_path}/by-company/",
                params={'company': company},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                pumps = data if isinstance(data, list) else data.get('results', [])
                print(f"   ✓ Found {len(pumps)} {company} pumps")
                return pumps
            else:
                print(f"   ⚠ Status {response.status_code}")
                return []

        except Exception as e:
            print(f"   ✗ Error: {e}")
            return []

    def fetch_nearby(self, latitude: float, longitude: float, radius: int = 5) -> List[Dict]:
        """Fetch nearby pumps within radius (km)"""
        print(f"\n📥 Fetching pumps near {latitude}, {longitude} (radius: {radius}km)...")

        try:
            response = requests.get(
                f"{self.base_url}{self.api_path}/nearby/",
                params={
                    'latitude': latitude,
                    'longitude': longitude,
                    'radius': radius
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                pumps = data if isinstance(data, list) else data.get('results', [])
                print(f"   ✓ Found {len(pumps)} nearby pumps")
                return pumps
            else:
                print(f"   ⚠ Status {response.status_code}")
                return []

        except Exception as e:
            print(f"   ✗ Error: {e}")
            return []

    def process_pumps(self, pumps: List[Dict]) -> List[Dict]:
        """Process and standardize pump data"""
        print(f"\n⚙️  Processing {len(pumps)} pumps...")

        processed = []

        for pump in pumps:
            try:
                # Standardize fields
                proc_pump = {
                    'name': pump.get('name') or pump.get('pump_name') or 'Unknown',
                    'latitude': self._safe_float(pump.get('latitude') or pump.get('lat')),
                    'longitude': self._safe_float(pump.get('longitude') or pump.get('lng')),
                    'city': pump.get('city') or pump.get('location') or 'Unknown',
                    'state': pump.get('state') or 'Unknown',
                    'company': pump.get('company') or pump.get('brand') or 'Unknown',
                    'address': pump.get('address') or '',
                    'phone': pump.get('phone') or '',
                    'fuel_types': pump.get('fuel_types') or []
                }

                # Only add if has coordinates
                if proc_pump['latitude'] and proc_pump['longitude']:
                    processed.append(proc_pump)

                    # Update stats
                    state = proc_pump['state']
                    city = proc_pump['city']
                    company = proc_pump['company']

                    self.stats['states'][state] = self.stats['states'].get(state, 0) + 1
                    self.stats['cities'][city] = self.stats['cities'].get(city, 0) + 1
                    self.stats['companies'][company] = self.stats['companies'].get(company, 0) + 1

            except Exception as e:
                continue

        self.stats['total'] = len(processed)

        print(f"   ✓ Processed {len(processed)} pumps")
        print(f"   ✓ States: {len(self.stats['states'])}")
        print(f"   ✓ Cities: {len(self.stats['cities'])}")
        print(f"   ✓ Companies: {len(self.stats['companies'])}")

        return processed

    def _safe_float(self, value) -> float:
        """Safely convert to float"""
        try:
            return float(value) if value else None
        except (ValueError, TypeError):
            return None

    def export_data(self, pumps: List[Dict], output_dir: str = "./outlet_data_ssri_pumps"):
        """Export pump data to multiple formats"""
        if not pumps:
            print("✗ No data to export")
            return

        Path(output_dir).mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print(f"\n💾 Exporting to {output_dir}/...")

        try:
            df = pd.DataFrame(pumps)

            # CSV
            csv_path = f"{output_dir}/ssri_pumps_{timestamp}.csv"
            df.to_csv(csv_path, index=False)
            print(f"   ✓ CSV: {csv_path}")

            # GeoJSON
            geojson = {"type": "FeatureCollection", "features": []}
            for pump in pumps:
                if pump['latitude'] and pump['longitude']:
                    geojson["features"].append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [pump['longitude'], pump['latitude']]
                        },
                        "properties": {
                            "name": pump['name'],
                            "company": pump['company'],
                            "city": pump['city'],
                            "state": pump['state'],
                            "address": pump.get('address', '')
                        }
                    })

            geojson_path = f"{output_dir}/ssri_pumps_{timestamp}.geojson"
            with open(geojson_path, 'w') as f:
                json.dump(geojson, f, indent=2)
            print(f"   ✓ GeoJSON: {geojson_path} ({len(geojson['features'])} features)")

            # JavaScript
            js_path = f"{output_dir}/ssri_pumps_{timestamp}.js"
            js_content = f"""// SSRI Petrol Pumps Data
// Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

const FUEL_PUMP_LOCATIONS = {json.dumps(pumps)};

const OUTLET_STATS = {{
    total: {len(pumps)},
    states: {len(self.stats['states'])},
    cities: {len(self.stats['cities'])},
    companies: {len(self.stats['companies'])},
    source: 'SSRI Petrol Pumps API'
}};
"""
            with open(js_path, 'w') as f:
                f.write(js_content)
            print(f"   ✓ JavaScript: {js_path}")

            # State-wise summary
            state_summary = {}
            for state, count in sorted(self.stats['states'].items()):
                state_summary[state] = count

            summary_path = f"{output_dir}/ssri_state_wise_{timestamp}.json"
            with open(summary_path, 'w') as f:
                json.dump({
                    'timestamp': timestamp,
                    'total_pumps': len(pumps),
                    'states': state_summary,
                    'cities': self.stats['cities'],
                    'companies': self.stats['companies']
                }, f, indent=2)
            print(f"   ✓ Summary: {summary_path}")

            print(f"\n✅ Export complete!")
            return output_dir

        except Exception as e:
            print(f"   ✗ Error: {e}")
            return None

    def print_summary(self):
        """Print summary"""
        print("\n" + "="*70)
        print("📊 SSRI PETROL PUMPS SUMMARY")
        print("="*70)
        print(f"Total Pumps: {self.stats['total']}")
        print(f"States: {len(self.stats['states'])}")
        print(f"Cities: {len(self.stats['cities'])}")
        print(f"Companies: {list(self.stats['companies'].keys())}")

        print(f"\n📍 Top 10 States:")
        for state, count in sorted(self.stats['states'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   {state}: {count}")

        print("="*70)


def main():
    """Main execution"""
    api = SSRIPetrolPumpsAPI()

    print("\n" + "="*70)
    print("🚀 SSRI PETROL PUMPS API CLIENT")
    print("="*70)

    # Try to fetch all pumps
    pumps = api.fetch_all_pumps(limit=1000)

    if not pumps:
        print("\n⚠ Trying alternative approach...")
        # Try by company
        companies = ['IOCL', 'BPCL', 'HPCL', 'Shell', 'Nayara']
        all_pumps = []
        for company in companies:
            company_pumps = api.fetch_by_company(company)
            all_pumps.extend(company_pumps)
        pumps = all_pumps

    if pumps:
        # Process
        processed = api.process_pumps(pumps)

        if processed:
            # Export
            api.export_data(processed)
            api.print_summary()
        else:
            print("❌ No valid pump data")
    else:
        print("❌ Failed to fetch pump data")


if __name__ == "__main__":
    main()
