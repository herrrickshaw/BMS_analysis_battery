#!/usr/bin/env python3
"""
SSR API Auto-Authentication
Runs SSR API integration with provided credentials
"""

import sys
from ssr_api_handler import SSRAPIHandler

def main():
    """Auto-authenticate and fetch data"""

    # Credentials from command line or environment
    if len(sys.argv) < 3:
        print("Usage: python3 ssr_auto_auth.py <username> <password> [method]")
        print("Example: python3 ssr_auto_auth.py user@email.com password basic")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    method = sys.argv[3] if len(sys.argv) > 3 else "basic"

    print("🔐 SSR Innovation Lab API - Auto Authentication")
    print("="*70)

    handler = SSRAPIHandler()

    # Authenticate
    print(f"\n🔑 Authenticating with {method.upper()} Auth...")
    print(f"   Username: {username[:15]}..." if len(username) > 15 else f"   Username: {username}")

    authenticated = handler.authenticate_basic(username, password)

    if not authenticated:
        print("\n❌ Authentication failed!")
        print("\nTroubleshooting:")
        print("  1. Check username is correct")
        print("  2. Check password is correct")
        print("  3. Verify account exists at https://api.ssrinnovationlab.com/")
        sys.exit(1)

    print("\n✅ Authentication successful!")

    # Fetch data
    print("\n📥 Fetching data from SSR API...")
    outlets = handler.fetch_data()

    if not outlets:
        print("❌ Failed to fetch data")
        sys.exit(1)

    print(f"✅ Fetched {len(outlets)} outlets")

    # Process
    print("\n⚙️  Processing outlets...")
    processed = handler.process_outlets()

    if not processed:
        print("❌ Processing failed")
        sys.exit(1)

    print(f"✅ Processed {len(processed)} outlets")

    # Export
    print("\n💾 Exporting data...")
    output_dir = handler.export_all_formats()

    if not output_dir:
        print("❌ Export failed")
        sys.exit(1)

    print(f"✅ Exported to {output_dir}/")

    # Summary
    handler.print_summary()

    print("\n🎉 SUCCESS! Data ready for integration")
    print(f"\n📂 Output files:")
    print(f"   CSV: {output_dir}/ssr_outlets_*.csv")
    print(f"   JSON: {output_dir}/ssr_outlets_*.json")
    print(f"   GeoJSON: {output_dir}/ssr_outlets_*.geojson")
    print(f"   JavaScript: {output_dir}/ssr_outlets_*.js")
    print(f"   Stats: {output_dir}/ssr_outlets_stats_*.json")

    print("\n📝 Next steps:")
    print(f"   1. cp {output_dir}/ssr_outlets_*.js ../fuel-pump-locations-map/locations-data.js")
    print(f"   2. cd ../fuel-pump-locations-map/")
    print(f"   3. python3 -m http.server 8000")
    print(f"   4. Visit http://localhost:8000")


if __name__ == "__main__":
    main()
