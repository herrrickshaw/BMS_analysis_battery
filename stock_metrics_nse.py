"""
stock_metrics_nse.py
====================
Extracts NSE corporate announcements/news and calculates four
stock-analysis metrics:

  1. NSE Corporate Announcements (news feed)
  2. PEG Ratio        = Trailing P/E  ÷  EPS Annual Growth Rate (%)
  3. PE × PB Ratio    = Price-to-Earnings × Price-to-Book
  4. RSI              = Relative Strength Index (Wilder, default 14-period)

Libraries:
    pip install "nse[local]" yfinance pandas requests

Usage (CLI):
    python stock_metrics_nse.py RELIANCE
    python stock_metrics_nse.py TCS --rsi-period 21 --news 5

Usage (import):
    from stock_metrics_nse import run_metrics
    result = run_metrics("INFY")
"""

import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

warnings.filterwarnings("ignore")

try:
    from nse import NSE
except ImportError:
    sys.exit("Install the NSE library:  pip install 'nse[local]'")

try:
    import yfinance as yf
except ImportError:
    sys.exit("Install yfinance:  pip install yfinance")


DOWNLOAD_DIR = Path("./nse_bse_data")
DOWNLOAD_DIR.mkdir(exist_ok=True)

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1.  NSE CORPORATE ANNOUNCEMENTS / NEWS
# ─────────────────────────────────────────────────────────────────────────────

def fetch_nse_news(symbol: str, limit: int = 10) -> list:
    """
    Fetches recent corporate announcements from NSE India for *symbol*.

    Returns a list of dicts with keys: date, subject, category, attachment.
    Falls back to an empty list on any network / parse error.
    """
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)

    try:
        # Prime session cookies so the subsequent API call is accepted
        session.get("https://www.nseindia.com", timeout=12)
    except Exception:
        pass

    url = (
        "https://www.nseindia.com/api/corporate-announcements"
        f"?index=equities&symbol={symbol}"
    )

    try:
        resp = session.get(url, timeout=12)
        resp.raise_for_status()
        data = resp.json()

        news_items = []
        for item in data[:limit]:
            news_items.append({
                "date":       (item.get("an_dt") or item.get("date") or "—")[:10],
                "subject":    item.get("subject") or item.get("desc") or "—",
                "category":   item.get("categoryColumn") or item.get("category") or "—",
                "attachment": item.get("attchmntFile") or "",
            })
        return news_items

    except Exception as exc:
        print(f"  [NSE News error] {exc}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 2.  RSI — RELATIVE STRENGTH INDEX
# ─────────────────────────────────────────────────────────────────────────────

def calculate_rsi(prices: list, period: int = 14) -> float:
    """
    Wilder's RSI over *period* bars.

    Parameters
    ----------
    prices : list[float]  – closing prices, oldest first
    period : int          – look-back window (default 14)

    Returns
    -------
    float or None if there are fewer than period + 1 data points.
    """
    if len(prices) < period + 1:
        return None

    s = pd.Series(prices, dtype=float)
    delta = s.diff().dropna()

    gains  = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)

    # Wilder's smoothing ≡ EWM with alpha = 1/period  (com = period - 1)
    avg_gain = gains.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = losses.ewm(com=period - 1, min_periods=period).mean()

    rs  = avg_gain / avg_loss.replace(0.0, float("nan"))
    rsi = 100.0 - (100.0 / (1.0 + rs))

    return round(float(rsi.iloc[-1]), 2)


def _prices_from_nse(nse: NSE, symbol: str, days: int = 120) -> list:
    """Returns a list of closing prices from NSE historical data (oldest first)."""
    try:
        end   = datetime.today()
        start = end - timedelta(days=days)
        data  = nse.fetch_equity_historical_data(symbol=symbol, from_date=start, to_date=end) or []
        prices = []
        for rec in data:
            close = rec.get("CH_CLOSING_PRICE") or rec.get("close")
            if close:
                prices.append(float(close))
        return prices
    except Exception as exc:
        print(f"  [NSE historical prices error] {exc}")
        return []


