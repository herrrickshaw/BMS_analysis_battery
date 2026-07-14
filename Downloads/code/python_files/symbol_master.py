# symbol_master.py
# ================
# Builds and maintains the SYMBOL MASTER — a persistent Parquet mapping of every
# tradeable stock's ticker ↔ company name ↔ exchange ↔ yfinance suffix.
#
# Sources (company names come free from the bhavcopy "FinInstrmNm" column):
#   NSE    — nse-library equityBhavcopy   (SctySrs == EQ)
#   BSE    — bse-library bhavcopyReport    (equity groups)
#   US     — SEC EDGAR company_tickers_exchange.json
#   JAPAN  — JPX data_j.xls (TSE equities, ETF/REIT categories excluded)
#   KOREA  — FinanceDataReader StockListing(KOSPI/KOSDAQ)
#   CHINA  — akshare stock_info_a_code_name() (SSE+SZSE A-shares; Beijing
#            Stock Exchange codes excluded, yfinance has no data for them)
#   HK     — FinanceDataReader StockListing('HKEX') (dual RMB-counter dupes
#            and US-megacap HDR trackers excluded, see _hongkong_names())
#   EUROPE — data/market_data.duckdb's europe_all_list table (falls back to
#            data/europe_all_list.csv if the table/file isn't there -- see
#            _europe_names(), matches backend/parsers/market_db.py's own
#            DuckDB-then-CSV fallback for the same underlying data)
#
# Output:  ~/Downloads/market_cache/symbol_master.parquet
#   columns: symbol, name, name_clean, exchange, suffix, yf_symbol
#
# `name_clean` is the matchable company root (corporate suffixes stripped) used
# by the news sentiment pipeline so headlines saying "Adani Enterprises" match
# the ADANIENT ticker (which the bare-ticker matcher missed).
#
# Usage:
#   python symbol_master.py                 # build/refresh the master
#   python symbol_master.py --refresh       # force full rebuild
#   from symbol_master import load_master, name_for, clean_name
#
# Refreshed automatically (incremental) whenever it's >24h old.

from __future__ import annotations

import argparse
import re
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

MASTER = Path.home() / "Downloads" / "market_cache" / "symbol_master.parquet"
MASTER.parent.mkdir(parents=True, exist_ok=True)
STALE_HOURS = 24

# ONLY true legal-form suffixes and pure filler are stripped. Descriptive words
# (Enterprises, Industries, Power, Ports …) are KEPT because they distinguish
# group companies — "Adani Enterprises" vs "Adani Ports" vs "Adani Power".
_CORP_TOKENS = {
    "LIMITED","LTD","LTD.","LIMITED.","PVT","PRIVATE","CORP","CORP.",
    "CO","CO.","INC","INC.","PLC","THE","OF","AND","&",
}


def clean_name(name: str) -> str:
    """
    Reduce a full company name to its distinctive matchable root, stripping only
    legal-form suffixes/filler (keeps descriptive tokens that disambiguate
    group companies).
      "ADANI ENTERPRISES LIMITED"      -> "ADANI ENTERPRISES"
      "MARUTI SUZUKI INDIA LTD."       -> "MARUTI SUZUKI INDIA"
      "Amara Raja Energy & Mobility L" -> "AMARA RAJA ENERGY MOBILITY"
    Keeps up to the first 3 meaningful tokens — specific enough for headlines.
    """
    if not name or not isinstance(name, str):
        return ""
    up = re.sub(r"[^A-Za-z ]", " ", name.upper())
    toks = [t for t in up.split() if t and t not in _CORP_TOKENS and len(t) >= 3]
    if not toks:
        return ""
    return " ".join(toks[:3])


# ── Builders per exchange ─────────────────────────────────────────────────────

def _nse_names() -> list:
    rows = []
    try:
        from nse import NSE
        with NSE(download_folder="/tmp", server=False) as n:
            for off in range(7):
                d = datetime.today() - timedelta(days=off)
                try:
                    r = n.equityBhavcopy(d)
                    if hasattr(r, "exists") and r.exists():
                        df = pd.read_csv(r)
                        eq = df[df["SctySrs"] == "EQ"]
                        for _, x in eq.iterrows():
                            sym = str(x["TckrSymb"]).strip()
                            nm  = str(x.get("FinInstrmNm","")).strip()
                            rows.append({"symbol": sym, "name": nm,
                                         "exchange": "NSE", "suffix": ".NS"})
                        break
                except Exception:
                    continue
    except ImportError:
        pass
    return rows


