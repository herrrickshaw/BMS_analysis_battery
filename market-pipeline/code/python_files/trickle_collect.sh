#!/bin/bash
# trickle_collect.sh — paced screener.in collection that stays under the block.
# ============================================================================
# One SMALL batch per invocation, several invocations per day, resuming
# automatically. The goal is to finish the India fundamentals collection without
# tripping screener.in's rate limiting, which a single bulk run cannot do.
#
# WHY A TRICKLE AND NOT A BULK RUN
# ────────────────────────────────
# Measured 2026-07-21, three bulk attempts, each ending in a hard connection
# refusal:
#     session 1: 155 tickers before ABORT
#     session 2: 124 tickers before ABORT
#     session 3:  52 tickers before ABORT
# The ceiling FALLS with repeated use — screener.in is tightening against this
# machine, not applying a fixed quota. So batch size is set well under the
# LOWEST observed ceiling, not the average, and the gap between runs is hours
# rather than minutes.
#
# Blocks lifted on their own between sessions (~30-60 min), so this backs off
# and retries later rather than treating a block as terminal.
#
# RESUME IS AUTOMATIC. --refresh-thin recomputes "done" from data quality each
# run: a ticker counts as done once it has cfo + screener source + >=3 fiscal
# years. A successfully fetched ticker therefore drops out of the todo list by
# itself — no cursor to keep, and nothing to corrupt if a run dies mid-batch.
#
#   ./trickle_collect.sh              # one batch (default 30)
#   ./trickle_collect.sh 20           # smaller batch
#   ./trickle_collect.sh --status     # progress toward the target, no fetching
#   ./trickle_collect.sh --install    # write the launchd plist (does NOT load)

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GSS="/Users/umashankar/repos/global-stock-screener"
VENV="$HERE/.venv/bin/python3"
STATE="$HERE/trickle_collect_state.log"

# Well under the lowest observed block (52). Tickers are cheap; a tripped block
# costs the rest of the day.
BATCH="${1:-30}"
TARGET=1000        # gate-passing tickers worth stopping at

progress() {
  "$VENV" - <<PY 2>/dev/null | grep -viE "notopenssl|warnings"
import pandas as pd
d=pd.read_parquet("$GSS/cache_seed/fundamentals_history/IN.parquet")
g=d.groupby(d['ticker'].astype(str).str.upper()).agg(
    yrs=('fy_end','nunique'), cfo=('cfo',lambda s:s.notna().sum()),
    ta=('total_assets',lambda s:s.notna().sum()))
gate=int(((g['yrs']>=5)&(g['cfo']>=3)&(g['ta']>=3)).sum())
print(f"{gate}|{len(d)}|{len(g)}")
PY
}

if [[ "${1:-}" == "--status" ]]; then
  IFS='|' read -r gate rows tickers <<< "$(progress)"
  echo "  gate-passing: ${gate:-?} / $TARGET target"
  echo "  rows        : ${rows:-?}   tickers stored: ${tickers:-?}"
  [[ -f "$STATE" ]] && { echo "  recent runs:"; tail -6 "$STATE" | sed 's/^/    /'; }
  exit 0
fi

if [[ "${1:-}" == "--install" ]]; then
  P="$HERE/launchd/com.umashankar.trickle.plist"
  mkdir -p "$HERE/launchd"
  # Four widely spaced slots. Spacing matters more than count: the block lifts
  # in ~30-60 min, so hours between runs keeps every batch starting clean.
  cat > "$P" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.umashankar.trickle</string>
  <key>EnvironmentVariables</key><dict>
    <key>MARKET_CACHE</key><string>/Users/umashankar/market-pipeline/market_cache</string>
    <key>BHAV_CACHE</key><string>/Users/umashankar/market-pipeline/data/bhavcopy_cache</string>
    <key>PATH</key><string>$HERE/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$HERE/trickle_collect.sh</string><string>30</string>
  </array>
  <key>WorkingDirectory</key><string>$HERE</string>
  <key>StandardOutPath</key><string>$HERE/trickle_out.log</string>
  <key>StandardErrorPath</key><string>$HERE/trickle_err.log</string>
  <key>StartCalendarInterval</key><array>
    <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>30</integer></dict>
  </array>
</dict></plist>
PLIST
  echo "  wrote $P"
  echo "  load: launchctl bootstrap gui/\$(id -u) $P"
  echo "  4 runs/day x 30 = ~120 tickers/day; ~1,700 remaining => ~14 days"
  exit 0
fi

IFS='|' read -r gate_before _ _ <<< "$(progress)"
if [[ -n "${gate_before:-}" && "$gate_before" -ge "$TARGET" ]]; then
  echo "$(date '+%F %T') | TARGET REACHED ($gate_before >= $TARGET) — nothing to do" | tee -a "$STATE"
  exit 0
fi

cd "$GSS" || exit 1
set -a; . ./.env 2>/dev/null; set +a

OUT=$(/usr/bin/python3 -u screener_history_collector.py \
        --liquid-only --refresh-thin --limit "$BATCH" 2>&1 | grep -viE "notopenssl|warnings.warn")
IFS='|' read -r gate_after _ _ <<< "$(progress)"

# 🔴 OUTCOME IS MEASURED BY GAIN, NOT BY THE ABSENCE OF AN ERROR STRING.
# The collector's circuit breaker needs 40 CONSECUTIVE failures to fire. A batch
# smaller than 40 that is fully blocked therefore never prints ABORT — it just
# fetches nothing and exits cleanly. The first version of this script read that
# as "ok": on 2026-07-21 a 15-ticker batch ran against an active block, gained
# zero tickers, and logged success. A batch below the breaker threshold cannot
# report its own failure, so the wrapper must judge by result.
DELTA=$(( ${gate_after:-0} - ${gate_before:-0} ))
CONN_REFUSED=0
grep -qiE "connection refused|ConnectionError|Max retries exceeded" <<< "$OUT" && CONN_REFUSED=1

if grep -q "ABORT" <<< "$OUT"; then
  n=$(grep -oE "Collected [0-9]+" <<< "$OUT" | grep -oE "[0-9]+" | head -1)
  # A block is EXPECTED, not an error. Exiting non-zero would make launchd's
  # logs read as a broken job and invite someone to "fix" a working trickle.
  echo "$(date '+%F %T') | BLOCKED after ${n:-0} | gate ${gate_before}->${gate_after}" | tee -a "$STATE"
elif [[ $CONN_REFUSED -eq 1 ]]; then
  echo "$(date '+%F %T') | REFUSED (host still blocking, batch too small to trip breaker) | gate ${gate_before}->${gate_after}" | tee -a "$STATE"
elif [[ $DELTA -le 0 ]]; then
  # Not necessarily a block: a batch can legitimately gain nothing if every
  # ticker in it lacks the balance sheet. Named distinctly so it is visible
  # either way rather than filed under "ok".
  echo "$(date '+%F %T') | STALLED batch=$BATCH gained 0 | gate ${gate_before}->${gate_after}" | tee -a "$STATE"
else
  echo "$(date '+%F %T') | ok batch=$BATCH +${DELTA} | gate ${gate_before}->${gate_after}" | tee -a "$STATE"
fi
exit 0
