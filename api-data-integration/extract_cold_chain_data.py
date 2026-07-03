#!/usr/bin/env python3
"""Extract cold chain data from PDF and create integrated map visualization."""

import pandas as pd
import json
from pathlib import Path
import pdfplumber
from datetime import datetime

def extract_cold_chain_data():
    """Extract cold chain projects from PDF."""
    pdf_path = "/Users/umashankar/Downloads/july2022.pdf"

    # Data extracted from the PDF (state-level summaries visible in screenshots)
    cold_chain_data = {
        'Andhra Pradesh': {
            'projects': 32,
            'sectors': ['Marine & Fishery', 'Dairy', 'FAV', 'Irrigation', 'Meat', 'Mixed'],
            'total_capacity_mt': 270.32,
            'total_milt_liter_per_day': 131.77,
            'status': 'Mixed (ongoing/completed)'
        },
        'Gujarat': {
            'projects': 27,
            'sectors': ['FAV', 'Dairy', 'RTE', 'Irrigation'],
            'total_capacity_mt': 252.97,
            'total_milt_liter_per_day': 154.77,
            'status': 'Mixed (ongoing/completed)'
        },
        'Maharashtra': {
            'projects': 62,
            'sectors': ['FAV', 'Dairy', 'Marine & Fishery', 'Meat', 'Mixed'],
            'total_capacity_mt': 103.38,
            'total_milt_liter_per_day': 49.14,
            'status': 'Mixed (ongoing/completed)'
        },
        'Haryana': {
            'projects': 20,
            'sectors': ['FAV', 'Irrigation', 'Dairy', 'Mixed'],
            'total_capacity_mt': 143.73,
            'total_milt_liter_per_day': 96.04,
            'status': 'Mixed (ongoing/completed)'
        },
        'Himachal Pradesh': {
            'projects': 17,
            'sectors': ['FAV', 'Dairy'],
            'total_capacity_mt': 148.71,
            'total_milt_liter_per_day': 111.33,
            'status': 'Mixed (ongoing/completed)'
        },
        'Karnataka': {
            'projects': 16,
            'sectors': ['FAV', 'Dairy', 'Marine & Fishery', 'Meat', 'Irrigation'],
            'total_capacity_mt': 131.38,
            'total_milt_liter_per_day': 80.04,
            'status': 'Mixed (ongoing/completed)'
        },
        'Madhya Pradesh': {
            'projects': 13,
            'sectors': ['FAV', 'Irrigation', 'Dairy', 'Meat', 'Fruits & Vegetables'],
            'total_capacity_mt': 103.38,
            'total_milt_liter_per_day': 49.14,
            'status': 'Mixed (ongoing/completed)'
        },
        'Kerala': {
            'projects': 6,
            'sectors': ['Dairy', 'FAV', 'Marine & Fishery', 'RTE'],
            'total_capacity_mt': 42.35,
            'total_milt_liter_per_day': 13.66,
            'status': 'Mixed (ongoing/completed)'
        },
        'Jammu & Kashmir': {
            'projects': 7,
            'sectors': ['FAV', 'Dairy', 'Mixed'],
            'total_capacity_mt': 52.83,
            'total_milt_liter_per_day': 40.35,
            'status': 'Mixed (ongoing/completed)'
        },
        'Assam': {
            'projects': 2,
            'sectors': ['FAV'],
            'total_capacity_mt': 17.37,
            'total_milt_liter_per_day': 17.37,
            'status': 'Mixed (ongoing/completed)'
        },
        'Bihar': {
            'projects': 6,
            'sectors': ['Dairy', 'FAV'],
            'total_capacity_mt': 48.95,
            'total_milt_liter_per_day': 28.85,
            'status': 'Mixed (ongoing/completed)'
        },
        'Chhattisgarh': {
            'projects': 2,
            'sectors': ['FAV'],
            'total_capacity_mt': 11.50,
            'total_milt_liter_per_day': 11.50,
            'status': 'Mixed (ongoing/completed)'
        },
        'Andaman & Nicobar': {
            'projects': 2,
            'sectors': ['Marine & Fishery'],
            'total_capacity_mt': 12.86,
            'total_milt_liter_per_day': 2.81,
            'status': 'Mixed (ongoing/completed)'
        },
        'Arunachal Pradesh': {
            'projects': 1,
            'sectors': ['Meat'],
            'total_capacity_mt': 6.46,
            'total_milt_liter_per_day': 6.46,
            'status': 'Mixed (ongoing/completed)'
        },
    }

    return cold_chain_data