def _bse_names(nse_symbols: set) -> list:
    rows = []
    try:
        from bse import BSE
        b = BSE(download_folder="/tmp")
        for off in range(7):
            d = datetime.today() - timedelta(days=off)
            try:
                p = b.bhavcopyReport(d)
                if hasattr(p, "exists") and p.exists():
                    df = pd.read_csv(p)
                    eq_groups = {"A","B","T","X","XT","M","MT","E"}
                    if "SctySrs" in df.columns:
                        df = df[df["SctySrs"].isin(eq_groups)]
                    for _, x in df.iterrows():
                        sym = str(x["TckrSymb"]).strip()
                        if sym in nse_symbols:   # dual-listed → use NSE
                            continue
                        nm = str(x.get("FinInstrmNm","")).strip()
                        rows.append({"symbol": sym, "name": nm,
                                     "exchange": "BSE", "suffix": ".BO"})
                    break
            except Exception:
                continue
    except ImportError:
        pass
    return rows


def _japan_names() -> list:
    """
    TSE equities via JPX's own data_j.xls (same source as run_app.sh's Japan
    refresh). Unlike NSE/BSE, symbol is stored PRE-SUFFIXED ("7203.T") with
    suffix="" -- matches CLAUDE.md's stated ticker-format convention for
    Japan/Korea (pre-suffixed already, no suffix to append), and
    market_correlation_scan.py's fetch_universe_prices() already guards
    against double-suffixing anything containing a "." .

    Uses an INCLUDE-list of the genuine common-equity market categories,
    not an exclude-list of fund/ETF categories. run_app.sh's original
    Japan-fetch logic used an exclude-list checking for the literal string
    "REIT・インフラファンド" -- but JPX's actual current label for that
    category is "REIT・ベンチャーファンド・カントリーファンド・インフラ
    ファンド" (confirmed by enumerating every real category value in the
    live file), so that exclusion silently never matched anything and 63
    J-REITs/funds were leaking into the "stock" universe undetected (found
    this via a real correlation scan: a 56-member "cluster" that turned out
    to be entirely J-REITs moving together on rate sentiment, not
    operating companies). An include-list of the 3 known board tiers
    (Prime/Standard/Growth, domestic) is robust to JPX renaming or adding
    fund categories in the future, where an exclude-list silently isn't.
    """
    _INCLUDE_CATEGORIES = {
        "プライム（内国株式）",   # Prime (domestic stock)
        "スタンダード（内国株式）",  # Standard (domestic stock)
        "グロース（内国株式）",   # Growth (domestic stock)
    }
    rows = []
    try:
        import xlrd
        import requests
        r = requests.get(
            "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls",
            timeout=60,
        )
        if r.ok:
            wb = xlrd.open_workbook(file_contents=r.content)
            ws = wb.sheet_by_index(0)
            for i in range(1, ws.nrows):
                code_raw = ws.cell_value(i, 1)
                name = str(ws.cell_value(i, 2)).strip()
                market_cat = str(ws.cell_value(i, 3)).strip()
                if not code_raw or not name or market_cat not in _INCLUDE_CATEGORIES:
                    continue
                try:
                    code = str(int(float(code_raw))).zfill(4)
                except Exception:
                    code = str(code_raw).strip()
                if code.isdigit():
                    rows.append({"symbol": f"{code}.T", "name": name,
                                 "exchange": "JAPAN", "suffix": ""})
    except ImportError:
        pass
    except Exception:
        pass
    return rows


