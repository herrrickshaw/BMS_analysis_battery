#!/bin/bash
# cloud_backup_verify.sh — INDEPENDENT check that the Dropbox mirror actually
# holds what the local trees hold. Run by the n8n GATE node after cloud_backup.sh;
# also usable standalone.
#
# Deliberately does not trust cloud_backup.sh's exit code or log: the point of a
# gate is to measure the world, not the process (the 2026-07-20 lesson — every
# check asked "does the file exist", none asked "is it current").
#
# Per tree: local bytes/count (same excludes as the backup) vs
# `rclone size` of current/<tree>. FAIL if the remote tree is missing/empty or
# byte totals diverge more than TOLERANCE (files legitimately change between
# backup and verify — dated workbooks land, stores checkpoint — so an exact
# match is wrong to demand).
# Exit 0 = mirror healthy. Non-zero exit + reasons on stdout.
set -uo pipefail

REMOTE="${CLOUD_REMOTE:-dropbox:market-data-archive}"
RCLONE=/opt/homebrew/bin/rclone
TOLERANCE_PCT=10
FAILS=0

TREES=(
  "market_cache|$HOME/market-pipeline/market_cache"
  "bhavcopy_cache|$HOME/market-pipeline/data/bhavcopy_cache"
  "cache_seed|$HOME/market-pipeline/code/python_files/cache_seed"
  "gmd_cache_seed|$HOME/repos/global-market-data/cache_seed"
  "warehouse_duckdb|$HOME/data"
)

for entry in "${TREES[@]}"; do
  name="${entry%%|*}"; src="${entry#*|}"
  [ -e "$src" ] || { echo "SKIP $name: local $src missing"; continue; }

  # local size with the backup's excludes (lmdb, tmp/bak, .DS_Store)
  lbytes=$(find "$src" -type f \
      ! -name "*.tmp" ! -name "*.bak" ! -name "*.parquet.bak" ! -name ".DS_Store" \
      ! -path "*/ohlcv.lmdb/*" -print0 2>/dev/null \
    | xargs -0 stat -f%z 2>/dev/null | awk '{s+=$1} END {print s+0}')

  rjson=$("$RCLONE" size "$REMOTE/current/$name" --json 2>/dev/null) || rjson=""
  rbytes=$(echo "$rjson" | /usr/bin/python3 -c "import sys,json;print(json.load(sys.stdin).get('bytes',0))" 2>/dev/null || echo 0)
  rcount=$(echo "$rjson" | /usr/bin/python3 -c "import sys,json;print(json.load(sys.stdin).get('count',0))" 2>/dev/null || echo 0)

  if [ "$rcount" = "0" ] || [ -z "$rjson" ]; then
    echo "FAIL $name: remote tree missing or empty"; FAILS=$((FAILS+1)); continue
  fi
  # integer % divergence of remote vs local bytes
  div=$(( ( (lbytes>rbytes ? lbytes-rbytes : rbytes-lbytes) * 100 ) / (lbytes>0 ? lbytes : 1) ))
  if [ "$div" -gt "$TOLERANCE_PCT" ]; then
    echo "FAIL $name: local $((lbytes/1048576))MB vs remote $((rbytes/1048576))MB (${div}% apart)"
    FAILS=$((FAILS+1))
  else
    echo "ok   $name: $rcount files, remote $((rbytes/1048576))MB (${div}% off local)"
  fi
done

# Monday pg dump should exist within the last 8 days
newest_dump=$("$RCLONE" lsf "$REMOTE/pg/" 2>/dev/null | sort | tail -1)
if [ -n "$newest_dump" ]; then
  dump_date=$(echo "$newest_dump" | grep -oE "20[0-9]{6}")
  cutoff=$(date -v-8d +%Y%m%d)
  if [ -n "$dump_date" ] && [ "$dump_date" -lt "$cutoff" ]; then
    echo "FAIL pg: newest dump $newest_dump is older than 8 days"; FAILS=$((FAILS+1))
  else
    echo "ok   pg: newest dump $newest_dump"
  fi
else
  echo "FAIL pg: no dumps on remote"; FAILS=$((FAILS+1))
fi

if [ "$FAILS" -gt 0 ]; then
  echo "VERIFY FAILED: $FAILS problem(s)"
  exit 1
fi
echo "VERIFY OK: dropbox mirror healthy"
