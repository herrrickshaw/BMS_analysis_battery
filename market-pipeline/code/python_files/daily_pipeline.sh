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
# Resolve our own venv — never inherit `python3` from the caller's PATH. A
# manual run from a plain shell resolved python3 to homebrew 3.14 on
# 2026-07-22 19:00: step [0] flagged missing deps, every scan died, and the
# validation gate suppressed the send. Same split documented in
# run_fundamentals_offhours.sh; launchd was never affected (plist sets PATH).
PY="$(dirname "$0")/.venv/bin/python3"
[ -x "$PY" ] || PY=python3
LOG="daily_pipeline_$(date +%Y%m%d).log"
mkdir -p correlation_scan
# ── step timing ───────────────────────────────────────────────────────────────
# Emits a machine-readable marker before every step so run times are MEASURED, not
# reconstructed. Until now the only evidence of what a step cost was artifact
# mtimes, hand-diffed after the fact — which is how Korea sat at 28 min unnoticed
# while Europe took 3. Parsed by scan_timings.py:
#   [STEP] <epoch> <ISO8601> <label>
# The trailing __end__ marker closes the final step so its duration is knowable.
step() {
  printf '[STEP] %s %s %s\n' "$(date +%s)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
  echo "$*"
}

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
  step "[0/14] dependency check"
  $PY check_deps.py || FAILURES+=("STARTUP: missing required dependencies (see banner above)")

  step "[1/14] India EOD refresh (official bhavcopy, incremental)"
  $PY bhavcopy_history.py 400 || { echo "  bhavcopy refresh failed (will use cache)"; FAILURES+=("India: bhavcopy refresh"); }

  step "[2/14] India full screener scan"
  $PY scan_bhavcopy.py || { echo "  scan failed (will use latest cache)"; FAILURES+=("India: full screener scan"); }

  step "[3/14] India combined report (fundamentals + street talk)"
  $PY daily_combined_report.py --market IN --html || { echo "  combined report failed"; FAILURES+=("India: combined report"); }

  step "[3b] refresh India CCC screen (screener.in)"
  $PY -c "import screener_in as s; s.ccc_screen().to_parquet('cache_seed/india_ccc_screen.parquet', index=False)" || { echo "  CCC refresh skipped"; FAILURES+=("India: CCC screen refresh"); }

  step "[3c] daily test: validate screener.in CCC scrape"
  $PY test_screener_in.py || { echo "  ⚠️  screener.in CCC test FAILED — see checks above. CCC section will show n/a until this is fixed."; FAILURES+=("India: CCC scrape test"); }

  step "[4/14] US full market scan (fresh, NASDAQ+NYSE, min-price \$2)"
  $PY full_us_market_scan.py --workers 10 --min-price 2 || { echo "  US full market scan failed (continuing)"; FAILURES+=("US: full market scan"); }

  step "[5/14] US combined report (fundamentals + street talk, reuses fresh US scan)"
  $PY daily_combined_report.py --market US --html || { echo "  US combined report failed (continuing)"; FAILURES+=("US: combined report"); }

  step "[6/14] Europe full market scan (broad 17-exchange / 966-stock universe)"
  $PY full_european_market_scan.py --universe data/europe_broad_list.csv --label broad || { echo "  Europe full market scan failed (continuing)"; FAILURES+=("Europe: full market scan"); }

  step "[7/14] Japan full market scan (TSE)"
  $PY full_japan_market_scan.py --workers 10 || { echo "  Japan full market scan failed (continuing)"; FAILURES+=("Japan: full market scan"); }

  step "[8/14] Korea full market scan (KOSPI+KOSDAQ)"
  $PY full_korea_market_scan.py --workers 10 || { echo "  Korea full market scan failed (continuing)"; FAILURES+=("Korea: full market scan"); }

  step "[9/14] Correlation scan — NSE"
  $PY market_correlation_scan.py --market NSE --output-dir correlation_scan || { echo "  NSE correlation scan failed (continuing)"; FAILURES+=("NSE: correlation scan"); }

  step "[10/14] Correlation scan — US"
  $PY market_correlation_scan.py --market US --output-dir correlation_scan || { echo "  US correlation scan failed (continuing)"; FAILURES+=("US: correlation scan"); }

  step "[11/14] Correlation scan — Europe"
  $PY market_correlation_scan.py --market EUROPE --output-dir correlation_scan || { echo "  Europe correlation scan failed (continuing)"; FAILURES+=("Europe: correlation scan"); }

  step "[12/14] Correlation scan — Japan"
  $PY market_correlation_scan.py --market JAPAN --output-dir correlation_scan || { echo "  Japan correlation scan failed (continuing)"; FAILURES+=("Japan: correlation scan"); }

  step "[13/14] Correlation scan — Korea"
  $PY market_correlation_scan.py --market KOREA --output-dir correlation_scan || { echo "  Korea correlation scan failed (continuing)"; FAILURES+=("Korea: correlation scan"); }

  # [13b] External validation — the gate between "built" and "sent".
  #
  # The screeners emit RECOMMENDATIONS. Checking the brief against our own scan
  # only proves internal consistency; it cannot catch a scan that is confidently
  # wrong about the world. On 2026-07-15 every internal check passed while the
  # pipeline quoted MODISONLTD at 284.6/+3.6% from 2026-05-29 — SEVEN WEEKS stale —
  # and shipped it as a GOLDEN_CROSS pick. The brief, the scan, the parquet and the
  # warehouse all agreed with each other and were all wrong together. Only
  # screener.in disagreed.
  #
  # So: if the picks don't match a public source, DON'T SEND — fall back to
  # --draft, which still writes brief_today.html for a human to inspect. A missing
  # brief is a visible problem; a confidently wrong one that lands in your inbox
  # is not.
  # [13a] Cross-market consistency — a market can look healthy alone and be the
  # odd one out in comparison. Every anomaly found on 2026-07-15 (Japan/Korea's
  # 200-DMA computed from a 3-month window and 0% populated; Europe+Japan running
  # with NO liquidity gate when the FX fetch failed; India momentum-only) was
  # invisible in its own scan and obvious side by side. Non-fatal: it registers a
  # FAILURE so the alert fires, without blocking a brief that is mostly sound.
  # [13y] Watchlist repair — fixes data gaps at the ROOT before anything
  # renders: NSE renames applied (symbolchange.csv, chain-resolved), wrong
  # symbols corrected against the current EQUITY list, ETFs/delisted names
  # archived with reasons (EDGAR registry check for US). Cheap: two cached
  # downloads, refreshed weekly.
  step "[13y/14] watchlist repair (renames/delists/ETFs)"
  $PY watchlist_repair.py \
    || FAILURES+=("repair: watchlist renames/delists")

  # [13z] Value re-rating screen (India) — the combined signal the PE
  # backtests earned (2026-07-23): cheap vs own sector ∩ expanding 12M PE,
  # ₹1cr/day liquidity-gated at source, top-15 promoted to watchlist.csv as
  # `signal` rows BEFORE the mailer builds, so today's picks are in today's
  # email. Reads only local parquets (screener history + adjusted panel).
  step "[13z/14] value re-rating screen (India)"
  $PY screen_value_rerating.py \
    || FAILURES+=("screen: value re-rating (India)")

  # [13x] Paper-track scorecard — accumulates every past mailer pick (signal
  # ledger) and marks to today, so the mailer carries a running report card.
  # Weekly (Mondays) — the forward horizons only move meaningfully week to
  # week, and it reads the same panels the digest already loads.
  if [[ "$(date +%u)" == "1" ]]; then
    step "[13x/14] paper-track scorecard (weekly)"
    $PY paper_track.py > /dev/null 2>&1 \
      || FAILURES+=("scorecard: paper_track")
  fi

  step "[13a/14] cross-market consistency audit"
  $PY consistency_audit.py || FAILURES+=("consistency: cross-market anomaly (see audit above)")

  step "[13b/14] validate brief against screener.in"
  if $PY validate_brief.py --sample 6; then
      step "[14/14] build + send mailer"
      $PY send_mailer.py "$@" || { echo "  mailer build/send failed"; FAILURES+=("mailer: build/send"); }
  else
      echo "  ❌ external validation FAILED — sending SUPPRESSED, saving draft instead"
      FAILURES+=("mailer: NOT SENT — brief failed screener.in validation (see above)")
      $PY send_mailer.py --draft || { echo "  draft save failed"; FAILURES+=("mailer: draft save"); }
  fi

  # [15] Warehouse ingest + per-ticker freshness ledger — appends today's scan
  # snapshots (and India's bhavcopy high-water mark) to Postgres market_daily.*
  # and refreshes the ticker/name/market/last-update ledger. This went 8 days
  # stale in July 2026 because it lived outside the pipeline and silently kept
  # reading the abandoned ~/Downloads tree after the migration; running it here
  # ties it to the same schedule as the data it records. NB: /usr/bin/python3,
  # not $PY — duckdb lives there, not in the venv.
  step "[15/15] warehouse ingest + ticker freshness ledger"
  # Rebuild the raw 34-col archives (nse.parquet/bse.parquet) from today's
  # day-CSVs FIRST — bhavcopy_to_db.py reads them for pg.bhavcopy.nse_raw/
  # bse_raw. Their original builder was never committed and vanished with the
  # ~/Downloads tree, freezing the raw layer at 2026-07-13 while everything
  # else stayed current (found 2026-07-22).
  $PY bhavcopy_raw_archive.py \
    || FAILURES+=("ingest: raw bhavcopy archive refresh")
  /usr/bin/python3 /Users/umashankar/scripts/bhavcopy_to_db.py --incremental \
    || FAILURES+=("ingest: bhavcopy incremental")
  /usr/bin/python3 /Users/umashankar/scripts/bhavcopy_to_db.py --to-postgres "dbname=market_data host=/tmp user=umashankar" \
    || FAILURES+=("ingest: bhavcopy -> postgres")
  /usr/bin/python3 /Users/umashankar/scripts/market_ingest.py \
    || FAILURES+=("ingest: market snapshots")
  mkdir -p reports
  /usr/bin/python3 /Users/umashankar/scripts/market_ingest.py --csv "$PWD/reports/ticker_freshness.csv" \
    || FAILURES+=("ingest: ticker_freshness.csv export")
  # Financial ratios (India + US): recompute PE/PB/ROE/ROCE/margins against
  # TODAY's closes from the off-hours fundamentals stores. Collection happens in
  # run_fundamentals_offhours.sh (its own launchd job); this step only re-prices.
  /usr/bin/python3 financial_ratios.py \
    || FAILURES+=("ratios: financial_ratios rebuild")

  # [16] Cloud copy — rclone-sync the data trees (market_cache, bhavcopy_cache,
  # cache_seed, gmd cache_seed, warehouse duckdb) to Google Drive with dated
  # history, replacing GitHub LFS as the off-machine store (LFS budget is
  # exhausted account-wide and rewritten parquets each became a permanent
  # blob there). Changed/deleted files move to history/<date>/, never lost.
  # Riding this run keeps it inside the 00:10 wake window — a separate schedule
  # would fire while the Mac sleeps (the market_ingest lesson, again).
  step "[16/16] cloud backup (rclone -> Google Drive)"
  /Users/umashankar/scripts/cloud_backup.sh \
    || FAILURES+=("cloud: rclone backup (see cloud_backup.log)")

  # [16d] Monthly refresh of the per-market zone rules + PE anomaly stats
  # (backtests over 10y panels; slow-ish, monthly is plenty). Same marker
  # pattern. zone_rules.json feeds the digest's per-market Buy/Hold/Sell.
  ZR_MARK="$HOME/.local/state/zone_rules_last_build"
  if [[ "$(cat "$ZR_MARK" 2>/dev/null)" != "$(date +%Y-%m)" ]]; then
    step "[16d] monthly zone-rule + PE-anomaly backtests"
    $PY backtest_zone_rules.py > /dev/null 2>&1 \
      && $PY backtest_pe_anomalies.py > /dev/null 2>&1 \
      && { mkdir -p "$(dirname "$ZR_MARK")" && date +%Y-%m > "$ZR_MARK"; \
           echo "  zone rules + PE anomalies refreshed"; } \
      || FAILURES+=("backtest: zone rules / PE anomalies")
  fi

  # [16c] Monthly bundle validation vs public benchmarks (user, 2026-07-23).
  # Runs the first pipeline run of each month, AFTER the mailer step has done
  # the monthly bundle rebuild — validates the fresh bundles against SPDR
  # holdings + NSE constituent lists (network, so it lives HERE and never
  # inside the mailer path). Same exactly-once marker pattern as [16b].
  BV_MARK="$HOME/.local/state/bundle_validation_last_run"
  if [[ -f cache_seed/portfolio_bundles.json && "$(cat "$BV_MARK" 2>/dev/null)" != "$(date +%Y-%m)" ]]; then
    step "[16c] monthly bundle validation vs benchmarks"
    if $PY bundle_validation.py > /dev/null; then
      mkdir -p "$(dirname "$BV_MARK")" && date +%Y-%m > "$BV_MARK"
      echo "  bundle validation refreshed -> reports/bundle_validation.md"
    else
      FAILURES+=("validate: bundle benchmark comparison")
    fi
  fi

  # [16b] Monthly snapshot of the purged-watchlist archive to Dropbox (user,
  # 2026-07-23). Rides the pipeline instead of owning a monthly schedule: the
  # pmset 00:25 wake guarantees THIS job fires, while a standalone monthly
  # cron on a sleeping Mac is silently skipped and runs a month late. The
  # marker file makes it exactly-once per calendar month — the first pipeline
  # run of a new month uploads the cumulative CSV as watchlist_purged_YYYY-MM.csv.
  PURGE_MARK="$HOME/.local/state/watchlist_purged_last_archive"
  THIS_MONTH="$(date +%Y-%m)"
  if [[ -f watchlist_purged.csv && "$(cat "$PURGE_MARK" 2>/dev/null)" != "$THIS_MONTH" ]]; then
    step "[16b] monthly purged-watchlist snapshot -> Dropbox"
    if /opt/homebrew/bin/rclone copyto watchlist_purged.csv \
         "dropbox:market-data-archive/watchlist_purged/watchlist_purged_${THIS_MONTH}.csv" \
         --retries 3; then
      mkdir -p "$(dirname "$PURGE_MARK")" && printf '%s' "$THIS_MONTH" > "$PURGE_MARK"
      echo "  archived watchlist_purged.csv -> Dropbox (${THIS_MONTH})"
    else
      FAILURES+=("archive: purged watchlist -> Dropbox")
    fi
  fi

  # [17] IUDX flood-sensor archive — pulls latest readings for the 77-sensor
  # EnvFlood fleet (Pune/Chennai/Kalyan-Dombivli) into ~/iudx-flood-collector/
  # flood.duckdb. Until the 3 provider access requests (PENDING since
  # 2026-07-23) are approved this collects 0 rows but doubles as the daily
  # approval-checker: the run after an approval starts archiving automatically.
  # IUDX serves live snapshots only, so the accumulated history IS the asset
  # (bhavcopy thesis). /usr/bin/python3, not $PY — duckdb, same as step [15].
  # Riding this run for the same reason as [16]: a separate schedule would
  # fire while the Mac sleeps.
  step "[17/17] IUDX flood-sensor collect"
  /usr/bin/python3 /Users/umashankar/iudx-flood-collector/collector.py \
    || FAILURES+=("iudx: flood collector (see access_log in flood.duckdb)")

  # [18] Annual IMD rainfall refresh — self-guarded: no-ops except in Jan/Feb
  # and only once per year (marker analysis/data/.refresh_done_<Y>). When IMD
  # finalizes last year it re-pulls the revised grids, rewrites the 12-city
  # series, recomputes metrics, mails the summary, and pushes kalki_flooding.
  # Riding this run for the usual reason: a standalone January schedule would
  # fire while the Mac sleeps and silently never happen. $PY (venv), not
  # /usr/bin/python3 — imdlib's numpy/xarray chain lives there + ./pkgs.
  step "[18/18] annual IMD rainfall refresh (Jan/Feb no-op guard)"
  $PY /Users/umashankar/iudx-flood-collector/annual_refresh.py \
    || FAILURES+=("rain: annual IMD refresh (see kalki_flooding)")

  # NOTE: the watchlist digest no longer has its own step. It rides INSIDE
  # send_mailer.py at [14/14] — brief + digest are ONE email (user,
  # 2026-07-23) — and that call also runs watchlist hygiene (entry backfill,
  # sell-zone eviction, >3-week purge). The old 07:00 n8n schedule stays
  # deactivated; a second sender would double-mail.

  if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo "[ALERT] ${#FAILURES[@]} step(s) failed: ${FAILURES[*]}"
    $PY send_alert.py "${FAILURES[@]}" || echo "  alert email itself failed to send"
  fi

  echo "=== done $(date) ==="
} >> "$LOG" 2>&1
echo "pipeline complete — see $LOG"
