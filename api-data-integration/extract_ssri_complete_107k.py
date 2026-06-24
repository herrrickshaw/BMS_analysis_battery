#!/usr/bin/env python3
"""
COMPLETE SSRI 107,380 PUMP EXTRACTION
======================================
Extracts complete SSRI petrol pump database (all 107,380 records).
Uses pagination with limit/page parameters, with optimized retry logic.
"""

import requests
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List

class CompleteSSRIExtractor107K:
    """Extract all 107,380 SSRI petrol pump records."""

    def __init__(self):
        """Initialize extractor."""
        self.base_url = "https://api.ssrinnovationlab.com"
        self.api_path = "/api/petrol-pumps/pumps"
        self.all_pumps = {}
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.stats = {
            'total_pages': 0,
            'records_fetched': 0,
            'unique_records': 0,
            'errors': 0,
            'rate_limited': 0
        }

    def fetch_page_optimized(self, page: int, limit: int = 100, retries: int = 3) -> tuple:
        """Fetch page with retry logic."""
        for attempt in range(retries):
            try:
                response = requests.get(
                    f"{self.base_url}{self.api_path}/",
                    params={'limit': limit, 'page': page},
                    timeout=30
                )

                if response.status_code == 429:  # Rate limited
                    wait_time = 5 * (attempt + 1)
                    print(f"⏳ Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    self.stats['rate_limited'] += 1
                    continue

                if response.status_code == 200:
                    data = response.json()
                    results = data.get('results', [])
                    has_next = 'next' in data and data['next']
                    return results, has_next, True

                elif response.status_code in [502, 503, 504]:  # Server errors
                    wait_time = 2 * (attempt + 1)
                    print(f"⚠ Server error {response.status_code}, retrying...")
                    time.sleep(wait_time)
                    continue

                else:
                    print(f"✗ Status {response.status_code}")
                    return [], False, False

            except requests.Timeout:
                print(f"⏱ Timeout on page {page}, retry {attempt+1}...")
                time.sleep(2)
                continue
            except Exception as e:
                print(f"✗ Error: {str(e)[:40]}")
                return [], False, False

        return [], False, False

    def add_pumps_batch(self, pumps: List[Dict]) -> int:
        """Add pumps with deduplication."""
        added = 0
        for pump in pumps:
            pump_id = pump.get('id')
            if pump_id and pump_id not in self.all_pumps:
                record = {
                    'id': pump_id,
                    'name': str(pump.get('name', '')),
                    'pump_name': str(pump.get('pump_name', '')),
                    'company': str(pump.get('company', '')),
                    'address': str(pump.get('address', '')),
                    'city': str(pump.get('city', '')),
                    'district': str(pump.get('district', '')),
                    'state': str(pump.get('state', '')),
                    'latitude': float(pump.get('latitude')) if pump.get('latitude') else None,
                    'longitude': float(pump.get('longitude')) if pump.get('longitude') else None,
                    'petrol_price': float(pump.get('petrol_price')) if pump.get('petrol_price') else None,
                    'diesel_price': float(pump.get('diesel_price')) if pump.get('diesel_price') else None,
                    'has_petrol': bool(pump.get('has_petrol', False)),
                    'has_diesel': bool(pump.get('has_diesel', False)),
                    'has_cng': bool(pump.get('has_cng', False)),
                    'station_timing': str(pump.get('station_timing', '')),
                    'direction_link': str(pump.get('direction_link', '')),
                    'phone': str(pump.get('phone', '')),
                    'source': 'SSRI API'
                }
                self.all_pumps[pump_id] = record
                added += 1

        return added

    def extract_all(self, max_pages: int = 1100):
        """Extract all pages from SSRI API."""
        print("\n" + "="*80)
        print("🚀 EXTRACTING ALL 107,380 SSRI PETROL PUMPS")
        print("="*80)
        print(f"Target: 107,380 records across ~1,074 pages\n")

        page = 1
        consecutive_fails = 0
        max_consecutive_fails = 3

        while page <= max_pages and consecutive_fails < max_consecutive_fails:
            print(f"Page {page:4}...", end=" ", flush=True)

            results, has_next, success = self.fetch_page_optimized(page)

            if success:
                added = self.add_pumps_batch(results)
                self.stats['records_fetched'] += len(results)
                self.stats['unique_records'] = len(self.all_pumps)
                consecutive_fails = 0

                print(f"✓ {len(results)} records, {added} new (Total: {len(self.all_pumps)})")

                if not has_next or len(results) == 0:
                    print(f"\n✅ Reached last page at {page}")
                    break

                # Adaptive delay based on page number
                if page % 100 == 0:
                    time.sleep(2)  # Longer delay every 100 pages
                else:
                    time.sleep(0.3)  # Standard rate limiting

            else:
                consecutive_fails += 1
                print(f"✗ Failed (attempt {consecutive_fails})")
                time.sleep(5)

            page += 1

        self.stats['total_pages'] = page - 1
        self.stats['unique_records'] = len(self.all_pumps)

        print(f"\n✅ Extraction Summary:")
        print(f"   Pages processed: {self.stats['total_pages']}")
        print(f"   Records fetched: {self.stats['records_fetched']:,}")
        print(f"   Unique records: {self.stats['unique_records']:,}")
        print(f"   Rate limited: {self.stats['rate_limited']}")

    def export_data(self, output_dir: str = "./outlet_data_ssri_107k"):
        """Export complete database."""
        print("\n" + "="*80)
        print("💾 EXPORTING COMPLETE SSRI DATABASE")
        print("="*80)

        Path(output_dir).mkdir(exist_ok=True)

        if not self.all_pumps:
            print("✗ No data to export")
            return

        pumps_list = list(self.all_pumps.values())

        # Export JSON
        print(f"\n  Exporting JSON...")
        json_path = f"{output_dir}/ssri_complete_107k_{self.timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(pumps_list, f)
        json_size = Path(json_path).stat().st_size / (1024*1024)
        print(f"    ✓ {json_path} ({json_size:.2f}MB, {len(pumps_list)} records)")

        # Export CSV
        print(f"  Exporting CSV...")
        import pandas as pd
        df = pd.DataFrame(pumps_list)
        csv_path = f"{output_dir}/ssri_complete_107k_{self.timestamp}.csv"
        df.to_csv(csv_path, index=False)
        csv_size = Path(csv_path).stat().st_size / (1024*1024)
        print(f"    ✓ {csv_path} ({csv_size:.2f}MB)")

        # Export summary
        summary = {
            'timestamp': self.timestamp,
            'total_pumps': len(self.all_pumps),
            'states': len(set(p['state'] for p in pumps_list if p['state'])),
            'companies': len(set(p['company'] for p in pumps_list if p['company'])),
            'with_coordinates': len([p for p in pumps_list if p['latitude'] and p['longitude']]),
            'with_cng': len([p for p in pumps_list if p['has_cng']]),
            'with_prices': len([p for p in pumps_list if p['petrol_price']])
        }

        summary_path = f"{output_dir}/ssri_complete_107k_summary_{self.timestamp}.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"    ✓ {summary_path}")

        print(f"\n✅ Export complete to {output_dir}/")
        return json_path

    def run(self):
        """Run extraction."""
        print("\n" + "="*80)
        print("🚀 COMPLETE SSRI 107,380 EXTRACTION")
        print("="*80)
        print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        self.extract_all()
        self.export_data()

        print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")


def main():
    """Main execution."""
    extractor = CompleteSSRIExtractor107K()
    extractor.run()


if __name__ == "__main__":
    main()
