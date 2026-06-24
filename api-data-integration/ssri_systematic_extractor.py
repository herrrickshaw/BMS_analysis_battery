#!/usr/bin/env python3
"""
SSRI Systematic Petrol Pumps Data Extractor
Extracts 100,000+ pumps systematically across:
- Multiple pages (pagination)
- All companies (IOCL, BPCL, HPCL, Shell, Nayara, etc.)
- All major Indian cities
- Geographic regions (nearby searches)
"""

import requests
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set
import time
import re

class SSRISystematicExtractor:
    def __init__(self):
        self.base_url = "https://api.ssrinnovationlab.com"
        self.api_path = "/api/petrol-pumps/pumps"
        self.all_pumps = {}  # Use dict with ID as key to deduplicate
        self.stats = {
            'total_fetched': 0,
            'total_unique': 0,
            'states': {},
            'companies': {},
            'cities': {},
            'sources': {
                'pagination': 0,
                'company': 0,
                'city': 0,
                'nearby': 0
            }
        }

    # ===== STRATEGY 1: PAGINATION =====
    def extract_by_pagination(self, max_pages: int = 100):
        """Extract pumps by fetching all pages"""
        print("\n" + "="*70)
        print("📄 STRATEGY 1: PAGINATION (All Pumps)")
        print("="*70)

        page = 1
        consecutive_empty = 0

        while page <= max_pages:
            print(f"\n  Page {page}...")

            try:
                response = requests.get(
                    f"{self.base_url}{self.api_path}/",
                    params={'limit': 1000, 'page': page},
                    timeout=30
                )

                if response.status_code != 200:
                    print(f"    ⚠ Status {response.status_code}")
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    page += 1
                    time.sleep(1)
                    continue

                data = response.json()
                pumps = data if isinstance(data, list) else data.get('results', data.get('data', []))

                if not pumps:
                    consecutive_empty += 1
                    print(f"    ✓ No more data (empty page {consecutive_empty}/3)")
                    if consecutive_empty >= 3:
                        break
                else:
                    consecutive_empty = 0
                    self._add_pumps(pumps, 'pagination')
                    print(f"    ✓ Added {len(pumps)} pumps (total unique: {len(self.all_pumps)})")

                page += 1
                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(f"    ✗ Error: {e}")
                page += 1
                time.sleep(2)

        print(f"\n  ✓ Pagination complete: {self.stats['sources']['pagination']} pumps")

    # ===== STRATEGY 2: BY COMPANY =====
    def extract_by_company(self):
        """Extract pumps by each company"""
        print("\n" + "="*70)
        print("🏢 STRATEGY 2: BY COMPANY")
        print("="*70)

        companies = [
            'IOCL', 'BPCL', 'HPCL', 'Shell', 'Nayara', 'Jio-BP', 'Jio-bp',
            'Indian Oil', 'Bharat Petroleum', 'Hindustan Petroleum',
            'Reliance', 'Essar', 'Chevron'
        ]

        for company in companies:
            print(f"\n  {company}...")

            try:
                response = requests.get(
                    f"{self.base_url}{self.api_path}/by-company/",
                    params={'company': company, 'limit': 1000},
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    pumps = data if isinstance(data, list) else data.get('results', data.get('data', []))

                    if pumps:
                        self._add_pumps(pumps, 'company')
                        print(f"    ✓ Added {len(pumps)} {company} pumps")
                    else:
                        print(f"    - No pumps found")
                else:
                    print(f"    ⚠ Status {response.status_code}")

                time.sleep(0.5)

            except Exception as e:
                print(f"    ✗ Error: {e}")
                time.sleep(1)

        print(f"\n  ✓ Company extraction complete: {self.stats['sources']['company']} new pumps")

    # ===== STRATEGY 3: BY CITY =====
    def extract_by_city(self, cities: List[str] = None):
        """Extract pumps by major cities"""
        print("\n" + "="*70)
        print("🏙️  STRATEGY 3: BY CITY")
        print("="*70)

        if not cities:
            # Major Indian cities and capitals
            cities = [
                # Metros
                'Delhi', 'Mumbai', 'Bangalore', 'Hyderabad', 'Chennai',
                'Kolkata', 'Pune', 'Ahmedabad', 'Jaipur', 'Lucknow',

                # State Capitals
                'Bhopal', 'Indore', 'Nashik', 'Nagpur', 'Aurangabad',
                'Vadodara', 'Surat', 'Rajkot', 'Chandigarh', 'Amritsar',
                'Ludhiana', 'Kota', 'Udaipur', 'Guwahati', 'Patna',
                'Ranchi', 'Raipur', 'Bhubaneswar', 'Kolhapur', 'Visakhapatnam',
                'Vijayawada', 'Kochi', 'Thiruvananthapuram', 'Coimbatore',
                'Madurai', 'Salem', 'Tiruchirappalli', 'Goa', 'Shimla',
                'Dehradun', 'Jodhpur', 'Bikaner', 'Panaji',

                # Tier 2 cities
                'Agra', 'Varanasi', 'Meerut', 'Noida', 'Gurgaon',
                'Faridabad', 'Ghaziabad', 'Kanpur', 'Lucknow', 'Indore',
                'Jabalpur', 'Gwalior', 'Ujjain', 'Sagar', 'Aligarh',
                'Mathura', 'Moradabad', 'Bareilly', 'Pilibhit', 'Haldwani'
            ]

        for city in cities:
            print(f"  {city}...", end=' ')

            try:
                response = requests.get(
                    f"{self.base_url}{self.api_path}/by-city/",
                    params={'city': city, 'limit': 1000},
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    pumps = data if isinstance(data, list) else data.get('results', data.get('data', []))

                    if pumps:
                        self._add_pumps(pumps, 'city')
                        print(f"✓ {len(pumps)} pumps")
                    else:
                        print(f"- 0 pumps")
                else:
                    print(f"⚠ {response.status_code}")

                time.sleep(0.3)

            except Exception as e:
                print(f"✗ Error")
                time.sleep(1)

        print(f"\n  ✓ City extraction complete: {self.stats['sources']['city']} new pumps")

    # ===== STRATEGY 4: NEARBY SEARCHES =====
    def extract_by_nearby(self, locations: List[tuple] = None):
        """Extract pumps using nearby/radius search"""
        print("\n" + "="*70)
        print("📍 STRATEGY 4: NEARBY SEARCHES (Radius)")
        print("="*70)

        if not locations:
            # Major city coordinates + regional centers
            locations = [
                # Metros
                (28.7041, 77.1025, 'Delhi'),
                (19.0760, 72.8777, 'Mumbai'),
                (12.9716, 77.5946, 'Bangalore'),
                (17.3850, 78.4867, 'Hyderabad'),
                (13.0827, 80.2707, 'Chennai'),

                # Regional Centers
                (26.8467, 80.9462, 'Lucknow'),
                (18.5204, 73.8567, 'Pune'),
                (23.0225, 72.5714, 'Ahmedabad'),
                (26.9124, 75.7873, 'Jaipur'),
                (22.5726, 88.3639, 'Kolkata'),
                (30.7333, 76.7794, 'Chandigarh'),
                (21.1456, 79.0882, 'Nagpur'),
                (15.8135, 78.4638, 'Visakhapatnam'),
                (11.0066, 76.9025, 'Coimbatore'),
                (9.9312, 76.2673, 'Kochi'),
            ]

        for lat, lng, city in locations:
            print(f"  {city} ({lat}, {lng})...", end=' ')

            try:
                response = requests.get(
                    f"{self.base_url}{self.api_path}/nearby/",
                    params={
                        'latitude': lat,
                        'longitude': lng,
                        'radius': 50  # 50 km radius
                    },
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    pumps = data if isinstance(data, list) else data.get('results', data.get('data', []))

                    if pumps:
                        self._add_pumps(pumps, 'nearby')
                        print(f"✓ {len(pumps)} pumps")
                    else:
                        print(f"- 0 pumps")
                else:
                    print(f"⚠ {response.status_code}")

                time.sleep(0.3)

            except Exception as e:
                print(f"✗ Error")
                time.sleep(1)

        print(f"\n  ✓ Nearby extraction complete: {self.stats['sources']['nearby']} new pumps")

    # ===== HELPER FUNCTIONS =====
    def _add_pumps(self, pumps: List[Dict], source: str):
        """Add pumps to collection with deduplication"""
        for pump in pumps:
            # Create unique ID based on coordinates + name
            lat = pump.get('latitude') or pump.get('lat')
            lng = pump.get('longitude') or pump.get('lng')
            name = pump.get('name') or pump.get('pump_name') or ''

            if not (lat and lng):
                continue

            pump_id = f"{lat:.4f}_{lng:.4f}_{name[:20]}"

            if pump_id not in self.all_pumps:
                # Standardize pump data
                standardized = {
                    'name': name,
                    'latitude': self._safe_float(lat),
                    'longitude': self._safe_float(lng),
                    'city': pump.get('city') or pump.get('location') or 'Unknown',
                    'state': pump.get('state') or 'Unknown',
                    'company': pump.get('company') or pump.get('brand') or 'Unknown',
                    'address': pump.get('address') or '',
                    'phone': pump.get('phone') or '',
                    'fuel_types': pump.get('fuel_types') or []
                }

                self.all_pumps[pump_id] = standardized

                # Update stats
                state = standardized['state']
                company = standardized['company']
                city = standardized['city']

                self.stats['states'][state] = self.stats['states'].get(state, 0) + 1
                self.stats['companies'][company] = self.stats['companies'].get(company, 0) + 1
                self.stats['cities'][city] = self.stats['cities'].get(city, 0) + 1

                self.stats['sources'][source] += 1
                self.stats['total_fetched'] += 1

        self.stats['total_unique'] = len(self.all_pumps)

    def _safe_float(self, value) -> float:
        """Safely convert to float"""
        try:
            return float(value) if value else None
        except (ValueError, TypeError):
            return None

    # ===== EXPORT FUNCTIONS =====
    def export_data(self, output_dir: str = "./outlet_data_ssri_100k"):
        """Export all extracted data"""
        if not self.all_pumps:
            print("✗ No data to export")
            return

        Path(output_dir).mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print(f"\n" + "="*70)
        print(f"💾 EXPORTING {len(self.all_pumps)} PUMPS")
        print("="*70)

        pumps_list = list(self.all_pumps.values())

        try:
            # CSV
            print(f"\n  Exporting CSV...")
            df = pd.DataFrame(pumps_list)
            csv_path = f"{output_dir}/ssri_pumps_100k_{timestamp}.csv"
            df.to_csv(csv_path, index=False)
            print(f"    ✓ {csv_path}")

            # GeoJSON
            print(f"  Exporting GeoJSON...")
            geojson = {"type": "FeatureCollection", "features": []}
            for pump in pumps_list:
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

            geojson_path = f"{output_dir}/ssri_pumps_100k_{timestamp}.geojson"
            with open(geojson_path, 'w') as f:
                json.dump(geojson, f, indent=2)
            print(f"    ✓ {geojson_path} ({len(geojson['features'])} features)")

            # JavaScript
            print(f"  Exporting JavaScript...")
            js_path = f"{output_dir}/ssri_pumps_100k_{timestamp}.js"
            js_content = f"""// SSRI Petrol Pumps - 100K+ Database
// Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
// Total Pumps: {len(pumps_list)}

const FUEL_PUMP_LOCATIONS = {json.dumps(pumps_list)};

const OUTLET_STATS = {{
    total: {len(pumps_list)},
    states: {len(self.stats['states'])},
    cities: {len(self.stats['cities'])},
    companies: {len(self.stats['companies'])},
    source: 'SSRI Petrol Pumps API (Systematic Extraction)'
}};
"""
            with open(js_path, 'w') as f:
                f.write(js_content)
            print(f"    ✓ {js_path}")

            # JSON
            print(f"  Exporting JSON...")
            json_path = f"{output_dir}/ssri_pumps_100k_{timestamp}.json"
            with open(json_path, 'w') as f:
                json.dump(pumps_list, f, indent=2)
            print(f"    ✓ {json_path}")

            # Summary
            print(f"  Exporting Summary...")
            summary = {
                'timestamp': timestamp,
                'total_pumps': len(pumps_list),
                'unique_states': len(self.stats['states']),
                'unique_cities': len(self.stats['cities']),
                'unique_companies': len(self.stats['companies']),
                'states': self.stats['states'],
                'companies': self.stats['companies'],
                'extraction_sources': self.stats['sources']
            }

            summary_path = f"{output_dir}/ssri_pumps_100k_summary_{timestamp}.json"
            with open(summary_path, 'w') as f:
                json.dump(summary, f, indent=2)
            print(f"    ✓ {summary_path}")

            print(f"\n  ✅ Export complete to {output_dir}/")
            return output_dir

        except Exception as e:
            print(f"  ✗ Export error: {e}")
            return None

    def print_final_summary(self):
        """Print final extraction summary"""
        print("\n" + "="*70)
        print("📊 FINAL EXTRACTION SUMMARY")
        print("="*70)
        print(f"\n  Total Unique Pumps: {len(self.all_pumps):,}")
        print(f"\n  States Covered: {len(self.stats['states'])}")
        for state, count in sorted(self.stats['states'].items(), key=lambda x: x[1], reverse=True)[:15]:
            print(f"    • {state}: {count:,}")
        if len(self.stats['states']) > 15:
            print(f"    ... and {len(self.stats['states']) - 15} more states")

        print(f"\n  Companies: {len(self.stats['companies'])}")
        for company, count in sorted(self.stats['companies'].items(), key=lambda x: x[1], reverse=True):
            print(f"    • {company}: {count:,}")

        print(f"\n  Extraction Sources:")
        total_fetched = sum(self.stats['sources'].values())
        for source, count in self.stats['sources'].items():
            pct = (count / total_fetched * 100) if total_fetched > 0 else 0
            print(f"    • {source.capitalize()}: {count:,} ({pct:.1f}%)")

        print(f"\n  Top Cities: {len(self.stats['cities'])}")
        for city, count in sorted(self.stats['cities'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"    • {city}: {count:,}")

        print("\n" + "="*70)

    def run_full_extraction(self):
        """Run complete systematic extraction"""
        print("\n" + "="*70)
        print("🚀 SSRI SYSTEMATIC EXTRACTION - 100,000+ PUMPS")
        print("="*70)
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Run all strategies
        self.extract_by_pagination(max_pages=150)  # Up to 150,000 pumps
        self.extract_by_company()
        self.extract_by_city()
        self.extract_by_nearby()

        # Export
        output_dir = self.export_data()

        # Summary
        self.print_final_summary()

        print(f"\nEnd time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n✅ EXTRACTION COMPLETE")
        print(f"Total unique pumps: {len(self.all_pumps):,}")

        return output_dir


def main():
    """Main execution"""
    extractor = SSRISystematicExtractor()
    output_dir = extractor.run_full_extraction()

    if output_dir:
        print(f"\n📂 Output directory: {output_dir}")
        print(f"\nNext steps:")
        print(f"  1. Copy JavaScript to maps:")
        print(f"     cp {output_dir}/ssri_pumps_100k_*.js ../fuel-pump-locations-map/locations-data.js")
        print(f"  2. Test in browser:")
        print(f"     cd ../fuel-pump-locations-map/")
        print(f"     python3 -m http.server 8000")
        print(f"  3. Commit to GitHub:")
        print(f"     git add {output_dir}/")
        print(f"     git commit -m 'Add 100K+ SSRI pumps'")
        print(f"     git push origin main")


if __name__ == "__main__":
    main()
