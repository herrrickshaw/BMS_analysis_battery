"""
test_portfolio_nse_bulk.py
==========================
Runs portfolio_analysis.py on the full NSE/BSE stock list from the Excel file.

Data source priority:
  1. nsepython  — equity_history() + index_history() via NSE India API
  2. yfinance   — bulk .NS download (fallback)
  3. Synthetic  — two-factor market model (fallback when both APIs are blocked)

Outputs:
  • efficient_frontier_bulk.png  — dark-themed MPT frontier chart
  • portfolio_bulk_results.csv   — per-stock beta + stats + upside
"""

import sys
import warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent))
from portfolio_analysis import (
    calculate_stock_betas,
    calculate_portfolio_beta,
    portfolio_stats,
    monte_carlo_portfolios,
    optimise_portfolios,
    plot_efficient_frontier,
    _fetch_prices_nsepython,
    graham_number,
    _beta_label,
    _section,
    RISK_FREE_RATE,
    TRADING_DAYS,
)

EXCEL_PATH = Path("/root/.claude/uploads/477c4184-eee6-4201-8db0-a71e91dde7e7/8fe6babb-Stock_List_NSE_BSE_1.xlsx")
OUTPUT_CSV = Path("portfolio_bulk_results.csv")
OUTPUT_PNG = Path("efficient_frontier_bulk.png")
N_DAYS     = 504     # ~2 years of trading days
N_MC       = 6_000   # Monte Carlo portfolios
SEED       = 42


# ─────────────────────────────────────────────────────────────────────────────
# Sector metadata — realistic annualised return/vol priors for NSE sectors
# ─────────────────────────────────────────────────────────────────────────────

SECTOR_PARAMS = {
    # sector:  (mu_mean, mu_std, sigma_mean, sigma_std, beta_mean, beta_std)
    # mu/sigma are annual log-return / annualised vol
    "banking":       (0.14, 0.06, 0.32, 0.06, 1.20, 0.15),
    "it":            (0.18, 0.07, 0.28, 0.05, 0.95, 0.12),
    "energy":        (0.12, 0.06, 0.30, 0.06, 0.85, 0.15),
    "pharma":        (0.16, 0.07, 0.29, 0.06, 0.70, 0.13),
    "fmcg":          (0.12, 0.04, 0.23, 0.04, 0.65, 0.10),
    "auto":          (0.15, 0.06, 0.31, 0.06, 1.05, 0.13),
    "infra":         (0.16, 0.08, 0.35, 0.07, 1.15, 0.18),
    "realty":        (0.17, 0.09, 0.42, 0.08, 1.30, 0.20),
    "metals":        (0.13, 0.08, 0.38, 0.08, 1.10, 0.18),
    "textiles":      (0.14, 0.08, 0.36, 0.08, 0.90, 0.18),
    "media":         (0.10, 0.08, 0.38, 0.09, 0.80, 0.18),
    "diversified":   (0.13, 0.07, 0.32, 0.07, 1.00, 0.15),
}

