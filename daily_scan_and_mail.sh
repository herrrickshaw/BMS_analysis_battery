#!/bin/bash
# Daily Scan and Mail Pipeline
# ============================================================================
# Runs all market scans, then generates and sends daily report
# Schedule: 08:00 AM (30 min before 08:30 email send)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$HOME/Downloads/BMS_analysis_battery"
LOG_DIR="$HOME/.screener"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/daily_scan_${TIMESTAMP}.log"

mkdir -p "$LOG_DIR"

echo "=========================================="
echo "Daily Scan & Mail Pipeline"
echo "=========================================="
echo "Started: $(date)"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1: Run Daily Scanners
# ─────────────────────────────────────────────────────────────────────────────

echo "[1/3] Running daily market scan..."

# 1. Run Darvas Box scan (all markets)
if [ -f "$REPO_ROOT/scanners/daily_scanner.py" ]; then
    echo "  → Darvas Box scan..."
    cd "$REPO_ROOT"
    python3 scanners/daily_scanner.py --scanner darvas --all-markets 2>&1 | tail -5 || echo "  [WARN] Darvas scan skipped"
fi

# 2. Run Piotroski scan (all markets)
if [ -f "$REPO_ROOT/scanners/daily_scanner.py" ]; then
    echo "  → Piotroski quality scan..."
    cd "$REPO_ROOT"
    python3 scanners/daily_scanner.py --scanner piotroski --all-markets 2>&1 | tail -5 || echo "  [WARN] Piotroski scan skipped"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2: German Market Analysis
# ─────────────────────────────────────────────────────────────────────────────

echo "[2/3] Running German market analysis..."

if [ -d "$REPO_ROOT/german_market" ]; then
    cd "$REPO_ROOT"

    # Run momentum and breakout scan
    if [ -f "german_market/momentum_breakout_scan.py" ]; then
        echo "  → German momentum & breakout scan..."
        python3 german_market/momentum_breakout_scan.py 2>&1 | tail -5 || echo "  [WARN] German scan skipped"
    fi

    # Run CCC analysis
    if [ -f "german_market/cash_conversion_cycle_analysis.py" ]; then
        echo "  → Cash Conversion Cycle analysis..."
        python3 german_market/cash_conversion_cycle_analysis.py 2>&1 | tail -5 || echo "  [WARN] CCC analysis skipped"
    fi
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3: Generate and Send Daily Report
# ─────────────────────────────────────────────────────────────────────────────

echo "[3/3] Generating and sending daily report..."

# Ensure mailer script exists
if [ ! -f "$SCRIPT_DIR/daily_mailer.py" ]; then
    echo "✗ daily_mailer.py not found at $SCRIPT_DIR"
    exit 1
fi

# Run the mailer with --send flag
python3 "$SCRIPT_DIR/daily_mailer.py" --send 2>&1 | tail -10

echo ""
echo "=========================================="
echo "✓ Daily Pipeline Complete"
echo "=========================================="
echo "Finished: $(date)"
echo ""
echo "Logs: $LOG_FILE"
tail -20 "$LOG_FILE" > /dev/null 2>&1 || true
