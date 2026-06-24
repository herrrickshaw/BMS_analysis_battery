#!/usr/bin/env python3
"""
Kaggle Indian Oil Retail Outlets Dataset Loader
Loads pre-compiled dataset from:
https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime

class KaggleDatasetLoader:
    def __init__(self):
        self.outlets = []
        self.stats = {
            'total': 0,
            'with_coords': 0,
            'states': 0,
            'cities': 0,
            'companies': 0
        }

    def load_from_csv(self, csv_path: str):
        """
        Load Indian oil retail outlets from Kaggle CSV

        Args:
            csv_path: Path to the CSV file downloaded from Kaggle
        """
        print(f"\n📥 Loading Kaggle dataset from: {csv_path}")

        try:
            df = pd.read_csv(csv_path)
            print(f"  ✓ Loaded {len(df)} rows")
            print(f"  Columns: {list(df.columns)}")

            # Standardize column names (adjust based on actual CSV structure)
            column_mapping = {
                'outlet_name': 'name',
                'Outlet Name': 'name',
                'name': 'name',
                'Name': 'name',
                'city': 'city',
                'City': 'city',
                'state': 'state',
                'State': 'state',
                'latitude': 'latitude',
                'Latitude': 'latitude',
                'lat': 'latitude',
                'Lat': 'latitude',
                'longitude': 'longitude',
                'Longitude': 'longitude',
                'lng': 'longitude',
                'Lng': 'longitude',
                'company': 'company',
                'Company': 'company',
                'operator': 'company',
                'Operator': 'company',
                'address': 'address',
                'Address': 'address',
            }

            df = df.rename(columns=column_mapping)

            # Process each row
            for idx, row in df.iterrows():
                try:
                    lat = row.get('latitude')
                    lng = row.get('longitude')

                    # Skip if no coordinates
                    if pd.isna(lat) or pd.isna(lng):
                        continue

                    outlet = {
                        'name': str(row.get('name', 'Unknown')),
                        'latitude': float(lat),
                        'longitude': float(lng),
                        'source': 'Kaggle',
                        'company': str(row.get('company', 'Unknown')),
                        'city': str(row.get('city', '')),
                        'state': str(row.get('state', '')),
                    }

                    self.outlets.append(outlet)

                except (ValueError, TypeError):
                    # Skip rows with invalid coordinates
                    continue

            self.stats['total'] = len(self.outlets)
            self.stats['with_coords'] = len(self.outlets)
            self.stats['states'] = len(set(o['state'] for o in self.outlets if o['state']))
            self.stats['cities'] = len(set(o['city'] for o in self.outlets if o['city']))
            self.stats['companies'] = len(set(o['company'] for o in self.outlets if o['company'] != 'Unknown'))

            print(f"  ✓ Processed {len(self.outlets)} outlets with valid coordinates")
            print(f"  ✓ States: {self.stats['states']}")
            print(f"  ✓ Cities: {self.stats['cities']}")
            print(f"  ✓ Companies: {self.stats['companies']}")

            return self.outlets

        except FileNotFoundError:
            print(f"  ✗ File not found: {csv_path}")
            print(f"\n  📥 To use Kaggle dataset:")
            print(f"    1. Visit: https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025")
            print(f"    2. Click: Download")
            print(f"    3. Extract the ZIP file")
            print(f"    4. Find the CSV file (usually 'indian_oil_outlets.csv' or similar)")
            print(f"    5. Place it in this directory")
            print(f"    6. Run: python3 kaggle_loader.py <csv_filename>")
            return []

        except Exception as e:
            print(f"  ✗ Error loading CSV: {e}")
            return []

    def export_all_formats(self, output_dir: str = "./outlet_data_kaggle"):
        """
        Export loaded data in multiple formats
        """
        if not self.outlets:
            print("✗ No outlets to export")
            return

        Path(output_dir).mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print(f"\n💾 Exporting data to {output_dir}/...")

        try:
            # Convert to DataFrame
            df = pd.DataFrame(self.outlets)

            # CSV Export
            csv_path = f"{output_dir}/kaggle_outlets_{timestamp}.csv"
            df.to_csv(csv_path, index=False)
            print(f"  ✓ CSV: {csv_path}")

            # GeoJSON Export (for mapping)
            geojson = {
                "type": "FeatureCollection",
                "features": []
            }

            for outlet in self.outlets:
                if outlet.get('latitude') and outlet.get('longitude'):
                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [outlet['longitude'], outlet['latitude']]
                        },
                        "properties": {
                            "name": outlet.get('name', 'Unknown'),
                            "company": outlet.get('company', ''),
                            "city": outlet.get('city', ''),
                            "state": outlet.get('state', '')
                        }
                    }
                    geojson["features"].append(feature)

            geojson_path = f"{output_dir}/kaggle_outlets_{timestamp}.geojson"
            with open(geojson_path, 'w') as f:
                json.dump(geojson, f, indent=2)
            print(f"  ✓ GeoJSON: {geojson_path} ({len(geojson['features'])} features)")

            # JavaScript Data File (for maps)
            js_path = f"{output_dir}/kaggle_outlets_{timestamp}.js"
            js_content = f"""// Kaggle Indian Oil Retail Outlets Dataset