def _prices_from_yfinance(symbol: str, period: str = "6mo") -> list:
    """Returns a list of closing prices from yfinance (.NS suffix)."""
    try:
        hist = yf.Ticker(f"{symbol}.NS").history(period=period)
        return hist["Close"].dropna().tolist()
    except Exception as exc:
        print(f"  [yfinance prices error] {exc}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 3.  FUNDAMENTAL DATA
# ─────────────────────────────────────────────────────────────────────────────

def fetch_fundamentals(symbol: str) -> dict:
    """
    Retrieves fundamental metrics from yfinance for an NSE-listed stock.

    Keys returned:
        pe_ratio, pb_ratio, eps, eps_growth (decimal),
        forward_pe, peg_ratio_native,
        market_cap, company_name, sector, industry
    """
    try:
        info = yf.Ticker(f"{symbol}.NS").info
        return {
            "pe_ratio":         info.get("trailingPE"),
            "pb_ratio":         info.get("priceToBook"),
            "eps":              info.get("trailingEps"),
            "eps_growth":       info.get("earningsGrowth"),   # e.g. 0.15 = 15%
            "forward_pe":       info.get("forwardPE"),
            "peg_ratio_native": info.get("pegRatio"),
            "market_cap":       info.get("marketCap"),
            "company_name":     info.get("longName") or info.get("shortName"),
            "sector":           info.get("sector"),
            "industry":         info.get("industry"),
        }
    except Exception as exc:
        print(f"  [yfinance fundamentals error] {exc}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 4.  METRIC CALCULATIONS
# ─────────────────────────────────────────────────────────────────────────────

def calculate_peg_ratio(pe: float, eps_growth_pct: float) -> float:
    """
    PEG Ratio = Trailing P/E ÷ EPS Annual Growth Rate (expressed as %)

    Example: PE=25, EPS growth=20% → PEG = 25/20 = 1.25

    Returns None when PE or growth is missing / zero.
    """
    if pe is None or eps_growth_pct is None or eps_growth_pct == 0:
        return None
    return round(float(pe) / float(eps_growth_pct), 4)


def calculate_pe_x_pb(pe: float, pb: float) -> float:
    """
    PE × PB combined valuation metric.

    Benjamin Graham's rule of thumb: PE × PB < 22.5 suggests a margin of safety.
    Returns None when either input is missing.
    """
    if pe is None or pb is None:
        return None
    return round(float(pe) * float(pb), 4)


# ─────────────────────────────────────────────────────────────────────────────
# 5.  DISPLAY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _section(title: str):
    w = 64
    print(f"\n{'─' * w}")
    print(f"  {title.upper()}")
    print(f"{'─' * w}")


def _row(label: str, value, width: int = 34):
    v = str(value) if value is not None else "N/A"
    print(f"  {label:<{width}} {v}")


def _interpret_rsi(rsi: float) -> str:
    if rsi >= 70:
        return "Overbought ▲ — momentum may reverse downward"
    if rsi <= 30:
        return "Oversold  ▼ — momentum may reverse upward"
    if rsi >= 60:
        return "Bullish momentum"
    if rsi <= 40:
        return "Bearish momentum"
    return "Neutral zone"


def _interpret_peg(peg: float) -> str:
    if peg < 0:
        return "Negative growth — caution"
    if peg < 1.0:
        return "Potentially undervalued relative to growth"
    if peg <= 1.5:
        return "Fairly valued"
    if peg <= 2.0:
        return "Slightly overvalued"
    return "Overvalued relative to growth"


def _interpret_pe_x_pb(val: float) -> str:
    if val < 22.5:
        return "Below Graham's 22.5 threshold — fair/undervalued"
    return "Above Graham's 22.5 threshold — monitor for overvaluation"


# ─────────────────────────────────────────────────────────────────────────────
# 6.  MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_metrics(symbol: str, rsi_period: int = 14, news_limit: int = 10) -> dict:
    """
    Runs the full metrics pipeline for *symbol* and prints a formatted report.

    Returns a dict with all computed values for programmatic use.
    """
    symbol = symbol.upper().strip()

    print(f"\n{'═' * 64}")
    print(f"  📊  NSE STOCK METRICS REPORT — {symbol}")
    print(f"  ⏱   {datetime.now().strftime('%d %b %Y  %H:%M:%S')}")
    print(f"{'═' * 64}")

    # ── 1. NEWS ──────────────────────────────────────────────────────────────
    _section("NSE Corporate Announcements / News")
    news = fetch_nse_news(symbol, limit=news_limit)
    if news:
        for item in news:
            subj = item["subject"][:68]
            print(f"  [{item['date']}]  {subj}")
            cat = item["category"]
            if cat and cat != "—":
                print(f"  {'':14}  Category: {cat}")
    else:
        print("  No recent announcements found.")

    # ── 2. FUNDAMENTALS ──────────────────────────────────────────────────────
    _section("Fundamental Data  (via yfinance / NSE .NS)")
    fund = fetch_fundamentals(symbol)

    _row("Company",            fund.get("company_name"))
    _row("Sector",             fund.get("sector"))
    _row("Industry",           fund.get("industry"))

    pe            = fund.get("pe_ratio")
    pb            = fund.get("pb_ratio")
    eps           = fund.get("eps")
    eps_growth_raw = fund.get("eps_growth")                    # decimal
    eps_growth_pct = (eps_growth_raw * 100) if eps_growth_raw is not None else None

    _row("Trailing P/E",        f"{pe:.2f}"               if pe  is not None else None)
    _row("Price-to-Book (P/B)", f"{pb:.2f}"               if pb  is not None else None)
    _row("Trailing EPS (₹)",    f"{eps:.2f}"              if eps is not None else None)
    _row("EPS Growth YoY",      f"{eps_growth_pct:.2f}%"  if eps_growth_pct is not None else None)
    _row("Forward P/E",         f"{fund.get('forward_pe'):.2f}" if fund.get("forward_pe") is not None else None)

    # ── 3. PEG RATIO ─────────────────────────────────────────────────────────
    _section("PEG Ratio  =  Trailing P/E  ÷  EPS Growth (%)")
    peg        = calculate_peg_ratio(pe, eps_growth_pct)
    native_peg = fund.get("peg_ratio_native")

    if peg is not None:
        _row("PEG (calculated)", f"{peg:.4f}  →  {_interpret_peg(peg)}")
    else:
        _row("PEG (calculated)", "N/A — P/E or EPS growth data unavailable")

    if native_peg is not None:
        _row("PEG (yfinance)",   f"{native_peg:.4f}  (cross-check)")
    else:
        _row("PEG (yfinance)",   "N/A")

    print(
        "\n  Formula: PEG = P/E ÷ annual_EPS_growth_pct\n"
        "  Rule of thumb: PEG < 1 → undervalued, PEG = 1 → fairly valued, PEG > 1 → overvalued"
    )

    # ── 4. PE × PB ───────────────────────────────────────────────────────────
    _section("PE × PB  (Combined Valuation Metric)")
    pe_x_pb = calculate_pe_x_pb(pe, pb)

    if pe_x_pb is not None:
        _row("PE × PB", f"{pe_x_pb:.4f}  →  {_interpret_pe_x_pb(pe_x_pb)}")
    else:
        _row("PE × PB", "N/A — P/E or P/B data unavailable")

    print(
        "\n  Benjamin Graham's threshold: PE × PB < 22.5 suggests a margin of safety.\n"
        "  High values indicate the stock is priced richly on both earnings & book value."
    )

    # ── 5. RSI ───────────────────────────────────────────────────────────────
    _section(f"RSI  (Relative Strength Index, {rsi_period}-period Wilder)")

    with NSE(download_folder=str(DOWNLOAD_DIR), server=False) as nse:
        prices = _prices_from_nse(nse, symbol, days=120)

    if len(prices) < rsi_period + 1:
        print(f"  NSE returned {len(prices)} data points — falling back to yfinance…")
        prices = _prices_from_yfinance(symbol, period="6mo")

    rsi_val = calculate_rsi(prices, period=rsi_period)

    _row("Price data points",  len(prices))
    if rsi_val is not None:
        _row(f"RSI ({rsi_period})", f"{rsi_val:.2f}  →  {_interpret_rsi(rsi_val)}")
    else:
        _row(f"RSI ({rsi_period})", "N/A — insufficient price history")

    print(
        f"\n  RSI scale: 0–30 Oversold | 30–70 Neutral | 70–100 Overbought\n"
        f"  Formula: RSI = 100 − 100 / (1 + avg_gain / avg_loss)  over {rsi_period} periods"
    )

    # ── FOOTER ───────────────────────────────────────────────────────────────
    print(f"\n{'═' * 64}")
    print("  Data: NSE India (announcements/prices) | yfinance (fundamentals)")
    print(f"{'═' * 64}\n")

    return {
        "symbol":          symbol,
        "company_name":    fund.get("company_name"),
        "pe_ratio":        pe,
        "pb_ratio":        pb,
        "eps":             eps,
        "eps_growth_pct":  eps_growth_pct,
        "peg_ratio":       peg,
        "pe_x_pb":         pe_x_pb,
        "rsi":             rsi_val,
        "rsi_period":      rsi_period,
        "news_count":      len(news),
        "news":            news,
    }


def run_batch(symbols: list, rsi_period: int = 14) -> pd.DataFrame:
    """
    Runs metrics for a list of NSE symbols and returns a summary DataFrame.

    Example:
        df = run_batch(["RELIANCE", "TCS", "INFY"])
        print(df.to_string())
    """
    rows = []
    for sym in symbols:
        try:
            result = run_metrics(sym, rsi_period=rsi_period, news_limit=3)
            rows.append({
                "Symbol":      result["symbol"],
                "Company":     result.get("company_name") or "—",
                "PE":          result.get("pe_ratio"),
                "PB":          result.get("pb_ratio"),
                "EPS Growth%": result.get("eps_growth_pct"),
                "PEG":         result.get("peg_ratio"),
                "PE×PB":       result.get("pe_x_pb"),
                f"RSI({rsi_period})": result.get("rsi"),
            })
        except Exception as exc:
            print(f"  [batch error for {sym}] {exc}")
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    # Strip Jupyter/Colab internal args before parsing
    _clean_argv = [sys.argv[0]]
    _i = 1
    while _i < len(sys.argv):
        arg = sys.argv[_i]
        if arg == "-f" and _i + 1 < len(sys.argv):
            _i += 2
        elif arg.startswith("/root/.local/share/jupyter/runtime/kernel-"):
            _i += 1
        else:
            _clean_argv.append(arg)
            _i += 1

    parser = argparse.ArgumentParser(
        description="NSE Stock Metrics: News, PEG Ratio, PE×PB, RSI"
    )
    parser.add_argument(
        "symbol",
        nargs="?",
        default="RELIANCE",
        help="NSE ticker symbol  (default: RELIANCE)",
    )
    parser.add_argument(
        "--rsi-period",
        type=int,
        default=14,
        help="RSI look-back period  (default: 14)",
    )
    parser.add_argument(
        "--news",
        type=int,
        default=10,
        help="Number of news items to display  (default: 10)",
    )
    parser.add_argument(
        "--batch",
        nargs="+",
        metavar="SYM",
        help="Run batch mode for multiple symbols, e.g. --batch TCS INFY WIPRO",
    )

    args = parser.parse_args(_clean_argv[1:])

    if args.batch:
        summary_df = run_batch(args.batch, rsi_period=args.rsi_period)
        print("\n" + "═" * 64)
        print("  BATCH SUMMARY")
        print("═" * 64)
        print(summary_df.to_string(index=False))
    else:
        run_metrics(args.symbol, rsi_period=args.rsi_period, news_limit=args.news)
