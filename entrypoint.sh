#!/bin/bash
# entrypoint.sh — Docker entry point for Stock Analysis System v1.0.0
# =====================================================================
# Usage: docker run stockscan:1.0.0 <command> [options]
#
# Commands:
#   scan        — Full scan: Indian + US universe, all 6 screeners + ML signal
#   ipo         — IPO tracker: discover new listings, run applicable screeners
#   backtest    — 1-year walk-forward backtest (--market IN|US|BOTH)
#   walkforward — 3y/5y/10y train/test/val research framework
#   monitor     — Intraday monitoring daemon (--interval 15|30 minutes)
#   cache-init  — Download and warm the 5-year OHLC cache
#   help        — Show this help

set -euo pipefail

VERSION=$(cat /app/VERSION 2>/dev/null || echo "unknown")
SCRIPTS=/app/scripts
OUTPUT=${OUTPUT_DIR:-/app/output}
CACHE=${CACHE_DIR:-/app/cache}
WORKERS=${WORKERS:-8}
MARKET=${MARKET:-BOTH}

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Override cache directory to use the Docker volume
export CACHE_ROOT="$CACHE"

log "Stock Analysis System v${VERSION}"
log "Command: $*"
log "Output:  $OUTPUT"
log "Cache:   $CACHE"
log "Workers: $WORKERS"

case "${1:-help}" in

  # ── Full scan ────────────────────────────────────────────────────────────────
  scan)
    shift
    log "=== FULL MARKET SCAN ==="

    log "Step 1: IPO Tracker (new listings)"
    python3 "$SCRIPTS/ipo_tracker.py" --days 90 --workers "$WORKERS" || log "IPO tracker failed (non-fatal)"

    if [[ "$MARKET" == "IN" || "$MARKET" == "BOTH" ]]; then
      log "Step 2: Full Indian Market Scan (NSE+BSE)"
      python3 "$SCRIPTS/full_indian_market_scan.py" --workers "$WORKERS" "$@" \
        2>&1 | tee "$OUTPUT/scan_indian_$(date +%Y%m%d).log"
    fi

    if [[ "$MARKET" == "US" || "$MARKET" == "BOTH" ]]; then
      log "Step 3: Full US Market Scan (NASDAQ+NYSE)"
      python3 "$SCRIPTS/full_us_market_scan.py" --min-price 2 --workers "$WORKERS" "$@" \
        2>&1 | tee "$OUTPUT/scan_us_$(date +%Y%m%d).log"
    fi

    log "=== SCAN COMPLETE ==="
    ;;

  # ── Backtest ─────────────────────────────────────────────────────────────────
  backtest)
    shift
    MARKET_ARG="${MARKET_ARG:-$MARKET}"
    log "=== BACKTEST ==="
    python3 "$SCRIPTS/backtest_screeners.py" --market "${MARKET_ARG:-IN}" \
      --workers "$WORKERS" "$@" \
      2>&1 | tee "$OUTPUT/backtest_$(date +%Y%m%d).log"
    ;;

  # ── Walk-forward research ─────────────────────────────────────────────────────
  walkforward)
    shift
    log "=== WALK-FORWARD BACKTEST (3y/5y/10y) ==="
    python3 "$SCRIPTS/walk_forward_backtest.py" --liquid --workers "$WORKERS" "$@" \
      2>&1 | tee "$OUTPUT/walkforward_$(date +%Y%m%d).log"
    ;;

  # ── IPO tracker ───────────────────────────────────────────────────────────────
  ipo)
    shift
    log "=== IPO TRACKER ==="
    python3 "$SCRIPTS/ipo_tracker.py" --workers "$WORKERS" "$@" \
      2>&1 | tee "$OUTPUT/ipo_$(date +%Y%m%d).log"
    ;;

  # ── Intraday monitor ──────────────────────────────────────────────────────────
  monitor)
    shift
    INTERVAL="${1:-15}"
    shift || true
    log "=== INTRADAY MONITOR (${INTERVAL}-min bars) ==="
    log "Market hours: 09:15–15:30 IST (NSE) / 09:30–16:00 ET (US)"
    python3 "$SCRIPTS/intraday_monitor.py" --interval "$INTERVAL" \
      --workers "$WORKERS" "$@" \
      2>&1 | tee -a "$OUTPUT/intraday_$(date +%Y%m%d).log"
    ;;

  # ── Cache warm-up ─────────────────────────────────────────────────────────────
  cache-init)
    shift
    log "=== CACHE INITIALISATION (5-year OHLC for full NSE universe) ==="
    log "Estimated time: ~12 minutes (cold), <60s (subsequent)"
    python3 - << 'PYEOF'
