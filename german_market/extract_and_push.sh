#!/bin/bash
# extract_and_push.sh
# Run ALL German market data extractions and push results to GitHub.
# Execute from the repo root: bash german_market/extract_and_push.sh

set -euo pipefail
cd "$(dirname "$0")/.."

run_step() {
  # Run a python step; on failure print the error but continue
  python3 "$@" 2>&1 || echo "  [WARN] step failed — continuing"
}
echo "=== Deutsche Börse Data Extraction ==="
echo "Working dir: $(pwd)"
echo ""

mkdir -p data

# ── 1. Eurex GraphQL (free, no auth) ──────────────────────────────────────────
echo "[1/4] Eurex products..."
python3 german_market/eurex_graphql.py --products \
  --out data/eurex_products.csv 2>&1
echo ""

echo "[2/4] Eurex contracts (DAX option = ODAX, DAX future = FDAX, BUND = FGBL)..."
for PROD in ODAX FDAX FGBL OGBL FESX OESX FEU3; do
  echo "  → $PROD"
  python3 german_market/eurex_graphql.py --contracts "$PROD" \
    --out "data/eurex_${PROD}_contracts.csv" 2>&1 | grep -E "contracts|Saved|Error" || true
done
echo ""

echo "[3/4] Eurex trading hours..."
run_step german_market/eurex_graphql.py --trading-hours \
  --out data/eurex_trading_hours.csv

echo "[4/4] Eurex trading holidays..."
run_step german_market/eurex_graphql.py --holidays \
  --out data/eurex_holidays.csv

echo "[5/5] Eurex schema introspection..."
run_step german_market/eurex_graphql.py --introspect | tee data/eurex_schema.txt
echo ""

# ── Show what we got ─────────────────────────────────────────────────────────
echo "=== Files extracted ==="
ls -lh data/eurex_*.csv data/eurex_schema.txt 2>/dev/null || true
echo ""
wc -l data/eurex_products.csv 2>/dev/null && echo " rows in eurex_products.csv"
echo ""

# ── Commit and push results ───────────────────────────────────────────────────
echo "=== Committing and pushing to GitHub ==="
git add data/eurex_*.csv data/eurex_schema.txt 2>/dev/null || true
if git diff --cached --quiet; then
  echo "Nothing new to commit."
else
  git commit -m "data: Eurex GraphQL extraction — products, contracts, trading hours, holidays"
  git push origin claude/nse-bse-pegu-scoring-k7vu9
  echo ""
  echo "Pushed! Claude can now read the data from GitHub."
fi

echo ""
echo "=== Done! ==="
