#!/usr/bin/env python3
"""
SSR Innovation Lab API Handler
Authenticates and fetches retail outlet data from:
https://api.ssrinnovationlab.com/api/test/18/
"""

import requests
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import getpass

class SSRAPIHandler:
    def __init__(self):
        self.base_url = "https://api.ssrinnovationlab.com"
        self.session = requests.Session()
        self.outlets = []
        self.stats = {
            'total': 0,
            'with_coords': 0,
            'states': 0,
            'cities': 0,
            'companies': 0
        }
        self.authenticated = False

    def authenticate_basic(self, username: str, password: str) -> bool:
        """
        Authenticate using Basic Auth (username:password)
        """
        print(f"\n🔐 Attempting Basic Authentication...")

        try:
            # Set up basic auth
            self.session.auth = (username, password)

            # Test with simple request
            response = self.session.get(
                f"{self.base_url}/api/test/18/",
                timeout=10,
                headers={'Accept': 'application/json'}
            )

            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"  ✓ Authentication successful!")
                    print(f"  ✓ Response contains {len(data) if isinstance(data, list) else 1} records")
                    self.authenticated = True
                    return True
                except json.JSONDecodeError:
                    print(f"  ⚠ Got HTML response (still not JSON)")
                    return False
            else:
                print(f"  ✗ Authentication failed: Status {response.status_code}")
                return False

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return False

    def authenticate_api_key(self, api_key: str) -> bool:
        """
        Authenticate using API Key (in header)
        """
        print(f"\n🔐 Attempting API Key Authentication...")

        try:
            headers = {
                'Authorization': f'Bearer {api_key}',
                'X-API-Key': api_key,
                'Accept': 'application/json'
            }

            response = self.session.get(
                f"{self.base_url}/api/test/18/",
                timeout=10,
                headers=headers
            )

            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"  ✓ Authentication successful!")
                    print(f"  ✓ Response contains {len(data) if isinstance(data, list) else 1} records")
                    self.session.headers.update(headers)
                    self.authenticated = True
                    return True
                except json.JSONDecodeError:
                    print(f"  ⚠ Got HTML response (still not JSON)")
                    return False
            else:
                print(f"  ✗ Status {response.status_code}")
                return False

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return False

    def authenticate_bearer_token(self, token: str) -> bool:
        """
        Authenticate using Bearer Token
        """
        print(f"\n🔐 Attempting Bearer Token Authentication...")

        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json'
            }

            response = self.session.get(
                f"{self.base_url}/api/test/18/",
                timeout=10,
                headers=headers
            )

            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"  ✓ Authentication successful!")
                    print(f"  ✓ Response contains {len(data) if isinstance(data, list) else 1} records")
                    self.session.headers.update(headers)
                    self.authenticated = True
                    return True
                except json.JSONDecodeError:
                    print(f"  ⚠ Got HTML response")
                    return False
            else:
                print(f"  ✗ Status {response.status_code}")
                return False

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return False

    def fetch_data(self) -> List[Dict]:
        """
        Fetch data from authenticated API
        """
        if not self.authenticated:
            print("✗ Not authenticated. Call authenticate_* methods first.")
            return []

        print(f"\n📥 Fetching data from SSR API...")

        try:
            response = self.session.get(
                f"{self.base_url}/api/test/18/",
                timeout=30,
                headers={'Accept': 'application/json'}
            )

            if response.status_code == 200:
                try:
                    data = response.json()

                    # Handle different response formats
                    if isinstance(data, dict) and 'data' in data:
                        outlets = data['data']
                    elif isinstance(data, dict) and 'outlets' in data:
                        outlets = data['outlets']
                    elif isinstance(data, list):
                        outlets = data
                    else:
                        print(f"  ⚠ Unknown response format")
                        return []

                    print(f"  ✓ Fetched {len(outlets)} outlets")
                    self.outlets = outlets
                    return outlets

                except json.JSONDecodeError as e:
                    print(f"  ✗ Invalid JSON: {e}")
                    return []
            else:
                print(f"  ✗ API returned status {response.status_code}")
                return []

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def process_outlets(self) -> List[Dict]:
        """
        Process and standardize outlet data
        """
        if not self.outlets:
            print("✗ No data to process")
            return []

        print(f"\n⚙️  Processing {len(self.outlets)} outlets...")

        processed = []

        for outlet in self.outlets:
            try:
                # Standardize fields
                lat = outlet.get('latitude') or outlet.get('lat')
                lng = outlet.get('longitude') or outlet.get('lng')

                if not lat or not lng:
                    continue

                processed_outlet = {
                    'name': str(outlet.get('outlet_name') or outlet.get('name', 'Unknown')),
                    'latitude': float(lat),
                    'longitude': float(lng),
                    'source': 'SSR_API',
                    'company': str(outlet.get('company', 'Unknown')),
                    'city': str(outlet.get('city', '')),
                    'state': str(outlet.get('state', '')),
                }

                processed.append(processed_outlet)

            except (ValueError, TypeError):
                continue

        self.stats['total'] = len(processed)
        self.stats['with_coords'] = len(processed)
        self.stats['states'] = len(set(o['state'] for o in processed if o['state']))
        self.stats['cities'] = len(set(o['city'] for o in processed if o['city']))

        print(f"  ✓ Processed {len(processed)} outlets")
        print(f"  ✓ States: {self.stats['states']}")
        print(f"  ✓ Cities: {self.stats['cities']}")

        return processed

    def export_formats(self, outlets: List[Dict], output_dir: str = "./outlet_data_ssr"):
        """
        Export to multiple formats
        """
        if not outlets:
            print("✗ No outlets to export")
            return

        Path(output_dir).mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print(f"\n💾 Exporting to {output_dir}/...")

        try:
            # DataFrame
            df = pd.DataFrame(outlets)

            # CSV
            csv_path = f"{output_dir}/ssr_outlets_{timestamp}.csv"
            df.to_csv(csv_path, index=False)
            print(f"  ✓ CSV: {csv_path}")

            # GeoJSON
            geojson = {"type": "FeatureCollection", "features": []}
            for outlet in outlets:
                if outlet.get('latitude') and outlet.get('longitude'):
                    geojson["features"].append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [outlet['longitude'], outlet['latitude']]
                        },
                        "properties": {
                            "name": outlet.get('name'),
                            "company": outlet.get('company'),
                            "city": outlet.get('city'),
                            "state": outlet.get('state')
                        }
                    })

            geojson_path = f"{output_dir}/ssr_outlets_{timestamp}.geojson"
            with open(geojson_path, 'w') as f:
                json.dump(geojson, f, indent=2)
            print(f"  ✓ GeoJSON: {geojson_path}")

            # JavaScript
            js_path = f"{output_dir}/ssr_outlets_{timestamp}.js"
            js_content = f"""// SSR Innovation Lab API Outlets
// Fetched: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

const FUEL_PUMP_LOCATIONS = {json.dumps(outlets)};

const OUTLET_STATS = {{
    total: {len(outlets)},
    states: {self.stats['states']},
    cities: {self.stats['cities']},
    source: 'SSR Innovation Lab API'
}};
"""
            with open(js_path, 'w') as f:
                f.write(js_content)
            print(f"  ✓ JavaScript: {js_path}")

            # JSON
            json_path = f"{output_dir}/ssr_outlets_{timestamp}.json"
            with open(json_path, 'w') as f:
                json.dump(outlets, f, indent=2)
            print(f"  ✓ JSON: {json_path}")

            # Stats
            stats_path = f"{output_dir}/ssr_outlets_stats_{timestamp}.json"
            with open(stats_path, 'w') as f:
                json.dump({
                    'timestamp': timestamp,
                    'total_outlets': len(outlets),
                    'states': self.stats['states'],
                    'cities': self.stats['cities'],
                    'source': 'SSR Innovation Lab API'
                }, f, indent=2)
            print(f"  ✓ Statistics: {stats_path}")

            print(f"\n✅ Export complete!")
            return output_dir

        except Exception as e:
            print(f"  ✗ Export error: {e}")
            return None

    def print_summary(self):
        """Print summary"""
        print("\n" + "="*70)
        print("📊 SSR API DATA SUMMARY")
        print("="*70)
        print(f"Total Outlets: {self.stats['total']}")
        print(f"States: {self.stats['states']}")
        print(f"Cities: {self.stats['cities']}")
        print("="*70)


