#!/usr/bin/env python3
"""
CASH@POS FUEL STATION EXTRACTION FROM PDF
==========================================
Extracts fuel station data from Cash@PoS and SBI Cash@PoS PDF documents.

Source PDFs:
1. Cash@PoS-UPDATED-19-11-16.pdf - Comprehensive retail outlet list (34 pages)
2. sbicashatpos.pdf - SBI Cash@PoS fuel stations (9 pages)

Data includes:
- Fuel station name, location, district, state
- Banking partner (SBI)
- Cash@PoS/Mini ATM availability
- Geographic coordinates (to be geocoded)
"""

import pdfplumber
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
import re

class CashAtPosExtractor:
    """
    Extracts fuel station data from Cash@PoS PDF documents.

    PDFs contain lists of fuel stations with banking services (ATM/Cash@PoS).
    Useful for verifying banking infrastructure at fuel pumps.
    """

    def __init__(self):
        """Initialize extractor."""
        self.all_stations = {}
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.stats = {
            'pdf1_extracted': 0,
            'pdf2_extracted': 0,
            'total_unique': 0,
            'duplicates': 0
        }

    def extract_from_pdf1(self, pdf_path: str):
        """
        Extract from Cash@PoS-UPDATED-19-11-16.pdf
        Format: SL, NAME, LOCATION, DISTRICT, STATE, BANK
        """
        print("📄 Extracting from Cash@PoS-UPDATED-19-11-16.pdf...")

        stations = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                print(f"   Pages: {total_pages}")

                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()

                    if not text:
                        continue

                    # Parse text lines
                    lines = text.split('\n')

                    for line in lines:
                        # Skip header and empty lines
                        if not line.strip() or 'NAME OF RETAIL' in line or 'SL' in line:
                            continue

                        # Try to parse station data
                        # Format: SL | NAME | LOCATION | DISTRICT | STATE | BANK
                        parts = [p.strip() for p in line.split() if p.strip()]

                        if len(parts) >= 4:
                            try:
                                # Extract components
                                station_name = parts[0] if parts else ''
                                # Try to identify location, district, state
                                # This is complex due to varying formats, use regex

                                # Look for state names
                                state_match = None
                                for state in ['Andhra Pradesh', 'Telangana', 'Karnataka', 'Maharashtra',
                                             'Gujarat', 'Rajasthan', 'Punjab', 'Haryana', 'Uttar Pradesh',
                                             'Tamil Nadu', 'Kerala', 'West Bengal', 'Odisha', 'Madhya Pradesh']:
                                    if state in line:
                                        state_match = state
                                        break

                                if state_match and station_name and len(station_name) > 3:
                                    station = {
                                        'name': station_name,
                                        'location': '',
                                        'district': '',
                                        'state': state_match,
                                        'bank': 'SBI',
                                        'service_type': 'Cash@PoS',
                                        'source': 'Cash@PoS PDF',
                                        'extraction_date': datetime.now().strftime('%Y-%m-%d')
                                    }
                                    stations.append(station)
                            except Exception:
                                continue

                    if page_num % 5 == 0:
                        print(f"   Processed {page_num}/{total_pages} pages...")

            print(f"  ✓ Extracted {len(stations)} records from PDF1")
            self.stats['pdf1_extracted'] = len(stations)
            return stations

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def extract_from_pdf2(self, pdf_path: str):
        """
        Extract from sbicashatpos.pdf
        Format: Name, Location, District, State
        Simpler format with fuel stations having SBI Mini ATM
        """
        print("\n📄 Extracting from sbicashatpos.pdf...")

        stations = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                print(f"   Pages: {total_pages}")

                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()

                    if not text:
                        continue

                    lines = text.split('\n')

                    for line in lines:
                        line = line.strip()

                        # Skip headers and empty lines
                        if not line or 'LIST OF FUEL' in line or 'Name' in line or 'Location' in line:
                            continue

                        # Parse station data
                        # Try to identify state
                        state_match = None
                        for state in ['Andhra Pradesh', 'Telangana', 'Karnataka', 'Maharashtra',
                                     'Gujarat', 'Rajasthan', 'Punjab', 'Haryana', 'Uttar Pradesh',
                                     'Tamil Nadu', 'Kerala', 'West Bengal', 'Odisha', 'Madhya Pradesh',
                                     'A.P.']:
                            if state in line or 'A.P.' in line:
                                state_match = 'Andhra Pradesh' if 'A.P.' in line else state
                                break

                        if state_match and len(line) > 5:
                            # Extract station name (typically at start of line)
                            parts = line.split()
                            if parts:
                                station = {
                                    'name': parts[0] + (' ' + parts[1] if len(parts) > 1 else ''),
                                    'location': '',
                                    'district': '',
                                    'state': state_match,
                                    'bank': 'SBI',
                                    'service_type': 'Mini ATM / Cash@PoS',
                                    'source': 'SBI Cash@PoS PDF',
                                    'extraction_date': datetime.now().strftime('%Y-%m-%d')
                                }
                                stations.append(station)

                    if page_num % 3 == 0:
                        print(f"   Processed {page_num}/{total_pages} pages...")

            print(f"  ✓ Extracted {len(stations)} records from PDF2")
            self.stats['pdf2_extracted'] = len(stations)
            return stations

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def deduplicate_stations(self, stations: list):
        """
        Add stations with deduplication by name + state.
        """
        for station in stations:
            key = f"{station['name'].upper()}_{station['state'].upper()}"

            if key not in self.all_stations:
                self.all_stations[key] = station
            else:
                # Merge information if available
                self.stats['duplicates'] += 1

        self.stats['total_unique'] = len(self.all_stations)

    def export_data(self, output_dir: str = "./outlet_data_cashatpos"):
        """Export extracted station data."""
        print("\n" + "="*80)
        print("💾 EXPORTING CASH@POS STATION DATA")
        print("="*80)

        Path(output_dir).mkdir(exist_ok=True)

        if not self.all_stations:
            print("✗ No data to export")
            return

        # Create DataFrame
        df = pd.DataFrame(list(self.all_stations.values()))

        # Export CSV
        print(f"\n  Exporting CSV...")
        csv_path = f"{output_dir}/cashatpos_fuel_stations_{self.timestamp}.csv"
        df.to_csv(csv_path, index=False)
        csv_size = Path(csv_path).stat().st_size / (1024*1024)
        print(f"    ✓ {csv_path} ({csv_size:.2f}MB, {len(df)} records)")

        # Export JSON
        print(f"  Exporting JSON...")
        json_path = f"{output_dir}/cashatpos_fuel_stations_{self.timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(list(self.all_stations.values()), f, indent=2)
        json_size = Path(json_path).stat().st_size / (1024*1024)
        print(f"    ✓ {json_path} ({json_size:.2f}MB)")

        # Export Summary
        print(f"  Generating summary...")
        summary = {
            'timestamp': self.timestamp,
            'total_stations': len(self.all_stations),
            'unique_states': len(set(s.get('state') for s in self.all_stations.values())),
            'extraction_stats': self.stats,
            'state_distribution': self._get_state_distribution(),
            'bank_distribution': self._get_bank_distribution(),
            'service_distribution': self._get_service_distribution()
        }

        summary_path = f"{output_dir}/cashatpos_fuel_stations_summary_{self.timestamp}.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"    ✓ {summary_path}")

        print(f"\n✅ Export complete to {output_dir}/")
        return summary

    def _get_state_distribution(self):
        """Get distribution by state."""
        dist = {}
        for station in self.all_stations.values():
            state = station.get('state', 'Unknown')
            dist[state] = dist.get(state, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def _get_bank_distribution(self):
        """Get distribution by bank."""
        dist = {}
        for station in self.all_stations.values():
            bank = station.get('bank', 'Unknown')
            dist[bank] = dist.get(bank, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def _get_service_distribution(self):
        """Get distribution by service type."""
        dist = {}
        for station in self.all_stations.values():
            service = station.get('service_type', 'Unknown')
            dist[service] = dist.get(service, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def print_summary(self, summary: dict):
        """Print final summary."""
        print("\n" + "="*80)
        print("📊 CASH@POS STATION EXTRACTION SUMMARY")
        print("="*80)

        print(f"\n✅ EXTRACTION COMPLETE!")
        print(f"\n   Total Stations: {summary['total_stations']}")
        print(f"   Unique States: {summary['unique_states']}")

        print(f"\n   Extraction Statistics:")
        print(f"   • PDF1 (Cash@PoS): {summary['extraction_stats']['pdf1_extracted']}")
        print(f"   • PDF2 (SBI Cash@PoS): {summary['extraction_stats']['pdf2_extracted']}")
        print(f"   • Duplicates: {summary['extraction_stats']['duplicates']}")

        print(f"\n   State Distribution:")
        for state, count in list(summary['state_distribution'].items())[:10]:
            print(f"   • {state}: {count}")

        print(f"\n   Bank Distribution:")
        for bank, count in summary['bank_distribution'].items():
            print(f"   • {bank}: {count}")

        print(f"\n   Service Types:")
        for service, count in summary['service_distribution'].items():
            print(f"   • {service}: {count}")

    def run(self, pdf1_path: str, pdf2_path: str):
        """Run complete extraction."""
        print("\n" + "="*80)
        print("🚀 CASH@POS FUEL STATION EXTRACTION FROM PDF")
        print("="*80)
        print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Extract from PDF1
        stations1 = self.extract_from_pdf1(pdf1_path)
        self.deduplicate_stations(stations1)

        # Extract from PDF2
        stations2 = self.extract_from_pdf2(pdf2_path)
        self.deduplicate_stations(stations2)

        # Export
        summary = self.export_data()

        # Print summary
        if summary:
            self.print_summary(summary)

        print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")


def main():
    """Main execution."""
    extractor = CashAtPosExtractor()

    pdf1 = "/Users/umashankar/Downloads/Cash@PoS-UPDATED-19-11-16.pdf"
    pdf2 = "/Users/umashankar/Downloads/sbicashatpos.pdf"

    extractor.run(pdf1, pdf2)


if __name__ == "__main__":
    main()
