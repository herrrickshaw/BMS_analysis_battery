#!/bin/bash
# run_fundamentals_offhours.sh — off-hours India fundamentals collection.
# Resolves its own venv (never inherits `python3` from the caller's PATH — that
# split is what made the pipeline behave differently under launchd than in a
# shell on 2026-07-21).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
export MARKET_CACHE="/Users/umashankar/market-pipeline/market_cache"
export BHAV_CACHE="/Users/umashankar/market-pipeline/data/bhavcopy_cache"
PY="$HERE/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
echo "=== fundamentals off-hours $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
# rate 1.0s is polite; the run skips names collected in the last 30 days, so a
# daily invocation only fetches what is stale and completes in minutes.
exec "$PY" fundamentals_offhours.py --rate 1.0 "$@"
