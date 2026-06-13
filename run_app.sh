#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing backend deps..."
cd "$ROOT/backend"
pip install -r requirements.txt -q

echo "==> Refreshing symbol lists for ticker lookup..."
mkdir -p "$ROOT/data"
curl -sL "https://archives.nseindia.com/content/equities/EQUITY_L.csv" \
  -o "$ROOT/data/nse_equity_list.csv" || echo "  (warning: could not refresh NSE list)"
curl -sL "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv" \
  -o "$ROOT/data/sp500_list.csv" || echo "  (warning: could not refresh S&P 500 list)"

echo "==> Starting backend on :8000..."
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

echo "==> Installing frontend deps..."
cd "$ROOT/frontend"
npm install --silent

echo "==> Starting frontend on :5173..."
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Stock Screener is running:"
echo "  API:    http://localhost:8000"
echo "  App:    http://localhost:5173"
echo "  Docs:   http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