def _korea_names() -> list:
    """
    KOSPI + KOSDAQ via FinanceDataReader (same source as run_app.sh's Korea
    refresh). KOSPI and KOSDAQ get distinct `exchange` values (mirroring how
    NASDAQ/NYSE are two exchange values under the "US" market grouping) so
    market_correlation_scan.py's --market KOREA can combine both the same
    way MARKET_EXCHANGES["US"] combines NASDAQ+NYSE. Pre-suffixed symbols
    (.KS / .KQ), suffix="" -- same reasoning as _japan_names().
    """
    rows = []
    try:
        import warnings as _w
        _w.filterwarnings("ignore")
        import FinanceDataReader as fdr
        for mkt, sfx, exch in [("KOSPI", ".KS", "KOSPI"), ("KOSDAQ", ".KQ", "KOSDAQ")]:
            try:
                df = fdr.StockListing(mkt)
            except Exception:
                continue
            for _, x in df.iterrows():
                sym = str(x.get("Code", x.get("Symbol", ""))).strip().zfill(6)
                name = str(x.get("Name", "")).strip()
                if sym and name:
                    rows.append({"symbol": f"{sym}{sfx}", "name": name,
                                 "exchange": exch, "suffix": ""})
    except ImportError:
        pass
    return rows


def _china_names() -> list:
    """
    SSE + SZSE A-shares via akshare's stock_info_a_code_name() (same source as
    run_app.sh's China refresh). Pre-suffixed symbols (.SS / .SZ), suffix=""
    -- same reasoning as _japan_names()/_korea_names().

    run_app.sh's suffix rule is `.SS if code.startswith('6') else .SZ`, which
    silently mis-suffixes the ~327 Beijing Stock Exchange codes (prefix "9",
    e.g. "920000") as .SZ. Checked live: yfinance has NO data at all for BJSE
    tickers regardless of suffix (both 920000.BJ and a real BJSE ticker
    830799.BJ return HTTP 404 "Quote not found") -- Yahoo Finance simply
    doesn't carry this exchange. So instead of mis-suffixing them, BJSE codes
    are excluded outright here (same rationale as _japan_names() excluding
    J-REITs: don't feed the correlation scan symbols that can only ever
    fail their price fetch). SSE (prefix "6", includes the 688xxx STAR
    Market sub-board) and SZSE (prefix "0" main board / "3" ChiNext) are
    both confirmed live against yfinance (000001.SZ, 600000.SS, 000002.SZ
    all returned real CNY-denominated quotes).
    """
    rows = []
    try:
        import warnings as _w
        _w.filterwarnings("ignore")
        import akshare as ak
        df = ak.stock_info_a_code_name()
        for _, x in df.iterrows():
            code = str(x.get("code", "")).strip().zfill(6)
            name = str(x.get("name", "")).strip()
            if not code or not name or not code.isdigit():
                continue
            if code.startswith("6"):
                sfx, exch = ".SS", "SSE"
            elif code.startswith(("0", "3")):
                sfx, exch = ".SZ", "SZSE"
            else:
                continue  # Beijing Stock Exchange (prefix "9") -- no yfinance data
            rows.append({"symbol": f"{code}{sfx}", "name": name,
                         "exchange": exch, "suffix": ""})
    except ImportError:
        pass
    except Exception:
        pass
    return rows


