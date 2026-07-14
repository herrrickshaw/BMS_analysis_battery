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

# Europe – build comprehensive list if missing (966 stocks across all major exchanges)
python3 - << 'PYEOF'
import os, csv, io, time
import duckdb
import requests

ROOT = os.environ.get('ROOT', '.')
data_dir = os.path.join(ROOT, 'data')
db_path = os.path.join(data_dir, 'market_data.duckdb')
con = duckdb.connect(db_path)
con.execute("CREATE TABLE IF NOT EXISTS build_meta (table_name VARCHAR PRIMARY KEY, built_at_epoch DOUBLE)")

# Skip if table exists and was built within 30 days
meta_row = con.execute(
    "SELECT built_at_epoch FROM build_meta WHERE table_name = 'europe_all_list'"
).fetchone()
if meta_row:
    age_days = (time.time() - meta_row[0]) / 86400
    if age_days < 30:
        count = con.execute("SELECT COUNT(*) FROM europe_all_list").fetchone()[0]
        print(f"  Europe list: {count} stocks (cached, {age_days:.0f}d old)")
        con.close()
        exit(0)

print("  Europe list: building from Wikipedia indices...")
session = requests.Session()
session.headers['User-Agent'] = 'Mozilla/5.0'
europe = {}

def add(yf, name, index, exchange):
    if yf not in europe:
        europe[yf] = {'yf_ticker': yf, 'name': name, 'index': index, 'exchange': exchange}

def wiki_table(url, suffix, index_name, exchange, tick_aliases=None, name_aliases=None):
    import pandas as pd
    tick_aliases = tick_aliases or ['Ticker','Symbol','Ticker symbol','MNEM code','Code']
    name_aliases = name_aliases or ['Company','Name','Stock']
    try:
        r = session.get(url, timeout=15)
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            tc = next((c for c in t.columns if str(c) in tick_aliases), None)
            nc = next((c for c in t.columns if str(c) in name_aliases), None)
            if tc and nc and t.shape[0] >= 10:
                for _, row in t.iterrows():
                    sym = str(row[tc]).strip().split('.')[0]
                    nm  = str(row[nc]).strip()
                    if sym and sym != 'nan':
                        add(sym + suffix, nm, index_name, exchange)
                time.sleep(0.6); return
    except Exception:
        pass
    time.sleep(0.6)

# Euronext
wiki_table('https://en.wikipedia.org/wiki/CAC_40',          '.PA', 'CAC40',   'Euronext Paris')
wiki_table('https://en.wikipedia.org/wiki/AEX_index',       '.AS', 'AEX25',   'Euronext Amsterdam')
wiki_table('https://en.wikipedia.org/wiki/BEL_20',          '.BR', 'BEL20',   'Euronext Brussels')
wiki_table('https://en.wikipedia.org/wiki/PSI-20',          '.LS', 'PSI20',   'Euronext Lisbon')
wiki_table('https://en.wikipedia.org/wiki/OBX_Index',       '.OL', 'OBX25',   'Oslo Bors')
wiki_table('https://en.wikipedia.org/wiki/FTSE_MIB',        '.MI', 'FTSEMIB', 'Borsa Italiana')
wiki_table('https://en.wikipedia.org/wiki/ISEQ_20',         '.IR', 'ISEQ20',  'Euronext Dublin', tick_aliases=['MNEM code'])
# Nasdaq Nordic
wiki_table('https://en.wikipedia.org/wiki/OMX_Stockholm_30',  '.ST', 'OMXS30', 'Nasdaq Stockholm')
wiki_table('https://en.wikipedia.org/wiki/OMX_Helsinki_25',   '.HE', 'OMXH25', 'Nasdaq Helsinki')
wiki_table('https://en.wikipedia.org/wiki/OMX_Copenhagen_25', '.CO', 'OMXC25', 'Nasdaq Copenhagen')
# BME / SIX
wiki_table('https://en.wikipedia.org/wiki/IBEX_35',           '.MC', 'IBEX35', 'BME Madrid')
wiki_table('https://en.wikipedia.org/wiki/Swiss_Market_Index','.SW', 'SMI20',  'SIX Swiss')