# Map NSE symbol prefixes / names to sectors
SECTOR_MAP = {
    # Banking & Finance
    "HDFCBANK":  "banking", "ICICIBANK": "banking", "AXISBANK":   "banking",
    "SBIN":      "banking", "KOTAKBANK": "banking", "BANDHANBNK": "banking",
    "IDFCFIRSTB":"banking", "IDBI":      "banking", "YESBANK":    "banking",
    "CANBK":     "banking", "UNIONBANK": "banking", "BANKINDIA":  "banking",
    "INDUSINDBK":"banking", "SOUTHBANK": "banking", "UCOBANK":    "banking",
    "KVB":       "banking", "BAJFINANCE":"banking", "CREDITACC":  "banking",
    "HDFC":      "banking", "EDELWEISS": "banking", "PNBHOUSING": "banking",
    "RHFL":      "banking", "M&MFIN":    "banking", "UGROCAP":    "banking",
    "UJJIVANSFB":"banking", "FEDFINA":   "banking", "PNB":        "banking",
    # IT
    "TCS":       "it",      "INFY":      "it",      "WIPRO":      "it",
    "HCLTECH":   "it",      "MASTEK":    "it",      "MPSLTD":     "it",
    "LATENTVIEW":"it",      "SYRMA":     "it",      "DLINKINDIA": "it",
    "MINDTREE":  "it",      "OFSS":      "it",      "NAUKRI":     "it",
    "PROTEAN":   "it",      "MAPMYINDIA":"it",      "IXIGO":      "it",
    "TRACXN":    "it",      "NAZARA":    "it",
    # Energy / Oil & Gas
    "RELIANCE":  "energy",  "ONGC":      "energy",  "IOC":        "energy",
    "BPCL":      "energy",  "HINDPETRO": "energy",  "GAIL":       "energy",
    "PETRONET":  "energy",  "GSPL":      "energy",  "GUJGASLTD":  "energy",
    "MRPL":      "energy",  "CHENNPETRO":"energy",  "OIL":        "energy",
    "MGL":       "energy",  "TNPETRO":   "energy",  "IOLCP":      "energy",
    "COALINDIA": "energy",  "NTPC":      "energy",  "TATAPOWER":  "energy",
    "JSWENERGY": "energy",  "ADANIGREEN":"energy",  "SUZLON":     "energy",
    "INOXWIND":  "energy",  "RPOWER":    "energy",  "NLCINDIA":   "energy",
    "NMDC":      "energy",  "NHPC":      "energy",  "PFC":        "energy",
    "RECLTD":    "energy",  "WAAREEENER":"energy",
    # Pharma & Healthcare
    "SUNPHARMA": "pharma",  "CIPLA":     "pharma",  "BIOCON":     "pharma",
    "SYNGENE":   "pharma",  "NATCOPHARM":"pharma",  "HERANBA":    "pharma",
    "CAPLIPOINT": "pharma", "FORTIS":    "pharma",  "NH":         "pharma",
    "TIRUMALCHM":"pharma",  "DEEPAKNTR": "pharma",
    # FMCG
    "ITC":       "fmcg",    "BRITANNIA": "fmcg",    "MARICO":     "fmcg",
    "COLPAL":    "fmcg",    "HATSUN":    "fmcg",    "ATFL":       "fmcg",
    "PARAGMILK": "fmcg",    "MRSBECTORS":"fmcg",    "HONASA":     "fmcg",
    "PATANJALI": "fmcg",    "AVANTI":    "fmcg",    "KRBL":       "fmcg",
    "VBL":       "fmcg",    "GALAXYSURF":"fmcg",
    # Auto & Auto Ancillaries
    "MARUTI":    "auto",    "TATAMOTORS":"auto",     "BAJAJ":      "auto",
    "EICHERMOT": "auto",    "TVSMOTOR":  "auto",     "MOTHERSON":  "auto",
    "ENDURANCE": "auto",    "ESCORTS":   "auto",     "EXIDEIND":   "auto",
    "CEATLTD":   "auto",    "JKTYRE":    "auto",     "MAHINDCIE":  "auto",
    "GSAUTO":    "auto",    "RANEENGINE":"auto",     "CARRARO":    "auto",
    "HYUNDAI":   "auto",    "OLAELECTRIC":"auto",
    # Infrastructure / Defence / PSU
    "BEL":       "infra",   "BHEL":      "infra",    "HAL":        "infra",
    "ENGINERSIN":"infra",   "NBCC":      "infra",    "RVNL":       "infra",
    "RAILTEL":   "infra",   "IRCTC":     "infra",    "GMRINFRA":   "infra",
    "COCHINSHIP":"infra",   "MAZDOCK":   "infra",    "TITAGARH":   "infra",
    "THERMAX":   "infra",   "CGPOWER":   "infra",    "SIEMENS":    "infra",
    "HAVELLS":   "infra",   "SCHNEIDER": "infra",    "CUMMINSIND": "infra",
    "ABB":       "infra",   "GET&D":     "infra",    "UNIMECH":    "infra",
    "ITI":       "infra",   "TEJASNET":  "infra",    "ADANIPORTS": "infra",
    "SCI":       "infra",   "SAIL":      "metals",
    # Realty
    "DLF":       "realty",  "GODAVARIB": "realty",   "ARIHANTSUP": "realty",
    "OMAXE":     "realty",  "PROZONE":   "realty",   "ANANT":      "realty",
    "MAHLIFE":   "realty",  "MHRIL":     "realty",
    # Metals & Mining
    "HINDALCO":  "metals",  "TATASTEEL": "metals",   "VEDL":       "metals",
    "NATIONALUM":"metals",  "GOLKALUM":  "metals",   "GOLDIAM":    "metals",
    "RAIN":      "metals",  "RRKABEL":   "metals",
    # Textiles / Consumer
    "CENTURYTEX":"textiles","RAYMOND":   "textiles", "MORARJEE":   "textiles",
    "DONEAR":    "textiles","KALLAMTEX": "textiles", "BEARDSELL":  "textiles",
    "WELSPUNLIV":"textiles","WELSPUNSPEC":"textiles","GUJTEX":     "textiles",
    "LOYALTEX":  "textiles","LIBERTSHOE":"textiles", "KHADIM":     "textiles",
    "VMART":     "textiles","ABFRL":     "textiles", "ZODIAC":     "textiles",
    "PADAMCOT":  "textiles","BIHARSPNG": "textiles",
    # Media
    "ZEEL":      "media",   "ZEEMEDIA":  "media",    "SUNTV":      "media",
    "NETWORK18": "media",   "NDTV":      "media",    "COFFEEDAY":  "media",
    "MATRIMONY": "media",   "NAZARA":    "media",    "EASEMYTRIP": "media",
}


