#!/usr/bin/env python3
"""
SSRI vs PPAC COMPREHENSIVE COMPARISON REPORT
============================================
Generates Excel workbook comparing SSRI extracted pumps against PPAC official data
with state-level, company-level, and complete outlet listing analysis.

PPAC Data Source: /Users/umashankar/Downloads/1666089602_Statewise_Retail_Outlets.xls
  - Published: October 1, 2021
  - Total Outlets: 79,417
  - Coverage: All major oil companies and retail operators

SSRI Data Source: https://api.ssrinnovationlab.com/api/petrol-pumps/pumps/
  - Extracted: June 24, 2026
  - Total Pumps: 50,374
  - Coverage: Real-time petrol pump locations

Output: Excel file with 4 sheets:
  1. STATE_COMPARISON - State-wise analysis (SSRI vs PPAC)
  2. COMPANY_ANALYSIS - Company distribution comparison
  3. EXTRACTED_OUTLETS - All 50,374 pump records with full details
  4. SUMMARY - Overall statistics and metrics
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime

class PPACComparison:
    """Generate comprehensive SSRI vs PPAC comparison Excel report."""

    def __init__(self, ssri_json_path: str, ppac_excel_path: str):
        """
        Initialize comparison engine.

        Args:
            ssri_json_path: Path to SSRI summary JSON file
            ppac_excel_path: Path to PPAC Excel data file
        """
        self.ssri_json_path = ssri_json_path
        self.ppac_excel_path = ppac_excel_path
        self.ssri_pumps = []
        self.ppac_data = None
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def load_ssri_data(self):
        """Load SSRI extracted pump data from JSON."""
        print("📂 Loading SSRI data...")
        with open(self.ssri_json_path, 'r') as f:
            self.ssri_pumps = json.load(f)
        print(f"  ✓ Loaded {len(self.ssri_pumps)} SSRI pump records")

    def load_ppac_data(self):
        """
        Load PPAC baseline data from Excel.

        The PPAC Excel file has a complex structure with headers at row 7.
        Format:
          - Row 0-6: Metadata (period, notes)
          - Row 7: Column headers (State/UT, company columns, total as of 1.10.2021)
          - Row 8+: Data rows with state names and outlet counts
        """
        print("📂 Loading PPAC data...")
        try:
            # Read PPAC Excel file, skipping header rows, using row 7 as header
            df = pd.read_excel(self.ppac_excel_path, header=7)

            # Clean up: Remove rows that are completely empty or contain only NaN
            df = df.dropna(how='all')

            # The first column is State/UT, the last column is total count (1.10.2021)
            # Rename columns for clarity
            if '1.10.2021 (P)' in df.columns:
                df['Count'] = df['1.10.2021 (P)'].astype(float, errors='ignore')
            else:
                # Use the last numeric column as count
                numeric_cols = df.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    df['Count'] = df[numeric_cols[-1]]

            # Use first column as State
            state_col = df.columns[0]
            df['State'] = df[state_col].str.strip().str.upper() if df[state_col].dtype == 'object' else df[state_col]

            # Filter out region headers (rows with no count data)
            df = df[df['Count'].notna()]

            self.ppac_data = df
            print(f"  ✓ Loaded {len(df)} PPAC outlet records")
            print(f"  ✓ Columns detected: {list(df.columns)}")
            return True
        except Exception as e:
            print(f"  ✗ Error loading PPAC: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_state_comparison(self) -> pd.DataFrame:
        """
        Create state-level comparison between SSRI and PPAC.

        Returns:
            DataFrame with columns:
            - State: State/UT name
            - SSRI_Count: Pump count from SSRI extraction
            - PPAC_Count: Outlet count from PPAC 2021
            - SSRI_Percent: Percentage of PPAC
            - Difference: SSRI - PPAC
            - Coverage: Assessment of SSRI coverage
        """
        print("📊 Analyzing state-wise distribution...")

        # Count SSRI pumps by state (normalize to uppercase for matching)
        ssri_state_counts = {}
        for pump in self.ssri_pumps:
            state = pump.get('state', 'Unknown').upper()
            ssri_state_counts[state] = ssri_state_counts.get(state, 0) + 1

        # Parse PPAC data by state
        ppac_state_counts = {}
        if self.ppac_data is not None:
            try:
                # The PPAC data should have 'State' and 'Count' columns after preprocessing
                if 'State' in self.ppac_data.columns and 'Count' in self.ppac_data.columns:
                    # Clean state names and create mapping
                    ppac_state_counts = {}
                    for idx, row in self.ppac_data.iterrows():
                        state_name = str(row['State']).strip().upper()
                        try:
                            count = int(float(row['Count']))
                            ppac_state_counts[state_name] = count
                        except:
                            pass
                    print(f"  ✓ Parsed PPAC data: {len(ppac_state_counts)} states with outlet counts")
                else:
                    print(f"  ⚠ PPAC columns not as expected")
                    print(f"  Available: {list(self.ppac_data.columns)}")
            except Exception as e:
                print(f"  ⚠ Error parsing PPAC: {e}")

        # Combine data from both sources
        all_states = set(ssri_state_counts.keys()) | set(ppac_state_counts.keys())

        comparison_data = []
        for state in sorted(all_states):
            ssri_count = ssri_state_counts.get(state, 0)
            ppac_count = ppac_state_counts.get(state, 0)

            # Calculate coverage percentage
            if ppac_count > 0:
                coverage_pct = (ssri_count / ppac_count) * 100
            else:
                coverage_pct = 0 if ssri_count == 0 else 100

            # Determine coverage assessment
            if coverage_pct >= 75:
                coverage = "EXCELLENT"
            elif coverage_pct >= 50:
                coverage = "GOOD"
            elif coverage_pct >= 25:
                coverage = "MODERATE"
            elif coverage_pct > 0:
                coverage = "LIMITED"
            else:
                coverage = "NONE"

            comparison_data.append({
                'State': state,
                'SSRI_Count': ssri_count,
                'PPAC_Count': ppac_count,
                'Coverage_%': round(coverage_pct, 2),
                'Difference': ssri_count - ppac_count,
                'Coverage_Level': coverage
            })

        df = pd.DataFrame(comparison_data).sort_values('SSRI_Count', ascending=False)
        print(f"  ✓ State comparison created: {len(df)} states/UTs")
        return df

    def create_company_comparison(self) -> pd.DataFrame:
        """
        Create company-level distribution comparison.

        Returns:
            DataFrame with columns:
            - Company: Oil company name
            - SSRI_Count: Pump count from SSRI
            - SSRI_Percent: Percentage of SSRI total
            - Description: Company details
        """
        print("📊 Analyzing company-wise distribution...")

        # Count SSRI pumps by company
        company_counts = {}
        for pump in self.ssri_pumps:
            company = pump.get('company', 'Unknown')
            company_counts[company] = company_counts.get(company, 0) + 1

        # Create company reference (major Indian oil companies)
        company_info = {
            'BPCL': 'Bharat Petroleum Corporation Limited',
            'HPCL': 'Hindustan Petroleum Corporation Limited',
            'IOCL': 'Indian Oil Corporation Limited',
            'Jio-bp': 'Jio-BP Energy Limited (Reliance-BP JV)',
            'Shell': 'Shell India (Royal Dutch Shell)',
            'Nayara': 'Nayara Energy (Essar rebranded)',
            'TPC': 'Tanganyika Petrol Company',
            'Unknown': 'Unclassified/Other Operators'
        }

        total_pumps = len(self.ssri_pumps)
        company_data = []

        for company, count in sorted(company_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_pumps) * 100
            description = company_info.get(company, f'Operator: {company}')

            company_data.append({
                'Company': company,
                'SSRI_Count': count,
                'SSRI_Percent_%': round(percentage, 2),
                'Description': description
            })

        df = pd.DataFrame(company_data)
        print(f"  ✓ Company analysis created: {len(df)} companies")
        return df

    def create_outlets_sheet(self) -> pd.DataFrame:
        """
        Create detailed listing of all extracted outlets.

        Returns:
            DataFrame with complete pump records (50,374 rows)
        """
        print("📊 Preparing complete outlet listing...")

        df = pd.DataFrame(self.ssri_pumps)

        # Ensure columns are in logical order
        column_order = ['name', 'state', 'city', 'company', 'latitude', 'longitude', 'address', 'phone']
        available_cols = [col for col in column_order if col in df.columns]
        df = df[available_cols]

        # Rename for clarity
        df.columns = ['Pump_Name', 'State', 'City', 'Company', 'Latitude', 'Longitude', 'Address', 'Phone']

        # Add index for easy reference
        df.insert(0, 'S.No', range(1, len(df) + 1))

        print(f"  ✓ Outlet listing prepared: {len(df)} records")
        return df

    def create_summary_sheet(self, state_df: pd.DataFrame, company_df: pd.DataFrame) -> pd.DataFrame:
        """
        Create summary statistics sheet.

        Returns:
            DataFrame with key metrics and analysis
        """
        print("📊 Creating summary statistics...")

        # Calculate metrics
        total_ssri = len(self.ssri_pumps)
        total_ppac = self.ppac_data['Count'].sum() if self.ppac_data is not None and 'Count' in self.ppac_data.columns else 0

        if total_ppac == 0:
            # Try alternative count column names
            for col in ['Total', 'Outlets', 'No. of Outlets']:
                if col in self.ppac_data.columns:
                    total_ppac = self.ppac_data[col].sum()
                    break

        coverage_pct = (total_ssri / total_ppac * 100) if total_ppac > 0 else 0

        states_ssri = len(state_df[state_df['SSRI_Count'] > 0])
        states_ppac = len(state_df[state_df['PPAC_Count'] > 0])
        states_covered_both = len(state_df[(state_df['SSRI_Count'] > 0) & (state_df['PPAC_Count'] > 0)])

        top_company = company_df.iloc[0] if len(company_df) > 0 else None

        summary_data = {
            'Metric': [
                'Total SSRI Pumps Extracted',
                'Total PPAC Outlets (Oct 2021)',
                'Overall Coverage %',
                '',
                'States Covered by SSRI',
                'States Covered by PPAC',
                'States Covered by Both',
                '',
                'Companies in SSRI Data',
                'Top Company',
                'Top Company Count',
                'Top Company Share %',
                '',
                'Extraction Date',
                'PPAC Date',
                'Data Age Difference'
            ],
            'Value': [
                total_ssri,
                int(total_ppac),
                f"{coverage_pct:.2f}%",
                '',
                states_ssri,
                states_ppac,
                states_covered_both,
                '',
                len(company_df),
                top_company['Company'] if top_company is not None else 'N/A',
                top_company['SSRI_Count'] if top_company is not None else 0,
                f"{top_company['SSRI_Percent_%']:.2f}%" if top_company is not None else 'N/A',
                '',
                '2026-06-24',
                '2021-10-01',
                '5 years (SSRI newer)'
            ]
        }

        df = pd.DataFrame(summary_data)
        print(f"  ✓ Summary statistics created")
        return df

    def generate_excel_report(self, output_path: str):
        """
        Generate comprehensive Excel report with multiple sheets.

        Args:
            output_path: Path to save Excel file
        """
        print("\n" + "="*80)
        print("🎯 SSRI vs PPAC COMPARISON REPORT")
        print("="*80)

        # Load data
        self.load_ssri_data()
        ppac_loaded = self.load_ppac_data()

        # Create analysis sheets
        state_df = self.create_state_comparison()
        company_df = self.create_company_comparison()
        outlets_df = self.create_outlets_sheet()
        summary_df = self.create_summary_sheet(state_df, company_df)

        # Write to Excel with multiple sheets
        print("\n📝 Writing Excel workbook...")
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            summary_df.to_excel(writer, sheet_name='SUMMARY', index=False)
            state_df.to_excel(writer, sheet_name='STATE_COMPARISON', index=False)
            company_df.to_excel(writer, sheet_name='COMPANY_ANALYSIS', index=False)
            outlets_df.to_excel(writer, sheet_name='EXTRACTED_OUTLETS', index=False)

        print(f"\n✅ Excel report generated: {output_path}")
        print(f"   Sheets created: SUMMARY, STATE_COMPARISON, COMPANY_ANALYSIS, EXTRACTED_OUTLETS")
        print(f"   File size: {Path(output_path).stat().st_size / (1024*1024):.2f} MB")


def main():
    """Main execution."""
    # Paths
    ssri_json = "/Users/umashankar/api-data-integration/outlet_data_ssri_complete/ssri_all_pumps_20260624_063249.json"
    ppac_excel = "/Users/umashankar/Downloads/1666089602_Statewise_Retail_Outlets.xls"
    output_excel = "/Users/umashankar/api-data-integration/SSRI_vs_PPAC_Comparison_Report.xlsx"

    # Generate comparison
    comparator = PPACComparison(ssri_json, ppac_excel)
    comparator.generate_excel_report(output_excel)


if __name__ == "__main__":
    main()
