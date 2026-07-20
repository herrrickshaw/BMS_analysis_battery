#!/bin/bash
# factor_tests.sh — SECTION 4 of 4: does a new factor/screener actually work?
# ===========================================================================
# The validation harness for candidate factors and screeners, kept separate from
# modelling.sh because the questions differ: modelling BUILDS, this section tries
# to REFUTE. A factor that survives here has earned a place in the brief.
#
#   ./factor_tests.sh                  # full grid, all markets
#   ./factor_tests.sh --market IN      # one market
#
# Reads:  ingest artifacts + factor.zscore_panel
# Feeds:  test.factorial, test.screeners
#
# WHY THIS IS ITS OWN SECTION
# ───────────────────────────
# The repo's own history is the argument. Two results that looked solid did not
# survive scrutiny:
#   * "Piotroski dominates all 7 markets" was a variance claim on a 272-stock
#     sample, contradicted by the real backtest.
#   * The illiquid-name Piotroski edge was first attributed to SMALL CAP; a
#     double-sort showed turnover~mcap correlate at +0.797 and the edge is
#     ILLIQUIDITY, not size.
# Both were caught by testing that was run deliberately, not as a pipeline
# side-effect. Giving that its own schedule and its own log is the point.

source "$(cd "$(dirname "$0")" && pwd)/pipeline_lib.sh"
section_start "factor_tests"

MARKET=""
[[ "${1:-}" == "--market" ]] && MARKET="${2:-}"

{
  warn_stale ingest

  # ── factorial screener grids ────────────────────────────────────────────────
  # Every factor combination against forward returns, per market. Run per-market
  # so one market's data gap doesn't void the whole grid.
  if [[ -n "$MARKET" ]]; then
    run "[1/6] factorial screener test — ${MARKET}" $PY "factorial_screener_test_${MARKET}.py"
  else
    run "[1/6] factorial screener test — India"  $PY factorial_screener_test_IN.py
    run "[2/6] factorial screener test — Japan"  $PY factorial_screener_test_JP.py
    run "[3/6] factorial screener test — Korea"  $PY factorial_screener_test_KR.py
    run "[4/6] factorial screener test — China"  $PY factorial_screener_test_CN.py
  fi

  # ── screener-level forward-return backtest ──────────────────────────────────
  # backtest_results/ does not exist yet — this has never completed. Expect a
  # first-run failure and treat it as a finding, not noise.
  run "[5/6] screener forward-return backtest" $PY backtest_screeners.py

  # ── liquidity-conditioned check ─────────────────────────────────────────────
  # The control for the finding above: any edge must be re-checked against the
  # liquidity gate, because the strongest one in this repo is a LIQUIDITY effect
  # that masqueraded as a size effect. Capacity is ~$300-500k — an edge that
  # dies at $10M is a real edge with a small ceiling, not a fake one, and the
  # difference only shows up when you condition on turnover.
  run "[6/6] liquidity-conditioned forward backtest" $PY backtest_liquidity_forward.py

  step "[index] factor_tests freshness"
  $PY data_index.py --section factor_tests || true

  section_end
} >> "$LOG" 2>&1

echo "factor_tests complete — see $LOG"
