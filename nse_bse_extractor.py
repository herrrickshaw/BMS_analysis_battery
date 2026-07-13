#!/usr/bin/env python3
"""
NSE/BSE Stock Data Extractor
Extracts comprehensive OHLCV, fundamentals, and technicals for all stocks
listed on NSE and BSE, ready for Pegu scoring and Sarvas scan in R.

Usage:
    python nse_bse_extractor.py --exchange BOTH --index NIFTY500
    python nse_bse_extractor.py --exchange NSE  --index ALL --batch-size 100
    python nse_bse_extractor.py --exchange BSE  --max-symbols 200
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timedelta
from io import StringIO
from typing import Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd
import requests
import warnings

warnings.filterwarnings("ignore")


def _write_duckdb_table(output_dir: str, table: str, df: pd.DataFrame) -> None:
    """Write a DataFrame into data/market_data.duckdb, replacing the table."""
    con = duckdb.connect(os.path.join(output_dir, "market_data.duckdb"))
    try:
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM df")
    finally:
        con.close()

# ── optional dependencies ─────────────────────────────────────
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    print("[WARN] yfinance not installed: pip install yfinance")

try:
    from nsepython import equity_history, nse_eq
    HAS_NSEPYTHON = True
except ImportError:
    HAS_NSEPYTHON = False
    print("[WARN] nsepython not installed: pip install nsepython")

# ── logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("nse_bse_extractor.log"),
    ],
)
logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
NSE_EQUITY_CSV = (
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
)
NSE_INDEX_URLS: Dict[str, str] = {
    "NIFTY50":         "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "NIFTY100":        "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "NIFTY200":        "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
    "NIFTY500":        "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "NIFTYMIDCAP50":   "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap50list.csv",
    "NIFTYMIDCAP150":  "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "NIFTYSMALLCAP250":"https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
}
BSE_EQUITY_LIST_URL = (
    "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"
    "?Group=&Scripcode=&industry=&segment=Equity&status=Active"
)


# ─────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────
def http_get(url: str, headers: dict, retries: int = 3, backoff: float = 2.0) -> Optional[requests.Response]:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                return r
            logger.warning("HTTP %d for %s (attempt %d)", r.status_code, url, attempt + 1)
        except requests.RequestException as exc:
            logger.warning("Request failed (attempt %d): %s", attempt + 1, exc)
        if attempt < retries - 1:
            time.sleep(backoff * (attempt + 1))
    return None


# ─────────────────────────────────────────────────────────────
# Symbol Fetchers
# ─────────────────────────────────────────────────────────────
class NSESymbolFetcher:
    # Curated NIFTY500-equivalent list (used when NSE archives are unreachable)
    _NIFTY500_FALLBACK = [
        # NIFTY50
        "RELIANCE","TCS","HDFCBANK","INFY","HINDUNILVR","ICICIBANK","SBIN",
        "BHARTIARTL","ITC","KOTAKBANK","LT","BAJFINANCE","AXISBANK","ASIANPAINT",
        "MARUTI","HCLTECH","SUNPHARMA","TITAN","ULTRACEMCO","WIPRO","BAJAJFINSV",
        "NESTLEIND","TECHM","POWERGRID","NTPC","ONGC","COALINDIA","JSWSTEEL",
        "TATASTEEL","INDUSINDBK","DRREDDY","DIVISLAB","CIPLA","APOLLOHOSP","LTIM",
        "ADANIENT","ADANIPORTS","TATACONSUM","BRITANNIA","HEROMOTOCO","BAJAJ-AUTO",
        "EICHERMOT","M&M","TATAMOTORS","TATAPOWER","HINDALCO","VEDL","GRASIM",
        "UPL","BPCL",
        # NIFTY NEXT 50
        "IOC","GAIL","TORNTPHARM","LUPIN","BIOCON","DMART","MUTHOOTFIN",
        "GODREJCP","PIDILITIND","HAVELLS","BERGEPAINT","VOLTAS","MOTHERSON",
        "MRF","BOSCHLTD","SIEMENS","ABB","CUMMINSIND","THERMAX","BHEL",
        "NMDC","SAIL","MOIL","NATIONALUM","HINDZINC","IDFCFIRSTB","FEDERALBNK",
        "BANDHANBNK","RBLBANK","PNB","BANKBARODA","CANBK","UNIONBANK","CHOLAFIN",
        "M&MFIN","SHRIRAMFIN","BAJAJHLDNG","LICHSGFIN","RECLTD","PFC",
        "IRFC","CESC","TORNTPOWER","TATACOMM","HDFCLIFE","SBILIFE",
        "ICICIGI","ICICIPRULI","LICI","STARHEALTH",
        # IT/Tech
        "NAUKRI","INDIAMART","MAPMYINDIA","ZOMATO","PAYTM","MPHASIS",
        "PERSISTENT","COFORGE","KPITTECH","MASTEK","TATAELXSI","LTTS","CYIENT",
        "HAPPSTMNDS","INTELLECT","TANLA","NEWGEN","ZENSAR","BIRLASOFT","HEXAWARE",
        # Pharma/Healthcare
        "AUROPHARMA","ALKEM","IPCALAB","GLENMARK","NATCOPHARM","AJANTPHARM",
        "GRANULES","LALPATHLAB","METROPOLIS","THYROCARE","MAXHEALTH","FORTIS",
        "NARAYANA","MANKIND","SUNPHARMA","DRREDDY",
        # Auto/Manufacturing
        "ASHOKLEY","BALKRISIND","AMARAJABAT","EXIDEIND","SUPRAJIT","SUNDRMFAST",
        "SCHAEFFLER","TIINDIA","ENDURANCE","CRAFTSMAN","RAMKRISHN","ESCORTS",
        "MAHINDCIE","VARROC","MOTHERSON","MINDARIND",
        # FMCG/Consumer
        "DABUR","COLPAL","MARICO","EMAMILTD","GODREJIND","VBL","RADICO",
        "UNITDSPR","ABCAPITAL","TRENT","SHOPERSTOP","DELHIVERY",
        "NYKAA","ZOMATO","DEVYANI","JUBLFOOD","WESTLIFE","SAPPHIRE",
        # Banking/Finance
        "AUBANK","DCBBANK","KARNATAKA","EQUITASBNK","UJJIVANSFB","SURYODAY",
        "ESAFSFB","UTKARSH","SBFC","FIVESTAR","IIFL","MOTILALOFS","ANGELONE",
        "ICICIPRULI","MAXFINSERV","MASFIN","CANFINHOME","HOMEFIRST","APTUS",
        # Energy/Utilities
        "ADANIGREEN","ADANIPOWER","TATAPOWER","TORNTPOWER","CESC","JPPOWER",
        "NHPC","SJVN","THERMAX","KALPATPOWR","KEC","KERITON","PGEL",
        # Metals/Mining
        "JINDALSTEL","WELSPUNLIV","TATAMETALI","HINDCOPPER","NALCO","GMRINFRA",
        "IRBINFRA","IRCON","RVNL","RAILVIKAS","LTTS","NBCC","NCC","PNC",
        # Chemicals/Specialty
        "PIDILITIND","AAVAS","AARTIIND","ALKYLAMINE","BALRAMCHIN","DIACHEM",
        "FATPIPE","FINPIPE","FLUOROCHEM","GALAXYSURF","GNFC","HSCL","IGPL",
        "INSECTICID","KANSAINER","LXCHEM","NAVINFLUOR","NEOGEN","PHILIPCARB",
        "PRIVISCL","SOLARINDS","SRF","TATACHEM","THIRUMALAI","VINYLCHEM",
        # Real Estate/Infra
        "DLF","GODREJPROP","OBEROIRLTY","PRESTIGE","SOBHA","BRIGADE","MAHLIFE",
        "KOLTEPATIL","PHOENIXLTD","SUNTECK","LODHA","MACROTECH",
    ]

    _NIFTY50_FALLBACK = [
        "RELIANCE","TCS","HDFCBANK","INFY","HINDUNILVR","ICICIBANK","SBIN",
        "BHARTIARTL","ITC","KOTAKBANK","LT","BAJFINANCE","AXISBANK","ASIANPAINT",
        "MARUTI","HCLTECH","SUNPHARMA","TITAN","ULTRACEMCO","WIPRO","BAJAJFINSV",
        "NESTLEIND","TECHM","POWERGRID","NTPC","ONGC","COALINDIA","JSWSTEEL",
        "TATASTEEL","INDUSINDBK","DRREDDY","DIVISLAB","CIPLA","APOLLOHOSP","LTIM",
        "ADANIENT","ADANIPORTS","TATACONSUM","BRITANNIA","HEROMOTOCO","BAJAJ-AUTO",
        "EICHERMOT","M&M","TATAMOTORS","TATAPOWER","HINDALCO","VEDL","GRASIM",
        "UPL","BPCL",
    ]

    def get_all_symbols(self) -> List[str]:
        r = http_get(NSE_EQUITY_CSV, NSE_HEADERS)
        if r is None:
            logger.warning("NSE equity CSV unreachable; using NIFTY500 fallback (%d symbols)",
                           len(self._NIFTY500_FALLBACK))
            return list(self._NIFTY500_FALLBACK)
        try:
            df = pd.read_csv(StringIO(r.text))
            col = next((c for c in df.columns if "SYMBOL" in c.upper()), None)
            if col:
                syms = df[col].str.strip().dropna().tolist()
                logger.info("NSE total equity symbols: %d", len(syms))
                return syms
        except Exception as exc:
            logger.error("NSE equity CSV parse error: %s", exc)
        return list(self._NIFTY500_FALLBACK)

    def get_index_symbols(self, index: str) -> List[str]:
        idx = index.upper().replace(" ", "")
        url = NSE_INDEX_URLS.get(idx)
        if url is None:
            logger.warning("Unknown index '%s'; falling back to NIFTY500", index)
            url = NSE_INDEX_URLS["NIFTY500"]
        r = http_get(url, NSE_HEADERS)
        if r is None:
            fallback = (
                self._NIFTY50_FALLBACK if idx == "NIFTY50"
                else self._NIFTY500_FALLBACK
            )
            logger.warning("Index CSV unreachable; using curated fallback (%d symbols)", len(fallback))
            return list(fallback)
        try:
            df = pd.read_csv(StringIO(r.text))
            col = next(
                (c for c in df.columns if "symbol" in c.lower() or "SYMBOL" in c),
                None,
            )
            if col:
                syms = df[col].str.strip().dropna().tolist()
                logger.info("%s symbols: %d", idx, len(syms))
                return syms
        except Exception as exc:
            logger.error("Index CSV parse error: %s", exc)
        return list(self._NIFTY500_FALLBACK)


class BSESymbolFetcher:
    # Curated BSE-500 equivalent symbols (NSE-listed names, yfinance uses .BO suffix)
    _FALLBACK = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR",
        "ICICIBANK", "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK",
        "LT", "BAJFINANCE", "AXISBANK", "ASIANPAINT", "MARUTI",
        "HCLTECH", "SUNPHARMA", "TITAN", "ULTRACEMCO", "WIPRO",
        "BAJAJFINSV", "NESTLEIND", "TECHM", "POWERGRID", "NTPC",
        "ONGC", "COALINDIA", "JSWSTEEL", "TATASTEEL", "INDUSINDBK",
        "DRREDDY", "DIVISLAB", "CIPLA", "APOLLOHOSP", "LTIM",
        "ADANIENT", "ADANIPORTS", "TATACONSUM", "BRITANNIA", "HEROMOTOCO",
        "BAJAJ-AUTO", "EICHERMOT", "M&M", "TATAMOTORS", "TATAPOWER",
        "HINDALCO", "VEDL", "GRASIM", "UPL", "BPCL",
        "IOC", "GAIL", "TORNTPHARM", "LUPIN", "BIOCON",
        "DMART", "MUTHOOTFIN", "GODREJCP", "PIDILITIND", "HAVELLS",
        "BERGEPAINT", "VOLTAS", "MOTHERSON", "MRF", "BOSCHLTD",
        "SIEMENS", "ABB", "CUMMINSIND", "THERMAX", "BHEL",
        "NMDC", "SAIL", "MOIL", "NATIONALUM", "HINDZINC",
        "IDFCFIRSTB", "FEDERALBNK", "BANDHANBNK", "RBLBANK", "PNB",
        "BANKBARODA", "CANBK", "UNIONBANK", "CHOLAFIN", "M&MFIN",
        "SHRIRAMFIN", "BAJAJHLDNG", "LICHSGFIN", "RECLTD", "PFC",
        "IRFC", "CESC", "TORNTPOWER", "TATACOMM", "HDFCLIFE",
        "SBILIFE", "ICICIGI", "ICICIPRULI", "LICI", "STARHEALTH",
        "NAUKRI", "INDIAMART", "MAPMYINDIA", "ZOMATO", "PAYTM",
        "FSL", "HAPPSTMNDS", "MPHASIS", "PERSISTENT", "COFORGE",
        "KPITTECH", "MASTEK", "TATAELXSI", "LTTS", "CYIENT",
    ]

    def get_all_symbols(self) -> List[str]:
        bse_hdrs = {**NSE_HEADERS, "Referer": "https://www.bseindia.com/"}
        r = http_get(BSE_EQUITY_LIST_URL, bse_hdrs)
        if r is not None:
            try:
                data = r.json()
                rows = data if isinstance(data, list) else data.get("Table", [])
                df = pd.DataFrame(rows)
                for col in ("SCRIPCODE", "scrip_code", "Scripcode"):
                    if col in df.columns:
                        codes = df[col].astype(str).str.strip().tolist()
                        logger.info("BSE active equities: %d", len(codes))
                        return codes
            except Exception as exc:
                logger.warning("BSE API parse error: %s", exc)
        logger.info("BSE API unavailable; using curated fallback (%d symbols)", len(self._FALLBACK))
        return list(self._FALLBACK)

    def get_bse500_symbols(self) -> List[str]:
        # Mirror of NIFTY500 constituents – use NSE fetcher
        syms = NSESymbolFetcher().get_index_symbols("NIFTY500")
        return syms if syms else list(self._FALLBACK)


# ─────────────────────────────────────────────────────────────
# yfinance Fundamental + Technical Fetcher
# ─────────────────────────────────────────────────────────────
_YF_FIELD_MAP: Dict[str, str] = {
    "trailingPE":                    "pe_ratio",
    "forwardPE":                     "forward_pe",
    "priceToBook":                   "pb_ratio",
    "priceToSalesTrailing12Months":  "ps_ratio",
    "pegRatio":                      "peg_ratio",
    "returnOnEquity":                "roe",
    "returnOnAssets":                "roa",
    "debtToEquity":                  "debt_equity",
    "currentRatio":                  "current_ratio",
    "quickRatio":                    "quick_ratio",
    "grossMargins":                  "gross_margins",
    "operatingMargins":              "operating_margins",
    "profitMargins":                 "profit_margins",
    "revenueGrowth":                 "revenue_growth",
    "earningsGrowth":                "earnings_growth",
    "trailingEps":                   "eps_trailing",
    "forwardEps":                    "eps_forward",
    "dividendYield":                 "dividend_yield",
    "marketCap":                     "market_cap",
    "enterpriseValue":               "enterprise_value",
    "enterpriseToEbitda":            "ev_ebitda",
    "enterpriseToRevenue":           "ev_revenue",
    "beta":                          "beta",
    "fiftyTwoWeekHigh":              "w52_high",
    "fiftyTwoWeekLow":               "w52_low",
    "averageVolume":                 "avg_volume",
    "sharesOutstanding":             "shares_outstanding",
    "bookValue":                     "book_value",
    "freeCashflow":                  "free_cash_flow",
    "totalCash":                     "total_cash",
    "totalDebt":                     "total_debt",
    "sector":                        "sector",
    "industry":                      "industry",
    "longName":                      "company_name",
    "fiftyDayAverage":               "ma_50",
    "twoHundredDayAverage":          "ma_200",
    "regularMarketPrice":            "last_price",
    "regularMarketVolume":           "volume",
    "regularMarketPreviousClose":    "prev_close",
    "totalRevenue":                  "total_revenue",
    "grossProfits":                  "gross_profit",
    "ebitda":                        "ebitda",
    "operatingCashflow":             "operating_cashflow",
    "recommendationKey":             "analyst_recommendation",
    "targetMeanPrice":               "target_price",
    "numberOfAnalystOpinions":       "analyst_count",
    "revenuePerShare":               "revenue_per_share",
    "trailingPegRatio":              "trailing_peg",
}


class YFinanceFetcher:
    def get_fundamentals(self, symbol: str, exchange: str) -> Dict:
        suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
        ticker_sym = f"{symbol}{suffix}"
        rec: Dict = {
            "symbol": symbol,
            "exchange": exchange,
            "ticker": ticker_sym,
            "fetch_ts": datetime.now().isoformat(),
        }
        if not HAS_YFINANCE:
            return rec
        try:
            info = yf.Ticker(ticker_sym).info
            for yf_key, col in _YF_FIELD_MAP.items():
                val = info.get(yf_key)
                rec[col] = val if val not in (None, "N/A", "") else np.nan

            # Derived
            lp = rec.get("last_price") or np.nan
            for ref_key, derived in [
                ("ma_50",   "pct_above_50dma"),
                ("ma_200",  "pct_above_200dma"),
                ("w52_high","pct_from_52w_high"),
                ("w52_low", "pct_from_52w_low"),
            ]:
                ref = rec.get(ref_key) or np.nan
                if ref and ref > 0 and not np.isnan(lp):
                    rec[derived] = round((lp / ref - 1) * 100, 2)

            tp = rec.get("target_price") or np.nan
            if not np.isnan(tp) and not np.isnan(lp) and lp > 0:
                rec["upside_pct"] = round((tp / lp - 1) * 100, 2)

        except Exception as exc:
            logger.debug("yfinance error %s: %s", ticker_sym, exc)
        return rec

    def get_price_history(self, symbol: str, exchange: str, period: str = "1y") -> pd.DataFrame:
        suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
        if not HAS_YFINANCE:
            return pd.DataFrame()
        try:
            hist = yf.Ticker(f"{symbol}{suffix}").history(period=period)
            if not hist.empty:
                hist["symbol"] = symbol
                hist["exchange"] = exchange
            return hist
        except Exception as exc:
            logger.debug("Price history error %s: %s", symbol, exc)
            return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# nsepython Enricher (NSE-specific quote fields)
# ─────────────────────────────────────────────────────────────
class NSEQuoteEnricher:
    def enrich(self, symbol: str) -> Dict:
        if not HAS_NSEPYTHON:
            return {}
        try:
            data = nse_eq(symbol)
            if not data:
                return {}
            pi = data.get("priceInfo", {})
            md = data.get("metadata", {})
            ii = data.get("industryInfo", {})
            si = data.get("securityInfo", {})
            whl = pi.get("weekHighLow", {})
            return {
                "nse_last_price":    pi.get("lastPrice"),
                "nse_change":        pi.get("change"),
                "nse_pchange":       pi.get("pChange"),
                "nse_vwap":          pi.get("vwap"),
                "nse_52w_high":      whl.get("max"),
                "nse_52w_low":       whl.get("min"),
                "nse_sector_pe":     ii.get("pe"),
                "nse_total_mktcap":  md.get("totalMarketCap"),
                "nse_ff_mktcap":     md.get("ffMktCap"),
                "nse_impact_cost":   md.get("impactCost"),
                "nse_face_value":    si.get("faceValue"),
                "nse_isin":          si.get("isin"),
                "nse_macro":         ii.get("macro"),
                "nse_sector":        ii.get("sector"),
                "nse_basic_industry":ii.get("basicIndustry"),
            }
        except Exception as exc:
            logger.debug("NSE quote error %s: %s", symbol, exc)
            return {}


# ─────────────────────────────────────────────────────────────
# Technical Indicators
# ─────────────────────────────────────────────────────────────
def compute_technicals(hist: pd.DataFrame) -> Dict:
    if hist.empty or len(hist) < 20:
        return {}

    close  = hist["Close"]
    high   = hist["High"]
    low    = hist["Low"]
    volume = hist["Volume"]
    result: Dict = {}

    # RSI-14
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    result["rsi_14"] = _last(rsi)

    # Moving Averages
    for period in (20, 50, 200):
        ma = close.rolling(period).mean()
        result[f"ma_{period}"] = _last(ma)
        lp = _last(close)
        mav = _last(ma)
        if mav and mav > 0 and lp:
            result[f"close_vs_ma{period}_pct"] = round((lp / mav - 1) * 100, 2)

    # MACD (12-26-9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    result["macd"]        = _last(macd)
    result["macd_signal"] = _last(sig)
    result["macd_hist"]   = _last(macd - sig)

    # Bollinger Bands (20, 2σ)
    ma20  = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bbu   = ma20 + 2 * std20
    bbl   = ma20 - 2 * std20
    result["bb_upper"] = _last(bbu)
    result["bb_lower"] = _last(bbl)
    ma20v = _last(ma20)
    if ma20v and ma20v > 0:
        result["bb_width_pct"] = round((_last(bbu) - _last(bbl)) / ma20v * 100, 2)
        lp = _last(close)
        bbu_v, bbl_v = _last(bbu), _last(bbl)
        if bbu_v and bbl_v and bbu_v != bbl_v:
            result["bb_pct_b"] = round((lp - bbl_v) / (bbu_v - bbl_v) * 100, 2)

    # Stochastic %K/%D (14)
    lo14 = low.rolling(14).min()
    hi14 = high.rolling(14).max()
    stk  = (close - lo14) / (hi14 - lo14 + 1e-10) * 100
    result["stoch_k"] = _last(stk)
    result["stoch_d"] = _last(stk.rolling(3).mean())

    # ATR-14
    tr = pd.concat(
        [high - low,
         (high - close.shift()).abs(),
         (low  - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean()
    result["atr_14"] = _last(atr)
    lp = _last(close)
    atr_v = _last(atr)
    if lp and lp > 0 and atr_v:
        result["atr_pct"] = round(atr_v / lp * 100, 2)

    # Volume ratio vs 20-day average
    vol_ma20 = volume.rolling(20).mean()
    vm = _last(vol_ma20)
    if vm and vm > 0:
        result["volume_ratio"] = round(_last(volume) / vm, 3)
    result["last_volume"] = _last(volume)

    # Price returns
    lp = _last(close)
    for days, label in [(5,"1w"),(21,"1m"),(63,"3m"),(126,"6m"),(252,"1y")]:
        if len(close) > days:
            past = close.iloc[-(days + 1)]
            if past and past > 0:
                result[f"return_{label}_pct"] = round((lp / past - 1) * 100, 2)

    result["last_price_tech"] = lp
    return result


def _last(series: pd.Series):
    try:
        v = series.iloc[-1]
        return float(v) if pd.notna(v) else np.nan
    except Exception:
        return np.nan


# ─────────────────────────────────────────────────────────────
# NSE equity_history enrichment (optional)
# ─────────────────────────────────────────────────────────────
def get_nse_history_technicals(symbol: str) -> Dict:
    if not HAS_NSEPYTHON:
        return {}
    end   = datetime.now().strftime("%d-%m-%Y")
    start = (datetime.now() - timedelta(days=365)).strftime("%d-%m-%Y")
    try:
        df = equity_history(symbol, "EQ", start, end)
        if df is None or df.empty:
            return {}
        rename = {"CH_OPENING_PRICE": "Open", "CH_TRADE_HIGH_PRICE": "High",
                  "CH_TRADE_LOW_PRICE": "Low", "CH_CLOSING_PRICE": "Close",
                  "CH_TOT_TRADED_VAL": "Volume"}
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        for col in ("Open", "High", "Low", "Close", "Volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return compute_technicals(df.sort_index())
    except Exception as exc:
        logger.debug("NSE history error %s: %s", symbol, exc)
        return {}


# ─────────────────────────────────────────────────────────────
# Batch Processor
# ─────────────────────────────────────────────────────────────
def process_batch(
    symbols: List[str],
    exchange: str,
    yf_fetcher: YFinanceFetcher,
    nse_enricher: NSEQuoteEnricher,
    delay: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    fund_rows, tech_rows = [], []
    total = len(symbols)

    for i, sym in enumerate(symbols):
        if i % 20 == 0:
            logger.info("[%s] %d/%d — %s", exchange, i + 1, total, sym)

        # Fundamentals via yfinance
        fund = yf_fetcher.get_fundamentals(sym, exchange)

        # NSE real-time quote enrichment
        if exchange.upper() == "NSE":
            nse_q = nse_enricher.enrich(sym)
            # Prefer NSE last_price if yfinance missing
            if nse_q.get("nse_last_price") and not fund.get("last_price"):
                fund["last_price"] = nse_q["nse_last_price"]
            fund.update(nse_q)

        fund_rows.append(fund)

        # Technical indicators from price history
        hist = yf_fetcher.get_price_history(sym, exchange, period="1y")
        if not hist.empty:
            tech = compute_technicals(hist)
        elif exchange.upper() == "NSE":
            tech = get_nse_history_technicals(sym)
        else:
            tech = {}

        if tech:
            tech["symbol"]   = sym
            tech["exchange"] = exchange
            tech_rows.append(tech)

        time.sleep(delay)

    return pd.DataFrame(fund_rows), pd.DataFrame(tech_rows) if tech_rows else pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="NSE/BSE Stock Data Extractor")
    ap.add_argument("--exchange",     choices=["NSE", "BSE", "BOTH"], default="BOTH")
    ap.add_argument("--index",        default="NIFTY500",
                    help="NIFTY50 | NIFTY200 | NIFTY500 | ALL  (for NSE)")
    ap.add_argument("--output-dir",   default="data")
    ap.add_argument("--batch-size",   type=int,   default=50)
    ap.add_argument("--delay",        type=float, default=0.5,
                    help="Seconds between API calls")
    ap.add_argument("--max-symbols",  type=int,   default=None,
                    help="Cap symbols for quick test runs")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    logger.info("=== NSE/BSE Extractor  exchange=%s  index=%s ===",
                args.exchange, args.index)

    nse_sym  = NSESymbolFetcher()
    bse_sym  = BSESymbolFetcher()
    yff      = YFinanceFetcher()
    nse_enr  = NSEQuoteEnricher()

    exchanges = []
    if args.exchange in ("NSE", "BOTH"):
        exchanges.append("NSE")
    if args.exchange in ("BSE", "BOTH"):
        exchanges.append("BSE")

    all_fund, all_tech = [], []

    for exchange in exchanges:
        logger.info("\n%s\nProcessing %s\n%s", "=" * 60, exchange, "=" * 60)

        # ── Symbol list ──────────────────────────────────────
        if exchange == "NSE":
            symbols = (
                nse_sym.get_all_symbols()
                if args.index.upper() == "ALL"
                else nse_sym.get_index_symbols(args.index)
                     or nse_sym.get_all_symbols()
            )
        else:
            symbols = (
                bse_sym.get_all_symbols()
                if args.index.upper() == "ALL"
                else bse_sym.get_bse500_symbols()
            )

        if args.max_symbols:
            symbols = symbols[: args.max_symbols]
        logger.info("%s symbols to process: %d", exchange, len(symbols))

        # ── Batched extraction ───────────────────────────────
        fund_dfs, tech_dfs = [], []
        for start in range(0, len(symbols), args.batch_size):
            batch = symbols[start : start + args.batch_size]
            fd, td = process_batch(batch, exchange, yff, nse_enr, args.delay)
            fund_dfs.append(fd)
            if not td.empty:
                tech_dfs.append(td)
            # Checkpoint after every batch
            pd.concat(fund_dfs, ignore_index=True).to_csv(
                f"{args.output_dir}/{exchange.lower()}_fundamental_chk.csv",
                index=False,
            )

        fund_df = pd.concat(fund_dfs, ignore_index=True) if fund_dfs else pd.DataFrame()
        tech_df = pd.concat(tech_dfs, ignore_index=True) if tech_dfs else pd.DataFrame()

        if not fund_df.empty:
            _write_duckdb_table(args.output_dir, f"{exchange.lower()}_stocks_fundamental", fund_df)
            logger.info("Saved %d %s fundamental rows", len(fund_df), exchange)
        if not tech_df.empty:
            tech_df.to_csv(
                f"{args.output_dir}/{exchange.lower()}_stocks_technical.csv",
                index=False,
            )
            logger.info("Saved %d %s technical rows", len(tech_df), exchange)

        all_fund.append(fund_df)
        all_tech.append(tech_df)

    # ── Merge fundamental + technical → combined CSV for R ──
    non_empty_fund = [d for d in all_fund if d is not None and not d.empty]
    non_empty_tech = [d for d in all_tech if d is not None and not d.empty]

    if not non_empty_fund:
        logger.error("No fundamental data collected — check network access and API keys.")
        return

    combined_fund = pd.concat(non_empty_fund, ignore_index=True)
    combined_tech = (
        pd.concat(non_empty_tech, ignore_index=True) if non_empty_tech else pd.DataFrame()
    )

    if not combined_tech.empty and not combined_fund.empty:
        merged = combined_fund.merge(
            combined_tech,
            on=["symbol", "exchange"],
            how="left",
            suffixes=("", "_tech"),
        )
        # Prefer technical values where fundamental is null
        for col in ("ma_50", "ma_200", "last_price", "rsi_14"):
            tech_col = f"{col}_tech"
            if col in merged.columns and tech_col in merged.columns:
                merged[col] = merged[col].fillna(merged[tech_col])
        merged.drop(
            columns=[c for c in merged.columns if c.endswith("_tech")],
            inplace=True,
        )
    else:
        merged = combined_fund

    _write_duckdb_table(args.output_dir, "all_stocks_combined", merged)
    logger.info("\nFinal combined table: all_stocks_combined  (%d stocks)", len(merged))

    # Quick summary
    by_exc = merged.groupby("exchange").size().to_dict()
    for exc, cnt in by_exc.items():
        logger.info("  %s : %d stocks", exc, cnt)
    if "pe_ratio" in merged.columns:
        pe_coverage = merged["pe_ratio"].notna().sum()
        logger.info("  Stocks with P/E data : %d (%.0f%%)",
                    pe_coverage, pe_coverage / len(merged) * 100)
    logger.info("Done.")


if __name__ == "__main__":
    main()