def main():
    """Main execution"""
    print("🔐 SSR Innovation Lab API Handler")
    print("="*70)

    handler = SSRAPIHandler()

    print("\n🔑 Authentication Methods:")
    print("  1. Basic Auth (username + password)")
    print("  2. API Key")
    print("  3. Bearer Token")
    print("  4. Enter custom credentials")
    print()

    choice = input("Select method (1-4): ").strip()

    authenticated = False

    if choice == "1":
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        authenticated = handler.authenticate_basic(username, password)

    elif choice == "2":
        api_key = input("API Key: ").strip()
        authenticated = handler.authenticate_api_key(api_key)

    elif choice == "3":
        token = input("Bearer Token: ").strip()
        authenticated = handler.authenticate_bearer_token(token)

    elif choice == "4":
        print("\nTry custom headers. What auth method?")
        print("  1. API Key in X-API-Key header")
        print("  2. Token in Authorization header")
        sub = input("Choose (1-2): ").strip()

        if sub == "1":
            api_key = input("API Key value: ").strip()
            authenticated = handler.authenticate_api_key(api_key)
        else:
            token = input("Token value: ").strip()
            authenticated = handler.authenticate_bearer_token(token)

    if not authenticated:
        print("\n❌ Authentication failed")
        print("\nTroubleshooting:")
        print("  1. Check credentials are correct")
        print("  2. Try different authentication methods")
        print("  3. Verify API endpoint is correct")
        print("  4. Check if API requires additional headers")
        return

    # Fetch data
    outlets = handler.fetch_data()

    if outlets:
        # Process
        processed = handler.process_outlets()

        if processed:
            # Export
            handler.export_formats(processed)
            handler.print_summary()

            print("\n✅ Success! Data exported to outlet_data_ssr/")
            print("\n📝 Next steps:")
            print("  1. Copy ssr_outlets_LATEST.js to your maps")
            print("  2. Test in browser")
            print("  3. Commit to GitHub")
    else:
        print("\n❌ Failed to fetch data")


if __name__ == "__main__":
    main()