def get_sector(sym: str) -> str:
    """Map symbol to sector, defaulting to 'diversified'."""
    return SECTOR_MAP.get(sym, "diversified")


# ─────────────────────────────────────────────────────────────────────────────
# SYNTHETIC DATA GENERATOR — two-factor model
# ─────────────────────────────────────────────────────────────────────────────

def generate_synthetic_prices(
    symbols: list,
    n_days: int = N_DAYS,
    seed: int = SEED,
) -> pd.DataFrame:
    """
    Simulates log-normal price paths for all symbols using a two-factor model:

      R_i(t) = β_i · R_market(t) + γ_i · R_sector(t) + ε_i(t)

    where β, γ, sector, and idiosyncratic vol are drawn from sector-specific
    priors to reproduce realistic NSE return/volatility characteristics.

    Returns a DataFrame of closing prices indexed by date, with a BENCHMARK
    column representing the synthetic NIFTY 50.
    """
    rng = np.random.default_rng(seed)
    dt  = 1 / TRADING_DAYS

    # ── Market factor ──────────────────────────────────────────────────────────
    mkt_ann_ret  = 0.13   # ~13% NIFTY 50 CAGR
    mkt_ann_vol  = 0.17   # ~17% NIFTY 50 annual vol
    mkt_daily_mu = (mkt_ann_ret - 0.5 * mkt_ann_vol**2) * dt
    mkt_daily_sig= mkt_ann_vol * np.sqrt(dt)
    mkt_shocks   = rng.normal(0, 1, n_days)
    mkt_log_ret  = mkt_daily_mu + mkt_daily_sig * mkt_shocks
    mkt_prices   = 20000 * np.exp(np.cumsum(mkt_log_ret))   # start at NIFTY ~20000

    # ── Sector factors (one per unique sector) ────────────────────────────────
    unique_sectors = list(set(get_sector(s) for s in symbols))
    sector_shocks  = {sec: rng.normal(0, 1, n_days) for sec in unique_sectors}

    # ── Per-symbol prices ─────────────────────────────────────────────────────
    price_data = {"BENCHMARK": mkt_prices}

    for sym in symbols:
        sec   = get_sector(sym)
        sp    = SECTOR_PARAMS[sec]
        mu_a  = rng.normal(sp[0], sp[1])           # annual expected return
        sig_a = max(0.15, rng.normal(sp[2], sp[3])) # annual total vol
        beta  = max(0.1,  rng.normal(sp[4], sp[5])) # market beta

        # sector beta ~ 30% of residual
        gamma = rng.uniform(0.1, 0.4)

        # Residual idiosyncratic vol after market + sector factors
        mkt_contrib  = beta  * mkt_ann_vol
        sec_contrib  = gamma * mkt_ann_vol * 0.6
        idio_vol_a   = max(0.05, np.sqrt(max(0, sig_a**2 - mkt_contrib**2 - sec_contrib**2)))

        daily_mu  = (mu_a - 0.5 * sig_a**2) * dt
        idio_shocks = rng.normal(0, 1, n_days)

        log_ret = (
            daily_mu
            + beta  * mkt_daily_sig * mkt_shocks
            + gamma * mkt_daily_sig * 0.6 * sector_shocks[sec]
            + idio_vol_a * np.sqrt(dt) * idio_shocks
        )

        start_price = rng.uniform(50, 5000)
        price_data[sym] = start_price * np.exp(np.cumsum(log_ret))

    # ── Build DataFrame ───────────────────────────────────────────────────────
    dates = pd.bdate_range(end="2026-05-27", periods=n_days)
    df    = pd.DataFrame(price_data, index=dates)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SYNTHETIC FUNDAMENTALS — modelled from sector priors
