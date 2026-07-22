#!/bin/bash
# modelling.sh — SECTION 3 of 4: build the models. WEEKLY, off the critical path.
# ==============================================================================
# Correlation clusters, factor panels, PPO weight training, walk-forward
# backtests. Heavy (hours), and nothing here is required for tomorrow's brief —
# which is the whole reason it is a separate section on a separate schedule.
#
#   ./modelling.sh              # full weekly run
#   ./modelling.sh --skip-ppo   # correlation + panels only (PPO is the long pole)
#
# Reads:  ingest artifacts + the week's scan workbooks
# Feeds:  correlation, factor.zscore_panel, ppo.weights, backtest.walk_forward
#
# WHY THE CORRELATION SCANS LIVE HERE
# ───────────────────────────────────
# They ran nightly until 2026-07-20 and cost ~25 min of the pre-open window while
# producing nothing the brief consumes. Worth noting they only started producing
# output at all after the tree moved out of ~/Downloads — networkx had been
# missing and every run failed silently behind a `|| echo failed (continuing)`.

source "$(cd "$(dirname "$0")" && pwd)/pipeline_lib.sh"
section_start "modelling"

SKIP_PPO=0
[[ "${1:-}" == "--skip-ppo" ]] && SKIP_PPO=1

{
  # Advisory, not hard. A day-old panel is a perfectly good research input, and
  # blocking the weekly research run because ingest is a few hours behind would
  # trade a real output for a theoretical risk. The mailer gates hard; this
  # doesn't — the asymmetry is intentional.
  warn_stale ingest

  # ── correlation clusters, 5 markets ─────────────────────────────────────────
  run "[1/8] Correlation scan — NSE"     $PY market_correlation_scan.py --market NSE    --output-dir correlation_scan
  run "[2/8] Correlation scan — US"      $PY market_correlation_scan.py --market US     --output-dir correlation_scan
  run "[3/8] Correlation scan — Europe"  $PY market_correlation_scan.py --market EUROPE --output-dir correlation_scan
  run "[4/8] Correlation scan — Japan"   $PY market_correlation_scan.py --market JAPAN  --output-dir correlation_scan
  run "[5/8] Correlation scan — Korea"   $PY market_correlation_scan.py --market KOREA  --output-dir correlation_scan

  # ── factor panel ────────────────────────────────────────────────────────────
  # Cross-sectional z-scores; the input every downstream weighting scheme reads.
  run "[6/8] factor z-score panel" $PY factor_zscore_panel.py

  # ── PPO factor weights ──────────────────────────────────────────────────────
  # Walk-forward variant only. The plain trainer overfits the factor weights —
  # entropy regularisation, walk-forward splits and shrinkage were added in
  # eb0c48f9 specifically to address that, so the walk-forward script is the one
  # to schedule.
  if [[ $SKIP_PPO -eq 0 ]]; then
    run "[7/8] PPO factor weights (walk-forward)" $PY train_ppo_walk_forward.py
  else
    step "[7/8] PPO factor weights — SKIPPED (--skip-ppo)"
  fi

  # ── walk-forward backtest ───────────────────────────────────────────────────
  # Note: wf_backtest/ is empty as of 2026-07-20 — this has never produced output.
  # Scheduling it is how that becomes visible rather than assumed.
  run "[8/8] walk-forward backtest" $PY walk_forward_backtest.py

  step "[index] modelling freshness"
  $PY data_index.py --section modelling || true

  section_end
} >> "$LOG" 2>&1

echo "modelling complete — see $LOG"
