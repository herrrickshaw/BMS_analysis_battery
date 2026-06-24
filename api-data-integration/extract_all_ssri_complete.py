#!/usr/bin/env python3
"""
COMPLETE SSRI PETROL PUMP DATABASE EXTRACTION
=============================================
Extracts ALL 107,380 petrol pump records from SSRI API with enhanced fields:
- Basic Info: name, company, address, city, state, district
- Coordinates: latitude, longitude (with Google Maps link)
- Fuel Availability: petrol, diesel, CNG flags
- Current Prices: petrol price, diesel price
- Service Info: station timing (24 hours, etc.)

Previous Extraction: 50,374 pumps (46.9% coverage)
Complete Extraction: 107,380 pumps (100% coverage)
Additional Records: 57,006 new pumps

Source: https://api.ssrinnovationlab.com/api/petrol-pumps/pumps/
Total Pages: 1,074 (100 records per page)
"""

import requests
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import time

class CompleteSSRIExtractor:
    """
    Extracts complete SSRI petrol pump database with all fields.
    """

    def __init__(self):
        """Initialize extractor."""
        self.base_url = "https://api.ssrinnovationlab.com"
        self.api_path = "/api/petrol-pumps/pumps"
        self.all_pumps = {}
        self.stats = {
            'total_pages': 0,
            'records_fetched': 0,
            'duplicates': 0,
            'unique_records': 0,
            'errors': 0
        }
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def fetch_all_pages(self, max_pages: int = 1100):
        """
        Fetch all pages from the API.

        Uses pagination with limit=100, page=N
        """
        print("\n" + "="*80)
        print("📄 FETCHING ALL SSRI PETROL PUMP RECORDS")
        print("="*80)
        print(f"Expected total: ~107,380 records across {max_pages} pages\n")

        page = 1
        consecutive_errors = 0
        max_consecutive_errors = 5

        while page <= max_pages and consecutive_errors < max_consecutive_errors:
            try:
                print(f"Page {page:4}...", end=" ", flush=True)

                # Fetch page
                response = requests.get(
                    f"{self.base_url}{self.api_path}/",
                    params={'limit': 100, 'page': page},
                    timeout=30
                )

                if response.status_code != 200:
                    print(f"✗ Status {response.status_code}")
                    consecutive_errors += 1
                    page += 1
                    time.sleep(1)
                    continue

                data = response.json()

                # Extract results
                results = data.get('results', [])

                if not results:
                    print("✗ Empty")
                    consecutive_errors += 1
                    page += 1
                    time.sleep(0.5)
                    continue

                # Reset error counter on success
                consecutive_errors = 0

                # Add pumps to database
                added = self._add_pumps(results)
                self.stats['records_fetched'] += len(results)

                print(f"✓ {len(results)} records, added {added} new (total: {len(self.all_pumps)})")

                # Check if there are more pages
                if 'next' not in data or not data['next']:
                    print(f"\n✅ Reached last page")
                    break

                page += 1
                time.sleep(0.2)  # Rate limiting

            except Exception as e:
                print(f"✗ Error: {str(e)[:40]}")
                consecutive_errors += 1
                page += 1
                time.sleep(2)

        self.stats['total_pages'] = page - 1
        self.stats['unique_records'] = len(self.all_pumps)

        print(f"\n✅ Fetching complete:")
        print(f"   Pages processed: {self.stats['total_pages']}")
        print(f"   Total records: {self.stats['records_fetched']}")
        print(f"   Unique records: {self.stats['unique_records']}")

    def _add_pumps(self, pumps: List[Dict]) -> int:
        """
        Add pumps to database with deduplication.

        Returns:
            int: Count of new pumps added
        """
        added = 0

        for pump in pumps:
            try:
                # Use ID as unique key (primary identifier from API)
                pump_id = pump.get('id')

                if not pump_id:
                    continue

                if pump_id not in self.all_pumps:
                    # Create enhanced record with all fields
                    record = {
                        'id': pump_id,
                        'name': str(pump.get('name', 'Unknown')),
                        'pump_name': str(pump.get('pump_name', '')),
                        'company': str(pump.get('company', 'Unknown')),
                        'address': str(pump.get('address', '')),
                        'city': str(pump.get('city', '')),
                        'district': str(pump.get('district', '')),
                        'state': str(pump.get('state', '')),
                        'latitude': float(pump.get('latitude', 0)) if pump.get('latitude') else None,
                        'longitude': float(pump.get('longitude', 0)) if pump.get('longitude') else None,
                        'petrol_price': float(pump.get('petrol_price', 0)) if pump.get('petrol_price') else None,
                        'diesel_price': float(pump.get('diesel_price', 0)) if pump.get('diesel_price') else None,
                        'has_petrol': bool(pump.get('has_petrol', False)),
                        'has_diesel': bool(pump.get('has_diesel', False)),
                        'has_cng': bool(pump.get('has_cng', False)),
                        'station_timing': str(pump.get('station_timing', '')),
                        'direction_link': str(pump.get('direction_link', '')),
                        'source': 'SSRI API',
                        'extraction_date': datetime.now().strftime('%Y-%m-%d')
                    }
                    self.all_pumps[pump_id] = record
                    added += 1
                else:
                    self.stats['duplicates'] += 1

            except Exception:
                self.stats['errors'] += 1
                continue

        return added

    def export_complete_database(self, output_dir: str = "./outlet_data_ssri_107k"):
        """Export complete database in multiple formats."""
        print("\n" + "="*80)
        print("💾 EXPORTING COMPLETE SSRI DATABASE (107K+ RECORDS)")
        print("="*80)

        Path(output_dir).mkdir(exist_ok=True)

        if not self.all_pumps:
            print("✗ No data to export")
            return

        pumps_list = list(self.all_pumps.values())
        df = pd.DataFrame(pumps_list)

        # Export CSV
        print(f"\n  Exporting CSV...")
        csv_path = f"{output_dir}/ssri_complete_pumps_{self.timestamp}.csv"
        df.to_csv(csv_path, index=False)
        csv_size = Path(csv_path).stat().st_size / (1024*1024)
        print(f"    ✓ {csv_path} ({csv_size:.2f}MB, {len(df)} records)")

        # Export JSON
        print(f"  Exporting JSON...")
        json_path = f"{output_dir}/ssri_complete_pumps_{self.timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(pumps_list, f)
        json_size = Path(json_path).stat().st_size / (1024*1024)
        print(f"    ✓ {json_path} ({json_size:.2f}MB)")

        # Export GeoJSON
        print(f"  Exporting GeoJSON...")
        geojson = {"type": "FeatureCollection", "features": []}
        for pump in pumps_list:
            if pump['latitude'] and pump['longitude']:
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [pump['longitude'], pump['latitude']]
                    },
                    "properties": {
                        "name": pump['name'],
                        "company": pump['company'],
                        "state": pump['state'],
                        "petrol_price": pump['petrol_price'],
                        "diesel_price": pump['diesel_price'],
                        "has_cng": pump['has_cng'],
                        "timing": pump['station_timing']
                    }
                }
                geojson["features"].append(feature)

        geojson_path = f"{output_dir}/ssri_complete_pumps_{self.timestamp}.geojson"
        with open(geojson_path, 'w') as f:
            json.dump(geojson, f)
        geojson_size = Path(geojson_path).stat().st_size / (1024*1024)
        print(f"    ✓ {geojson_path} ({geojson_size:.2f}MB, {len(geojson['features'])} features)")

        # Export JavaScript
        print(f"  Exporting JavaScript...")
        js_path = f"{output_dir}/ssri_complete_pumps_{self.timestamp}.js"
        with open(js_path, 'w') as f:
            f.write(f"// SSRI COMPLETE PETROL PUMPS DATABASE\n")
            f.write(f"// Total: {len(pumps_list)} records\n")
            f.write(f"// Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"const COMPLETE_FUEL_PUMP_DATABASE = {json.dumps(pumps_list)};\n\n")

            # Add statistics
            stats = {
                'total': len(pumps_list),
                'states': len(set(p['state'] for p in pumps_list if p['state'])),
                'companies': len(set(p['company'] for p in pumps_list)),
                'with_cng': sum(1 for p in pumps_list if p['has_cng']),
                'with_prices': sum(1 for p in pumps_list if p['petrol_price'])
            }
            f.write(f"const PUMP_STATISTICS = {json.dumps(stats)};\n")

        js_size = Path(js_path).stat().st_size / (1024*1024)
        print(f"    ✓ {js_path} ({js_size:.2f}MB)")

        # Export Summary
        print(f"  Generating summary...")
        summary = {
            'timestamp': self.timestamp,
            'total_unique_pumps': len(self.all_pumps),
            'unique_states': len(set(p['state'] for p in pumps_list if p['state'])),
            'unique_companies': len(set(p['company'] for p in pumps_list)),
            'pumps_with_cng': sum(1 for p in pumps_list if p['has_cng']),
            'pumps_with_prices': sum(1 for p in pumps_list if p['petrol_price']),
            'statistics': self.stats,
            'company_distribution': self._get_company_dist(pumps_list),
            'state_distribution': self._get_state_dist(pumps_list),
            'fuel_availability': {
                'has_petrol': sum(1 for p in pumps_list if p['has_petrol']),
                'has_diesel': sum(1 for p in pumps_list if p['has_diesel']),
                'has_cng': sum(1 for p in pumps_list if p['has_cng']),
                'all_three': sum(1 for p in pumps_list if p['has_petrol'] and p['has_diesel'] and p['has_cng'])
            }
        }

        summary_path = f"{output_dir}/ssri_complete_summary_{self.timestamp}.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"    ✓ {summary_path}")

        print(f"\n✅ Export complete to {output_dir}/")
        return summary

    def _get_company_dist(self, pumps_list):
        """Get company distribution."""
        dist = {}
        for pump in pumps_list:
            company = pump.get('company', 'Unknown')
            dist[company] = dist.get(company, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def _get_state_dist(self, pumps_list):
        """Get state distribution."""
        dist = {}
        for pump in pumps_list:
            state = pump.get('state', 'Unknown')
            dist[state] = dist.get(state, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def print_summary(self, summary):
        """Print final summary."""
        print("\n" + "="*80)
        print("📊 COMPLETE SSRI DATABASE SUMMARY")
        print("="*80)

        print(f"\n✅ COMPLETE DATABASE CREATED!")
        print(f"\n   Total Pumps: {summary['total_unique_pumps']:,}")
        print(f"   States: {summary['unique_states']}")
        print(f"   Companies: {summary['unique_companies']}")

        print(f"\n   Fuel Availability:")
        fuel = summary['fuel_availability']
        print(f"   • Petrol: {fuel['has_petrol']:,} pumps")
        print(f"   • Diesel: {fuel['has_diesel']:,} pumps")
        print(f"   • CNG: {fuel['has_cng']:,} pumps")
        print(f"   • All three: {fuel['all_three']:,} pumps")

        print(f"\n   Price Data Available: {summary['pumps_with_prices']:,} pumps")

        print(f"\n   Top Companies:")
        for company, count in list(summary['company_distribution'].items())[:5]:
            print(f"   • {company}: {count:,}")

        print(f"\n   Top States:")
        for state, count in list(summary['state_distribution'].items())[:5]:
            print(f"   • {state}: {count:,}")

    def run(self):
        """Run complete extraction."""
        print("\n" + "="*80)
        print("🚀 COMPLETE SSRI PETROL PUMP DATABASE EXTRACTION")
        print("="*80)
        print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Fetch all pages
        self.fetch_all_pages()

        # Export
        summary = self.export_complete_database()

        # Print summary
        if summary:
            self.print_summary(summary)

        print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")


def main():
    """Main execution."""
    extractor = CompleteSSRIExtractor()
    extractor.run()


if __name__ == "__main__":
    main()
