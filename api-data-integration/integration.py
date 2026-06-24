#!/usr/bin/env python3
"""
SSR Innovation Lab API Integration
Fetches retail outlet location data and integrates with fuel infrastructure mapping
"""

import requests
import pandas as pd
import json
from datetime import datetime
from pathlib import Path

class OutletAPIIntegration:
    def __init__(self):
        self.api_base = "https://api.ssrinnovationlab.com"
        self.api_endpoints = {
            'test': "/api/test/18/",
            'outlets': "/api/outlets/",
            'locations': "/api/locations/",
            'retail': "/api/retail-outlets/"
        }
        self.outlets_data = []

    def fetch_from_api(self, endpoint_type='test'):
        """
        Fetch outlet data from SSR Innovation Lab API

        Args:
            endpoint_type: Type of endpoint to access

        Returns:
            dict: API response data
        """
        url = self.api_base + self.api_endpoints.get(endpoint_type, "/api/test/18/")

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Python/Retail-Mapper)'
        }

        try:
            print(f"Fetching data from: {url}")
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"✓ Successfully fetched {len(data)} records")
                    return data
                except json.JSONDecodeError:
                    print("⚠ Response is HTML, not JSON (likely UI page)")
                    return None
            else:
                print(f"✗ API returned status code: {response.status_code}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"✗ API request failed: {e}")
            return None

    def process_outlet_data(self, raw_data):
        """
        Process and standardize outlet data

        Args:
            raw_data: Raw data from API

        Returns:
            pd.DataFrame: Standardized outlet data
        """
        if not raw_data:
            return None

        try:
            df = pd.DataFrame(raw_data)

            # Standardize column names
            column_mapping = {
                'outlet_name': 'outlet_name',
                'name': 'outlet_name',
                'location': 'location',
                'city': 'city',
                'state': 'state',
                'latitude': 'latitude',
                'lat': 'latitude',
                'longitude': 'longitude',
                'lng': 'longitude',
                'company': 'company',
                'type': 'outlet_type',
                'address': 'address',
                'phone': 'phone',
                'services': 'services'
            }

            # Rename columns
            df = df.rename(columns=column_mapping)

            # Ensure required columns exist
            required_cols = ['outlet_name', 'latitude', 'longitude', 'city', 'state']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = None

            # Clean data
            df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
            df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')

            print(f"✓ Processed {len(df)} outlets")
            return df

        except Exception as e:
            print(f"✗ Data processing error: {e}")
            return None

    def merge_with_existing(self, api_data, existing_data_path=None):
        """
        Merge API data with existing retail outlet data

        Args:
            api_data: DataFrame from API
            existing_data_path: Path to existing outlet CSV

        Returns:
            pd.DataFrame: Merged outlet data
        """
        if api_data is None:
            print("⚠ No API data to merge")
            return None

        # Start with API data
        merged = api_data.copy()

        # Load existing data if provided
        if existing_data_path and Path(existing_data_path).exists():
            try:
                existing = pd.read_csv(existing_data_path)

                # Merge on location coordinates
                merged = pd.concat([merged, existing], ignore_index=True)

                # Remove duplicates (same coordinates)
                merged = merged.drop_duplicates(
                    subset=['latitude', 'longitude', 'outlet_name'],
                    keep='first'
                )

                print(f"✓ Merged with existing data: {len(merged)} unique outlets")

            except Exception as e:
                print(f"✗ Merge error: {e}")

        return merged

    def export_to_formats(self, data, output_dir="./outlet_data"):
        """
        Export outlet data in multiple formats

        Args:
            data: DataFrame to export
            output_dir: Directory to save files
        """
        Path(output_dir).mkdir(exist_ok=True)

        if data is None or len(data) == 0:
            print("✗ No data to export")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            # CSV export
            csv_path = f"{output_dir}/outlets_{timestamp}.csv"
            data.to_csv(csv_path, index=False)
            print(f"✓ CSV exported: {csv_path}")

            # GeoJSON export (for mapping)
            geojson = {
                "type": "FeatureCollection",
                "features": []
            }

            for idx, row in data.iterrows():
                if pd.notna(row['latitude']) and pd.notna(row['longitude']):
                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [float(row['longitude']), float(row['latitude'])]
                        },
                        "properties": {
                            "name": str(row.get('outlet_name', 'Unknown')),
                            "city": str(row.get('city', '')),
                            "state": str(row.get('state', '')),
                            "company": str(row.get('company', ''))
                        }
                    }
                    geojson["features"].append(feature)

            geojson_path = f"{output_dir}/outlets_{timestamp}.geojson"
            with open(geojson_path, 'w') as f:
                json.dump(geojson, f, indent=2)
            print(f"✓ GeoJSON exported: {geojson_path} ({len(geojson['features'])} features)")

            # JSON export
            json_path = f"{output_dir}/outlets_{timestamp}.json"
            data.to_json(json_path, orient='records', indent=2)
            print(f"✓ JSON exported: {json_path}")

            # Summary stats
            stats = {
                "total_outlets": len(data),
                "with_coordinates": len(data.dropna(subset=['latitude', 'longitude'])),
                "cities": data['city'].nunique() if 'city' in data.columns else 0,
                "states": data['state'].nunique() if 'state' in data.columns else 0,
                "companies": data['company'].nunique() if 'company' in data.columns else 0,
                "export_timestamp": timestamp
            }

            stats_path = f"{output_dir}/outlets_stats_{timestamp}.json"
            with open(stats_path, 'w') as f:
                json.dump(stats, f, indent=2)
            print(f"✓ Statistics saved: {stats_path}")

        except Exception as e:
            print(f"✗ Export error: {e}")


def main():
    """Main execution"""
    print("🔄 SSR Innovation Lab API Integration")
    print("=" * 60)

    integration = OutletAPIIntegration()

    # Attempt to fetch data
    print("\n1️⃣  Attempting to fetch data from API...")
    api_data = integration.fetch_from_api(endpoint_type='test')

    if api_data:
        print("\n2️⃣  Processing API data...")
        processed_data = integration.process_outlet_data(api_data)

        if processed_data is not None:
            print("\n3️⃣  Exporting to multiple formats...")
            integration.export_to_formats(processed_data)

            print("\n✅ Integration complete!")
        else:
            print("\n⚠ Failed to process API data")
    else:
        print("\n⚠ Unable to fetch data from API")
        print("\nPossible solutions:")
        print("  1. Check API endpoint URL")
        print("  2. Verify API authentication/credentials")
        print("  3. Use manual data import instead")
        print("  4. Check if API requires specific headers or parameters")


if __name__ == "__main__":
    main()