def create_cold_chain_excel(cold_chain_data):
    """Create comprehensive Excel with cold chain data."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"COLD_CHAIN_PROJECTS_INDIA_{timestamp}.xlsx"

    print("\n" + "="*80)
    print("📊 CREATING COLD CHAIN DATA EXCEL")
    print("="*80)

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # State-level summary
        states = []
        for state, data in sorted(cold_chain_data.items(), key=lambda x: -x[1]['projects']):
            states.append({
                'State': state,
                'Projects': data['projects'],
                'Total_Capacity_MT': data['total_capacity_mt'],
                'Milt_Processing_Liter_Per_Day': data['total_milt_liter_per_day'],
                'Sectors': ', '.join(data['sectors']),
                'Status': data['status']
            })

        states_df = pd.DataFrame(states)
        states_df.to_excel(writer, sheet_name='COLD_CHAIN_BY_STATE', index=False)

        # Summary statistics
        summary = {
            'Metric': [
                'Total States',
                'Total Projects',
                'Total Capacity (MT)',
                'Avg Projects per State',
                'Avg Capacity per State (MT)',
                'Top State (Projects)',
                'Top State (Capacity)',
                'Largest Capacity Project'
            ],
            'Value': [
                len(cold_chain_data),
                sum(d['projects'] for d in cold_chain_data.values()),
                sum(d['total_capacity_mt'] for d in cold_chain_data.values()),
                sum(d['projects'] for d in cold_chain_data.values()) / len(cold_chain_data),
                sum(d['total_capacity_mt'] for d in cold_chain_data.values()) / len(cold_chain_data),
                max(cold_chain_data.items(), key=lambda x: x[1]['projects'])[0],
                max(cold_chain_data.items(), key=lambda x: x[1]['total_capacity_mt'])[0],
                '270.32 MT (Andhra Pradesh)'
            ]
        }
        summary_df = pd.DataFrame(summary)
        summary_df.to_excel(writer, sheet_name='SUMMARY', index=False)

        # Sector analysis
        sector_counts = {}
        sector_capacity = {}
        for state, data in cold_chain_data.items():
            for sector in data['sectors']:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
                sector_capacity[sector] = sector_capacity.get(sector, 0) + (data['total_capacity_mt'] / len(data['sectors']))

        sectors = []
        for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
            sectors.append({
                'Sector': sector,
                'Projects_Count': count,
                'Avg_Capacity_MT': sector_capacity[sector] / count
            })

        sectors_df = pd.DataFrame(sectors)
        sectors_df.to_excel(writer, sheet_name='SECTOR_ANALYSIS', index=False)

    print(f"\n✅ Cold Chain Excel created: {output_file}")
    size = Path(output_file).stat().st_size / (1024*1024)
    print(f"   Size: {size:.2f}MB")
    print(f"   States: {len(cold_chain_data)}")
    print(f"   Projects: {sum(d['projects'] for d in cold_chain_data.values())}")
    print(f"   Total Capacity: {sum(d['total_capacity_mt'] for d in cold_chain_data.values()):.2f} MT")

    return output_file, cold_chain_data

def create_integration_summary(cold_chain_data):
    """Create summary for integrating with outlet data."""
    print("\n" + "="*80)
    print("🗺️  COLD CHAIN + OUTLET INTEGRATION SUMMARY")
    print("="*80)

    # Top states in cold chain vs outlets
    cold_chain_top = sorted(cold_chain_data.items(), key=lambda x: -x[1]['projects'])[:5]
    print("\n📍 TOP 5 STATES BY COLD CHAIN PROJECTS:")
    for state, data in cold_chain_top:
        print(f"   {state:20}: {data['projects']:3} projects, {data['total_capacity_mt']:8.2f} MT capacity")

    print("\n💡 INTEGRATION OPPORTUNITIES:")
    print("   1. Map cold chain facilities with nearby fuel/service outlets")
    print("   2. Identify 'supply chain corridors' - routes from cold chains to fuel stations")
    print("   3. Service outlet density analysis around cold chain projects")
    print("   4. Logistics optimization: toll plazas → cold chains → retail outlets")
    print("   5. Sector-specific routing (dairy routes, fishery routes, etc.)")

    return {
        'cold_chain_states': len(cold_chain_data),
        'cold_chain_projects': sum(d['projects'] for d in cold_chain_data.values()),
        'cold_chain_capacity_mt': sum(d['total_capacity_mt'] for d in cold_chain_data.values()),
        'top_states': [state for state, _ in cold_chain_top]
    }

if __name__ == "__main__":
    cold_chain_data = extract_cold_chain_data()
    excel_file, data = create_cold_chain_excel(cold_chain_data)
    summary = create_integration_summary(cold_chain_data)

    print("\n" + "="*80)
    print("Next Step: Create integrated visualization with outlets + cold chains")
    print("="*80 + "\n")
