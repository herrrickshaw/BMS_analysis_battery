#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing backend deps..."
cd "$ROOT/backend"
pip install -r requirements.txt -q

echo "==> Refreshing symbol lists for ticker lookup..."
mkdir -p "$ROOT/data"

# India (NSE)
curl -sL "https://archives.nseindia.com/content/equities/EQUITY_L.csv" \
  -o "$ROOT/data/nse_equity_list.csv" || echo "  (warning: could not refresh NSE list)"

# US – NASDAQ trader files (~7,000 equities after ETF filter)
python3 - << 'PYEOF'
import requests, csv, os

ROOT = os.environ.get('ROOT', os.path.dirname(os.path.abspath(__file__ if '__file__' in dir() else '.')))
data_dir = os.path.join(ROOT, 'data')

def fetch_trader(url):
    try:
        r = requests.get(url, timeout=30)
        return r.text if r.ok else ''
    except Exception:
        return ''

import io

def parse_trader(text, sym_col, name_col, etf_col, test_col):
    rows = []
    reader = csv.DictReader(io.StringIO(text), delimiter='|')
    for row in reader:
        if row.get(test_col) == 'Y' or row.get(etf_col) == 'Y':
            continue
        sym = row.get(sym_col, '').strip()
        name = row.get(name_col, '').strip()
        if sym and name and sym not in ('Symbol', 'ACT Symbol'):
            rows.append({'symbol': sym, 'name': name, 'yf_ticker': sym})
    return rows

nasdaq = parse_trader(
    fetch_trader('https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt'),
    'Symbol', 'Security Name', 'ETF', 'Test Issue')
other = parse_trader(
    fetch_trader('https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt'),
    'ACT Symbol', 'Security Name', 'ETF', 'Test Issue')

merged = {r['symbol']: r for r in nasdaq}
for r in other:
    if r['symbol'] not in merged:
        merged[r['symbol']] = r

out = list(merged.values())
if out:
    path = os.path.join(data_dir, 'us_list.csv')
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['symbol','name','yf_ticker'])
        w.writeheader(); w.writerows(out)
    print(f"  US list: {len(out)} stocks")
else:
    print("  (warning: could not refresh US list)")
PYEOF

# Japan – JPX data_j.xls (TSE equities)
python3 - << 'PYEOF'
import requests, csv, os, io

ROOT = os.environ.get('ROOT', '.')
data_dir = os.path.join(ROOT, 'data')

try:
    import xlrd
    r = requests.get('https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls', timeout=60)
    if r.ok:
        wb = xlrd.open_workbook(file_contents=r.content)
        ws = wb.sheet_by_index(0)
        rows = []
        ETF_CATS = {'ETF・ETN', 'REIT・インフラファンド'}
        for i in range(1, ws.nrows):
            code_raw = ws.cell_value(i, 1)
            name = str(ws.cell_value(i, 2)).strip()
            market_cat = str(ws.cell_value(i, 3)).strip()
            if not code_raw or not name or market_cat in ETF_CATS:
                continue
            try:
                code = str(int(float(code_raw))).zfill(4)
            except Exception:
                code = str(code_raw).strip()
            if code.isdigit():
                rows.append({'symbol': code, 'name': name, 'market': market_cat, 'yf_ticker': code + '.T'})
        if rows:
            path = os.path.join(data_dir, 'japan_list.csv')
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=['symbol','name','market','yf_ticker'])
                w.writeheader(); w.writerows(rows)
            print(f"  Japan list: {len(rows)} stocks")
        else:
            print("  (warning: Japan list empty)")
    else:
        print(f"  (warning: JPX returned {r.status_code})")
except Exception as e:
    print(f"  (warning: could not refresh Japan list: {e})")
PYEOF

# Korea – FinanceDataReader (KRX)
python3 - << 'PYEOF'
import csv, os, warnings
warnings.filterwarnings('ignore')
ROOT = os.environ.get('ROOT', '.')
data_dir = os.path.join(ROOT, 'data')
try:
    import FinanceDataReader as fdr
    rows = []
    for mkt, sfx in [('KOSPI', '.KS'), ('KOSDAQ', '.KQ')]:
        df = fdr.StockListing(mkt)
        for _, r in df.iterrows():
            sym = str(r.get('Code', r.get('Symbol', ''))).strip().zfill(6)
            name = str(r.get('Name', '')).strip()
            if sym and name:
                rows.append({'symbol': sym, 'name': name, 'market': mkt, 'yf_ticker': sym + sfx})
    if rows:
        path = os.path.join(data_dir, 'korea_list.csv')
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['symbol','name','market','yf_ticker'])
            w.writeheader(); w.writerows(rows)
        print(f"  Korea list: {len(rows)} stocks")
    else:
        print("  (warning: Korea list empty)")
except Exception as e:
    print(f"  (warning: could not refresh Korea list: {e})")
PYEOF

# China – akshare A-shares
python3 - << 'PYEOF'
import csv, os, warnings
warnings.filterwarnings('ignore')
ROOT = os.environ.get('ROOT', '.')
data_dir = os.path.join(ROOT, 'data')
try:
    import akshare as ak
    df = ak.stock_info_a_code_name()
    rows = []
    for _, r in df.iterrows():
        code = str(r['code']).strip().zfill(6)
        name = str(r['name']).strip()
        suffix = '.SS' if code.startswith('6') else '.SZ'
        rows.append({'symbol': code, 'name': name, 'exchange': 'SSE' if suffix=='.SS' else 'SZSE', 'yf_ticker': code + suffix})
    if rows:
        path = os.path.join(data_dir, 'china_list.csv')
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['symbol','name','exchange','yf_ticker'])
            w.writeheader(); w.writerows(rows)
        print(f"  China list: {len(rows)} stocks")
    else:
        print("  (warning: China list empty)")
except Exception as e:
    print(f"  (warning: could not refresh China list: {e})")

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
