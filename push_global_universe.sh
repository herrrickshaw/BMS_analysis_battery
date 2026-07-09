#!/usr/bin/env bash
# Syncs updated data + README from this repo (claude/nse-bse-pegu-scoring-k7vu9)
# to herrrickshaw/global-ticker-universe.
# Run from your Mac: bash push_global_universe.sh
set -euo pipefail

BRANCH="claude/nse-bse-pegu-scoring-k7vu9"
# NB: "herrrickshaw/herrrickshaw" (this repo's name before it was renamed to
# BMS_analysis_battery) still resolves here via GitHub's rename redirect, but
# pin the current name so this script doesn't depend on that redirect staying
# in place indefinitely.
SRC_BASE="https://raw.githubusercontent.com/herrrickshaw/BMS_analysis_battery/${BRANCH}"
REPO_URL="https://github.com/herrrickshaw/global-ticker-universe"
REPO_DIR="${1:-/tmp/global-ticker-universe-sync}"

echo "=== herrrickshaw/global-ticker-universe sync ==="
echo "Source branch : herrrickshaw/BMS_analysis_battery @ ${BRANCH}"
echo "Target repo   : ${REPO_URL}"
echo "Local clone   : ${REPO_DIR}"
echo

# Clone or pull
if [ ! -d "${REPO_DIR}/.git" ]; then
  git clone "${REPO_URL}" "${REPO_DIR}"
else
  git -C "${REPO_DIR}" pull origin main
fi

mkdir -p "${REPO_DIR}/data"

FILES=(
  "data/validated_universe_flat.csv"
  "data/german_pegu_scored.csv"
  "data/eurex_pegu_all_europe.csv"
  "data/india_pegu_scored.csv"
)

echo "Downloading data files..."
for f in "${FILES[@]}"; do
  echo "  ${f}"
  curl -sfL "${SRC_BASE}/${f}" -o "${REPO_DIR}/${f}"
done

echo "Downloading README..."
curl -sfL "${SRC_BASE}/README.md" -o "${REPO_DIR}/README.md"

cd "${REPO_DIR}"
git add README.md "${FILES[@]}"

if git diff --cached --quiet; then
  echo
  echo "Already up to date — nothing to push."
else
  git commit -m "data: update global ticker universe — 60,971 tickers, German Eurex PEGU + India PEGU scores"
  git push origin main
  echo
  echo "Done. Pushed to ${REPO_URL}"
fi