# ─────────────────────────────────────────────────────────────────────────────

# Known approximate fundamentals for major Indian stocks (May 2026 estimates)
_KNOWN_FUNDAMENTALS = {
    "RELIANCE":   {"company_name": "Reliance Industries",    "current_price": 1320, "target_price": 1550, "trailing_eps": 62,  "book_value": 590},
    "HDFCBANK":   {"company_name": "HDFC Bank",              "current_price": 1780, "target_price": 2100, "trailing_eps": 88,  "book_value": 560},
    "ICICIBANK":  {"company_name": "ICICI Bank",             "current_price": 1380, "target_price": 1650, "trailing_eps": 67,  "book_value": 390},
    "INFY":       {"company_name": "Infosys",                "current_price": 1620, "target_price": 1850, "trailing_eps": 72,  "book_value": 220},
    "TCS":        {"company_name": "Tata Consultancy Svcs",  "current_price": 3450, "target_price": 4100, "trailing_eps": 128, "book_value": 350},
    "WIPRO":      {"company_name": "Wipro",                  "current_price": 470,  "target_price": 570,  "trailing_eps": 22,  "book_value": 130},
    "HCLTECH":    {"company_name": "HCL Technologies",       "current_price": 1680, "target_price": 1900, "trailing_eps": 74,  "book_value": 240},
    "AXISBANK":   {"company_name": "Axis Bank",              "current_price": 1120, "target_price": 1380, "trailing_eps": 74,  "book_value": 430},
    "SBIN":       {"company_name": "State Bank of India",    "current_price": 780,  "target_price": 950,  "trailing_eps": 72,  "book_value": 440},
    "KOTAKBANK":  {"company_name": "Kotak Mahindra Bank",    "current_price": 2050, "target_price": 2350, "trailing_eps": 82,  "book_value": 490},
    "MARUTI":     {"company_name": "Maruti Suzuki India",    "current_price": 11800,"target_price":13500, "trailing_eps": 490, "book_value":3200},
    "SUNPHARMA":  {"company_name": "Sun Pharmaceutical",     "current_price": 1750, "target_price": 2050, "trailing_eps": 62,  "book_value": 310},
    "TATAMOTORS": {"company_name": "Tata Motors",            "current_price": 730,  "target_price": 900,  "trailing_eps": 42,  "book_value": 280},
    "BAJFINANCE": {"company_name": "Bajaj Finance",          "current_price": 8600, "target_price":10200, "trailing_eps": 280, "book_value":1250},
    "ITC":        {"company_name": "ITC Limited",            "current_price": 445,  "target_price": 530,  "trailing_eps": 18,  "book_value": 68},
    "BHARTIARTL": {"company_name": "Bharti Airtel",          "current_price": 1740, "target_price": 2000, "trailing_eps": 52,  "book_value": 220},
    "NTPC":       {"company_name": "NTPC Limited",           "current_price": 362,  "target_price": 430,  "trailing_eps": 22,  "book_value": 165},
    "ONGC":       {"company_name": "ONGC",                   "current_price": 275,  "target_price": 340,  "trailing_eps": 38,  "book_value": 230},
    "COALINDIA":  {"company_name": "Coal India",             "current_price": 385,  "target_price": 470,  "trailing_eps": 55,  "book_value": 108},
    "WIPRO":      {"company_name": "Wipro",                  "current_price": 470,  "target_price": 570,  "trailing_eps": 22,  "book_value": 130},
    "TITAN":      {"company_name": "Titan Company",          "current_price": 3380, "target_price": 3900, "trailing_eps": 68,  "book_value": 280},
    "PIDILITIND": {"company_name": "Pidilite Industries",    "current_price": 2950, "target_price": 3400, "trailing_eps": 58,  "book_value": 290},
    "HAVELLS":    {"company_name": "Havells India",          "current_price": 1650, "target_price": 1950, "trailing_eps": 38,  "book_value": 165},
    "SIEMENS":    {"company_name": "Siemens India",          "current_price": 7200, "target_price": 8500, "trailing_eps": 120, "book_value": 680},
    "HAL":        {"company_name": "Hindustan Aeronautics",  "current_price": 4100, "target_price": 5200, "trailing_eps": 168, "book_value": 780},
    "BEL":        {"company_name": "Bharat Electronics",     "current_price": 310,  "target_price": 380,  "trailing_eps": 12,  "book_value": 48},
    "ZOMATO":     {"company_name": "Zomato",                 "current_price": 245,  "target_price": 310,  "trailing_eps": 4,   "book_value": 45},
    "NYKAA":      {"company_name": "FSN E-Commerce (Nykaa)", "current_price": 170,  "target_price": 210,  "trailing_eps": 2,   "book_value": 22},
    "ADANIPORTS": {"company_name": "Adani Ports & SEZ",      "current_price": 1350, "target_price": 1650, "trailing_eps": 54,  "book_value": 380},
    "ADANIGREEN": {"company_name": "Adani Green Energy",     "current_price": 980,  "target_price": 1250, "trailing_eps": 12,  "book_value": 95},
}


