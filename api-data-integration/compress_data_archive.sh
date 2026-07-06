#!/bin/bash

# Data compression and archival script
# Compresses large datasets to save storage space while maintaining accessibility

set -e

echo "================================================================================"
echo "📦 DATA COMPRESSION & ARCHIVAL STRATEGY"
echo "================================================================================"

ARCHIVE_DIR="data_archives"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MANIFEST="data_compression_manifest_${TIMESTAMP}.txt"

mkdir -p "$ARCHIVE_DIR"

echo ""
echo "📊 CURRENT SPACE USAGE:"
du -sh . | head -1
echo ""

# Function to compress and track files
compress_file() {
    local file=$1
    local desc=$2

    if [ -f "$file" ]; then
        local size_before=$(du -sh "$file" | awk '{print $1}')
        echo "Compressing: $desc ($size_before)"

        gzip -9 -k "$file" 2>/dev/null || true

        if [ -f "${file}.gz" ]; then
            local size_after=$(du -sh "${file}.gz" | awk '{print $1}')
            local ratio=$(echo "scale=1; $(stat -f%z "${file}.gz") * 100 / $(stat -f%z "$file")" | bc 2>/dev/null || echo "N/A")
            echo "   ✓ $size_before → $size_after ($ratio%)"
            echo "$file.gz ($size_after, $ratio%)" >> "$MANIFEST"
        fi
    fi
}

# Archive large datasets
echo ""
echo "🗜️  COMPRESSING LARGE DATASETS:"
echo "================================"

# SSRI outlets
compress_file "outlet_data_ssri_107k/ssri_complete_pumps_20260624_084618.csv" \
    "SSRI Petrol Pumps (104,961 outlets)"

# Excel files
compress_file "ALL_OUTLETS_COMPREHENSIVE_20260625_023546.xlsx" \
    "All Outlets Comprehensive (12 sheets)"

compress_file "MASTER_OUTLETS_COLDCHAIN_INTEGRATED_20260702_222758.xlsx" \
    "Master Integrated Outlets + Cold Chains"

compress_file "api-data-integration/SSRI_vs_PPAC_Comparison_Report.xlsx" \
    "SSRI vs PPAC Comparison"

# CSV exports
find . -maxdepth 2 -name "*.csv" -type f 2>/dev/null | while read csv; do
    compress_file "$csv" "Dataset: $(basename $csv)"
done

echo ""
echo "📦 CREATING TAR ARCHIVES:"
echo "========================="

# Archive 1: Outlet Data
if [ -d "outlet_data_ssri_107k" ]; then
    echo "Archiving outlet data..."
    tar -czf "$ARCHIVE_DIR/outlet_data_ssri_107k_${TIMESTAMP}.tar.gz" outlet_data_ssri_107k/ 2>/dev/null
    size=$(du -sh "$ARCHIVE_DIR/outlet_data_ssri_107k_${TIMESTAMP}.tar.gz" | awk '{print $1}')
    echo "   ✓ outlet_data_ssri_107k ($size)"
fi

# Archive 2: API Integration Data
if [ -d "api-data-integration" ]; then
    echo "Archiving API integration data..."
    tar -czf "$ARCHIVE_DIR/api_data_integration_${TIMESTAMP}.tar.gz" \
        api-data-integration/*.xlsx \
        api-data-integration/*.csv 2>/dev/null || true
    size=$(du -sh "$ARCHIVE_DIR/api_data_integration_${TIMESTAMP}.tar.gz" | awk '{print $1}')
    echo "   ✓ api_data_integration ($size)"
fi

# Archive 3: Market Data
if [ -d "market-data-artifacts" ]; then
    echo "Archiving market data artifacts..."
    tar -czf "$ARCHIVE_DIR/market_data_artifacts_${TIMESTAMP}.tar.gz" \
        market-data-artifacts/ 2>/dev/null || true
    size=$(du -sh "$ARCHIVE_DIR/market_data_artifacts_${TIMESTAMP}.tar.gz" | awk '{print $1}')
    echo "   ✓ market-data-artifacts ($size)"
fi

# Archive 4: BPCL Data
if [ -d "outlet_data_bpcl_complete" ]; then
    echo "Archiving BPCL data..."
    tar -czf "$ARCHIVE_DIR/bpcl_outlets_${TIMESTAMP}.tar.gz" \
        outlet_data_bpcl_complete/ 2>/dev/null || true
    size=$(du -sh "$ARCHIVE_DIR/bpcl_outlets_${TIMESTAMP}.tar.gz" | awk '{print $1}')
    echo "   ✓ outlet_data_bpcl_complete ($size)"
fi

echo ""
echo "🗑️  CLEANING UP REDUNDANT FILES:"
echo "==============================="

# Remove original files if compressed versions exist
echo "Checking for compression success..."

for file in outlet_data_ssri_107k/*.csv; do
    if [ -f "${file}.gz" ]; then
        echo "   ✓ Keeping ${file}.gz, original: $file"
    fi
done

echo ""
echo "📊 SPACE ANALYSIS:"
echo "=================="

echo ""
echo "Archive Directory Contents:"
du -sh "$ARCHIVE_DIR"/* 2>/dev/null | sort -rh

echo ""
echo "📈 COMPRESSION SUMMARY:"
find "$ARCHIVE_DIR" -name "*.tar.gz" -o -name "*.gz" | while read f; do
    orig_size=$(tar -tzf "$f" 2>/dev/null | wc -l)
    arch_size=$(du -sh "$f" | awk '{print $1}')
    echo "   $f: $arch_size"
done

echo ""
echo "✅ ARCHIVAL COMPLETE!"
echo "================================================================================"
echo ""
echo "📋 MANIFEST:"
cat "$MANIFEST" 2>/dev/null || echo "   (No manifest created)"

echo ""
echo "💡 NEXT STEPS:"
echo "   1. Verify archives with: tar -tzf filename.tar.gz"
echo "   2. Delete original files if archives confirmed OK"
echo "   3. Push compressed files to GitHub"
echo "   4. Add .gz files to .gitignore if very large"
echo ""
echo "================================================================================"
