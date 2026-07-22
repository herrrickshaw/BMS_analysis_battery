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
# US fundamentals from SEC EDGAR companyfacts — official, dated, no alphabetical
# throttle. 1,500/session at 0.25s covers the ~7k universe in ~5 sessions
# (9 slots/week), after which only >30d-stale names refetch. Same store shape
# as IN_current so every India-store consumer reads it unchanged.
"$PY" us_fundamentals_edgar.py --limit 1500 --rate 0.25 || echo "US EDGAR collection failed (continuing)"
# Rebuild the India+US ratio table (PE/PB/ROE/ROCE/D-E/margins/FCF yield) from
# whatever the stores now hold + latest closes. /usr/bin/python3, NOT the venv —
# duckdb lives there (the same split documented in daily_pipeline step 15).
/usr/bin/python3 financial_ratios.py || echo "ratio rebuild failed (continuing)"
exit $RC
