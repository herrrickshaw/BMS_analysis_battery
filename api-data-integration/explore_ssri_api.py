#!/usr/bin/env python3
"""
SSRI API EXPLORATION & DISCOVERY
================================
Systematically explores the SSRI Innovation Lab API to discover all available
data types, endpoints, and resources beyond petrol pumps.

Base URL: https://api.ssrinnovationlab.com
Known endpoints to explore:
- /api/petrol-pumps/ (existing, 50K+ pumps)
- /api/* (other potential endpoints)
- /test/* (test/demo endpoints)
"""

import requests
import json
from datetime import datetime
from typing import Dict, List
import time

class SSRIAPIExplorer:
    """
    Explores SSRI API to discover available data types and endpoints.
    """

    def __init__(self):
        """Initialize API explorer."""
        self.base_url = "https://api.ssrinnovationlab.com"
        self.endpoints_found = {}
        self.data_types = {}
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def test_endpoint(self, path: str) -> tuple:
        """
        Test if an endpoint exists and returns data.

        Returns:
            (exists, data_count, sample_data)
        """
        try:
            url = f"{self.base_url}{path}"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                # Handle different response formats
                if isinstance(data, list):
                    return True, len(data), data[:2] if data else []
                elif isinstance(data, dict):
                    if 'results' in data:
                        results = data['results']
                        count = len(results) if isinstance(results, list) else 1
                        return True, count, results[:2] if isinstance(results, list) else [results]
                    elif 'data' in data:
                        d = data['data']
                        count = len(d) if isinstance(d, list) else 1
                        return True, count, d[:2] if isinstance(d, list) else [d]
                    else:
                        return True, 1, [data]
                else:
                    return True, 1, [data]

            elif response.status_code == 404:
                return False, 0, []
            else:
                return None, 0, []

        except Exception as e:
            return None, 0, []

    def discover_api_structure(self):
        """Discover main API structure."""
        print("\n" + "="*80)
        print("🔍 DISCOVERING SSRI API STRUCTURE")
        print("="*80)

        # Common API path patterns
        base_paths = [
            "/api/",
            "/api/petrol-pumps/",
            "/api/fuel-stations/",
            "/api/retail/",
            "/api/outlets/",
            "/api/stores/",
            "/api/locations/",
            "/api/services/",
            "/api/cng/",
            "/api/ev-charging/",
            "/api/atm/",
            "/api/banks/",
            "/api/convenience/",
            "/api/supermarket/",
            "/api/restaurants/",
            "/test/",
        ]

        print("\n📍 Testing base paths...")
        for path in base_paths:
            exists, count, sample = self.test_endpoint(path)
            status = "✓" if exists else "✗" if exists is False else "?"

            if exists:
                print(f"  {status} {path:35} - {count} records")
                self.endpoints_found[path] = count
            elif exists is False:
                pass
            else:
                print(f"  {status} {path:35} - (timeout/error)")

    def explore_petrol_pumps_endpoints(self):
        """Explore all petrol pump related endpoints."""
        print("\n" + "="*80)
        print("⛽ EXPLORING PETROL PUMPS ENDPOINTS")
        print("="*80)

        # Sub-endpoints for petrol pumps
        sub_endpoints = [
            "/api/petrol-pumps/",
            "/api/petrol-pumps/by-company/",
            "/api/petrol-pumps/by-city/",
            "/api/petrol-pumps/by-state/",
            "/api/petrol-pumps/by-district/",
            "/api/petrol-pumps/nearby/",
            "/api/petrol-pumps/search/",
            "/api/petrol-pumps/filter/",
            "/api/petrol-pumps/stats/",
            "/api/petrol-pumps/companies/",
        ]

        print("\n📍 Testing petrol pump endpoints...")
        for endpoint in sub_endpoints:
            exists, count, sample = self.test_endpoint(endpoint)
            status = "✓" if exists else "✗" if exists is False else "?"

            if exists:
                print(f"  {status} {endpoint:40} - {count} records/results")
                self.endpoints_found[endpoint] = count
            elif exists is False:
                print(f"  {status} {endpoint:40}")

            time.sleep(0.3)

    def explore_alternative_fuels(self):
        """Explore alternative fuel endpoints."""
        print("\n" + "="*80)
        print("🔋 EXPLORING ALTERNATIVE FUEL ENDPOINTS")
        print("="*80)

        fuel_types = [
            "/api/cng-stations/",
            "/api/cng/",
            "/api/lpg-stations/",
            "/api/lpg/",
            "/api/ev-charging/",
            "/api/charging-stations/",
            "/api/electric-vehicle/",
            "/api/biogas/",
            "/api/hydrogen/",
            "/api/compressed-natural-gas/",
        ]

        print("\n📍 Testing alternative fuel endpoints...")
        for endpoint in fuel_types:
            exists, count, sample = self.test_endpoint(endpoint)
            status = "✓" if exists else "✗" if exists is False else "?"

            if exists:
                print(f"  {status} {endpoint:40} - {count} records")
                self.endpoints_found[endpoint] = count
                self.data_types['alternative_fuels'] = endpoint
            elif exists is False:
                pass

            time.sleep(0.2)

    def explore_retail_endpoints(self):
        """Explore retail and POI endpoints."""
        print("\n" + "="*80)
        print("🏪 EXPLORING RETAIL & POI ENDPOINTS")
        print("="*80)

        retail_types = [
            "/api/convenience-stores/",
            "/api/supermarkets/",
            "/api/restaurants/",
            "/api/shops/",
            "/api/markets/",
            "/api/malls/",
            "/api/hotels/",
            "/api/hospitals/",
            "/api/banks/",
            "/api/atm/",
            "/api/cafes/",
            "/api/retail/",
            "/api/poi/",
            "/api/points-of-interest/",
        ]

        print("\n📍 Testing retail & POI endpoints...")
        for endpoint in retail_types:
            exists, count, sample = self.test_endpoint(endpoint)
            status = "✓" if exists else "✗" if exists is False else "?"

            if exists:
                print(f"  {status} {endpoint:40} - {count} records")
                self.endpoints_found[endpoint] = count
                self.data_types[endpoint.split('/')[2]] = endpoint
            elif exists is False:
                pass

            time.sleep(0.2)

    def explore_service_endpoints(self):
        """Explore service-related endpoints."""
        print("\n" + "="*80)
        print("🔧 EXPLORING SERVICE ENDPOINTS")
        print("="*80)

        service_types = [
            "/api/service-centers/",
            "/api/repair-shops/",
            "/api/car-wash/",
            "/api/tires/",
            "/api/batteries/",
            "/api/mechanics/",
            "/api/maintenance/",
            "/api/workshops/",
        ]

        print("\n📍 Testing service endpoints...")
        for endpoint in service_types:
            exists, count, sample = self.test_endpoint(endpoint)
            status = "✓" if exists else "✗" if exists is False else "?"

            if exists:
                print(f"  {status} {endpoint:40} - {count} records")
                self.endpoints_found[endpoint] = count
                self.data_types['services'] = endpoint
            elif exists is False:
                pass

            time.sleep(0.2)

    def explore_data_endpoints(self):
        """Explore data/analytics endpoints."""
        print("\n" + "="*80)
        print("📊 EXPLORING DATA & ANALYTICS ENDPOINTS")
        print("="*80)

        data_types = [
            "/api/statistics/",
            "/api/analytics/",
            "/api/reports/",
            "/api/data/",
            "/api/states/",
            "/api/cities/",
            "/api/districts/",
            "/api/regions/",
            "/api/zones/",
        ]

        print("\n📍 Testing data endpoints...")
        for endpoint in data_types:
            exists, count, sample = self.test_endpoint(endpoint)
            status = "✓" if exists else "✗" if exists is False else "?"

            if exists:
                print(f"  {status} {endpoint:40} - {count} records/results")
                self.endpoints_found[endpoint] = count

            time.sleep(0.2)

    def test_pagination_parameters(self):
        """Test pagination and filtering parameters."""
        print("\n" + "="*80)
        print("📄 TESTING PAGINATION & FILTER PARAMETERS")
        print("="*80)

        print("\n🔍 Testing parameter combinations...")

        # Test different parameter patterns
        test_urls = [
            "/api/petrol-pumps/?limit=1000&page=1",
            "/api/petrol-pumps/?skip=0&take=100",
            "/api/petrol-pumps/?offset=0&limit=100",
            "/api/petrol-pumps/search?q=Mumbai",
            "/api/petrol-pumps/filter?state=Maharashtra",
            "/api/petrol-pumps/stats",
            "/api/petrol-pumps/companies",
            "/api/petrol-pumps/cities",
            "/api/petrol-pumps/states",
        ]

        for url in test_urls:
            full_url = f"{self.base_url}{url}"
            try:
                response = requests.get(full_url, timeout=5)
                status = "✓" if response.status_code == 200 else f"✗ ({response.status_code})"
                print(f"  {status} {url}")
            except:
                print(f"  ✗ {url} (timeout)")

            time.sleep(0.2)

    def get_endpoint_sample_data(self, endpoint: str):
        """Get sample data from an endpoint."""
        print(f"\n📋 Sample data from {endpoint}:")
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if isinstance(data, list):
                    if data:
                        print(json.dumps(data[0], indent=2)[:500])
                elif isinstance(data, dict):
                    if 'results' in data and data['results']:
                        print(json.dumps(data['results'][0], indent=2)[:500])
                    elif 'data' in data and data['data']:
                        print(json.dumps(data['data'][0], indent=2)[:500])
                    else:
                        print(json.dumps(data, indent=2)[:500])

        except Exception as e:
            print(f"Error: {e}")

    def generate_report(self):
        """Generate discovery report."""
        print("\n" + "="*80)
        print("📊 SSRI API DISCOVERY REPORT")
        print("="*80)

        print(f"\n✅ ENDPOINTS DISCOVERED: {len(self.endpoints_found)}")

        if self.endpoints_found:
            print("\n🔗 Active Endpoints:")
            for endpoint, count in sorted(self.endpoints_found.items(), key=lambda x: x[1], reverse=True):
                print(f"  • {endpoint:45} - {count:,} records")

        print(f"\n📁 Data Types Found:")
        for dtype, endpoint in sorted(self.data_types.items()):
            print(f"  • {dtype:30} - {endpoint}")

        # Save report
        report = {
            'timestamp': self.timestamp,
            'endpoints_found': self.endpoints_found,
            'data_types': self.data_types,
            'total_endpoints': len(self.endpoints_found),
            'discovery_notes': [
                'SSRI API provides access to multiple data types',
                'Main focus: Petrol pump/fuel station locations',
                'Alternative fuels may be available',
                'Retail POI data structure unknown',
                'Pagination: limit/page parameters confirmed'
            ]
        }

        report_path = f"./ssri_api_discovery_report_{self.timestamp}.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n💾 Report saved: {report_path}")

    def run_full_discovery(self):
        """Run complete API discovery."""
        print("\n" + "="*80)
        print("🚀 SSRI API COMPREHENSIVE DISCOVERY")
        print("="*80)
        print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Run all discovery methods
        self.discover_api_structure()
        self.explore_petrol_pumps_endpoints()
        self.explore_alternative_fuels()
        self.explore_retail_endpoints()
        self.explore_service_endpoints()
        self.explore_data_endpoints()
        self.test_pagination_parameters()

        # Get sample data from main endpoint
        if "/api/petrol-pumps/" in self.endpoints_found:
            self.get_endpoint_sample_data("/api/petrol-pumps/?limit=1")

        # Generate report
        self.generate_report()

        print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")


def main():
    """Main execution."""
    explorer = SSRIAPIExplorer()
    explorer.run_full_discovery()


if __name__ == "__main__":
    main()
