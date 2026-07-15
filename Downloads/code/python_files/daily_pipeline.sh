#!/bin/bash
# daily_pipeline.sh — full token-free Daily Market Brief.
# Runs entirely in local Python (no Claude / no LLM tokens) and emails the brief.
#
# Covers 5 markets end-to-end every weekday morning: India (NSE/BSE), US
# (NASDAQ/NYSE), Europe (17 exchanges / broad 966-stock universe), Japan
# (TSE), and Korea (KOSPI+KOSDAQ) — full fresh scans for all five, plus a
# 5-market correlation/cluster scan (NSE, US, Europe, Japan, Korea). Each
# market's steps are independently guarded with `|| echo ... failed
# (continuing)` so one market's failure (rate limit, network hiccup, etc.)
# never blocks the rest of the pipeline or the final mailer build. Any
# failed step is collected and triggers a short alert email (see
# send_alert.py) once the run finishes, separate from the main brief.
#
# Estimated runtime: ~3-5+ hours (was ~90 min for India alone before this
# update) — scheduled well before market open accordingly, see
# com.umashankar.dailybrief.plist (00:30 IST weekdays).
#
# Schedule it with cron or launchd (see com.umashankar.dailybrief.plist). Set
# credentials in the environment first (GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO).
#
#   ./daily_pipeline.sh            # refresh + screen (5 markets) + send
#   ./daily_pipeline.sh --draft    # refresh + screen (5 markets) + save brief_today.html
set -uo pipefail
cd "$(dirname "$0")"
PY=python3
LOG="daily_pipeline_$(date +%Y%m%d).log"
mkdir -p correlation_scan
FAILURES=()
{
  echo "=== Daily pipeline $(date) ==="

  # [0] Dependency check — FIRST, and loud.
  #
  # Every step below is guarded with `|| echo "... failed (continuing)"` so one
  # market can't sink the run. The cost of that resilience is that a missing
  # dependency looks exactly like a bad network day: one line in the log, pipeline
  # moves on, market silently goes stale for days. On 2026-07-15 four deps were
  # missing this way (networkx -> all 5 correlation scans dead; lmdb -> store never
  # written; duckdb; pykrx -> Korea aborted and produced NO output, and was not even
  # declared in requirements.txt).
  #
  # Deliberately does NOT abort: a missing networkx shouldn't stop India from
  # scanning. It prints a banner and registers a FAILURE so the alert email fires —
  # loud and attributable, without throwing away the steps that would still work.
  echo "[0/14] dependency check"
  $PY check_deps.py || FAILURES+=("STARTUP: missing required dependencies (see banner above)")

  echo "[1/14] India EOD refresh (official bhavcopy, incremental)"
  $PY bhavcopy_history.py 400 || { echo "  bhavcopy refresh failed (will use cache)"; FAILURES+=("India: bhavcopy refresh"); }

  echo "[2/14] India full screener scan"
  $PY scan_bhavcopy.py || { echo "  scan failed (will use latest cache)"; FAILURES+=("India: full screener scan"); }

  echo "[3/14] India combined report (fundamentals + street talk)"
  $PY daily_combined_report.py --market IN --html || { echo "  combined report failed"; FAILURES+=("India: combined report"); }

  echo "[3b] refresh India CCC screen (screener.in)"
  $PY -c "import screener_in as s; s.ccc_screen().to_parquet('cache_seed/india_ccc_screen.parquet', index=False)" || { echo "  CCC refresh skipped"; FAILURES+=("India: CCC screen refresh"); }

  echo "[3c] daily test: validate screener.in CCC scrape"
  $PY test_screener_in.py || { echo "  ⚠️  screener.in CCC test FAILED — see checks above. CCC section will show n/a until this is fixed."; FAILURES+=("India: CCC scrape test"); }

  echo "[4/14] US full market scan (fresh, NASDAQ+NYSE, min-price \$2)"
  $PY full_us_market_scan.py --workers 10 --min-price 2 || { echo "  US full market scan failed (continuing)"; FAILURES+=("US: full market scan"); }

  echo "[5/14] US combined report (fundamentals + street talk, reuses fresh US scan)"
  $PY daily_combined_report.py --market US --html || { echo "  US combined report failed (continuing)"; FAILURES+=("US: combined report"); }

  echo "[6/14] Europe full market scan (broad 17-exchange / 966-stock universe)"
  $PY full_european_market_scan.py --universe data/europe_broad_list.csv --label broad || { echo "  Europe full market scan failed (continuing)"; FAILURES+=("Europe: full market scan"); }

  echo "[7/14] Japan full market scan (TSE)"
  $PY full_japan_market_scan.py --workers 10 || { echo "  Japan full market scan failed (continuing)"; FAILURES+=("Japan: full market scan"); }

  echo "[8/14] Korea full market scan (KOSPI+KOSDAQ)"
  $PY full_korea_market_scan.py --workers 10 || { echo "  Korea full market scan failed (continuing)"; FAILURES+=("Korea: full market scan"); }

  echo "[9/14] Correlation scan — NSE"
  $PY market_correlation_scan.py --market NSE --output-dir correlation_scan || { echo "  NSE correlation scan failed (continuing)"; FAILURES+=("NSE: correlation scan"); }

  echo "[10/14] Correlation scan — US"
  $PY market_correlation_scan.py --market US --output-dir correlation_scan || { echo "  US correlation scan failed (continuing)"; FAILURES+=("US: correlation scan"); }

  echo "[11/14] Correlation scan — Europe"
  $PY market_correlation_scan.py --market EUROPE --output-dir correlation_scan || { echo "  Europe correlation scan failed (continuing)"; FAILURES+=("Europe: correlation scan"); }

  echo "[12/14] Correlation scan — Japan"
  $PY market_correlation_scan.py --market JAPAN --output-dir correlation_scan || { echo "  Japan correlation scan failed (continuing)"; FAILURES+=("Japan: correlation scan"); }

  echo "[13/14] Correlation scan — Korea"
  $PY market_correlation_scan.py --market KOREA --output-dir correlation_scan || { echo "  Korea correlation scan failed (continuing)"; FAILURES+=("Korea: correlation scan"); }

  echo "[14/14] build + send mailer"
  $PY send_mailer.py "$@" || { echo "  mailer build/send failed"; FAILURES+=("mailer: build/send"); }

  if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo "[ALERT] ${#FAILURES[@]} step(s) failed: ${FAILURES[*]}"
    $PY send_alert.py "${FAILURES[@]}" || echo "  alert email itself failed to send"
  fi

  echo "=== done $(date) ==="
} >> "$LOG" 2>&1
echo "pipeline complete — see $LOG"