# Hardcoded: ATX Vienna
for sym, nm in [('EBS','Erste Group Bank'),('OMV','OMV'),('VER','Verbund'),('RBI','Raiffeisen Bank International'),
    ('VOE','voestalpine'),('ANDR','Andritz'),('TKA','Telekom Austria'),('POST','Oesterreichische Post'),
    ('WIE','Wienerberger'),('LNZ','Lenzing'),('VIG','Vienna Insurance Group'),('MMK','Mayr-Melnhof Karton'),
    ('BG','BAWAG Group'),('FLU','Flughafen Wien'),('UQA','UNIQA Insurance Group'),('STR','Strabag'),
    ('SBO','Schoeller-Bleckmann'),('IIA','Immofinanz'),('CAI','CA Immobilien Anlagen'),('PYT','Polytec Holding')]:
    add(sym+'.VI', nm, 'ATX20', 'Vienna')

# Hardcoded: WIG20 Warsaw
for sym, nm in [('ALLEGRO','Allegro.eu'),('DINO','Dino Polska'),('CDR','CD Projekt'),('PKO','PKO Bank Polski'),
    ('PZU','PZU'),('PKN','PKN Orlen'),('PEO','Bank Pekao'),('KGHM','KGHM Polska Miedz'),('LPP','LPP'),
    ('CCC','CCC'),('JSW','JSW'),('MBK','mBank'),('OPL','Orange Polska'),('ALE','Allegro'),
    ('DNP','DataWalk'),('KTY','Kety'),('MRC','Mercator Medical'),('SGN','Shaftesbury'),('BDX','Budimex'),('ATC','Atlantic')]:
    add(sym+'.WA', nm, 'WIG20', 'Warsaw GPW')

# Hardcoded: Athens
for sym, nm in [('ALPHA','Alpha Bank'),('TPEIR','Piraeus Financial Holdings'),('ETE','National Bank of Greece'),
    ('EUROB','Eurobank Ergasias'),('OPAP','OPAP'),('MYTIL','Mytilineos'),('HTO','Hellenic Telecommunications'),
    ('MOH','Motor Oil Hellas'),('ELPE','Hellenic Petroleum'),('EYDAP','Athens Water Supply'),
    ('ADMIE','ADMIE Holding'),('PPC','Public Power'),('LAMDA','Lamda Development'),('GEK','GEK Terna'),
    ('TITC','Titan Cement'),('INLOT','Intralot'),('BELA','Jumbo'),('ELLAKTOR','Ellaktor'),
    ('OTOEL','Autohellas'),('PLATH','Athens Medical Group'),('EUPIC','European Reliance'),
    ('GEKTERNA','GEK Terna'),('NKAS','Nikos Kazantzakis Airport'),('GEBKA','Gebka'),('FLEXO','Flexopack')]:
    add(sym+'.AT', nm, 'FTSEATHEX', 'Athens Stock Exchange')

# Frankfurt / London lists — read from DuckDB tables (migrated from frankfurt_list.csv / london_list.csv)
for table, exch in [
    ('frankfurt_list', 'Deutsche Boerse Frankfurt'),
    ('london_list', 'London Stock Exchange'),
]:
    try:
        for yf_ticker, name, idx in con.execute(f'SELECT yf_ticker, name, "index" FROM {table}').fetchall():
            add(yf_ticker, name, idx, exch)
    except duckdb.Error:
        pass

if europe:
    rows = sorted(europe.values(), key=lambda x: x['exchange']+x['yf_ticker'])
    con.execute("DROP TABLE IF EXISTS europe_all_list")
    con.execute('CREATE TABLE europe_all_list (yf_ticker VARCHAR, name VARCHAR, "index" VARCHAR, exchange VARCHAR)')
    con.executemany(
        "INSERT INTO europe_all_list VALUES (?, ?, ?, ?)",
        [(r['yf_ticker'], r['name'], r['index'], r['exchange']) for r in rows],
    )
    con.execute("DELETE FROM build_meta WHERE table_name = 'europe_all_list'")
    con.execute("INSERT INTO build_meta VALUES ('europe_all_list', ?)", [time.time()])
    print(f"  Europe list: {len(rows)} stocks (rebuilt)")
