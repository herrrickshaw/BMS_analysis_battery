#!/usr/bin/env python3
"""
Utility script to update toll plaza visualizations with new payment data
Usage: python3 update_toll_visualization.py --data your_payment_data.csv
"""

import argparse
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from toll_plaza_dashboard import TollPlazaDashboard


def validate_payment_data(csv_path):
    """Validate that payment data has required columns"""
    try:
        df = pd.read_csv(csv_path)
        required_columns = ['plaza_name', 'date', 'amount']

        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            print(f"❌ Error: Missing required columns: {', '.join(missing)}")
            print(f"✓ Available columns: {', '.join(df.columns)}")
            return False

        # Validate data types
        try:
            df['date'] = pd.to_datetime(df['date'])
            df['amount'] = pd.to_numeric(df['amount'])
            print(f"✓ Data validation passed")
            print(f"  - Records: {len(df):,}")
            print(f"  - Date range: {df['date'].min().date()} to {df['date'].max().date()}")
            print(f"  - Unique plazas: {df['plaza_name'].nunique()}")
            return True
        except ValueError as e:
            print(f"❌ Error converting data types: {e}")
            return False

    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False


def update_visualizations(payment_data_path, output_dir='Downloads', verbose=True):
    """Update all visualizations with new payment data"""

    print("\n" + "="*70)
    print("TOLL PLAZA VISUALIZATION UPDATE")
    print("="*70 + "\n")

    # Validate input data
    print("Step 1: Validating payment data...")
    if not validate_payment_data(payment_data_path):
        return False

    print("\nStep 2: Initializing dashboard...")
    plaza_data = f'/Users/umashankar/{output_dir}/toll_plazas_cleaned.csv'

    if not Path(plaza_data).exists():
        print(f"❌ Error: Plaza data not found at {plaza_data}")
        return False

    try:
        dashboard = TollPlazaDashboard(plaza_data, payment_data_path)
    except Exception as e:
        print(f"❌ Error initializing dashboard: {e}")
        return False

    print("\nStep 3: Generating updated visualizations...")
    output_path = f'/Users/umashankar/{output_dir}'

    try:
        # Generate outputs
        dashboard_html = f'{output_path}/toll_dashboard_updated.html'
        metrics_json = f'{output_path}/toll_metrics_updated.json'
        report_txt = f'{output_path}/toll_analysis_report_updated.txt'

        print(f"  • Creating interactive dashboard...")
        dashboard.create_interactive_dashboard(dashboard_html)

        print(f"  • Exporting metrics...")
        dashboard.export_metrics_json(metrics_json)

        print(f"  • Generating text report...")
        dashboard.generate_text_report(report_txt)

        # Generate summary statistics
        print(f"\nStep 4: Computing summary statistics...")
        stats = {
            'update_timestamp': datetime.now().isoformat(),
            'total_collections_crores': dashboard.metrics['total_collections'] / 10000000,
            'data_records': len(dashboard.payments),
            'active_plazas': dashboard.payments['plaza_name'].nunique(),
            'date_range': {
                'start': dashboard.payments['date'].min().strftime('%Y-%m-%d'),
                'end': dashboard.payments['date'].max().strftime('%Y-%m-%d')
            },
            'top_3_plazas': list(
                dashboard.metrics['top_plazas'].items()
            )[:3]
        }

        print(f"\n{'='*70}")
        print("SUMMARY STATISTICS")
        print(f"{'='*70}")
        print(f"Total Collections: ₹{stats['total_collections_crores']:.2f} Crore")
        print(f"Data Records: {stats['data_records']:,}")
        print(f"Active Plazas: {stats['active_plazas']}")
        print(f"Date Range: {stats['date_range']['start']} to {stats['date_range']['end']}")
        print(f"\nTop 3 Performing Plazas:")
        for i, (plaza, amount) in enumerate(stats['top_3_plazas'], 1):
            print(f"  {i}. {plaza}: ₹{amount/100000:.2f} Lakhs")

        print(f"\n{'='*70}")
        print("✅ VISUALIZATIONS UPDATED SUCCESSFULLY!")
        print(f"{'='*70}\n")

        print("Generated files:")
        print(f"  📊 {dashboard_html}")
        print(f"  📈 {metrics_json}")
        print(f"  📄 {report_txt}\n")

        print("To view the updated dashboard:")
        print(f"  open {dashboard_html}\n")

        return True

    except Exception as e:
        print(f"\n❌ Error generating visualizations: {e}")
        return False


def archive_previous_versions(output_dir='Downloads'):
    """Archive previous visualization versions"""
    output_path = Path(f'/Users/umashankar/{output_dir}')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    files_to_archive = [
        'toll_dashboard.html',
        'toll_metrics.json',
        'toll_analysis_report.txt'
    ]

    print(f"\nArchiving previous versions with timestamp {timestamp}...")

    for filename in files_to_archive:
        source = output_path / filename
        if source.exists():
            archive_name = source.stem + f'_backup_{timestamp}' + source.suffix
            archive_path = output_path / archive_name
            source.rename(archive_path)
            print(f"  ✓ Archived: {archive_name}")


def main():
    parser = argparse.ArgumentParser(
        description='Update toll plaza visualizations with new payment data'
    )
    parser.add_argument(
        '--data',
        required=True,
        help='Path to payment data CSV file'
    )
    parser.add_argument(
        '--output',
        default='Downloads',
        help='Output directory (default: Downloads)'
    )
    parser.add_argument(
        '--archive',
        action='store_true',
        help='Archive previous versions before updating'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force update without confirmation'
    )

    args = parser.parse_args()

    # Validate file exists
    if not Path(args.data).exists():
        print(f"❌ Error: File not found: {args.data}")
        return False

    # Ask for confirmation
    if not args.force:
        response = input("\nThis will update all visualizations. Continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Cancelled.")
            return False

    # Archive previous versions if requested
    if args.archive:
        archive_previous_versions(args.output)

    # Update visualizations
    success = update_visualizations(args.data, args.output)

    return success


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