import warnings; warnings.filterwarnings("ignore")
import sys; sys.path.insert(0, "/app/scripts")
from market_data_cache import warm_cache, CACHE_ROOT
from pathlib import Path
import os

# Override cache location to Docker volume
os.environ["CACHE_ROOT"] = os.environ.get("CACHE_DIR", "/app/cache")

from nse_data_fetcher import NSEDataFetcher
nse    = NSEDataFetcher()
syms   = nse.get_all_symbols()
tickers = [f"{s}.NS" for s in syms]
print(f"Warming cache for {len(tickers)} NSE EQ stocks (5-year OHLC)...")
warm_cache(tickers, period_years=5)
PYEOF
    ;;

  # ── Quick screener (screener.in pre-filter) ───────────────────────────────────
  screener)
    shift
    log "=== SCREENER ANALYSIS (markitdown pre-filter) ==="
    python3 "$SCRIPTS/screener_analysis.py" --workers "$WORKERS" "$@" \
      2>&1 | tee "$OUTPUT/screener_$(date +%Y%m%d).log"
    ;;

  # ── Live market context ───────────────────────────────────────────────────────
  live)
    log "=== LIVE MARKET CONTEXT ==="
    python3 - << 'PYEOF'
import warnings; warnings.filterwarnings("ignore")
import sys; sys.path.insert(0, "/app/scripts")
from nse_data_fetcher import NSEDataFetcher
NSEDataFetcher().print_live_context()
PYEOF
    ;;

  # ── Interactive shell ─────────────────────────────────────────────────────────
  shell)
    log "Launching interactive Python shell with all modules imported..."
    python3 - << 'PYEOF'
import sys; sys.path.insert(0, "/app/scripts")
print("Stock Analysis System — Interactive Mode")
print("Available: market_data_cache, nse_data_fetcher, ml_signal_engine,")
print("           screener_analysis, backtest_screeners, ipo_tracker")
import code; code.interact(local=locals())
PYEOF
    ;;

  # ── Help ──────────────────────────────────────────────────────────────────────
  help|--help|-h)
    cat << 'HELP'
Stock Analysis System v${VERSION}
==================================

COMMANDS:
  scan          Full scan: all 6 screeners on NSE+BSE+NASDAQ+NYSE
  ipo           IPO tracker: new listings + graduated screeners
  backtest      1-year walk-forward backtest
  walkforward   3y/5y/10y train/test/val research
  screener      Fast screener.in pre-filtered scan
  monitor       Intraday 15/30-min monitoring daemon
  cache-init    Download and warm the 5-year OHLC Parquet cache
  live          Print live market context (regime, VIX, FII/DII)
  shell         Interactive Python shell

ENVIRONMENT VARIABLES:
  MARKET        IN | US | BOTH (default: BOTH)
  WORKERS       parallel threads (default: 8)
  OUTPUT_DIR    output directory (default: /app/output)
  CACHE_DIR     Parquet cache directory (default: /app/cache)

EXAMPLES:
  docker run --rm -v $(pwd)/out:/app/output stockscan:1.0.0 scan
  docker run --rm -v $(pwd)/out:/app/output stockscan:1.0.0 ipo --days 30
  docker run --rm -v $(pwd)/out:/app/output stockscan:1.0.0 backtest --market US
  docker run -d  -v $(pwd)/out:/app/output stockscan:1.0.0 monitor 15
  docker run -it --rm stockscan:1.0.0 shell

VOLUMES (mount for persistence):
  /app/output   scan results, Excel reports, logs
  /app/cache    5-year OHLC Parquet cache (persists across container restarts)

HELP
    ;;

  *)
    log "Unknown command: $1. Run 'help' for usage."
    exit 1
    ;;

esac
