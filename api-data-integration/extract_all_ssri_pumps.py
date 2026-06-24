#!/usr/bin/env python3
"""
SSRI Complete Petrol Pumps Extraction
Systematically extracts ALL pumps using multiple strategies with full pagination
"""

import requests
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import time

class CompleteSSRIExtractor:
    def __init__(self):
        self.base_url = "https://api.ssrinnovationlab.com"
        self.api_path = "/api/petrol-pumps/pumps"
        self.all_pumps = {}  # Deduplicated by ID
        self.stats = {
            'pagination': 0,
            'companies': 0,
            'cities': 0,
            'nearby': 0,
            'duplicates_found': 0,
            'total_unique': 0
        }
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def extract_all_pages(self, max_pages: int = 500):
        """Extract all pages with pagination"""
        print("\n" + "="*80)
        print("📄 STRATEGY 1: PAGINATION - Extracting all available pages")
        print("="*80)

        page = 1
        empty_pages = 0
        total_added = 0

        while page <= max_pages and empty_pages < 5:
            try:
                print(f"\n  Page {page}...", end=" ", flush=True)

                response = requests.get(
                    f"{self.base_url}{self.api_path}/",
                    params={'limit': 1000, 'page': page},
                    timeout=30
                )

                if response.status_code != 200:
                    print(f"Status {response.status_code}")
                    empty_pages += 1
                    page += 1
                    continue

                data = response.json()
                pumps = data if isinstance(data, list) else data.get('results', data.get('data', []))

                if not pumps:
                    empty_pages += 1
                    print("Empty")
                    page += 1
                    time.sleep(0.5)
                    continue

                empty_pages = 0
                added = self._add_pumps(pumps, 'pagination')
                total_added += added
                print(f"✓ {len(pumps)} pumps, added {added} new (total unique: {len(self.all_pumps)})")

                page += 1
                time.sleep(0.3)  # Rate limiting

            except Exception as e:
                print(f"Error: {str(e)[:30]}")
                page += 1
                time.sleep(1)

        self.stats['pagination'] = total_added
        print(f"\n✓ Pagination complete: {total_added} pumps added")

    def extract_by_all_companies(self):
        """Extract by all major companies"""
        print("\n" + "="*80)
        print("🏢 STRATEGY 2: BY COMPANY - Extracting all major operators")
        print("="*80)

        companies = [
            'IOCL', 'Indian Oil', 'Indian Oil Corporation',
            'BPCL', 'Bharat Petroleum', 'Bharat Petroleum Corporation',
            'HPCL', 'Hindustan Petroleum', 'Hindustan Petroleum Corporation',
            'Shell', 'Royal Dutch Shell',
            'Nayara', 'Nayara Energy', 'Essar',
            'Jio-BP', 'Jio-bp', 'Reliance',
            'BP', 'Chevron', 'TPC', 'Lukoil'
        ]

        total_added = 0

        for company in companies:
            try:
                print(f"  {company:30}", end=" ", flush=True)

                response = requests.get(
                    f"{self.base_url}{self.api_path}/by-company/",
                    params={'company': company, 'limit': 1000},
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    pumps = data if isinstance(data, list) else data.get('results', data.get('data', []))

                    if pumps:
                        added = self._add_pumps(pumps, 'company')
                        total_added += added
                        print(f"✓ {added} new pumps")
                    else:
                        print("No results")
                else:
                    print(f"Status {response.status_code}")

                time.sleep(0.5)

            except Exception as e:
                print(f"Error")
                time.sleep(1)

        self.stats['companies'] = total_added
        print(f"\n✓ Company extraction complete: {total_added} pumps added")

    def extract_major_cities(self):
        """Extract from all major cities"""
        print("\n" + "="*80)
        print("🏙️  STRATEGY 3: BY CITY - Extracting from all major cities")
        print("="*80)

        cities = [
            # Metros
            'Delhi', 'Mumbai', 'Bangalore', 'Hyderabad', 'Chennai',
            'Kolkata', 'Pune', 'Ahmedabad', 'Jaipur', 'Lucknow',

            # State Capitals & Tier-1
            'Bhopal', 'Indore', 'Nashik', 'Nagpur', 'Aurangabad',
            'Vadodara', 'Surat', 'Rajkot', 'Chandigarh', 'Amritsar',
            'Ludhiana', 'Kota', 'Udaipur', 'Guwahati', 'Patna',
            'Ranchi', 'Raipur', 'Bhubaneswar', 'Kolhapur', 'Visakhapatnam',
            'Vijayawada', 'Kochi', 'Thiruvananthapuram', 'Coimbatore',
            'Madurai', 'Salem', 'Tiruchirappalli', 'Goa', 'Shimla',
            'Dehradun', 'Jodhpur', 'Bikaner', 'Panaji', 'Agra',
            'Varanasi', 'Meerut', 'Noida', 'Gurgaon', 'Faridabad',

            # Tier-2 & Highway Cities
            'Ghaziabad', 'Kanpur', 'Jabalpur', 'Gwalior', 'Ujjain',
            'Sagar', 'Aligarh', 'Mathura', 'Moradabad', 'Bareilly',
            'Pilibhit', 'Haldwani', 'Rishikesh', 'Mussoorie', 'Nainital',
            'Almora', 'Abohar', 'Hisar', 'Rohtak', 'Yamunanagar',
            'Amritsar', 'Jalandhar', 'Bathinda', 'Firozpur', 'Ferozepur'
        ]

        total_added = 0
        count = 0

        for city in cities:
            try:
                count += 1
                print(f"  {count:2}. {city:25}", end=" ", flush=True)

                response = requests.get(
                    f"{self.base_url}{self.api_path}/by-city/",
                    params={'city': city, 'limit': 1000},
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    pumps = data if isinstance(data, list) else data.get('results', data.get('data', []))

                    if pumps:
                        added = self._add_pumps(pumps, 'city')
                        total_added += added
                        print(f"✓ {added} new")
                    else:
                        print("No results")
                else:
                    print(f"Status {response.status_code}")

                time.sleep(0.3)

            except Exception as e:
                print(f"Error")
                time.sleep(1)

        self.stats['cities'] = total_added
        print(f"\n✓ City extraction complete: {total_added} pumps added")

    def extract_nearby_searches(self):
        """Extract using nearby searches with different radii"""
        print("\n" + "="*80)
        print("📍 STRATEGY 4: NEARBY SEARCHES - Radius-based extraction")
        print("="*80)

        # Grid of locations across India
        locations = [
            # North
            (28.7041, 77.1025, 'Delhi'), (30.7333, 76.7794, 'Chandigarh'),
            (31.6340, 74.8723, 'Amritsar'), (30.9010, 75.8573, 'Ludhiana'),
            (26.8467, 80.9462, 'Lucknow'), (26.9124, 75.7873, 'Jaipur'),

            # South
            (13.0827, 80.2707, 'Chennai'), (12.9716, 77.5946, 'Bangalore'),
            (9.9312, 76.2673, 'Kochi'), (13.3333, 80.7667, 'Chennai-East'),

            # East
            (22.5726, 88.3639, 'Kolkata'), (25.5941, 85.1376, 'Patna'),
            (21.1458, 79.0882, 'Nagpur'),

            # West
            (19.0760, 72.8777, 'Mumbai'), (23.0225, 72.5714, 'Ahmedabad'),
            (21.1702, 72.8311, 'Surat'),

            # Central
            (17.3850, 78.4867, 'Hyderabad'), (23.1815, 79.9864, 'Bhopal'),
        ]

        total_added = 0
        radii = [10, 25, 50]

        for lat, lng, city in locations:
            for radius in radii:
                try:
                    print(f"  {city:20} {radius:2}km ", end="", flush=True)

                    response = requests.get(
                        f"{self.base_url}{self.api_path}/nearby/",
                        params={
                            'latitude': lat,
                            'longitude': lng,
                            'radius': radius
                        },
                        timeout=30
                    )

                    if response.status_code == 200:
                        data = response.json()
                        pumps = data if isinstance(data, list) else data.get('results', data.get('data', []))

                        if pumps:
                            added = self._add_pumps(pumps, 'nearby')
                            total_added += added
                            print(f"✓ {added} new")
                        else:
                            print("No results")
                    else:
                        print(f"Status {response.status_code}")

                    time.sleep(0.2)

                except Exception as e:
                    print(f"Error")
                    time.sleep(0.5)

        self.stats['nearby'] = total_added
        print(f"\n✓ Nearby extraction complete: {total_added} pumps added")

    def _add_pumps(self, pumps: List[Dict], source: str) -> int:
        """Add pumps with deduplication"""
        added = 0

        for pump in pumps:
            try:
                lat = pump.get('latitude') or pump.get('lat')
                lng = pump.get('longitude') or pump.get('lng')
                name = pump.get('name', 'Unknown')

                if not (lat and lng):
                    continue

                # Create unique ID
                pump_id = f"{float(lat):.6f}_{float(lng):.6f}"

                if pump_id not in self.all_pumps:
                    self.all_pumps[pump_id] = {
                        'name': str(name),
                        'latitude': float(lat),
                        'longitude': float(lng),
                        'city': str(pump.get('city', 'Unknown')),
                        'state': str(pump.get('state', 'Unknown')),
                        'company': str(pump.get('company', 'Unknown')),
                        'address': str(pump.get('address', '')),
                        'phone': str(pump.get('phone', '')) if pump.get('phone') else ''
                    }
                    added += 1
                else:
                    self.stats['duplicates_found'] += 1

            except Exception:
                continue

        return added

    def export_all(self, output_dir: str = "./outlet_data_ssri_complete"):
        """Export all data in multiple formats"""
        print("\n" + "="*80)
        print("💾 EXPORTING DATA")
        print("="*80)

        Path(output_dir).mkdir(exist_ok=True)

        if not self.all_pumps:
            print("✗ No data to export")
            return

        pumps_list = list(self.all_pumps.values())

        try:
            # CSV
            print(f"\n  Exporting CSV...")
            df = pd.DataFrame(pumps_list)
            csv_path = f"{output_dir}/ssri_all_pumps_{self.timestamp}.csv"
            df.to_csv(csv_path, index=False)
            csv_size = Path(csv_path).stat().st_size / (1024*1024)
            print(f"    ✓ {csv_path} ({csv_size:.2f}MB)")

            # JavaScript
            print(f"  Exporting JavaScript...")
            js_path = f"{output_dir}/ssri_all_pumps_{self.timestamp}.js"
            with open(js_path, 'w') as f:
                f.write(f"// SSRI Complete Petrol Pumps Database\n")
                f.write(f"// Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"// Total pumps: {len(pumps_list)}\n\n")
                f.write(f"const FUEL_PUMP_LOCATIONS = {json.dumps(pumps_list)};\n\n")
                f.write(f"const OUTLET_STATS = {{\n")
                f.write(f"  total: {len(pumps_list)},\n")
                f.write(f"  states: {len(set(p['state'] for p in pumps_list))},\n")
                f.write(f"  cities: {len(set(p['city'] for p in pumps_list))},\n")
                f.write(f"  companies: {len(set(p['company'] for p in pumps_list))},\n")
                f.write(f"  source: 'SSRI Petrol Pumps API (Complete)'\n")
                f.write(f"}};\n")
            js_size = Path(js_path).stat().st_size / (1024*1024)
            print(f"    ✓ {js_path} ({js_size:.2f}MB)")

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

            geojson_path = f"{output_dir}/ssri_all_pumps_{self.timestamp}.geojson"
            with open(geojson_path, 'w') as f:
                json.dump(geojson, f)
            geojson_size = Path(geojson_path).stat().st_size / (1024*1024)
            print(f"    ✓ {geojson_path} ({geojson_size:.2f}MB, {len(geojson['features'])} features)")

            # JSON
            print(f"  Exporting JSON...")
            json_path = f"{output_dir}/ssri_all_pumps_{self.timestamp}.json"
            with open(json_path, 'w') as f:
                json.dump(pumps_list, f, indent=2)
            json_size = Path(json_path).stat().st_size / (1024*1024)
            print(f"    ✓ {json_path} ({json_size:.2f}MB)")

            # Summary statistics
            print(f"  Generating summary...")

            state_counts = {}
            city_counts = {}
            company_counts = {}

            for pump in pumps_list:
                state = pump['state']
                city = pump['city']
                company = pump['company']

                state_counts[state] = state_counts.get(state, 0) + 1
                city_counts[city] = city_counts.get(city, 0) + 1
                company_counts[company] = company_counts.get(company, 0) + 1

            summary = {
                'timestamp': self.timestamp,
                'total_pumps': len(pumps_list),
                'unique_states': len(state_counts),
                'unique_cities': len(city_counts),
                'unique_companies': len(company_counts),
                'states': dict(sorted(state_counts.items(), key=lambda x: x[1], reverse=True)),
                'companies': dict(sorted(company_counts.items(), key=lambda x: x[1], reverse=True)),
                'extraction_stats': self.stats
            }

            summary_path = f"{output_dir}/ssri_all_pumps_summary_{self.timestamp}.json"
            with open(summary_path, 'w') as f:
                json.dump(summary, f, indent=2)
            print(f"    ✓ {summary_path}")

            print(f"\n✅ Export complete to {output_dir}/")
            return output_dir, summary

        except Exception as e:
            print(f"✗ Export error: {e}")
            return None, None

    def run_complete_extraction(self):
        """Run all extraction strategies"""
        print("\n" + "="*80)
        print("🚀 SSRI COMPLETE EXTRACTION - ALL PUMPS")
        print("="*80)
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        self.extract_all_pages(max_pages=500)
        self.extract_by_all_companies()
        self.extract_major_cities()
        self.extract_nearby_searches()

        output_dir, summary = self.export_all()

        print("\n" + "="*80)
        print("📊 FINAL SUMMARY")
        print("="*80)

        if summary:
            print(f"\n✅ EXTRACTION COMPLETE!")
            print(f"\n   Total Unique Pumps: {summary['total_pumps']:,}")
            print(f"   States: {summary['unique_states']}")
            print(f"   Cities: {summary['unique_cities']}")
            print(f"   Companies: {summary['unique_companies']}")
            print(f"\n   Extraction breakdown:")
            print(f"   ├─ Pagination: {self.stats['pagination']:,} pumps")
            print(f"   ├─ Companies: {self.stats['companies']:,} pumps")
            print(f"   ├─ Cities: {self.stats['cities']:,} pumps")
            print(f"   └─ Nearby: {self.stats['nearby']:,} pumps")
            print(f"\n   Duplicates found: {self.stats['duplicates_found']:,}")

            print(f"\n   Top Companies:")
            for company, count in list(summary['companies'].items())[:5]:
                print(f"   • {company}: {count:,}")

            print(f"\n   Top States:")
            for state, count in list(summary['states'].items())[:5]:
                print(f"   • {state}: {count:,}")

        print(f"\nEnd time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")


def main():
    extractor = CompleteSSRIExtractor()
    extractor.run_complete_extraction()


if __name__ == "__main__":
    main()