else:
    print("  (warning: could not build Europe list)")
con.close()
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
PYEOF

# Hong Kong – Hang Seng + broader HKEX list via FinanceDataReader
python3 - << 'PYEOF'
import csv, os, warnings
warnings.filterwarnings('ignore')
ROOT = os.environ.get('ROOT', '.')
data_dir = os.path.join(ROOT, 'data')
rows = []
try:
    import FinanceDataReader as fdr
    df = fdr.StockListing('HKEX')
    for _, r in df.iterrows():
        code_raw = str(r.get('Code', r.get('Symbol', ''))).strip()
        name = str(r.get('Name', r.get('CompanyName', ''))).strip()
        if not code_raw or not name:
            continue
        # HKEX codes are up to 5 digits, zero-padded to 4
        try:
            code = str(int(float(code_raw))).zfill(4)
        except Exception:
            code = code_raw
        if code.isdigit():
            rows.append({'symbol': code, 'name': name, 'exchange': 'HKEX', 'yf_ticker': code + '.HK'})
except Exception as e:
    print(f"  (FDR failed for HK: {e})")

# Fallback: hardcode Hang Seng 50 constituents
if not rows:
    hs50 = [
        ('0700', 'Tencent Holdings'), ('0005', 'HSBC Holdings'), ('0939', 'China Construction Bank'),
        ('1398', 'ICBC'), ('3988', 'Bank of China'), ('2318', 'Ping An Insurance'),
        ('0941', 'China Mobile'), ('0883', 'CNOOC'), ('0388', 'Hong Kong Exchanges'),
        ('1299', 'AIA Group'), ('0016', 'Sun Hung Kai Properties'), ('0001', 'CK Hutchison'),
        ('2628', 'China Life Insurance'), ('0823', 'Link REIT'), ('0002', 'CLP Holdings'),
        ('0003', 'Hong Kong & China Gas'), ('0006', 'Power Assets'), ('0011', 'Hang Seng Bank'),
        ('0012', 'Henderson Land'), ('0017', 'New World Development'), ('0019', 'Swire Pacific'),
        ('0027', 'Galaxy Entertainment'), ('0066', 'MTR Corporation'), ('0101', 'Hang Lung Properties'),
        ('0175', 'Geely Automobile'), ('0267', 'CITIC'), ('0291', 'China Resources Beer'),
        ('0316', 'Orient Overseas'), ('0386', 'Sinopec'), ('0669', 'Techtronic Industries'),
        ('0688', 'China Overseas Land'), ('0762', 'China Unicom'), ('0857', 'PetroChina'),
        ('0868', 'Xinyi Glass'), ('0960', 'Longfor Group'), ('1038', 'CK Infrastructure'),
        ('1044', 'Hengan International'), ('1093', 'CSPC Pharmaceutical'), ('1109', 'China Resources Land'),
        ('1177', 'Sino Biopharmaceutical'), ('1211', 'BYD Company'), ('1997', 'Wharf Real Estate'),
        ('2020', 'ANTA Sports'), ('2269', 'WuXi Biologics'), ('2313', 'Shenzhou International'),
        ('2382', 'Sunny Optical'), ('3690', 'Meituan'), ('6098', 'Country Garden Services'),
        ('6862', 'Haidilao'), ('9988', 'Alibaba Group'),
    ]
    rows = [{'symbol': c, 'name': n, 'exchange': 'HKEX', 'yf_ticker': c + '.HK'} for c, n in hs50]

if rows:
    path = os.path.join(data_dir, 'hk_list.csv')
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['symbol','name','exchange','yf_ticker'])
        w.writeheader(); w.writerows(rows)
    print(f"  Hong Kong list: {len(rows)} stocks")
else:
    print("  (warning: could not build Hong Kong list)")
PYEOF

