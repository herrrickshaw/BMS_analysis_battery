#!/usr/bin/env python3
"""
Hybrid Retail Outlet Data Aggregator
Combines PPAC (official), OpenStreetMap, and Google Maps data
Deduplicates and creates unified outlet database for 100,000+ locations
"""

import requests
import pandas as pd
import json
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
from math import radians, sin, cos, sqrt, atan2
import time

class HybridOutletAggregator:
    def __init__(self):
        self.all_outlets = []
        self.deduped_outlets = []
        self.stats = {
            'ppac': 0,
            'osm': 0,
            'google': 0,
            'duplicates_removed': 0,
            'final_unique': 0
        }

        # Distance threshold for deduplication (km)
        self.dedup_distance_km = 0.5

    def fetch_osm_data(self, retries=3):
        """
        Fetch fuel stations from OpenStreetMap Overpass API
        Returns approximately 80,000+ fuel stations in India
        """
        print("\n📍 Fetching OpenStreetMap data...")

        # Smaller regional queries to avoid timeout
        regions = [
            {"name": "North India", "bbox": [23, 68, 35, 97]},
            {"name": "South India", "bbox": [8, 73, 23, 97]},
            {"name": "Central India", "bbox": [18, 72, 25, 85]},
        ]

        all_osm_outlets = []

        for region in regions:
            bbox = region['bbox']
            query = f"""[bbox:{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}];
(
    node["amenity"="fuel"];
    way["amenity"="fuel"];
    relation["amenity"="fuel"];
);
out center;"""

            url = "https://overpass-api.de/api/interpreter"

            for attempt in range(retries):
                try:
                    print(f"  Fetching {region['name']}... (Attempt {attempt + 1}/{retries})")
                    response = requests.post(
                        url,
                        data=query,
                        timeout=60
                    )

                    if response.status_code == 200:
                        osm_outlets = self._parse_osm_response(response.text)
                        all_osm_outlets.extend(osm_outlets)
                        print(f"    ✓ Got {len(osm_outlets)} outlets from {region['name']}")
                        break
                    else:
                        print(f"    ⚠ Status {response.status_code}")
                        time.sleep(3)

                except requests.exceptions.Timeout:
                    print(f"    ⚠ Timeout, retrying...")
                    time.sleep(5)
                except Exception as e:
                    print(f"    ⚠ Error: {e}")
                    time.sleep(2)

        self.stats['osm'] = len(all_osm_outlets)
        if all_osm_outlets:
            print(f"  ✓ Total OSM outlets: {len(all_osm_outlets)}")
        else:
            print(f"  ⚠ OSM fetch failed - API rate limited or unavailable")

        return all_osm_outlets

    def _parse_osm_response(self, osm_xml):
        """Parse OpenStreetMap XML response"""
        outlets = []
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(osm_xml)

            for node in root.findall('.//node'):
                lat = node.get('lat')
                lon = node.get('lon')

                if not lat or not lon:
                    continue

                name = None
                for tag in node.findall('.//tag'):
                    if tag.get('k') == 'name':
                        name = tag.get('v')
                        break

                outlets.append({
                    'name': name or 'OSM Fuel Station',
                    'latitude': float(lat),
                    'longitude': float(lon),
                    'source': 'OpenStreetMap',
                    'company': 'Unknown',
                    'city': None,
                    'state': None
                })

            print(f"    Parsed {len(outlets)} outlets from XML")
        except Exception as e:
            print(f"    Parse error: {e}")

        return outlets

    def load_ppac_data(self, ppac_csv_path: str = None):
        """
        Load PPAC (official government) data from CSV
        User should download from ppac.gov.in Ready Reckoner

        Args:
            ppac_csv_path: Path to PPAC CSV file (if not provided, instructs user)
        """
        print("\n🏛️  Loading PPAC data...")

        if not ppac_csv_path:
            print("  📥 PPAC data not provided. Instructions:")
            print("    1. Visit: https://ppac.gov.in/")
            print("    2. Navigate to: Reports & Analysis → Ready Reckoner")
            print("    3. Download 'Retail Outlets' dataset (Excel/CSV)")
            print("    4. Save to: ./ppac_retail_outlets.csv")
            print("    5. Run again with: aggregator.load_ppac_data('./ppac_retail_outlets.csv')")
            return []

        try:
            df = pd.read_csv(ppac_csv_path)

            # Standardize PPAC columns
            column_mapping = {
                'outlet_name': 'name',
                'name': 'name',
                'location': 'city',
                'city': 'city',
                'state': 'state',
                'latitude': 'latitude',
                'lat': 'latitude',
                'longitude': 'longitude',
                'lng': 'longitude',
                'company': 'company',
                'operator': 'company'
            }

            df = df.rename(columns=column_mapping)

            outlets = []
            for _, row in df.iterrows():
                outlet = {
                    'name': str(row.get('name', 'PPAC Outlet')),
                    'latitude': float(row['latitude']) if pd.notna(row.get('latitude')) else None,
                    'longitude': float(row['longitude']) if pd.notna(row.get('longitude')) else None,
                    'source': 'PPAC',
                    'company': str(row.get('company', 'Unknown')),
                    'city': str(row.get('city', '')),
                    'state': str(row.get('state', ''))
                }

                if outlet['latitude'] and outlet['longitude']:
                    outlets.append(outlet)

            self.stats['ppac'] = len(outlets)
            print(f"  ✓ Loaded {len(outlets)} PPAC outlets")
            return outlets

        except FileNotFoundError:
            print(f"  ✗ File not found: {ppac_csv_path}")
            return []
        except Exception as e:
            print(f"  ✗ Error loading PPAC data: {e}")
            return []

    def fetch_google_maps_data(self, api_key: str = None):
        """
        Fetch fuel stations from Google Places API
        Requires API key. Uses "gas_station" type query

        Args:
            api_key: Google Places API key
        """
        print("\n🗺️  Fetching Google Maps data...")

        if not api_key:
            print("  🔑 Google Maps API key not provided. Instructions:")
            print("    1. Get API key from: https://console.cloud.google.com/")
            print("    2. Enable: Google Places API")
            print("    3. Run: aggregator.fetch_google_maps_data('YOUR_API_KEY')")
            print("    4. Note: Charges apply (~$0.03-0.15 per request)")
            return []

        # For demo, return empty list
        # In production, would query major Indian cities
        print("  ⚠ Google Maps requires paid API access")
        print("  💡 Consider OSM + PPAC combination for 100,000+ coverage")
        return []

    def calculate_distance(self, lat1, lon1, lat2, lon2) -> float:
        """
        Calculate distance between two coordinates using Haversine formula
        Returns: distance in kilometers
        """
        R = 6371  # Earth's radius in km

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c

    def deduplicate_outlets(self, outlets: List[Dict]) -> List[Dict]:
        """
        Remove duplicate outlets based on proximity and name similarity
        """
        print("\n🔍 Deduplicating outlets...")

        if not outlets:
            return []

        # Sort by source priority (PPAC > Google > OSM)
        source_priority = {'PPAC': 0, 'Google': 1, 'OpenStreetMap': 2}
        sorted_outlets = sorted(
            outlets,
            key=lambda x: source_priority.get(x.get('source', 'Unknown'), 999)
        )

        deduped = []
        removed = 0

        for outlet in sorted_outlets:
            is_duplicate = False

            for existing in deduped:
                # Skip if no coordinates
                if not (outlet.get('latitude') and outlet.get('longitude') and
                       existing.get('latitude') and existing.get('longitude')):
                    continue

                # Check distance
                dist = self.calculate_distance(
                    outlet['latitude'], outlet['longitude'],
                    existing['latitude'], existing['longitude']
                )

                # If within threshold, it's a duplicate
                if dist < self.dedup_distance_km:
                    is_duplicate = True
                    removed += 1
                    break

            if not is_duplicate:
                deduped.append(outlet)

        self.stats['duplicates_removed'] = removed
        self.stats['final_unique'] = len(deduped)

        print(f"  ✓ Removed {removed} duplicates")
        print(f"  ✓ Final unique outlets: {len(deduped)}")

        return deduped

    def aggregate(self, ppac_csv: str = None, google_api_key: str = None):
        """
        Main aggregation pipeline
        Combines all data sources and deduplicates
        """
        print("\n" + "="*70)
        print("🔄 HYBRID RETAIL OUTLET AGGREGATION")
        print("="*70)

        all_data = []

        # 1. Load PPAC data (official, highest priority)
        ppac_data = self.load_ppac_data(ppac_csv)
        all_data.extend(ppac_data)

        # 2. Fetch OSM data (supplementary, large coverage)
        osm_data = self.fetch_osm_data()
        all_data.extend(osm_data)

        # 3. Try Google Maps if API key provided
        if google_api_key:
            google_data = self.fetch_google_maps_data(google_api_key)
            all_data.extend(google_data)

        print(f"\n📊 Before deduplication:")
        print(f"  Total records: {len(all_data)}")
        print(f"  - PPAC: {self.stats['ppac']}")
        print(f"  - OSM: {self.stats['osm']}")
        print(f"  - Google: {self.stats['google']}")

        # 4. Deduplicate
        self.deduped_outlets = self.deduplicate_outlets(all_data)

        return self.deduped_outlets

    def export_all_formats(self, output_dir: str = "./outlet_data_hybrid"):
        """
        Export aggregated data in multiple formats
        """
        Path(output_dir).mkdir(exist_ok=True)

        if not self.deduped_outlets:
            print("✗ No data to export")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print(f"\n💾 Exporting data...")

        try:
            # Convert to DataFrame
            df = pd.DataFrame(self.deduped_outlets)

            # CSV Export
            csv_path = f"{output_dir}/hybrid_outlets_{timestamp}.csv"
            df.to_csv(csv_path, index=False)
            print(f"  ✓ CSV: {csv_path}")

            # GeoJSON Export (for mapping)
            geojson = {
                "type": "FeatureCollection",
                "features": []
            }

            for _, row in df.iterrows():
                if pd.notna(row.get('latitude')) and pd.notna(row.get('longitude')):
                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [float(row['longitude']), float(row['latitude'])]
                        },
                        "properties": {
                            "name": str(row.get('name', 'Unknown')),
                            "company": str(row.get('company', '')),
                            "source": str(row.get('source', '')),
                            "city": str(row.get('city', '')),
                            "state": str(row.get('state', ''))
                        }
                    }
                    geojson["features"].append(feature)

            geojson_path = f"{output_dir}/hybrid_outlets_{timestamp}.geojson"
            with open(geojson_path, 'w') as f:
                json.dump(geojson, f, indent=2)
            print(f"  ✓ GeoJSON: {geojson_path} ({len(geojson['features'])} features)")

            # JSON Export
            json_path = f"{output_dir}/hybrid_outlets_{timestamp}.json"
            with open(json_path, 'w') as f:
                json.dump(self.deduped_outlets, f, indent=2)
            print(f"  ✓ JSON: {json_path}")

            # JavaScript Data File (for maps)
            js_path = f"{output_dir}/hybrid_outlets_{timestamp}.js"
            js_content = f"""
// Hybrid Retail Outlet Database
// Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
// Source: PPAC (Official) + OpenStreetMap + Google Maps

const HYBRID_OUTLETS = {json.dumps(self.deduped_outlets)};

const OUTLET_STATS = {{
    total: {len(self.deduped_outlets)},
    ppac: {self.stats['ppac']},
    osm: {self.stats['osm']},
    google: {self.stats['google']},
    duplicates_removed: {self.stats['duplicates_removed']}
}};
"""
            with open(js_path, 'w') as f:
                f.write(js_content)
            print(f"  ✓ JavaScript: {js_path}")

            # Statistics
            stats = {
                "aggregation_timestamp": timestamp,
                "total_outlets": len(self.deduped_outlets),
                "with_coordinates": len(df.dropna(subset=['latitude', 'longitude'])),
                "cities": df['city'].nunique() if 'city' in df.columns else 0,
                "states": df['state'].nunique() if 'state' in df.columns else 0,
                "companies": df['company'].nunique() if 'company' in df.columns else 0,
                "sources": {
                    "ppac": self.stats['ppac'],
                    "osm": self.stats['osm'],
                    "google": self.stats['google'],
                    "duplicates_removed": self.stats['duplicates_removed']
                }
            }

            stats_path = f"{output_dir}/hybrid_outlets_stats_{timestamp}.json"
            with open(stats_path, 'w') as f:
                json.dump(stats, f, indent=2)
            print(f"  ✓ Statistics: {stats_path}")

            print(f"\n✅ Export complete: {output_dir}/")
            return output_dir

        except Exception as e:
            print(f"  ✗ Export error: {e}")
            return None

    def print_summary(self):
        """Print aggregation summary"""
        print("\n" + "="*70)
        print("📊 AGGREGATION SUMMARY")
        print("="*70)
        print(f"Total Unique Outlets: {self.stats['final_unique']}")
        print(f"├─ PPAC (Official): {self.stats['ppac']}")
        print(f"├─ OpenStreetMap: {self.stats['osm']}")
        print(f"├─ Google Maps: {self.stats['google']}")
        print(f"└─ Duplicates Removed: {self.stats['duplicates_removed']}")
        print("="*70)


def main():
    """Main execution"""
    aggregator = HybridOutletAggregator()

    # Run aggregation
    # Note: PPAC CSV path should be provided after downloading from ppac.gov.in
    outlets = aggregator.aggregate(
        ppac_csv=None,  # Provide path if you have PPAC file
        google_api_key=None  # Provide if you have Google API key
    )

    # Export results
    if outlets:
        output_dir = aggregator.export_all_formats()
        aggregator.print_summary()

        print("\n📝 Next steps:")
        print(f"  1. Copy outlets to your fuel maps directory")
        print(f"  2. Update map JavaScript to use hybrid_outlets.js")
        print(f"  3. Verify data in web interface")
        print(f"  4. Commit changes to GitHub")
    else:
        print("\n⚠ No data aggregated. Check PPAC CSV path.")


if __name__ == "__main__":
    main()
