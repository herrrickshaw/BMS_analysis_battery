"""
global_tickers.py
=================
Curated top-cap tickers across 20 major markets.
All symbols use yfinance suffixes for direct compatibility.

Usage:
    from global_tickers import MARKETS, all_tickers, tickers_for
    syms = tickers_for("JP")                 # Japan only
    syms = tickers_for("US", "IN", "UK")     # multi-market
    syms = all_tickers()                     # all 20 markets
"""

from typing import Dict, List

# ── Market registry ────────────────────────────────────────────────────────────
# Each entry: code → {name, exchange, suffix, currency, tickers}
# suffix="" means no suffix needed (US markets)

MARKETS: Dict[str, dict] = {

    # ── ASIA ──────────────────────────────────────────────────────────────────

    "IN": {
        "name": "India", "exchange": "NSE/BSE", "suffix": ".NS", "currency": "INR",
        "tickers": [
            "RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","SBIN","HINDUNILVR",
            "BHARTIARTL","ITC","KOTAKBANK","AXISBANK","LT","BAJFINANCE","HCLTECH",
            "ASIANPAINT","MARUTI","TITAN","SUNPHARMA","WIPRO","NESTLEIND",
            "ULTRACEMCO","POWERGRID","NTPC","BAJAJFINSV","ONGC","TECHM","INDUSINDBK",
            "DIVISLAB","DRREDDY","CIPLA","EICHERMOT","COALINDIA","BPCL","IOC","GAIL",
            "TATAMOTORS","TATASTEEL","JSWSTEEL","HINDALCO","VEDL","ADANIPORTS",
            "ADANIGREEN","ADANIENT","APOLLOHOSP","DMART","PIDILITIND","HAVELLS",
            "SIEMENS","ABB","BOSCHLTD","MUTHOOTFIN","CHOLAFIN","LICHSGFIN",
        ],
    },

    "JP": {
        "name": "Japan", "exchange": "TSE", "suffix": ".T", "currency": "JPY",
        "tickers": [
            "7203","6758","6861","8306","9984","7267","4502","6954","9432","8316",
            "9433","7741","2914","6501","6326","8035","4063","6367","9020","7751",
            "4661","8411","3382","8766","4543","6902","7270","2802","4568","8001",
        ],
    },

    "CN": {
        "name": "China", "exchange": "SSE/SZSE", "suffix": ".SS", "currency": "CNY",
        "tickers": [
            "600519","601318","600036","600900","601166","601398","601288","601988",
            "600028","600030","601857","600016","601628","601601","600050",
        ],
        "extra": {
            # Shenzhen-listed (.SZ suffix)
            "suffix": ".SZ",
            "tickers": ["000858","000333","002594","000651","300750","002415","000002"],
        },
    },

    "HK": {
        "name": "Hong Kong", "exchange": "HKEX", "suffix": ".HK", "currency": "HKD",
        "tickers": [
            "0700","9988","0005","0941","2318","1299","0939","3690","0388","0883",
            "2020","1211","9618","0016","0001","0011","0003","0823","2382","1810",
            "0688","9999","2269","0002","0006","1038","2007","0960","0012","0175",
        ],
    },

    "KR": {
        "name": "South Korea", "exchange": "KRX", "suffix": ".KS", "currency": "KRW",
        "tickers": [
            "005930","000660","035420","005380","051910","068270","035720","096770",
            "003550","017670","066570","004020","028260","000270","009150",
            "207940","000100","011070","010950","032830",
        ],
    },

    "TW": {
        "name": "Taiwan", "exchange": "TWSE", "suffix": ".TW", "currency": "TWD",
        "tickers": [
            "2330","2317","2454","2308","2882","2881","2412","2303","1301","2886",
            "2891","3711","2002","1303","2357","5871","2382","1216","2395","3008",
        ],
    },

    "SG": {
        "name": "Singapore", "exchange": "SGX", "suffix": ".SI", "currency": "SGD",
        "tickers": [
            "D05","O39","U11","Z74","C6L","BN4","G13","C31","A17U","H78",
            "9CI","F34","U96","S68","V03","BS6","N2IU","BUOU","ME8U","AJBU",
        ],
    },

    "AU": {
        "name": "Australia", "exchange": "ASX", "suffix": ".AX", "currency": "AUD",
        "tickers": [
            "BHP","CBA","CSL","ANZ","WBC","NAB","RIO","WES","WOW","MQG",
            "FMG","TLS","GMG","NCM","REA","ALL","COL","TCL","MIN","IEL",
            "APX","WDS","STO","ORG","AGL","QAN","CWY","APA","JHX","SHL",
        ],
    },

    # ── EUROPE ────────────────────────────────────────────────────────────────

    "UK": {
        "name": "United Kingdom", "exchange": "LSE", "suffix": ".L", "currency": "GBP",
        "tickers": [
            "SHEL","AZN","HSBA","ULVR","BP","RIO","GSK","LSEG","BARC","LLOY",
            "BT-A","VOD","REL","PRU","NG","DGE","RKT","EXPN","STAN","GLEN",
            "IMB","BA","CNA","SDR","HIK","TSCO","CPG","INF","WPP","IAG",
        ],
    },

    "DE": {
        "name": "Germany", "exchange": "XETRA", "suffix": ".DE", "currency": "EUR",
        "tickers": [
            "SAP","SIE","ALV","DTE","BAYN","BMW","BAS","ADS","VOW3","MRK",
            "MBG","DBK","HNR1","EOAN","CON","RWE","HEI","FRE","MTX","ZAL",
            "DHER","QIA","PAH3","VNA","HFG","DPW","AIXA","NFBK","TUI1","LHA",
        ],
    },

    "FR": {
        "name": "France", "exchange": "Euronext Paris", "suffix": ".PA", "currency": "EUR",
        "tickers": [
            "MC","TTE","SAN","AI","BNP","OR","CS","EL","DG","CAP",
            "RI","SGO","ATO","VIE","BN","KER","ACA","GLE","SU","DSY",
            "RNO","STM","HO","LR","ML","PUB","FP","EN","TEP","AF",
        ],
    },

    "CH": {
        "name": "Switzerland", "exchange": "SIX", "suffix": ".SW", "currency": "CHF",
        "tickers": [
            "NESN","NOVN","ROG","ABB","ZURN","UBSG","LONN","SIKA","LHN","GIVN",
            "SLHN","SCMN","PGHN","CFR","CSGN","TEMN","ALC","GEBN","ADEN","BARN",
        ],
    },

    "NL": {
        "name": "Netherlands", "exchange": "Euronext Amsterdam", "suffix": ".AS", "currency": "EUR",
        "tickers": [
            "ASML","HEIA","PHIA","NN","ABN","AKZA","WKL","AD","RAND","INGA",
            "AGN","URW","BESI","IMCD","LIGHT","MT","OCI","TKWY","DSM","SBMO",
        ],
    },

    "IT": {
        "name": "Italy", "exchange": "Borsa Italiana", "suffix": ".MI", "currency": "EUR",
        "tickers": [
            "ENI","ENEL","ISP","UCG","TIT","LDO","RACE","STM","CPR","PRY",
            "G","BAMI","MB","BGN","SRG","A2A","PIRC","AMP","BPSO","CNH",
        ],
    },

    "ES": {
        "name": "Spain", "exchange": "BME", "suffix": ".MC", "currency": "EUR",
        "tickers": [
            "IBE","SAN","ITX","TEF","BBVA","BKT","REP","AENA","ACS","GRF",
            "FER","ELE","MEL","MAP","IDR","CIE","VIS","ACX","NTGY","MRL",
        ],
    },

    # ── AMERICAS ──────────────────────────────────────────────────────────────

    "US": {
        "name": "United States", "exchange": "NASDAQ/NYSE", "suffix": "", "currency": "USD",
        "tickers": [
            # Mega cap
            "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","BRK-B","LLY","AVGO",
            # Financials
            "JPM","BAC","WFC","GS","MS","AXP","BLK","SCHW","USB","PNC",
            # Healthcare
            "UNH","JNJ","ABBV","MRK","PFE","TMO","ABT","DHR","ISRG","REGN",
            # Consumer
            "WMT","PG","KO","PEP","COST","HD","MCD","NKE","SBUX","TGT",
            # Energy
            "XOM","CVX","COP","EOG","SLB","MPC","VLO","PSX","OXY","HES",
            # Tech
            "V","MA","ORCL","CRM","ADBE","QCOM","AMD","INTC","NOW","PANW",
            # Industrial
            "CAT","DE","HON","GE","RTX","LMT","BA","UNP","UPS","FDX",
        ],
    },

    "CA": {
        "name": "Canada", "exchange": "TSX", "suffix": ".TO", "currency": "CAD",
        "tickers": [
            "RY","TD","BNS","BMO","ENB","CNR","CP","BCE","SU","ABX",
            "MFC","SLF","TRI","ATD","CVE","MRU","WCN","AEM","SHOP","OTEX",
            "NTR","IMO","TRP","H","CM","POW","AQN","GWO","FFH","CNQ",
        ],
    },

    "BR": {
        "name": "Brazil", "exchange": "B3", "suffix": ".SA", "currency": "BRL",
        "tickers": [
            "PETR4","VALE3","ITUB4","BBDC4","BBAS3","ABEV3","WEGE3","RENT3","LREN3","SUZB3",
            "RAIL3","GGBR4","UGPA3","CSAN3","B3SA3","RADL3","ELET3","SBSP3","TOTS3","EMBR3",
        ],
    },

    # ── MIDDLE EAST ───────────────────────────────────────────────────────────

    "SA": {
        "name": "Saudi Arabia", "exchange": "Tadawul", "suffix": ".SR", "currency": "SAR",
        "tickers": [
            "2222","1120","2010","1180","2350","4030","1050","2380","2330","1010",
            "1211","2020","2080","4280","8010","4200","4070","3020","2170","1030",
        ],
    },

    "AE": {
        "name": "UAE", "exchange": "ADX/DFM", "suffix": ".AE", "currency": "AED",
        "tickers": [
            "FAB","ADCB","ADNOC","ADNOCDIST","ALDAR","EMAAR","DIB","ENBD",
            "TAQA","IHC","EMIRATES","ETISALAT","DU","AMANAT","GFH",
        ],
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def tickers_for(*market_codes: str, with_suffix: bool = True) -> List[str]:
    """
    Return yfinance symbols for one or more market codes.

    Examples:
        tickers_for("US")           → ["AAPL", "MSFT", ...]
        tickers_for("JP")           → ["7203.T", "6758.T", ...]
        tickers_for("IN","UK")      → ["RELIANCE.NS", ..., "SHEL.L", ...]
        tickers_for("IN", with_suffix=False) → ["RELIANCE", "TCS", ...]
    """
    result = []
    for code in market_codes:
        m = MARKETS.get(code.upper())
        if not m:
            raise ValueError(f"Unknown market code '{code}'. Valid: {sorted(MARKETS)}")
        sfx = m["suffix"] if with_suffix else ""
        result.extend(f"{t}{sfx}" for t in m["tickers"])
        # Include extra sub-exchange if defined (e.g. CN Shenzhen)
        if "extra" in m:
            ex = m["extra"]
            esfx = ex["suffix"] if with_suffix else ""
            result.extend(f"{t}{esfx}" for t in ex["tickers"])
    return result


def all_tickers(with_suffix: bool = True) -> List[str]:
    """Return all tickers across all 20 markets."""
    return tickers_for(*MARKETS.keys(), with_suffix=with_suffix)


def market_summary() -> None:
    """Print a summary table of all markets and ticker counts."""
    total = 0
    print(f"{'Code':<5} {'Market':<35} {'Exchange':<25} {'Tickers':>7}")
    print("─" * 75)
    for code, m in MARKETS.items():
        n = len(m["tickers"]) + len(m.get("extra", {}).get("tickers", []))
        total += n
        print(f"{code:<5} {m['name']:<35} {m['exchange']:<25} {n:>7}")
    print("─" * 75)
    print(f"{'TOTAL':<5} {'20 markets':<35} {'':<25} {total:>7}")


if __name__ == "__main__":
    market_summary()
    print()
    print("Sample — India (first 5):", tickers_for("IN")[:5])
    print("Sample — US   (first 5):", tickers_for("US")[:5])
    print("Sample — JP   (first 5):", tickers_for("JP")[:5])
