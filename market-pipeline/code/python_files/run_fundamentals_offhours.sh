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
"$PY" fundamentals_offhours.py --rate 1.0 "$@"
RC=$?
# NSE XBRL point-in-time trickle: ~110k filings total; ~2,000 files per session
# (~30 min) means the full 10-year history lands in ~8 weeks of off-hours runs,
# hash-ordered so the panel is representative at every stage. Refreshes the
# index weekly-ish (2 quarters), then files, then parse.
"$PY" nse_xbrl_results.py --index --quarters 2
"$PY" nse_xbrl_results.py --files --limit 2000
"$PY" nse_xbrl_results.py --parse
exit $RC
