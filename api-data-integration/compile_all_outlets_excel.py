#!/usr/bin/env python3
"""Compile all outlet data into comprehensive Excel workbook."""

import pandas as pd
from pathlib import Path
from datetime import datetime
import glob

def main():
    print("\n" + "="*80)
    print("📊 COMPILING ALL OUTLET DATA TO EXCEL")
    print("="*80)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"ALL_OUTLETS_COMPREHENSIVE_{timestamp}.xlsx"

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Load SSRI data
        print("\n📂 Loading SSRI petrol pump database...")
        ssri_files = glob.glob("outlet_data_ssri_107k/ssri_complete_pumps_*.csv")
        if ssri_files:
            ssri_df = pd.read_csv(ssri_files[0])
            print(f"   ✓ Loaded {len(ssri_df):,} SSRI outlets")
            ssri_df.to_excel(writer, sheet_name='SSRI_PUMPS', index=False)

            # Summary stats
            print(f"\n   State coverage: {ssri_df['state'].nunique()} states")
            print(f"   Company distribution:")
            company_counts = ssri_df['company'].value_counts().head(10)
            for company, count in company_counts.items():
                print(f"      {company}: {count}")
        else:
            print("   ✗ SSRI file not found")

        # Load Cash@PoS extracted data
        print("\n📂 Loading Cash@PoS extracted outlets...")
        cashatpos_files = glob.glob("api-data-integration/outlet_data_cashatpos/cashatpos_fuel_stations_*.csv")
        if cashatpos_files:
            cashatpos_df = pd.read_csv(cashatpos_files[0])
            print(f"   ✓ Loaded {len(cashatpos_df)} Cash@PoS outlets")
            cashatpos_df.to_excel(writer, sheet_name='CASHATPOS_EXTRACTED', index=False)

            # Summary stats
            if 'state' in cashatpos_df.columns:
                print(f"\n   State coverage: {cashatpos_df['state'].nunique()} states")
                state_counts = cashatpos_df['state'].value_counts().head(10)
                print("   Top states:")
                for state, count in state_counts.items():
                    print(f"      {state}: {count}")
        else:
            print("   ✗ Cash@PoS file not found")

        # Create combined summary
        print("\n📊 Creating summary sheet...")
        summary_data = {
            'Dataset': ['SSRI Petrol Pumps', 'Cash@PoS Extracted'],
            'Total Records': [len(ssri_df) if 'ssri_df' in locals() else 0,
                            len(cashatpos_df) if 'cashatpos_df' in locals() else 0],
            'States': [ssri_df['state'].nunique() if 'ssri_df' in locals() else 0,
                      cashatpos_df['state'].nunique() if 'cashatpos_df' in locals() and 'state' in cashatpos_df.columns else 0],
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='SUMMARY', index=False)

        # State-wise breakdown
        print("📍 Creating state-wise analysis...")
        if 'ssri_df' in locals():
            state_summary = ssri_df.groupby('state').agg({
                'name': 'count',
                'company': 'nunique'
            }).rename(columns={'name': 'outlet_count', 'company': 'companies'}).reset_index()
            state_summary.columns = ['State', 'SSRI_Outlets', 'Companies']
            state_summary = state_summary.sort_values('SSRI_Outlets', ascending=False)
            state_summary.to_excel(writer, sheet_name='STATE_ANALYSIS', index=False)

        # Company breakdown
        print("🏢 Creating company breakdown...")
        if 'ssri_df' in locals():
            company_summary = ssri_df['company'].value_counts().reset_index()
            company_summary.columns = ['Company', 'Outlet_Count']
            company_summary.to_excel(writer, sheet_name='COMPANY_BREAKDOWN', index=False)

        print(f"\n✅ Excel workbook created: {output_file}")
        file_size = Path(output_file).stat().st_size / (1024*1024)
        print(f"   Size: {file_size:.2f}MB")
        print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    main()
