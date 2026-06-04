#!/usr/bin/env bash
# =============================================================
#  run_pegu_sarvas.sh
#  Full pipeline: extract stock data → score with Pegu → Sarvas scan
# =============================================================
#
#  Usage:
#    ./run_pegu_sarvas.sh                      # NIFTY500 (NSE) + BSE-500
#    ./run_pegu_sarvas.sh nifty50              # NIFTY50 only (quick test)
#    ./run_pegu_sarvas.sh all                  # ALL NSE + BSE equities (slow)
#    ./run_pegu_sarvas.sh nse_only NIFTY200    # NSE NIFTY200 only
#
#  Environment variables (override defaults):
#    EXCHANGE     NSE | BSE | BOTH   (default: BOTH)
#    INDEX        NIFTY50 | NIFTY200 | NIFTY500 | ALL  (default: NIFTY500)
#    MAX_SYMBOLS  integer cap for quick runs  (default: none)
#    BATCH_SIZE   symbols per batch  (default: 50)
#    DELAY        seconds between API calls  (default: 0.5)
#    DATA_DIR     output data directory  (default: data)
#    REPORT_DIR   R output directory  (default: reports)
#    TOP_N        top picks count  (default: 50)
# =============================================================

set -euo pipefail

# ── defaults ─────────────────────────────────────────────────
EXCHANGE="${EXCHANGE:-BOTH}"
INDEX="${INDEX:-NIFTY500}"
MAX_SYMBOLS="${MAX_SYMBOLS:-}"
BATCH_SIZE="${BATCH_SIZE:-50}"
DELAY="${DELAY:-0.5}"
DATA_DIR="${DATA_DIR:-data}"
REPORT_DIR="${REPORT_DIR:-reports}"
TOP_N="${TOP_N:-50}"

# ── parse positional shortcuts ────────────────────────────────
if [[ "${1:-}" == "nifty50" ]]; then
  INDEX="NIFTY50";  EXCHANGE="NSE"
elif [[ "${1:-}" == "nifty200" ]]; then
  INDEX="NIFTY200"; EXCHANGE="NSE"
elif [[ "${1:-}" == "all" ]]; then
  INDEX="ALL";      EXCHANGE="BOTH"
elif [[ "${1:-}" == "nse_only" ]]; then
  EXCHANGE="NSE";   INDEX="${2:-NIFTY500}"
elif [[ "${1:-}" == "bse_only" ]]; then
  EXCHANGE="BSE"
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs"
mkdir -p "$LOG_DIR" "$DATA_DIR" "$REPORT_DIR"

echo "============================================================="
echo "  Pegu Score & Sarvas Scan Pipeline  —  $TIMESTAMP"
echo "  Exchange : $EXCHANGE"
echo "  Index    : $INDEX"
echo "  Data dir : $DATA_DIR"
echo "  Reports  : $REPORT_DIR"
echo "============================================================="
echo ""

# ── Step 1: Python extractor ──────────────────────────────────
echo "[1/2] Extracting stock data from NSE/BSE..."

PY_ARGS=(
  --exchange   "$EXCHANGE"
  --index      "$INDEX"
  --output-dir "$DATA_DIR"
  --batch-size "$BATCH_SIZE"
  --delay      "$DELAY"
)
[[ -n "$MAX_SYMBOLS" ]] && PY_ARGS+=(--max-symbols "$MAX_SYMBOLS")

python3 nse_bse_extractor.py "${PY_ARGS[@]}" \
  2>&1 | tee "$LOG_DIR/extractor_${TIMESTAMP}.log"

if [[ $? -ne 0 ]]; then
  echo "[ERROR] Python extractor failed. Check $LOG_DIR/extractor_${TIMESTAMP}.log"
  exit 1
fi

# Check output
if [[ ! -f "$DATA_DIR/all_stocks_combined.csv" ]]; then
  # Accept per-exchange files as fallback
  if [[ ! -f "$DATA_DIR/nse_stocks_fundamental.csv" && \
        ! -f "$DATA_DIR/bse_stocks_fundamental.csv" ]]; then
    echo "[ERROR] No CSV data files found in $DATA_DIR/"
    exit 1
  fi
fi
echo "[1/2] Data extraction complete."
echo ""

# ── Step 2: R analysis ────────────────────────────────────────
echo "[2/2] Running Pegu scoring & Sarvas scan in R..."

# Check R packages
Rscript - <<'RCHECK'
pkgs <- c("dplyr", "ggplot2", "tidyr", "readr", "scales")
missing <- pkgs[!sapply(pkgs, requireNamespace, quietly = TRUE)]
if (length(missing) > 0) {
  cat("[INFO] Installing missing R packages:", paste(missing, collapse=", "), "\n")
  install.packages(missing, repos = "https://cloud.r-project.org", quiet = TRUE)
}
cat("[INFO] R package check OK\n")
RCHECK

Rscript pegu_sarvas_analysis.R \
  --data-dir "$DATA_DIR" \
  --out-dir  "$REPORT_DIR" \
  --top-n    "$TOP_N" \
  2>&1 | tee "$LOG_DIR/pegu_sarvas_${TIMESTAMP}.log"

if [[ $? -ne 0 ]]; then
  echo "[ERROR] R analysis failed. Check $LOG_DIR/pegu_sarvas_${TIMESTAMP}.log"
  exit 1
fi
echo "[2/2] R analysis complete."
echo ""

# ── Summary ───────────────────────────────────────────────────
echo "============================================================="
echo "  Pipeline completed — $TIMESTAMP"
echo "============================================================="
echo ""
echo "  Data files:"
ls -lh "$DATA_DIR"/*.csv 2>/dev/null | awk '{print "    "$NF, $5}' || true
echo ""
echo "  Report files:"
ls -lh "$REPORT_DIR"/*.csv 2>/dev/null | awk '{print "    "$NF, $5}' || true
echo ""
echo "  Plots:"
ls -lh "$REPORT_DIR"/*.png 2>/dev/null | awk '{print "    "$NF, $5}' || true
echo ""

# Quick peek at top picks
if [[ -f "$REPORT_DIR/top_pegu_picks.csv" ]]; then
  echo "  Top 5 by Pegu score:"
  python3 - <<PYPRINT
import pandas as pd, sys
try:
    df = pd.read_csv("$REPORT_DIR/top_pegu_picks.csv")
    cols = [c for c in ["symbol","exchange","company_name","pegu_score","pegu_grade","sarvas_signal"]
            if c in df.columns]
    print(df[cols].head(5).to_string(index=False))
except Exception as e:
    print("  (preview unavailable:", e, ")")
PYPRINT
fi
echo ""
echo "  Done. Full results: $REPORT_DIR/"
