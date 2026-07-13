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
    print(f"  NSE: {len(nse)} | BSE-only: {len(bse)} | US: {len(us)} | "
          f"Japan: {len(japan)} | Korea: {len(korea)}")

    df = pd.DataFrame(nse + bse + us + japan + korea)
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