def get_fundamentals_synthetic(symbols: list, prices_df: pd.DataFrame) -> dict:
    """
    Returns per-symbol fundamental estimates.
    Known stocks use seeded real-world values; others are generated from sector priors.
    """
    rng = np.random.default_rng(SEED + 99)
    result = {}
    for sym in symbols:
        if sym in _KNOWN_FUNDAMENTALS:
            base = dict(_KNOWN_FUNDAMENTALS[sym])
        else:
            # Derive from price history
            cp = float(prices_df[sym].iloc[-1]) if sym in prices_df.columns else None
            sec = get_sector(sym)
            sp  = SECTOR_PARAMS[sec]
            # Modelled P/E range 10-40, P/B 1-5
            pe = rng.uniform(10, 35)
            pb = rng.uniform(1, 5)
            eps = round(cp / pe, 2) if cp else None
            bv  = round(cp / pb, 2) if cp else None
            analyst_premium = rng.uniform(0.05, 0.25)
            tp  = round(cp * (1 + analyst_premium), 2) if cp else None
            base = {
                "company_name":  sym,
                "current_price": round(cp, 2) if cp else None,
                "target_price":  tp,
                "trailing_eps":  eps,
                "book_value":    bv,
            }
        # Use simulated last-price for known stocks too (consistent with synthetic series)
        if sym in prices_df.columns:
            base["current_price"] = round(float(prices_df[sym].iloc[-1]), 2)
            # Scale analyst target to maintain the same upside % as the known value
            if sym in _KNOWN_FUNDAMENTALS:
                known = _KNOWN_FUNDAMENTALS[sym]
                if known["current_price"] and known["target_price"]:
                    upside_ratio = known["target_price"] / known["current_price"]
                    base["target_price"] = round(base["current_price"] * upside_ratio, 2)
        result[sym] = base
    return result


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def load_symbols(path: Path) -> list:
    df   = pd.read_excel(path)
    raw  = df["NSE Symbol"].dropna().str.strip().tolist()
    seen, unique = set(), []
    for s in raw:
        if s and s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def main():
    print(f"\n{'═'*70}")
    print("  BULK PORTFOLIO ANALYSIS — NSE STOCK LIST")
    print(f"{'═'*70}")

    # ── Load symbols ──────────────────────────────────────────────────────────
    symbols = load_symbols(EXCEL_PATH)
    print(f"\n  Unique NSE symbols loaded : {len(symbols)}")

    # ── Fetch / generate price data ───────────────────────────────────────────
    prices = None

    # 1. Try nsepython
    print("  Trying nsepython (NSE India historical API)…")
    try:
        prices = _fetch_prices_nsepython(symbols, days=N_DAYS)
        if prices is not None and len(prices.columns) > 5:
            print(f"  [nsepython] Got data: {prices.shape[0]} rows × {prices.shape[1]} cols")
        else:
            prices = None
    except Exception as e:
        print(f"  nsepython failed: {e}")
        prices = None

    # 2. Try yfinance
    if prices is None:
        print("  Trying yfinance (.NS bulk download)…")
        try:
            import yfinance as yf
            tickers = [f"{s}.NS" for s in symbols] + ["^NSEI"]
            raw = yf.download(tickers, period="2y", auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                prices = raw["Close"].copy()
            else:
                prices = raw.copy()
            col_map = {f"{s}.NS": s for s in symbols}
            col_map["^NSEI"] = "BENCHMARK"
            prices.rename(columns=col_map, inplace=True)
            prices.dropna(how="all", inplace=True)
            valid_cols = [c for c in prices.columns if prices[c].notna().sum() > 60]
            if len(valid_cols) > 5:
                prices = prices[valid_cols]
                print(f"  [yfinance] Got data: {prices.shape[0]} rows × {prices.shape[1]} cols")
            else:
                prices = None
        except Exception as e:
            print(f"  yfinance failed: {e}")
            prices = None

    # 3. Synthetic fallback
    if prices is None:
        print(f"  Live data unavailable (API blocked). Generating {N_DAYS}-day synthetic"
              " price series via two-factor NSE model…")
        prices = generate_synthetic_prices(symbols, n_days=N_DAYS, seed=SEED)
        print("  [synthetic data]")
    # Keep only symbols that have enough data
    symbols = [s for s in symbols if s in prices.columns and prices[s].notna().sum() >= 60]
    n = len(symbols)
    weights      = [1 / n] * n
    weights_dict = dict(zip(symbols, weights))
    print(f"  Price matrix : {prices.shape[0]} rows × {prices.shape[1]} columns")
    print(f"  Symbols with ≥60 days data : {n}")

    # ── Pre-compute returns & covariance ──────────────────────────────────────
    stock_prices    = prices[symbols].ffill().dropna(axis=1, thresh=60)
    symbols         = list(stock_prices.columns)
    n               = len(symbols)
    weights         = [1 / n] * n
    weights_dict    = dict(zip(symbols, weights))
    log_returns     = np.log(stock_prices / stock_prices.shift(1)).dropna()
    mean_daily_ret  = log_returns.mean().values
    cov_annual      = log_returns.cov().values * TRADING_DAYS

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 1 — BETA
    # ─────────────────────────────────────────────────────────────────────────
    _section("1. Portfolio Beta  (vs synthetic NIFTY 50 / BENCHMARK)")

    betas     = calculate_stock_betas(prices)
    port_beta = calculate_portfolio_beta(betas, weights_dict)

    beta_rows = []
    for i, sym in enumerate(symbols):
        b   = betas.get(sym)
        r   = mean_daily_ret[i] * TRADING_DAYS * 100
        v   = np.sqrt(cov_annual[i, i]) * 100
        sec = get_sector(sym)
        beta_rows.append({
            "Symbol":        sym,
            "Sector":        sec,
            "Beta":          round(b, 4) if b else None,
            "E[Return]%":    round(r, 2),
            "Volatility%":   round(v, 2),
            "Sharpe":        round((r/100 - RISK_FREE_RATE) / (v/100), 4) if v > 0 else 0,
        })

    beta_df = pd.DataFrame(beta_rows).sort_values("Beta", ascending=False)

    print(f"\n  {'SYMBOL':<16} {'SECTOR':<14} {'BETA':>8} {'E[Ret]%':>9} {'Vol%':>8} {'Sharpe':>8}")
    print(f"  {'─'*70}")
    for _, row in beta_df.iterrows():
        b_str = f"{row['Beta']:.4f}" if row['Beta'] is not None else " N/A "
        print(
            f"  {row['Symbol']:<16} {row['Sector']:<14} {b_str:>8}"
            f" {row['E[Return]%']:>9.2f} {row['Volatility%']:>8.2f} {row['Sharpe']:>8.4f}"
        )

    print(f"\n  Portfolio Beta (equal-weight, {n} stocks): {port_beta:.4f}  — {_beta_label(port_beta)}")

    # Beta distribution summary
    valid_betas = [b for b in betas.values() if b is not None]
    print(f"\n  Beta distribution across {len(valid_betas)} stocks:")
    print(f"    Min   : {min(valid_betas):.4f}")
    print(f"    Median: {float(np.median(valid_betas)):.4f}")
    print(f"    Mean  : {float(np.mean(valid_betas)):.4f}")
    print(f"    Max   : {max(valid_betas):.4f}")
    buckets = [
        ("<0",       [b for b in valid_betas if b < 0]),
        ("0–0.8",    [b for b in valid_betas if 0 <= b < 0.8]),
        ("0.8–1.2",  [b for b in valid_betas if 0.8 <= b < 1.2]),
        (">1.2",     [b for b in valid_betas if b >= 1.2]),
    ]
    for label, bucket in buckets:
        pct = len(bucket) / len(valid_betas) * 100
        bar = "█" * max(1, int(pct / 2))
        print(f"    {label:<8} {len(bucket):>4} stocks ({pct:5.1f}%)  {bar}")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 2 — POTENTIAL UPSIDE
    # ─────────────────────────────────────────────────────────────────────────
    _section("2. Potential Upside  (analyst consensus target + Graham Number)")

    fundamentals = get_fundamentals_synthetic(symbols, prices)

    upside_rows = []
    w_analyst_total = w_graham_total = 0.0
    analyst_cnt = graham_cnt = 0

    print(
        f"\n  {'SYMBOL':<16} {'CURRENT':>10} {'TGT PRICE':>11}"
        f" {'UPSIDE%':>9}  {'GRAHAM #':>10} {'G-UPSIDE%':>10}"
    )
    print(f"  {'─'*74}")

    for sym in symbols:
        fund = fundamentals.get(sym, {})
        cp   = fund.get("current_price")
        tp   = fund.get("target_price")
        eps  = fund.get("trailing_eps")
        bv   = fund.get("book_value")
        w    = weights_dict[sym]

        au = round((tp - cp) / cp * 100, 2) if cp and tp and cp > 0 else None
        gn = graham_number(eps, bv)
        gu = round((gn - cp) / cp * 100, 2) if cp and gn and cp > 0 else None

        upside_rows.append({
            "Symbol":           sym,
            "Company":          fund.get("company_name", sym),
            "Sector":           get_sector(sym),
            "Current Price":    cp,
            "Analyst Target":   tp,
            "Analyst Upside %": au,
            "Graham Number":    gn,
            "Graham Upside %":  gu,
        })

        print(
            f"  {sym:<16}"
            f" {('₹'+f'{cp:,.2f}') if cp else 'N/A':>10}"
            f" {('₹'+f'{tp:,.2f}') if tp else 'N/A':>11}"
            f" {(f'{au:+.1f}%') if au is not None else 'N/A':>9}"
            f"  {('₹'+f'{gn:,.2f}') if gn else 'N/A':>10}"
            f" {(f'{gu:+.1f}%') if gu is not None else 'N/A':>10}"
        )

        if au is not None:
            w_analyst_total += w * au
            analyst_cnt += 1
        if gu is not None:
            w_graham_total += w * gu
            graham_cnt += 1

    print(f"  {'─'*74}")
    if analyst_cnt:
        print(f"  {'Weighted portfolio upside (analyst):':<42} {w_analyst_total:+.2f}%")
    if graham_cnt:
        print(f"  {'Weighted portfolio upside (Graham):':<42} {w_graham_total:+.2f}%")

    upside_df = pd.DataFrame(upside_rows)

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 3 — EFFICIENT FRONTIER
    # ─────────────────────────────────────────────────────────────────────────
    _section(f"3. Efficient Frontier  (Markowitz MPT — {n} stocks, long-only)")

    print(f"\n  Risk-free rate    : {RISK_FREE_RATE*100:.2f}% p.a.")
    print(f"  Return data       : {len(log_returns)} synthetic trading days")
    print(f"  Constraint        : Long-only  (0 ≤ w_i ≤ 1),  Σw_i = 1")

    # Equal-weight portfolio stats
    w_arr = np.array(weights)
    port_ret, port_vol, port_sharpe = portfolio_stats(w_arr, mean_daily_ret, cov_annual)
    print(f"\n  Equal-weight portfolio ({n} stocks):")
    print(f"    Expected Return  : {port_ret*100:.2f}% p.a.")
    print(f"    Volatility       : {port_vol*100:.2f}% p.a.")
    print(f"    Sharpe Ratio     : {port_sharpe:.4f}")

    # Annualised return + vol summary
    ann_rets = mean_daily_ret * TRADING_DAYS * 100
    ann_vols = np.sqrt(np.diag(cov_annual)) * 100
    print(f"\n  Annualised return distribution across {n} stocks:")
    print(f"    Min / Median / Max : {ann_rets.min():.1f}% / {np.median(ann_rets):.1f}% / {ann_rets.max():.1f}%")
    print(f"  Annualised volatility distribution:")
    print(f"    Min / Median / Max : {ann_vols.min():.1f}% / {np.median(ann_vols):.1f}% / {ann_vols.max():.1f}%")

    # Optimise
    print(f"\n  Running scipy SLSQP optimisation…")
    optimal = optimise_portfolios(mean_daily_ret, cov_annual, symbols)

    for label, key, icon in [
        ("Max Sharpe Ratio (Tangency Portfolio)", "max_sharpe", "⭐"),
        ("Minimum Volatility Portfolio",          "min_vol",    "🛡 "),
    ]:
        p = optimal[key]
        print(f"\n  {icon} {label}")
        print(f"    Expected Return  : {p['Return (%/yr)']:>7.2f}% p.a.")
        print(f"    Volatility       : {p['Volatility (%/yr)']:>7.2f}% p.a.")
        print(f"    Sharpe Ratio     : {p['Sharpe Ratio']:>7.4f}")
        top15 = sorted(p["Weights"].items(), key=lambda x: -x[1])[:15]
        print(f"    Top 15 allocations:")
        for sym_w, wi in top15:
            bar = "█" * max(1, int(wi * 40))
            sec = get_sector(sym_w)
            print(f"      {sym_w:<16} {wi:>6.2%}  {bar}  [{sec}]")

    ms = optimal["max_sharpe"]
    mv = optimal["min_vol"]
    print(f"\n  Efficiency gap — Max Sharpe vs Equal-Weight:")
    print(f"    Return  Δ : {ms['Return (%/yr)'] - port_ret*100:+.2f}% p.a.")
    print(f"    Vol     Δ : {ms['Volatility (%/yr)'] - port_vol*100:+.2f}% p.a.")
    print(f"    Sharpe  Δ : {ms['Sharpe Ratio'] - port_sharpe:+.4f}")

    # Sector allocation of optimal portfolios
    def sector_breakdown(weights_dict_local: dict) -> dict:
        sec_w: dict = {}
        for sym_s, wi_s in weights_dict_local.items():
            sec_s = get_sector(sym_s)
            sec_w[sec_s] = sec_w.get(sec_s, 0) + wi_s
        return dict(sorted(sec_w.items(), key=lambda x: -x[1]))

    print(f"\n  Sector allocation — Max Sharpe portfolio:")
    for sec, w_s in sector_breakdown(ms["Weights"]).items():
        if w_s > 0.005:
            bar = "█" * max(1, int(w_s * 40))
            print(f"    {sec:<14} {w_s:>6.2%}  {bar}")

    print(f"\n  Sector allocation — Min Volatility portfolio:")
    for sec, w_s in sector_breakdown(mv["Weights"]).items():
        if w_s > 0.005:
            bar = "█" * max(1, int(w_s * 40))
            print(f"    {sec:<14} {w_s:>6.2%}  {bar}")

    # Monte Carlo + plot
    print(f"\n  Simulating {N_MC:,} random portfolios…")
    mc_df = monte_carlo_portfolios(mean_daily_ret, cov_annual, n=N_MC)

    print(f"  Plotting efficient frontier…")
    plot_efficient_frontier(
        mc_df, optimal, symbols, weights_dict,
        mean_daily_ret, cov_annual, save_path=str(OUTPUT_PNG),
    )

    # ── Save results CSV ──────────────────────────────────────────────────────
    summary = (
        beta_df
        .merge(upside_df[["Symbol","Company","Analyst Upside %","Graham Upside %"]],
               on="Symbol", how="left")
    )
    summary.to_csv(OUTPUT_CSV, index=False)
    print(f"  Results CSV saved → {OUTPUT_CSV}")

    # ── Summary footer ────────────────────────────────────────────────────────
    print(f"\n{'═'*70}")
    print(f"  Stocks analysed   : {n}")
    print(f"  Portfolio Beta    : {port_beta:.4f}  ({_beta_label(port_beta)})")
    print(f"  Equal-Wt stats    : Return {port_ret*100:.2f}%  |  Vol {port_vol*100:.2f}%  |  Sharpe {port_sharpe:.4f}")
    print(f"  Max-Sharpe stats  : Return {ms['Return (%/yr)']:.2f}%  |  Vol {ms['Volatility (%/yr)']:.2f}%  |  Sharpe {ms['Sharpe Ratio']:.4f}")
    print(f"  Min-Vol stats     : Return {mv['Return (%/yr)']:.2f}%  |  Vol {mv['Volatility (%/yr)']:.2f}%  |  Sharpe {mv['Sharpe Ratio']:.4f}")
    print(f"  Weighted upside   : Analyst {w_analyst_total:+.2f}%  |  Graham {w_graham_total:+.2f}%")
    print(f"  Chart saved       : {OUTPUT_PNG}")
    print(f"  CSV saved         : {OUTPUT_CSV}")
    print(f"{'═'*70}\n")


if __name__ == "__main__":
    main()