def _hongkong_names() -> list:
    """
    HKEX via FinanceDataReader's StockListing('HKEX') (same source as
    run_app.sh's Hong Kong refresh). Pre-suffixed symbols (.HK), suffix=""
    -- same reasoning as _japan_names()/_korea_names()/_china_names().

    Checked live against the real FDR listing (2,838 rows) and found two
    contamination sources run_app.sh's simpler logic doesn't filter:

    1. 25 "8"-prefixed codes (e.g. 80700) are exact-duplicate alternate
       trading counters of an already-included "0"-prefixed code (e.g.
       00700) -- same company, same `Name` field, verified by grouping on
       duplicated names. Including both would trivially self-correlate
       (same underlying price series twice) and inflate cluster sizes for
       no real reason. Excluded via a plain `not symbol.startswith("8")`.

    2. All 7 codes in the "04xxx" block (04332/04333/04335/04336/04337/
       04338/04621) are HKEX's newer Hong Kong Depositary Receipt (HDR)
       products tracking US megacaps directly (Microsoft, Cisco, Intel,
       Applied Materials, Amgen, Starbucks, a CH Cinda preferred share) --
       not genuine HK-operating companies. Their price mechanically
       tracks the US underlying, so they'd only ever show "correlates
       with the US market", not real HK-market structure. No genuine
       HK company currently occupies the 04xxx block (all 7 rows in it
       are HDRs), so excluding that whole prefix is safe today.

    3. FDR's raw `Symbol` field is already 5-digit zero-padded (e.g.
       "00700" for Tencent), but the real yfinance/Yahoo Finance HK
       ticker is 4-digit ("0700.HK", not "00700.HK") -- confirmed live:
       00700.HK / 08321.HK / 09988.HK all 404, while the 4-digit
       0700.HK / 8321.HK / 9988.HK all resolved real HKD quotes. A
       plain `.zfill(4)` on an already-5-char string is a no-op, so it
       silently preserved the wrong-width code for every single HK row
       -- this is why the very first full HK scan attempt resolved
       0/2,805 symbols and looked exactly like sustained rate-limiting
       (yfinance's bulk downloader reports "possibly delisted" for a
       plain 404, indistinguishable from a real rate-limit response in
       the printed log) when it was actually every request 404'ing on
       ticker format. Normalizing via `str(int(sym)).zfill(4)` strips
       the excess padding before re-padding to exactly 4 digits.
    """
    rows = []
    try:
        import warnings as _w
        _w.filterwarnings("ignore")
        import FinanceDataReader as fdr
        df = fdr.StockListing("HKEX")
        for _, x in df.iterrows():
            sym = str(x.get("Symbol", "")).strip()
            name = str(x.get("Name", "")).strip()
            if not sym or not name or not sym.isdigit():
                continue
            if sym.startswith("8") or sym.startswith("04"):
                continue  # dual RMB-counter dupe or US-megacap HDR tracker
            code = str(int(sym)).zfill(4)
            rows.append({"symbol": f"{code}.HK", "name": name,
                         "exchange": "HKEX", "suffix": ""})
    except ImportError:
        pass
    except Exception:
        pass
    return rows


def _europe_names() -> list:
    """
    966 stocks across 17 European exchanges, from run_app.sh's own Europe
    refresh (Wikipedia index scraping, rebuilt only if missing/>30 days old
    -- see CLAUDE.md). Symbols are pre-suffixed (e.g. "ADMIE.AT"), suffix=""
    -- same reasoning as _japan_names()/_korea_names()/_china_names()/
    _hongkong_names().

    Two repo branches currently disagree on where this data lives: `main`
    still has the original data/europe_all_list.csv (LFS-tracked), while the
    feature branch migrated it into data/market_data.duckdb's
    europe_all_list table and deleted the CSV outright (a different,
    concurrent change to this repo, not made as part of the market-scan
    work in this file). Tries DuckDB first, falls back to the CSV --
    mirrors backend/parsers/market_db.py's own DuckDB-then-CSV fallback for
    this exact table, so this function keeps working regardless of which
    branch/merge state it runs against.

    `exchange` here is the 17 raw per-venue values already in the source
    data (e.g. "Euronext Paris", "Nasdaq Stockholm"), not CLAUDE.md's
    8 grouped "Exchange groups" rows -- passed through as-is rather than
    re-bucketed, consistent with every other _xxx_names() function just
    reshaping its source's columns rather than inventing new grouping.
    """
    rows = []
    root = Path(__file__).resolve().parents[3]

    try:
        import duckdb
        con = duckdb.connect(str(root / "data" / "market_data.duckdb"), read_only=True)
        try:
            df = con.execute("SELECT yf_ticker, name, exchange FROM europe_all_list").fetchdf()
        finally:
            con.close()
        for _, x in df.iterrows():
            yf_ticker = str(x["yf_ticker"]).strip()
            name = str(x["name"]).strip()
            exch = str(x["exchange"]).strip()
            if yf_ticker and name:
                rows.append({"symbol": yf_ticker, "name": name, "exchange": exch, "suffix": ""})
        if rows:
            return rows
    except Exception:
        pass

    try:
        csv_path = root / "data" / "europe_all_list.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            for _, x in df.iterrows():
                yf_ticker = str(x["yf_ticker"]).strip()
                name = str(x["name"]).strip()
                exch = str(x["exchange"]).strip()
                if yf_ticker and name:
                    rows.append({"symbol": yf_ticker, "name": name, "exchange": exch, "suffix": ""})
    except Exception:
        pass
    return rows


