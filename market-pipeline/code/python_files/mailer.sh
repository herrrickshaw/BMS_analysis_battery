#!/bin/bash
# mailer.sh — SECTION 2 of 4: the daily brief. THE CRITICAL PATH.
# ==============================================================
# Five market scans, cross-market audit, external validation, send. This is the
# only section that produces something a human acts on, so it is the only one
# where a wrong answer is worse than no answer.
#
#   ./mailer.sh            # scan + validate + send
#   ./mailer.sh --draft    # scan + validate + write brief_today.html, don't send
#
# Correlation scans are NOT here — they moved to modelling.sh on 2026-07-20.
# They cost ~25 min of the nightly critical path and nothing in the brief reads
# their output.
#
# Reads:  everything ingest.sh produces (gated below)
# Feeds:  scan.{india,us,europe,japan,korea}, report.combined, brief.html

source "$(cd "$(dirname "$0")" && pwd)/pipeline_lib.sh"
section_start "mailer"

{
  # ── linkage to ingest ───────────────────────────────────────────────────────
  # Hard gate. Building the brief on stale ingest data is precisely the 2026-07-20
  # failure: the US scan crashed, its 3.9-day-old workbook stayed on disk, and the
  # brief was assembled and SENT from it because every check asked "does this file
  # exist" rather than "is it from today".
  require_fresh ingest

  # ── scans ───────────────────────────────────────────────────────────────────
  # Independently guarded: one market's rate limit must not cost the other four.
  run "[1/9] India full screener scan"        $PY scan_bhavcopy.py
  run "[2/9] India combined report"           $PY daily_combined_report.py --market IN --html
  run "[3/9] US full market scan"             $PY full_us_market_scan.py --workers 10 --min-price 2
  run "[4/9] US combined report"              $PY daily_combined_report.py --market US --html
  run "[5/9] Europe full market scan"         $PY full_european_market_scan.py --universe data/europe_broad_list.csv --label broad
  run "[6/9] Japan full market scan"          $PY full_japan_market_scan.py --workers 10
  run "[7/9] Korea full market scan"          $PY full_korea_market_scan.py --workers 10

  # ── [8/9] cross-market consistency ──────────────────────────────────────────
  # A market can look healthy alone and be the odd one out in comparison. Every
  # anomaly found on 2026-07-15 — Japan/Korea's 200-DMA from a 3-month window,
  # Europe+Japan running with NO liquidity gate after an FX failure, India
  # momentum-only — was invisible in its own scan and obvious side by side.
  # Non-fatal: registers a failure so the alert fires, without blocking a brief
  # that is mostly sound.
  run "[8/9] cross-market consistency audit"  $PY consistency_audit.py

  # ── [9/9] external validation — the gate between "built" and "sent" ─────────
  # The screeners emit RECOMMENDATIONS. Checking the brief against our own scan
  # proves internal consistency only; it cannot catch a scan that is confidently
  # wrong about the world. On 2026-07-15 every internal check passed while the
  # pipeline quoted MODISONLTD at a SEVEN-WEEK-STALE price and shipped it as a
  # GOLDEN_CROSS pick. The brief, the scan, the parquet and the warehouse all
  # agreed with each other and were all wrong together. Only screener.in disagreed.
  #
  # So: if the picks don't match a public source, DON'T SEND — fall back to
  # --draft, which still writes brief_today.html for a human to inspect. A missing
  # brief is a visible problem; a confidently wrong one in your inbox is not.
  step "[9/9] validate brief against screener.in"
  if $PY validate_brief.py --sample 6; then
      step "[9/9] build + send mailer"
      $PY send_mailer.py "$@" || FAILURES+=("mailer: build/send")
  else
      echo "  ❌ external validation FAILED — sending SUPPRESSED, saving draft instead"
      FAILURES+=("mailer: NOT SENT — brief failed screener.in validation (see above)")
      $PY send_mailer.py --draft || FAILURES+=("mailer: draft save")
  fi

  # ── record today's filter passes ────────────────────────────────────────────
  # AFTER the send, deliberately. This is a diary of what the filters said today,
  # measured against what happens next — the only evidence here free of the
  # survivorship and lookahead that flatter every backtest in this repo. It must
  # never be able to block or delay the brief, so it runs last and is guarded.
  run "[10/10] record filter passes to signal ledger" \
      $PY signal_tracker.py --record

  section_end
} >> "$LOG" 2>&1

echo "mailer complete — see $LOG"