// Source: https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025
// Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

const FUEL_PUMP_LOCATIONS = {json.dumps(self.outlets)};

const OUTLET_STATS = {{
    total: {len(self.outlets)},
    states: {self.stats['states']},
    cities: {self.stats['cities']},
    companies: {self.stats['companies']},
    source: 'Kaggle Indian Oil Retail Outlets 2025'
}};

// For backward compatibility
const KAGGLE_OUTLETS = FUEL_PUMP_LOCATIONS;
"""
            with open(js_path, 'w') as f:
                f.write(js_content)
            print(f"  ✓ JavaScript: {js_path}")

            # JSON Export
            json_path = f"{output_dir}/kaggle_outlets_{timestamp}.json"
            with open(json_path, 'w') as f:
                json.dump(self.outlets, f, indent=2)
            print(f"  ✓ JSON: {json_path}")

            # Statistics
            stats_file = f"{output_dir}/kaggle_outlets_stats_{timestamp}.json"
            stats_data = {
                "timestamp": timestamp,
                "total_outlets": len(self.outlets),
                "states_covered": self.stats['states'],
                "cities_covered": self.stats['cities'],
                "companies": self.stats['companies'],
                "source": "Kaggle - Indian Oil Retail Outlets 2025",
                "dataset_url": "https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025"
            }
            with open(stats_file, 'w') as f:
                json.dump(stats_data, f, indent=2)
            print(f"  ✓ Statistics: {stats_file}")

            print(f"\n✅ Export complete to {output_dir}/")
            return output_dir

        except Exception as e:
            print(f"  ✗ Export error: {e}")
            return None

    def print_summary(self):
        """Print loading summary"""
        print("\n" + "="*70)
        print("📊 KAGGLE DATASET SUMMARY")
        print("="*70)
        print(f"Total Outlets: {self.stats['total']}")
        print(f"States Covered: {self.stats['states']}")
        print(f"Cities Covered: {self.stats['cities']}")
        print(f"Companies: {self.stats['companies']}")
        print("="*70)


def main():
    """Main execution"""
    import sys

    # Get CSV path from command line or use default
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        # Try common filenames
        possible_paths = [
            'indian_oil_outlets.csv',
            'indian-oil-retail-outlets.csv',
            'outlets.csv',
            'retail_outlets.csv',
        ]

        csv_path = None
        for path in possible_paths:
            if Path(path).exists():
                csv_path = path
                break

        if not csv_path:
            print("🔍 Kaggle Indian Oil Retail Outlets Loader")
            print("="*70)
            print("\n❌ CSV file not found.")
            print("\n📥 To use this script:")
            print("  1. Download dataset from Kaggle:")
            print("     https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025")
            print("  2. Extract the ZIP file")
            print("  3. Find the CSV file and place it in this directory")
            print("  4. Run: python3 kaggle_loader.py <csv_filename>")
            print("\n  Or with default name: python3 kaggle_loader.py")
            print("  (Script looks for: indian_oil_outlets.csv, outlets.csv, etc.)")
            print("\n" + "="*70)
            return

    print("🔍 Kaggle Indian Oil Retail Outlets Loader")
    print("="*70)

    loader = KaggleDatasetLoader()
    outlets = loader.load_from_csv(csv_path)

    if outlets:
        output_dir = loader.export_all_formats()
        loader.print_summary()

        print("\n✅ Ready to use!")
        print(f"\n📝 Next steps:")
        print(f"  1. Copy {output_dir}/kaggle_outlets_LATEST.js to fuel maps")
        print(f"  2. Update map to use new data")
        print(f"  3. Test in browser")
        print(f"  4. Commit to GitHub")
    else:
        print("\n⚠ Failed to load dataset")


if __name__ == "__main__":
    main()