def _us_names() -> list:
    rows = []
    try:
        import requests
        url  = "https://www.sec.gov/files/company_tickers_exchange.json"
        hdrs = {"User-Agent": "StockScanner umashankartd1991@gmail.com"}
        data = requests.get(url, timeout=30, headers=hdrs).json()
        for row in data.get("data", []):
            name = str(row[1]).strip() if len(row) > 1 else ""
            tk   = str(row[2]).strip().upper() if len(row) > 2 else ""
            exch = str(row[3]).strip().lower() if len(row) > 3 else ""
            if not tk or len(tk) > 5 or any(c in tk for c in " .,"):
                continue
            ex = ("NASDAQ" if "nasdaq" in exch else
                  "NYSE" if ("nyse" in exch or "amex" in exch) else None)
            if ex:
                rows.append({"symbol": tk, "name": name,
                             "exchange": ex, "suffix": ""})
    except Exception:
        pass
    return rows


# ── Public API ────────────────────────────────────────────────────────────────

def build_master(refresh: bool = False, include_us: bool = True) -> pd.DataFrame:
    """Build the full symbol master and persist it as Parquet."""
    print("Building symbol master (ticker ↔ company name) …")
    nse = _nse_names()
    nse_syms = {r["symbol"] for r in nse}
    bse = _bse_names(nse_syms)
    us  = _us_names() if include_us else []
    japan = _japan_names()
    korea = _korea_names()
    china = _china_names()
    hk = _hongkong_names()
    europe = _europe_names()
    print(f"  NSE: {len(nse)} | BSE-only: {len(bse)} | US: {len(us)} | "
          f"Japan: {len(japan)} | Korea: {len(korea)} | China: {len(china)} | "
          f"HK: {len(hk)} | Europe: {len(europe)}")

    df = pd.DataFrame(nse + bse + us + japan + korea + china + hk + europe)
    if df.empty:
        print("  ⚠️  No symbols fetched."); return df
    df = df.drop_duplicates(subset=["symbol","exchange"])
    df["name_clean"] = df["name"].map(clean_name)
    df["yf_symbol"]  = df["symbol"] + df["suffix"]
    df = df[["symbol","name","name_clean","exchange","suffix","yf_symbol"]]

    df.to_parquet(MASTER, compression="snappy", index=False)
    print(f"  ✅ Symbol master saved: {len(df)} stocks → {MASTER}")
    print(f"     ({(df['name_clean']!='').sum()} have a usable company-name root)")
    return df


def load_master(auto_refresh: bool = True) -> pd.DataFrame:
    """Load the symbol master, rebuilding if missing or >24h stale."""
    if MASTER.exists():
        age_h = (datetime.now().timestamp() - MASTER.stat().st_mtime) / 3600
        if not (auto_refresh and age_h > STALE_HOURS):
            try:
                return pd.read_parquet(MASTER)
            except Exception:
                pass
    return build_master()


# Cached lookups (built once per process)
_LOOKUP = {}

def _ensure_lookup():
    global _LOOKUP
    if not _LOOKUP:
        m = load_master()
        if not m.empty:
            # A ticker can appear on >1 exchange (e.g. NSE & US). Keep first
            # so the symbol index is unique.
            m = m.drop_duplicates(subset=["symbol"], keep="first")
            _LOOKUP = m.set_index("symbol").to_dict("index")


def name_for(symbol: str) -> str:
    """Full company name for a ticker (e.g. 'ADANI ENTERPRISES LIMITED')."""
    _ensure_lookup()
    return _LOOKUP.get(symbol, {}).get("name", "")


def clean_name_for(symbol: str) -> str:
    """Matchable company root for a ticker (e.g. 'ADANI ENTERPRISES')."""
    _ensure_lookup()
    return _LOOKUP.get(symbol, {}).get("name_clean", "")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build the ticker↔name symbol master parquet")
    p.add_argument("--refresh", action="store_true", help="Force full rebuild")
    p.add_argument("--no-us", action="store_true", help="Skip US (SEC EDGAR)")
    a = p.parse_args()
    df = build_master(refresh=a.refresh, include_us=not a.no_us)
    if not df.empty:
        print("\nSample:")
        print(df.head(8).to_string(index=False))
        # Show the key fix: ADANIENT now has a company name
        for s in ["ADANIENT","RELIANCE","TCS","MARUTI"]:
            row = df[df["symbol"]==s]
            if not row.empty:
                r = row.iloc[0]
                print(f"  {s:<12} name='{r['name']}' clean='{r['name_clean']}'")
