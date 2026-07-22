#!/bin/bash
# cloud_backup.sh — mirror the market-data trees to Dropbox via rclone.
#
# WHY CLOUD AND NOT GITHUB LFS: the account-wide LFS budget is exhausted, LFS
# stores every rewritten parquet as a new permanent blob (no delta compression,
# ~120 MB/day of churn), and only deleting a whole repo ever frees space. The
# Dropbox remote has 1.6 TiB free, uploads only changed files, and this script
# keeps explicit dated history instead of destructive overwrites.
# (2026-07-22: user chose dropbox over googledrive — also sidesteps rclone's
# shared Google client_id retiring during 2026.)
#
# LAYOUT on the remote (default dropbox:market-data-archive):
#   current/<tree>/...          exact mirror of each local tree
#   history/<YYYY-MM-DD>/<tree> files that were CHANGED or DELETED that day
#                               (moved there by --backup-dir, never destroyed)
#   pg/market_data_<date>.dump  weekly compressed Postgres dump (Mondays)
#
# Retrieval:
#   rclone copy dropbox:market-data-archive/current/market_cache ~/restore/
#   rclone ls   dropbox:market-data-archive/history/2026-07-22/
#
# History older than $KEEP_DAYS is pruned; the current/ mirror is never pruned.
#
# Usage:
#   cloud_backup.sh              # sync all trees; pg dump if Monday
#   cloud_backup.sh --with-pg    # force the Postgres dump too
#   CLOUD_REMOTE=googledrive:market-data-archive cloud_backup.sh  # other account
set -uo pipefail

REMOTE="${CLOUD_REMOTE:-dropbox:market-data-archive}"
TODAY="$(date +%Y-%m-%d)"
KEEP_DAYS=60
LOG="$HOME/market-pipeline/code/python_files/cloud_backup.log"
RCLONE=/opt/homebrew/bin/rclone
FAILS=0

# Single-instance lock. On 2026-07-22 two concurrent invocations (pipeline
# step 16 + a manual --with-pg) shared /tmp/market_data_<date>.dump: instance A
# finished and rm'd the file while B's rclone was mid-transfer -> hash mismatch
# -> rclone deleted the "corrupted" REMOTE copy too. The sync trees survive
# concurrency (rclone per-file), but the dump lifecycle does not.
LOCK="/tmp/cloud_backup.$(echo "$REMOTE" | tr ':/' '__').lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "cloud_backup: another instance holds $LOCK — exiting (not an error)" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# name -> local path. lmdb dirs and tmp/bak files are excluded below: lmdb is a
# live-updated memory-mapped store (copying mid-write gives a corrupt snapshot,
# and it is rebuilt from the parquets anyway); .tmp/.bak are churn.
TREES=(
  "market_cache|$HOME/market-pipeline/market_cache"
  "bhavcopy_cache|$HOME/market-pipeline/data/bhavcopy_cache"
  "cache_seed|$HOME/market-pipeline/code/python_files/cache_seed"
  "gmd_cache_seed|$HOME/repos/global-market-data/cache_seed"
  "warehouse_duckdb|$HOME/data"
)

{
  echo "=== cloud backup $(date '+%Y-%m-%d %H:%M:%S %Z') -> $REMOTE ==="

  for entry in "${TREES[@]}"; do
    name="${entry%%|*}"; src="${entry#*|}"
    if [ ! -e "$src" ]; then
      echo "  ! $name: $src missing — skipped"; FAILS=$((FAILS+1)); continue
    fi
    "$RCLONE" sync "$src" "$REMOTE/current/$name" \
      --backup-dir "$REMOTE/history/$TODAY/$name" \
      --exclude "*.tmp" --exclude "*.bak" --exclude "*.parquet.bak" \
      --exclude "ohlcv.lmdb/**" --exclude ".DS_Store" \
      --transfers 4 --checkers 8 --dropbox-chunk-size 96M \
      --stats-one-line --stats 0 --log-level NOTICE \
      && echo "  ok $name" \
      || { echo "  ! $name: sync FAILED"; FAILS=$((FAILS+1)); }
  done

  # Weekly Postgres dump (Mondays, or --with-pg). Custom format = compressed +
  # selective restore (pg_restore -t). The warehouse IS rebuildable from the
  # caches, but a direct dump makes retrieval one step instead of a pipeline.
  if [ "$(date +%u)" = "1" ] || [ "${1:-}" = "--with-pg" ]; then
    # $$ in the LOCAL name: even with the lock, a unique path means an aborted
    # instance can never collide with a later one. The REMOTE name stays dated.
    DUMP="/tmp/market_data_$(date +%Y%m%d).$$.dump"
    if /opt/homebrew/bin/pg_dump -d market_data -Fc -f "$DUMP" 2>/dev/null \
       || pg_dump -d market_data -Fc -f "$DUMP"; then
      "$RCLONE" copyto "$DUMP" "$REMOTE/pg/market_data_$(date +%Y%m%d).dump" --stats-one-line --stats 0 \
        && echo "  ok pg dump $(du -h "$DUMP" | cut -f1)" \
        || { echo "  ! pg dump upload FAILED"; FAILS=$((FAILS+1)); }
      rm -f "$DUMP"
      # keep the last 8 weekly dumps (sort -r|tail +9: macOS head has no -n -8)
      "$RCLONE" lsf "$REMOTE/pg/" 2>/dev/null | sort -r | tail -n +9 | while read -r old; do
        [ -n "$old" ] && "$RCLONE" deletefile "$REMOTE/pg/$old" \
          && echo "  pruned pg/$old"
      done
    else
      echo "  ! pg_dump FAILED"; FAILS=$((FAILS+1))
    fi
  fi

  # Prune history dirs older than KEEP_DAYS (current/ is never touched).
  CUTOFF=$(date -v-${KEEP_DAYS}d +%Y-%m-%d 2>/dev/null || date -d "-${KEEP_DAYS} days" +%Y-%m-%d)
  "$RCLONE" lsf --dirs-only "$REMOTE/history/" 2>/dev/null | tr -d '/' | while read -r d; do
    if [[ "$d" < "$CUTOFF" ]]; then
      "$RCLONE" purge "$REMOTE/history/$d" && echo "  pruned history/$d"
    fi
  done

  # One-line verification per tree: local vs remote file count + total size.
  for entry in "${TREES[@]}"; do
    name="${entry%%|*}"; src="${entry#*|}"
    [ -e "$src" ] || continue
    rsize=$("$RCLONE" size "$REMOTE/current/$name" --json 2>/dev/null)
    echo "  verify $name: remote $rsize"
  done

  if [ "$FAILS" -gt 0 ]; then
    echo "=== done with $FAILS FAILURE(S) $(date '+%H:%M:%S') ==="
    exit 1
  fi
  echo "=== done $(date '+%H:%M:%S') ==="
} >> "$LOG" 2>&1