# Canada – S&P/TSX via FinanceDataReader
python3 - << 'PYEOF'
import csv, os, warnings
warnings.filterwarnings('ignore')
ROOT = os.environ.get('ROOT', '.')
data_dir = os.path.join(ROOT, 'data')
rows = []
try:
    import FinanceDataReader as fdr
    df = fdr.StockListing('TSX')
    for _, r in df.iterrows():
        sym = str(r.get('Symbol', r.get('Code', ''))).strip()
        name = str(r.get('Name', r.get('CompanyName', ''))).strip()
        if sym and name and not sym.endswith('.TO'):
            rows.append({'symbol': sym, 'name': name, 'exchange': 'TSX', 'yf_ticker': sym + '.TO'})
except Exception as e:
    print(f"  (FDR failed for TSX: {e})")

# Fallback: S&P/TSX 60 constituents
if not rows:
    tsx60 = [
        ('SHOP', "Shopify"), ('CNR', 'Canadian National Railway'), ('TD', 'Toronto-Dominion Bank'),
        ('ENB', 'Enbridge'), ('RY', 'Royal Bank of Canada'), ('CP', 'Canadian Pacific Kansas City'),
        ('BN', 'Brookfield Corp'), ('BAM', 'Brookfield Asset Management'), ('BCE', 'BCE Inc'),
        ('SU', 'Suncor Energy'), ('TRI', 'Thomson Reuters'), ('ATD', 'Alimentation Couche-Tard'),
        ('ABX', 'Barrick Gold'), ('AEM', 'Agnico Eagle Mines'), ('BNS', 'Bank of Nova Scotia'),
        ('BMO', 'Bank of Montreal'), ('MFC', 'Manulife Financial'), ('SLF', 'Sun Life Financial'),
        ('GIB.A', 'CGI Inc'), ('TRP', 'TC Energy'), ('CNQ', 'Canadian Natural Resources'),
        ('CCO', 'Cameco'), ('CSU', 'Constellation Software'), ('DOL', 'Dollarama'),
        ('EMA', 'Emera'), ('FTS', 'Fortis'), ('GWO', 'Great-West Lifeco'),
        ('H', 'Hydro One'), ('IFC', 'Intact Financial'), ('IMO', 'Imperial Oil'),
        ('K', 'Kinross Gold'), ('L', 'Loblaw Companies'), ('MRU', 'Metro Inc'),
        ('NA', 'National Bank of Canada'), ('NTR', 'Nutrien'), ('OVV', 'Ovintiv'),
        ('POW', 'Power Corporation of Canada'), ('PPL', 'Pembina Pipeline'),
        ('QSR', 'Restaurant Brands International'), ('RCI.B', 'Rogers Communications'),
        ('SAP', 'Saputo'), ('STBV', 'Stella-Jones'), ('T', 'TELUS'),
        ('TOU', 'Tourmaline Oil'), ('WCN', 'Waste Connections'), ('WFG', 'West Fraser Timber'),
        ('WN', 'George Weston'), ('WPM', 'Wheaton Precious Metals'), ('X', 'TMX Group'),
        ('YRI', 'Yamana Gold'), ('ACO.X', 'ATCO'), ('ALA', 'AltaGas'), ('AQN', 'Algonquin Power'),
        ('CAR.UN', 'Canadian Apartment REIT'), ('CCA', 'Cogeco Communications'),
        ('CTC.A', 'Canadian Tire'), ('EQB', 'EQB Inc'), ('FM', 'First Quantum Minerals'),
        ('GFL', 'GFL Environmental'), ('PKI', 'Parkland Corp'), ('PSI', 'Pason Systems'),
    ]
    rows = [{'symbol': s, 'name': n, 'exchange': 'TSX', 'yf_ticker': s + '.TO'} for s, n in tsx60]

if rows:
    path = os.path.join(data_dir, 'canada_list.csv')
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['symbol','name','exchange','yf_ticker'])
        w.writeheader(); w.writerows(rows)
    print(f"  Canada list: {len(rows)} stocks")
else:
    print("  (warning: could not build Canada list)")
PYEOF

echo "==> Starting backend on :8000..."
# PREFETCH_HOUR / PREFETCH_MINUTE control the daily pre-compute schedule (default midnight)
export PREFETCH_HOUR="${PREFETCH_HOUR:-0}"
export PREFETCH_MINUTE="${PREFETCH_MINUTE:-0}"
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
