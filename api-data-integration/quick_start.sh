#!/bin/bash

# Hybrid Data Aggregation Quick Start
# Run this script to begin the aggregation process

set -e

echo "🚀 HYBRID OUTLET DATA AGGREGATION - QUICK START"
echo "=============================================="
echo ""

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.9+"
    exit 1
fi

echo "✓ Python 3 found"
echo ""

# Create output directory
mkdir -p outlet_data_hybrid
echo "✓ Output directory ready: outlet_data_hybrid/"
echo ""

# Show menu
echo "Choose aggregation mode:"
echo ""
echo "1️⃣  OSM Only (Free, 50,000-80,000 outlets)"
echo "   - No data files needed"
echo "   - ~10 minutes"
echo ""
echo "2️⃣  PPAC + OSM (Recommended, 100,000+ outlets)"
echo "   - Requires PPAC CSV from ppac.gov.in"
echo "   - ~10 minutes"
echo ""
echo "3️⃣  Full Hybrid (All sources, best coverage)"
echo "   - Requires PPAC CSV + Google API key"
echo "   - ~1-2 hours"
echo ""
echo "4️⃣  Show Instructions (Get PPAC data)"
echo ""
echo "Select option (1-4): "
read -r option

case $option in
    1)
        echo ""
        echo "Running OSM-only aggregation..."
        python3 hybrid_aggregator.py
        ;;
    2)
        echo ""
        echo "PPAC CSV needed. Instructions:"
        echo "1. Go to: https://ppac.gov.in/"
        echo "2. Download: Reports & Analysis → Ready Reckoner → Retail Outlets"
        echo "3. Save to: ./ppac_retail_outlets.csv"
        echo ""
        read -p "Have you downloaded PPAC CSV to ./ppac_retail_outlets.csv? (y/n) " confirm
        if [ "$confirm" = "y" ]; then
            python3 -c "
from hybrid_aggregator import HybridOutletAggregator
agg = HybridOutletAggregator()
outlets = agg.aggregate(ppac_csv='ppac_retail_outlets.csv')
if outlets:
    agg.export_all_formats()
    agg.print_summary()
"
        else
            echo "Please download PPAC CSV first, then run this script again."
        fi
        ;;
    3)
        echo ""
        echo "Full Hybrid Aggregation"
        echo "====================="
        echo ""
        read -p "PPAC CSV path (or press Enter if not available): " ppac_csv
        read -p "Google API Key (or press Enter to skip): " google_key

        python3 -c "
from hybrid_aggregator import HybridOutletAggregator
agg = HybridOutletAggregator()
ppac_path = '$ppac_csv' if '$ppac_csv' else None
google_api = '$google_key' if '$google_key' else None
outlets = agg.aggregate(ppac_csv=ppac_path, google_api_key=google_api)
if outlets:
    agg.export_all_formats()
    agg.print_summary()
"
        ;;
    4)
        echo ""
        cat << 'EOF'
📋 HOW TO GET PPAC DATA
======================

PPAC (Petroleum Planning & Analysis Cell) provides official outlet database.

Step 1: Visit Website
  → https://ppac.gov.in/

Step 2: Navigate to Reports
  → Click: Reports & Analysis
  → Look for: Ready Reckoner section

Step 3: Download Dataset
  → Click: Retail Outlets (Excel format)
  → This downloads all outlets by state and company
  → Expected: 95,000-105,000 outlets

Step 4: Convert to CSV (if needed)
  → Open Excel file
  → File → Save As → CSV format
  → Save as: ppac_retail_outlets.csv

Step 5: Place File
  → Move ppac_retail_outlets.csv to current directory
  → Or provide full path when running aggregation

Expected File Structure:
  outlet_name, company, state, city, latitude, longitude, address
  IOC-001, IOCL, Maharashtra, Mumbai, 19.0760, 72.8777, ...
  ...

For Questions:
  Email: ppac-mopng@nic.in
  Phone: +91-11-26740551
EOF
        ;;
    *)
        echo "Invalid option. Please run script again."
        exit 1
        ;;
esac

echo ""
echo "=============================================="
echo "Next steps:"
echo "1. Check output in: outlet_data_hybrid/"
echo "2. Review statistics in: *_stats.json"
echo "3. Test in maps: python3 -m http.server 8000"
echo "4. Commit to GitHub"
echo ""
