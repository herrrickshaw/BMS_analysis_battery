#!/bin/bash
# push_validated_universe.sh
# Pushes the validated (delisted-cleaned) ticker universe to global-ticker-universe.
# Run on your LOCAL machine with GitHub credentials.
# Result: 60,971 tradeable tickers across 34 markets

set -e
echo "=== Push Validated Universe to global-ticker-universe ==="

WORK=$(mktemp -d)
echo "Working in: $WORK"

# ── 1. Get source data from herrrickshaw (BMS analysis battery) ───────────────
# The validated files were produced by validate_universe_fd.py on branch:
#   claude/nse-bse-pegu-scoring-k7vu9
git clone --depth 1 -b claude/nse-bse-pegu-scoring-k7vu9 \
    https://github.com/herrrickshaw/herrrickshaw.git "$WORK/src"

# Verify the validated file exists
wc -l "$WORK/src/data/validated_universe_flat.csv"

# ── 2. Clone global-ticker-universe ──────────────────────────────────────────
git clone https://github.com/herrrickshaw/global-ticker-universe.git "$WORK/dest"
cd "$WORK/dest"
mkdir -p data

# ── 3. Copy validated data ────────────────────────────────────────────────────
cp "$WORK/src/data/validated_universe_flat.csv" data/global_universe_flat.csv
[ -f "$WORK/src/data/global_universe.json" ] && cp "$WORK/src/data/global_universe.json" data/
for jf in "$WORK/src/data/"*_tickers_full.json; do
  [ -f "$jf" ] && cp "$jf" data/
done
[ -f "$WORK/src/data/validation_report.json" ] && cp "$WORK/src/data/validation_report.json" data/

echo ""
echo "Files to push:"
wc -l data/global_universe_flat.csv
ls data/*.json 2>/dev/null | wc -l
echo " JSON files"

# ── 4. Commit and push ────────────────────────────────────────────────────────
git add data/
git status --short

if git diff --cached --quiet; then
  echo "Nothing changed — already up to date."
else
  git commit -m "validate: remove delisted/invalid tickers via FinanceDatabase

- 13,268 tickers removed (17.9% of 74,239 total)
- 60,971 tradeable tickers remain across 34 markets
- Validation: JerBouma/FinanceDatabase delisted=false cross-reference (29 exchanges)
- Markets kept without FD validation: BR CH ES AE GR FI BE IE PL PT
- Validated 2026-07-04 by validate_universe_fd.py"
  git push origin main
  echo ""
  echo "Done! Validated CSV live at:"
  echo "https://raw.githubusercontent.com/herrrickshaw/global-ticker-universe/main/data/global_universe_flat.csv"
fi

echo ""
echo "Cleanup: rm -rf $WORK"
