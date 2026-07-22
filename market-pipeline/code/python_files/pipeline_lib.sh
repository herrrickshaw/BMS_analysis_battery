#!/bin/bash
# pipeline_lib.sh — shared machinery for the pipeline sections.
# ============================================================
# Sourced by ingest.sh, mailer.sh, modelling.sh and factor_tests.sh. Holds the
# step timing, failure collection, alerting and upstream gating so those four
# scripts contain only their own steps and nothing else.
#
# WHY A LIBRARY AND NOT FOUR COPIES
# ─────────────────────────────────
# daily_pipeline.sh carried this logic inline. Splitting it into four scripts by
# copy-paste would mean four places to fix the next time a guard is wrong — and
# the guards are exactly what went wrong on 2026-07-20: every step is wrapped in
# `|| FAILURES+=(...)`, so a crashed US scan and a bad network day are
# indistinguishable at a glance. That behaviour is deliberate (one market must
# not block the other four) but it only stays safe if the failure path is
# identical everywhere. One definition, four users.
#
# USAGE
#   source "$(dirname "$0")/pipeline_lib.sh"
#   section_start "mailer"
#   require_fresh ingest              # optional upstream gate
#   run "[1/5] India scan"  $PY scan_bhavcopy.py
#   section_end                       # prints trailer, sends alert; EXIT CODE STAYS 0
#
# ⚠️  section_end deliberately does NOT exit non-zero when individual steps fail,
# despite what an earlier version of this comment claimed. Verified 2026-07-20:
# ingest.sh finished with "[ALERT] 1 step(s) failed" and still returned 0, so the
# n8n node reported success.
#
# That is the correct behaviour, not an oversight. A section is a bag of mostly
# independent steps; a failed symbol-master refresh must not trigger a retry of
# the 23-minute ingest that already succeeded, and must not block a brief whose
# data is fine. The signals that a partial failure DID happen are the alert email
# and the [ALERT] trailer — not the exit code.
#
# Non-zero is reserved for the two cases where continuing is genuinely wrong:
#   run_critical   — the step's failure invalidates everything after it
#   require_fresh  — upstream data is stale, so the output would be confidently wrong
# Anything orchestrating these scripts should gate on data freshness, not on
# section exit codes.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 1

# Resolve the interpreter from the REPO, not from the caller's PATH.
#
# This was `PY="${PY:-python3}"`, which meant the pipeline ran under whatever
# `python3` happened to mean to whoever invoked it. The launchd plists put
# .venv/bin first on PATH, so SCHEDULED runs used the venv; a plain shell has no
# such PATH, so MANUAL runs used /usr/bin/python3 — a different interpreter with
# a different dependency set.
#
# On 2026-07-21 that produced a whole afternoon of phantom failures: the 04:10
# and 06:59 scheduled runs sent cleanly with 0 failed steps, while five manual
# runs died at `[1/9] India full screener scan` on a missing `bseindia` that was
# only absent from the system interpreter. Because no fresh India scan was
# produced, the brief then validated a stale 13:36 intraday workbook and
# HDFCBANK "mismatched" screener.in by 2.18% every time — which read as a data
# fault and was really a wrong-interpreter fault, plus five spurious alert
# emails. Same shape as the two cache trees and the two bhavcopy stores: one
# thing, two resolutions, silent divergence.
#
# $PY still wins if set explicitly, so a caller can target another interpreter
# deliberately — but the DEFAULT is now the venv this repo owns.
if [ -n "${PY:-}" ]; then
  :                                   # explicit override, respect it
elif [ -x "$HERE/.venv/bin/python" ]; then
  PY="$HERE/.venv/bin/python"
else
  PY="python3"
  echo "  ⚠️  $HERE/.venv/bin/python not found — falling back to PATH python3;" \
       "dependency set may differ from the scheduled runs" >&2
fi

FAILURES=()
SECTION=""
LOG=""
SECTION_T0=0

# ── step timing ───────────────────────────────────────────────────────────────
# Machine-readable marker before every step so run times are MEASURED, not
# reconstructed from artifact mtimes after the fact — which is how Korea sat at
# 28 minutes unnoticed while Europe took 3. Parsed by run_monitor.py:
#   [STEP] <epoch> <ISO8601> <section> <label>
step() {
  echo "[STEP] $(date +%s) $(date -u +%Y-%m-%dT%H:%M:%SZ) ${SECTION} $*"
  echo "$*"
}

# ── run one step ──────────────────────────────────────────────────────────────
# Emits the marker, runs the command, and records a failure WITHOUT aborting.
# The label doubles as the failure key so the alert email names the step rather
# than an exit code.
run() {
  local label="$1"; shift
  step "$label"
  if ! "$@"; then
    echo "  ✗ ${label} failed (continuing)"
    FAILURES+=("${SECTION}: ${label}")
    return 1
  fi
  return 0
}

# ── run a step that MUST succeed ──────────────────────────────────────────────
# For steps where continuing produces a confidently wrong result rather than a
# smaller one. Aborts the section immediately.
run_critical() {
  local label="$1"; shift
  step "$label"
  if ! "$@"; then
    echo "  ✗✗ ${label} FAILED — critical, aborting ${SECTION}"
    FAILURES+=("${SECTION}: ${label} (CRITICAL — section aborted)")
    section_end
    exit 1
  fi
  return 0
}

# ── upstream gate ─────────────────────────────────────────────────────────────
# The linkage between sections. Refuses to proceed when the upstream section's
# data is stale or missing, instead of silently rebuilding on top of it.
#
# This is the specific hole that shipped a stale brief on 2026-07-20: the US scan
# crashed, left a 3.9-day-old workbook in place, and every downstream step
# consumed it because it checked existence rather than age.
require_fresh() {
  local upstream="$1"
  step "[gate] upstream freshness: ${upstream}"
  if ! $PY data_index.py --require "$upstream"; then
    echo "  ✗✗ upstream '${upstream}' is stale/missing — refusing to run ${SECTION} on it"
    FAILURES+=("${SECTION}: BLOCKED — upstream ${upstream} stale (see gate above)")
    section_end
    exit 1
  fi
}

# Same check, advisory only: report and carry on. For sections where running on
# slightly old inputs is a judgement call rather than an error.
warn_stale() {
  local upstream="$1"
  step "[gate] upstream freshness (advisory): ${upstream}"
  $PY data_index.py --require "$upstream" || {
    echo "  ⚠️  upstream '${upstream}' stale — continuing anyway (advisory gate)"
    FAILURES+=("${SECTION}: upstream ${upstream} stale (advisory)")
  }
}

# ── section lifecycle ─────────────────────────────────────────────────────────
section_start() {
  SECTION="$1"
  SECTION_T0=$(date +%s)
  LOG="${SECTION}_pipeline_$(date +%Y%m%d).log"
  echo "=== ${SECTION} section $(date) ==="
}

section_end() {
  local dur=$(( $(date +%s) - SECTION_T0 ))
  step "__end__"
  if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo "[ALERT] ${#FAILURES[@]} step(s) failed in ${SECTION}: ${FAILURES[*]}"
    $PY send_alert.py "${FAILURES[@]}" || echo "  alert email itself failed to send"
  fi
  echo "=== done ${SECTION} $(date) — $((dur / 60))m $((dur % 60))s ==="
}

# Section scripts wrap their body in { ... } >> "$LOG" 2>&1 after calling
# section_start, so LOG must be resolved by the caller (bash expands the
# redirection target before the block runs).
