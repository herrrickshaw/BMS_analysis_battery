"""
portfolio_analysis.py
=====================
Portfolio analytics for NSE-listed stocks using Modern Portfolio Theory (MPT):

  1. Portfolio Beta       – weighted sensitivity to the market (NIFTY 50)
  2. Potential Upside     – analyst price-target gap + Graham Number fair value
  3. Efficient Frontier   – Markowitz mean-variance optimisation
     • Monte Carlo simulation of random portfolio cloud
     • Minimum-variance portfolio
     • Maximum Sharpe-ratio portfolio (tangent portfolio)
     • Analytical efficient frontier curve

Libraries:
    pip install yfinance pandas numpy scipy matplotlib

Usage (CLI):
    python portfolio_analysis.py --symbols RELIANCE TCS INFY --weights 0.4 0.35 0.25
    python portfolio_analysis.py --symbols RELIANCE TCS INFY WIPRO HDFCBANK

Usage (import):
    from portfolio_analysis import run_portfolio_analysis
    result = run_portfolio_analysis(
        symbols=["RELIANCE", "TCS", "INFY"],
        weights=[0.4, 0.35, 0.25],
    )
"""

import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    sys.exit("Install yfinance:  pip install yfinance")

try:
    from scipy.optimize import minimize
except ImportError:
    sys.exit("Install scipy:  pip install scipy")


BENCHMARK = "^NSEI"      # NIFTY 50
RISK_FREE_RATE = 0.065   # ~6.5% India 10-yr G-Sec proxy
N_PORTFOLIOS = 8_000     # Monte Carlo portfolios for scatter cloud
PRICE_PERIOD = "2y"      # Historical window for return estimation
TRADING_DAYS = 252


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

def _yf_symbol(sym: str) -> str:
    """Append .NS for NSE stocks unless the symbol already has an exchange suffix."""
    if "." in sym or sym.startswith("^"):
        return sym
    return f"{sym}.NS"


def _fetch_prices_nsepython(
    symbols: list,
    benchmark_sym: str = "NIFTY 50",
    days: int = 504,
) -> pd.DataFrame | None:
    """
    Fetches closing prices via nsepython's equity_history + index_history.

    Returns a DataFrame (symbol columns + BENCHMARK) or None on failure.
    nsepython hits NSE India's official historical data API.
    """
    try:
        from nsepython import equity_history, index_history
        from datetime import datetime, timedelta

        end_dt   = datetime.today()
        start_dt = end_dt - timedelta(days=days)
        end_s    = end_dt.strftime("%d-%m-%Y")
        start_s  = start_dt.strftime("%d-%m-%Y")

        all_series: dict[str, pd.Series] = {}

        for sym in symbols:
            try:
                df = equity_history(sym, "EQ", start_s, end_s)
                if df is not None and not df.empty and "CH_CLOSING_PRICE" in df.columns:
                    df["date"] = pd.to_datetime(df["CH_TIMESTAMP"])
                    df = df.sort_values("date").set_index("date")
                    all_series[sym] = df["CH_CLOSING_PRICE"].astype(float)
            except Exception:
                pass

        if not all_series:
            return None

        # Benchmark (NIFTY 50)
        try:
            bdf = index_history(benchmark_sym, start_s, end_s)
            if bdf is not None and not bdf.empty:
                bdf = pd.DataFrame(bdf)
                bdf["date"] = pd.to_datetime(bdf["HistoricalDate"], dayfirst=True)
                bdf = bdf.sort_values("date").set_index("date")
                close_col = next(
                    (c for c in bdf.columns if "close" in c.lower()), None
                )
                if close_col:
                    all_series["BENCHMARK"] = bdf[close_col].astype(float)
        except Exception:
            pass

        prices = pd.DataFrame(all_series)
        prices.dropna(how="all", inplace=True)
        return prices if len(prices) > 10 else None

    except ImportError:
        return None
    except Exception:
        return None


# nsepython days-of-history per yfinance `period` string, used only for the
# nsepython data-source attempt below.
_PERIOD_DAYS = {
    "1mo": 35,  "3mo": 95,  "6mo": 190,
    "1y":  380, "2y":  760, "3y":  1140, "5y": 1900,
}


def fetch_prices(symbols: list, benchmark: str = BENCHMARK, period: str = PRICE_PERIOD) -> pd.DataFrame:
    """
    Downloads adjusted closing prices for *symbols* and *benchmark*.

    Attempts data sources in order:
      1. nsepython (equity_history + index_history via NSE India API)
      2. yfinance  (.NS suffix, bulk download)

    Returns a DataFrame with one column per ticker; benchmark column is labelled
    "BENCHMARK".  Rows with all-NaN are dropped.
    """
    # ── 1. nsepython ────────────────────────────────────────────────────────
    prices_nse = _fetch_prices_nsepython(symbols, days=_PERIOD_DAYS.get(period, 760))
    if prices_nse is not None and len(prices_nse.columns) > 1:
        print("  [data source: nsepython]")
        if "BENCHMARK" not in prices_nse.columns:
            prices_nse["BENCHMARK"] = float("nan")
        for s in symbols:
            if s not in prices_nse.columns:
                prices_nse[s] = float("nan")
        return prices_nse

    # ── 2. yfinance fallback ────────────────────────────────────────────────
    print("  [data source: yfinance]")
    tickers = [_yf_symbol(s) for s in symbols] + [benchmark]
    raw = yf.download(tickers, period=period, auto_adjust=True, progress=False)

    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"].copy()
    else:
        prices = raw.copy()

    # Re-label columns: original symbols + BENCHMARK
    col_map = {_yf_symbol(s): s for s in symbols}
    col_map[benchmark] = "BENCHMARK"
    prices.rename(columns=col_map, inplace=True)

    prices.dropna(how="all", inplace=True)
    return prices


def fetch_fundamentals_bulk(symbols: list) -> dict:
    """
    Fetches fundamental data for each symbol via yfinance.

    Returns dict of symbol → {currentPrice, targetMeanPrice, trailingEps,
                               bookValue, market_cap, sector, pe_ratio, …}
    """
    result = {}
    for sym in symbols:
        try:
            info = yf.Ticker(_yf_symbol(sym)).info
            result[sym] = {
                "company_name":    info.get("longName") or info.get("shortName") or sym,
                "current_price":   info.get("currentPrice") or info.get("regularMarketPrice"),
                "target_price":    info.get("targetMeanPrice"),
                "target_high":     info.get("targetHighPrice"),
                "target_low":      info.get("targetLowPrice"),
                "trailing_eps":    info.get("trailingEps"),
                "book_value":      info.get("bookValue"),
                "market_cap":      info.get("marketCap"),
                "sector":          info.get("sector"),
                "pe_ratio":        info.get("trailingPE"),
            }
        except Exception as exc:
            print(f"  [fundamentals error for {sym}] {exc}")
            result[sym] = {}
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 1.  PORTFOLIO BETA
# ─────────────────────────────────────────────────────────────────────────────

def calculate_stock_betas(prices: pd.DataFrame) -> dict:
    """
    Computes beta for each stock column against the BENCHMARK column.

    β_i = Cov(R_i, R_market) / Var(R_market)

    Parameters
    ----------
    prices : DataFrame with stock columns + "BENCHMARK" column (closing prices)

    Returns
    -------
    dict of symbol → beta (float)
    """
    returns = prices.pct_change().dropna()
    market_ret = returns["BENCHMARK"]
    market_var = market_ret.var()

    if market_var == 0:
        return {col: None for col in returns.columns if col != "BENCHMARK"}

    betas = {}
    for col in returns.columns:
        if col == "BENCHMARK":
            continue
        cov = returns[col].cov(market_ret)
        betas[col] = round(cov / market_var, 4)

    return betas


def calculate_portfolio_beta(betas: dict, weights: dict) -> float:
    """
    Computes weighted-average portfolio beta.

    β_portfolio = Σ w_i × β_i
    """
    total = sum(
        weights[s] * betas[s]
        for s in weights
        if betas.get(s) is not None
    )
    return round(total, 4)


def _beta_label(beta: float) -> str:
    if beta is None:
        return "N/A"
    if beta < 0:
        return "Inverse market correlation (hedge-like)"
    if beta < 0.5:
        return "Very low market sensitivity"
    if beta < 0.8:
        return "Defensive (below-market sensitivity)"
    if beta < 1.0:
        return "Slightly defensive"
    if beta < 1.2:
        return "Near-market sensitivity"
    if beta < 1.5:
        return "Moderately aggressive"
    return "High sensitivity — amplifies market moves"


# ─────────────────────────────────────────────────────────────────────────────
# 2.  POTENTIAL UPSIDE
# ─────────────────────────────────────────────────────────────────────────────

def graham_number(eps: float, bv: float) -> float | None:
    """
    Graham Number = √(22.5 × Trailing EPS × Book Value per Share)

    A conservative intrinsic-value estimate per Benjamin Graham.
    Returns None when EPS or BV is missing or non-positive.
    """
    if eps is None or bv is None or eps <= 0 or bv <= 0:
        return None
    return round((22.5 * float(eps) * float(bv)) ** 0.5, 2)


def calculate_upside(fundamentals: dict) -> dict:
    """
    Derives per-symbol upside estimates from analyst targets and Graham Number.

    Returns dict of symbol → {current_price, analyst_target, analyst_upside_pct,
                               graham_number, graham_upside_pct, …}
    """
    upside = {}
    for sym, info in fundamentals.items():
        cp  = info.get("current_price")
        tp  = info.get("target_price")
        eps = info.get("trailing_eps")
        bv  = info.get("book_value")

        analyst_upside = (
            round((tp - cp) / cp * 100, 2)
            if cp and tp and cp > 0
            else None
        )

        gn = graham_number(eps, bv)
        graham_upside = (
            round((gn - cp) / cp * 100, 2)
            if cp and gn and cp > 0
            else None
        )

        upside[sym] = {
            "company_name":        info.get("company_name"),
            "current_price":       cp,
            "analyst_target":      tp,
            "analyst_target_high": info.get("target_high"),
            "analyst_target_low":  info.get("target_low"),
            "analyst_upside_pct":  analyst_upside,
            "graham_number":       gn,
            "graham_upside_pct":   graham_upside,
        }
    return upside


# ─────────────────────────────────────────────────────────────────────────────
# 3.  EFFICIENT FRONTIER  (Markowitz MPT)
# ─────────────────────────────────────────────────────────────────────────────

def portfolio_stats(
    weights: np.ndarray,
    mean_daily_returns: np.ndarray,
    cov_daily: np.ndarray,
) -> tuple[float, float, float]:
    """
    Annualised expected return, volatility, and Sharpe ratio for a weight vector.

    Parameters
    ----------
    weights            : 1-D array of portfolio weights (must sum to 1)
    mean_daily_returns : 1-D array of mean daily log-returns
    cov_daily          : 2-D annualised (×252) covariance matrix of daily returns

    Returns
    -------
    (expected_return, volatility, sharpe_ratio)  — all annualised
    """
    ret = float(np.dot(weights, mean_daily_returns) * TRADING_DAYS)
    vol = float(np.sqrt(weights @ cov_daily @ weights))
    sharpe = (ret - RISK_FREE_RATE) / vol if vol > 0 else 0.0
    return ret, vol, sharpe


def _neg_sharpe(w, mu, cov):
    _, _, s = portfolio_stats(w, mu, cov)
    return -s


def _portfolio_vol(w, mu, cov):
    _, v, _ = portfolio_stats(w, mu, cov)
    return v


def monte_carlo_portfolios(
    mean_daily_returns: np.ndarray,
    cov_annual: np.ndarray,
    n: int = N_PORTFOLIOS,
) -> pd.DataFrame:
    """
    Generates *n* random portfolios via Dirichlet sampling.

    Returns a DataFrame with columns: Return, Volatility, Sharpe, W_0 … W_k
    """
    n_assets = len(mean_daily_returns)
    results  = np.zeros((n, 3 + n_assets))

    for i in range(n):
        w = np.random.dirichlet(np.ones(n_assets))
        r, v, s = portfolio_stats(w, mean_daily_returns, cov_annual)
        results[i] = [r, v, s, *w]

    cols = ["Return", "Volatility", "Sharpe"] + [f"W_{i}" for i in range(n_assets)]
    return pd.DataFrame(results, columns=cols)


def optimise_portfolios(
    mean_daily_returns: np.ndarray,
    cov_annual: np.ndarray,
    symbols: list,
) -> dict:
    """
    Finds two key portfolios on the efficient frontier via scipy SLSQP:
      - max_sharpe : tangency portfolio (highest risk-adjusted return)
      - min_vol    : global minimum variance portfolio

    Returns a dict with both portfolios including weights and stats.
    """
    n = len(symbols)
    w0 = np.full(n, 1 / n)
    bounds      = [(0.0, 1.0)] * n
    sum_to_one  = {"type": "eq", "fun": lambda w: np.sum(w) - 1}

    res_sharpe = minimize(
        _neg_sharpe, w0,
        args=(mean_daily_returns, cov_annual),
        method="SLSQP", bounds=bounds, constraints=sum_to_one,
        options={"ftol": 1e-12, "maxiter": 1000},
    )
    res_vol = minimize(
        _portfolio_vol, w0,
        args=(mean_daily_returns, cov_annual),
        method="SLSQP", bounds=bounds, constraints=sum_to_one,
        options={"ftol": 1e-12, "maxiter": 1000},
    )

    w_sharpe = res_sharpe.x if res_sharpe.success else w0
    w_vol    = res_vol.x    if res_vol.success    else w0

    def _summary(w):
        r, v, s = portfolio_stats(w, mean_daily_returns, cov_annual)
        return {
            "Return (%/yr)":     round(r * 100, 2),
            "Volatility (%/yr)": round(v * 100, 2),
            "Sharpe Ratio":      round(s, 4),
            "Weights": {sym: round(float(wi), 4) for sym, wi in zip(symbols, w)},
        }

    return {
        "max_sharpe": _summary(w_sharpe),
        "min_vol":    _summary(w_vol),
    }


def efficient_frontier_curve(
    mean_daily_returns: np.ndarray,
    cov_annual: np.ndarray,
    n_points: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Traces the analytical efficient frontier by minimising volatility at each
    target return level between the global-min-vol return and the maximum
    single-asset return.

    Returns (returns_pct, vols_pct) — both as percentage arrays.
    """
    n      = len(mean_daily_returns)
    bounds = [(0.0, 1.0)] * n
    eq_sum = {"type": "eq", "fun": lambda w: np.sum(w) - 1}

    # Find global minimum-vol return as the lower bound
    res0 = minimize(
        _portfolio_vol, np.full(n, 1 / n),
        args=(mean_daily_returns, cov_annual),
        method="SLSQP", bounds=bounds, constraints=eq_sum,
    )
    min_ret = float(np.dot(res0.x, mean_daily_returns) * TRADING_DAYS)
    max_ret = float(np.max(mean_daily_returns) * TRADING_DAYS)

    target_rets = np.linspace(min_ret, max_ret * 1.05, n_points)
    frontier_vols = []
    w_prev = np.full(n, 1 / n)

    for target in target_rets:
        constraints = [
            eq_sum,
            {"type": "eq",
             "fun": lambda w, t=target: np.dot(w, mean_daily_returns) * TRADING_DAYS - t},
        ]
        res = minimize(
            _portfolio_vol, w_prev,
            args=(mean_daily_returns, cov_annual),
            method="SLSQP", bounds=bounds, constraints=constraints,
            options={"ftol": 1e-10, "maxiter": 500},
        )
        if res.success:
            frontier_vols.append(_portfolio_vol(res.x, mean_daily_returns, cov_annual))
            w_prev = res.x
        else:
            frontier_vols.append(np.nan)

    return target_rets * 100, np.array(frontier_vols) * 100


def _mc_frontier_hull(mc_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """
    Approximates the efficient frontier from the MC cloud by computing
    the minimum-volatility portfolio for each return bucket.
    Used for large portfolios where the analytical curve is too slow.

    Returns (returns_pct, vols_pct), matching efficient_frontier_curve's order.
    """
    rets = mc_df["Return"].values * 100
    vols = mc_df["Volatility"].values * 100
    buckets = np.linspace(rets.min(), rets.max(), 120)
    step    = (buckets[1] - buckets[0]) / 2
    hull_r, hull_v = [], []
    for r in buckets:
        mask = (rets >= r - step) & (rets < r + step)
        if mask.sum() > 0:
            hull_r.append(r)
            hull_v.append(vols[mask].min())
    return np.array(hull_r), np.array(hull_v)


LARGE_N_THRESHOLD = 40   # skip the slow analytical frontier curve above this


# ─────────────────────────────────────────────────────────────────────────────
# VISUALISATION
# ─────────────────────────────────────────────────────────────────────────────

def plot_efficient_frontier(
    mc_df: pd.DataFrame,
    optimal: dict,
    symbols: list,
    weights_dict: dict,
    mean_daily_returns: np.ndarray,
    cov_annual: np.ndarray,
    save_path: str = "efficient_frontier.png",
):
    """
    Saves a dark-themed efficient frontier chart showing:
      • Monte Carlo portfolio cloud (coloured by Sharpe ratio)
      • Analytical frontier line (small portfolios) or MC hull (large)
      • Max Sharpe, Min Volatility, and Current Portfolio markers
      • Individual stock positions (only shown when n <= LARGE_N_THRESHOLD)
    """
    n_assets = len(symbols)
    if n_assets <= LARGE_N_THRESHOLD:
        ef_rets, ef_vols = efficient_frontier_curve(mean_daily_returns, cov_annual)
        frontier_label = "Efficient Frontier"
    else:
        ef_rets, ef_vols = _mc_frontier_hull(mc_df)
        frontier_label = "Efficient Frontier (MC approx.)"

    fig, ax = plt.subplots(figsize=(13, 8))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")

    # Monte Carlo scatter
    sc = ax.scatter(
        mc_df["Volatility"] * 100,
        mc_df["Return"] * 100,
        c=mc_df["Sharpe"],
        cmap="plasma",
        alpha=0.45,
        s=8,
        zorder=2,
    )
    cbar = fig.colorbar(sc, ax=ax, pad=0.02)
    cbar.set_label("Sharpe Ratio", color="white", fontsize=10)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")

    # Efficient frontier line
    valid = ~np.isnan(ef_vols)
    ax.plot(ef_vols[valid], ef_rets[valid], "w-", linewidth=2.5, zorder=3, label=frontier_label)

    # Capital Market Line (risk-free → max Sharpe)
    ms = optimal["max_sharpe"]
    x_cml = np.array([0, ms["Volatility (%/yr)"] * 1.4])
    y_cml = RISK_FREE_RATE * 100 + (
        (ms["Return (%/yr)"] - RISK_FREE_RATE * 100) / ms["Volatility (%/yr)"]
    ) * x_cml
    ax.plot(x_cml, y_cml, "--", color="#aaaaaa", linewidth=1.2, zorder=2, label="Capital Market Line")

    # Max Sharpe portfolio
    ax.scatter(
        ms["Volatility (%/yr)"], ms["Return (%/yr)"],
        marker="*", s=350, color="#FFD700", zorder=5,
        label=f"Max Sharpe  (SR={ms['Sharpe Ratio']:.2f})",
    )
    ax.annotate(
        f"Max Sharpe\n{ms['Return (%/yr)']:.1f}% / {ms['Volatility (%/yr)']:.1f}%",
        xy=(ms["Volatility (%/yr)"], ms["Return (%/yr)"]),
        xytext=(12, 8), textcoords="offset points",
        color="#FFD700", fontsize=8.5, fontweight="bold", zorder=6,
    )

    # Min Volatility portfolio
    mv = optimal["min_vol"]
    ax.scatter(
        mv["Volatility (%/yr)"], mv["Return (%/yr)"],
        marker="D", s=170, color="#00FF7F", zorder=5,
        label="Min Volatility",
    )
    ax.annotate(
        f"Min Vol\n{mv['Return (%/yr)']:.1f}% / {mv['Volatility (%/yr)']:.1f}%",
        xy=(mv["Volatility (%/yr)"], mv["Return (%/yr)"]),
        xytext=(8, -22), textcoords="offset points",
        color="#00FF7F", fontsize=8.5, fontweight="bold", zorder=6,
    )

    # Current portfolio
    w_arr = np.array([weights_dict[s] for s in symbols])
    cr, cv, _ = portfolio_stats(w_arr, mean_daily_returns, cov_annual)
    ax.scatter(
        cv * 100, cr * 100,
        marker="^", s=220, color="#FF6B6B", zorder=5,
        label="Current Portfolio",
    )
    ax.annotate(
        f"Current\n{cr*100:.1f}% / {cv*100:.1f}%",
        xy=(cv * 100, cr * 100),
        xytext=(10, 10), textcoords="offset points",
        color="#FF6B6B", fontsize=8.5, fontweight="bold", zorder=6,
    )

    # Individual stock dots (only when the portfolio is small enough to be legible)
    if n_assets <= LARGE_N_THRESHOLD:
        for i, sym in enumerate(symbols):
            sr = mean_daily_returns[i] * TRADING_DAYS * 100
            sv = np.sqrt(cov_annual[i, i]) * 100
            ax.scatter(sv, sr, marker="o", s=90, color="#87CEFA", zorder=4)
            ax.annotate(
                sym, xy=(sv, sr),
                xytext=(5, 5), textcoords="offset points",
                color="#87CEFA", fontsize=8,
            )

    # Risk-free rate marker
    ax.axhline(
        RISK_FREE_RATE * 100, color="#888888",
        linestyle=":", linewidth=1, zorder=1,
        label=f"Risk-free rate ({RISK_FREE_RATE*100:.1f}%)",
    )

    ax.set_xlabel("Annualised Volatility (%)", color="white", fontsize=12)
    ax.set_ylabel("Annualised Expected Return (%)", color="white", fontsize=12)
    ax.set_title(
        "Efficient Frontier — Modern Portfolio Theory (MPT) | NSE Equities",
        color="white", fontsize=14, fontweight="bold", pad=16,
    )
    ax.tick_params(colors="white", labelsize=10)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")
    ax.legend(
        facecolor="#1a1f2e", labelcolor="white", fontsize=9,
        loc="upper left", framealpha=0.85,
    )
    ax.grid(True, color="#2a2f3e", linestyle="--", linewidth=0.5, zorder=1)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"\n  Chart saved → {save_path}")


def plot_seasonality_spiral(
    symbol: str,
    years: int = 8,
    save_path: str = "seasonality_spiral.png",
) -> pd.DataFrame:
    """
    Derived from patent MY269086 "System and method for visualizing large
    graph data using spirals" (IIIT-Hyderabad, DSAC). Renders monthly returns
    for *symbol* as a growing spiral (radius = elapsed time, angle = month of
    year), so seasonal patterns line up radially across years -- the same
    layout style popularised for visualising climate time series.

    Returns the underlying monthly-returns DataFrame (Year, Month, Return_pct)
    so callers can inspect the numbers behind the chart.
    """
    prices = fetch_prices([symbol], period=f"{years}y")
    if symbol not in prices.columns or prices[symbol].dropna().empty:
        raise ValueError(f"No price history returned for {symbol!r}")

    monthly = prices[symbol].dropna().resample("ME").last()
    monthly_ret = monthly.pct_change().dropna() * 100

    rows = [
        {"Year": idx.year, "Month": idx.month, "Return_pct": float(r)}
        for idx, r in monthly_ret.items()
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError(f"Not enough monthly history for {symbol!r} to plot seasonality")

    # Spiral coordinates: radius grows monotonically with elapsed time so each
    # calendar year forms one full loop further out than the last; angle is
    # purely month-of-year, so December of every year lines up radially with
    # every other December.
    t0_year, t0_month = df["Year"].min(), df.loc[df["Year"] == df["Year"].min(), "Month"].min()
    elapsed_months = (df["Year"] - t0_year) * 12 + (df["Month"] - t0_month)
    df["_r"] = 1.0 + elapsed_months / 12.0
    df["_theta"] = (df["Month"] - 1) / 12.0 * 2 * np.pi

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw={"projection": "polar"})
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")

    vmax = float(np.abs(df["Return_pct"]).max()) or 1.0
    for yr, grp in df.sort_values("_r").groupby("Year"):
        grp = grp.sort_values("Month")
        ax.plot(grp["_theta"], grp["_r"], "-", color="#555", linewidth=1, zorder=1)
        sc = ax.scatter(
            grp["_theta"], grp["_r"], c=grp["Return_pct"],
            cmap="RdYlGn", vmin=-vmax, vmax=vmax, s=70, zorder=2,
            edgecolors="white", linewidths=0.3,
        )

    ax.set_xticks(np.linspace(0, 2 * np.pi, 12, endpoint=False))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], color="white")
    ax.set_yticklabels([])
    ax.tick_params(colors="white")
    ax.spines["polar"].set_color("#333")
    ax.set_title(f"Seasonality Spiral — {symbol}\n(radius = year, colour = monthly return %)",
                 color="white", fontsize=13, fontweight="bold", pad=20)
    cbar = fig.colorbar(sc, ax=ax, pad=0.1, shrink=0.7)
    cbar.set_label("Monthly Return (%)", color="white", fontsize=9)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"\n  Chart saved → {save_path}")

    return df[["Year", "Month", "Return_pct"]].reset_index(drop=True)


def plot_correlation_network(
    symbols: list,
    prices: pd.DataFrame,
    edge_threshold: float = 0.5,
    save_path: str = "correlation_network.png",
):
    """
    Derived from patents MY269086/MY2690135 "reducing node overlaps and edge
    crossings in large graph data" (IIIT-Hyderabad, DSAC). Visualises the
    portfolio's return-correlation structure as a force-directed network
    graph, pruning edges below *edge_threshold* -- a practical declutter
    equivalent for a small stock-count graph: with only the strong
    relationships kept, node overlaps and edge crossings drop out almost
    entirely without needing the full crossing-minimisation algorithm.

    Node size scales with degree (how many other holdings a stock is
    strongly correlated with); edge width/opacity scales with |correlation|.
    """
    import networkx as nx

    returns = prices[symbols].pct_change().dropna()
    corr = returns.corr()

    G = nx.Graph()
    G.add_nodes_from(symbols)
    for i, a in enumerate(symbols):
        for b in symbols[i + 1:]:
            c = corr.loc[a, b]
            if abs(c) >= edge_threshold:
                G.add_edge(a, b, weight=float(c))

    pos = nx.spring_layout(G, seed=42, k=1.5 / max(len(symbols) ** 0.5, 1))

    fig, ax = plt.subplots(figsize=(10, 9))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")

    for a, b, data in G.edges(data=True):
        w = data["weight"]
        color = "#2e7d32" if w > 0 else "#c62828"
        ax.plot(
            [pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]],
            color=color, alpha=min(abs(w), 1.0), linewidth=1 + 2 * abs(w), zorder=1,
        )

    degrees = dict(G.degree())
    xs = [pos[s][0] for s in symbols]
    ys = [pos[s][1] for s in symbols]
    sizes = [200 + 120 * degrees.get(s, 0) for s in symbols]
    ax.scatter(xs, ys, s=sizes, color="#87CEFA", edgecolors="white", linewidths=0.8, zorder=2)
    # Labels sit just above each node (not centred inside it) so long tickers
    # (RELIANCE, HDFCBANK, ...) stay legible regardless of marker size.
    for s in symbols:
        ax.annotate(s, xy=pos[s], xytext=(0, 12), textcoords="offset points",
                    ha="center", va="bottom", color="white", fontsize=9, fontweight="bold", zorder=3)

    ax.set_title(
        f"Correlation Network (|corr| ≥ {edge_threshold:.2f} shown)\n"
        f"green edge = positive correlation, red = negative, width/size = strength",
        color="white", fontsize=12, fontweight="bold", pad=14,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    # Generous margins: labels extend beyond node markers, and force-directed
    # layouts can place nodes near the auto-scaled data boundary.
    ax.margins(0.2)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"\n  Chart saved → {save_path}")

    return corr


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _section(title: str, width: int = 68):
    print(f"\n{'─' * width}")
    print(f"  {title.upper()}")
    print(f"{'─' * width}")


def _row(label: str, value, w: int = 36):
    print(f"  {label:<{w}} {value if value is not None else 'N/A'}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_portfolio_analysis(
    symbols: list,
    weights: list = None,
    benchmark: str = BENCHMARK,
    period: str = PRICE_PERIOD,
    plot: bool = True,
    save_path: str = "efficient_frontier.png",
) -> dict:
    """
    Full portfolio analysis pipeline:

      1. Portfolio Beta vs NIFTY 50 (^NSEI)
      2. Potential Upside — analyst consensus target + Graham Number
      3. Efficient Frontier — Markowitz MPT with optimal portfolios

    Parameters
    ----------
    symbols   : NSE ticker list, e.g. ["RELIANCE", "TCS", "INFY"]
    weights   : portfolio weights summing to 1; equal-weight if None
    benchmark : market index ticker (default: ^NSEI)
    period    : yfinance period string for price history (default: "2y")
    plot      : whether to save the efficient frontier PNG
    save_path : output file path for the chart

    Returns
    -------
    dict with keys: symbols, weights, betas, portfolio_beta, upside,
                    portfolio_stats, optimal_portfolios, mc_simulations
    """
    symbols = [s.upper().strip() for s in symbols]
    n = len(symbols)

    if weights is None:
        weights = [1 / n] * n
    if abs(sum(weights) - 1.0) > 1e-6:
        raise ValueError(f"Weights must sum to 1.0  (got {sum(weights):.6f})")
    if len(weights) != n:
        raise ValueError("len(weights) must equal len(symbols)")

    weights_dict = dict(zip(symbols, weights))

    print(f"\n{'═' * 68}")
    print("  PORTFOLIO ANALYSIS  —  BETA · UPSIDE · EFFICIENT FRONTIER (MPT)")
    print(f"  Symbols  : {', '.join(symbols)}")
    print(f"  Weights  : {', '.join(f'{w:.2%}' for w in weights)}")
    print(f"  Benchmark: {benchmark}  |  Period: {period}")
    print(f"  {datetime.now().strftime('%d %b %Y  %H:%M:%S')}")
    print(f"{'═' * 68}")

    # ── FETCH PRICES ──────────────────────────────────────────────────────────
    print("\n  Downloading price history…")
    prices = fetch_prices(symbols, benchmark=benchmark, period=period)

    # Drop any symbol that didn't return enough data
    available = [
        s for s in symbols
        if s in prices.columns and prices[s].notna().sum() > 60
    ]
    if len(available) < len(symbols):
        missing = set(symbols) - set(available)
        print(f"  WARNING: Insufficient data for {missing}. Dropping from analysis.")
        symbols = available
        total_w = sum(weights_dict[s] for s in symbols)
        weights_dict = {s: weights_dict[s] / total_w for s in symbols}
        weights = [weights_dict[s] for s in symbols]

    n = len(symbols)

    # ── FETCH FUNDAMENTALS ────────────────────────────────────────────────────
    print("  Downloading fundamental data…")
    fundamentals = fetch_fundamentals_bulk(symbols)

    # ── PRE-COMPUTE RETURNS / COVARIANCE ─────────────────────────────────────
    stock_prices    = prices[symbols].dropna()
    log_returns     = np.log(stock_prices / stock_prices.shift(1)).dropna()
    mean_daily_ret  = log_returns.mean().values
    cov_annual      = log_returns.cov().values * TRADING_DAYS   # annualised

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 1 — BETA
    # ─────────────────────────────────────────────────────────────────────────
    _section("1. Portfolio Beta  (vs NIFTY 50 / ^NSEI)")

    betas = calculate_stock_betas(prices)
    port_beta = calculate_portfolio_beta(betas, weights_dict)

    print(f"\n  {'SYMBOL':<14} {'WEIGHT':>8} {'BETA':>8}   INTERPRETATION")
    print(f"  {'─' * 66}")
    for sym in symbols:
        b = betas.get(sym)
        b_str = f"{b:.4f}" if b is not None else "N/A"
        w_str = f"{weights_dict[sym]:.2%}"
        print(f"  {sym:<14} {w_str:>8} {b_str:>8}   {_beta_label(b)}")

    print(f"  {'─' * 66}")
    print(f"  {'Portfolio Beta':<14} {'':>8} {port_beta:>8.4f}   {_beta_label(port_beta)}")
    print(
        "\n  β = Cov(R_stock, R_market) / Var(R_market)"
        "\n  β < 1  → less volatile than market  |  β > 1  → amplifies market moves"
        "\n  β = 1  → moves in lockstep with the index"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 2 — UPSIDE
    # ─────────────────────────────────────────────────────────────────────────
    _section("2. Potential Upside  (Analyst Target  +  Graham Number)")

    upside_data = calculate_upside(fundamentals)

    weighted_analyst = 0.0
    weighted_graham  = 0.0
    analyst_count = graham_count = 0

    print(
        f"\n  {'SYMBOL':<12} {'CURRENT':>10} {'ANALYST TGT':>12}"
        f" {'UPSIDE%':>9}  {'GRAHAM #':>10} {'G-UPSIDE%':>10}"
    )
    print(f"  {'─' * 70}")

    for sym in symbols:
        u  = upside_data[sym]
        cp = u["current_price"]
        tp = u["analyst_target"]
        au = u["analyst_upside_pct"]
        gn = u["graham_number"]
        gu = u["graham_upside_pct"]
        w  = weights_dict[sym]

        print(
            f"  {sym:<12}"
            f" {('₹'+f'{cp:,.2f}') if cp else 'N/A':>10}"
            f" {('₹'+f'{tp:,.2f}') if tp else 'N/A':>12}"
            f" {(f'{au:+.1f}%') if au is not None else 'N/A':>9}"
            f"  {('₹'+f'{gn:,.2f}') if gn else 'N/A':>10}"
            f" {(f'{gu:+.1f}%') if gu is not None else 'N/A':>10}"
        )

        if au is not None:
            weighted_analyst += w * au
            analyst_count += 1
        if gu is not None:
            weighted_graham += w * gu
            graham_count += 1

    print(f"  {'─' * 70}")
    if analyst_count:
        print(f"  {'Weighted portfolio upside (analyst):':<40} {weighted_analyst:+.2f}%")
    if graham_count:
        print(f"  {'Weighted portfolio upside (Graham):':<40} {weighted_graham:+.2f}%")

    print(
        "\n  Analyst Upside = (Consensus Target − Current Price) / Current Price × 100"
        "\n  Graham Number  = √(22.5 × Trailing EPS × Book Value per Share)"
        "\n  Rule of thumb: Graham # < Current Price → potentially overvalued"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 3 — EFFICIENT FRONTIER
    # ─────────────────────────────────────────────────────────────────────────
    _section("3. Efficient Frontier  (Markowitz MPT — no short selling)")

    print(f"\n  Risk-free rate : {RISK_FREE_RATE*100:.2f}% p.a.  (India 10-yr G-Sec proxy)")
    print(f"  Return model   : Log-returns, {len(log_returns)} trading days of history")
    print(f"  Constraints    : Long-only (0 ≤ w_i ≤ 1),  Σw_i = 1")

    # Per-stock statistics
    print(f"\n  {'SYMBOL':<14} {'E[Return]%':>12} {'Volatility%':>12} {'Sharpe':>10} {'Sector':<20}")
    print(f"  {'─' * 72}")
    for i, sym in enumerate(symbols):
        r = mean_daily_ret[i] * TRADING_DAYS * 100
        v = np.sqrt(cov_annual[i, i]) * 100
        s = (r / 100 - RISK_FREE_RATE) / (v / 100) if v > 0 else 0.0
        sector = (fundamentals[sym].get("sector") or "—")[:18]
        print(f"  {sym:<14} {r:>12.2f} {v:>12.2f} {s:>10.4f} {sector:<20}")

    # Current portfolio statistics
    w_arr = np.array(weights)
    port_ret, port_vol, port_sharpe = portfolio_stats(w_arr, mean_daily_ret, cov_annual)

    print(f"\n  Current Portfolio (user-defined weights):")
    print(f"    Expected Return  : {port_ret*100:>7.2f}% p.a.")
    print(f"    Volatility       : {port_vol*100:>7.2f}% p.a.")
    print(f"    Sharpe Ratio     : {port_sharpe:>7.4f}")

    # Correlation matrix
    corr = log_returns.corr()
    print(f"\n  Correlation Matrix (daily log-returns):")
    header = f"  {'':14}" + "".join(f"{s:>10}" for s in symbols)
    print(header)
    for sym_r in symbols:
        row_str = f"  {sym_r:<14}" + "".join(
            f"{corr.loc[sym_r, sym_c]:>10.4f}" for sym_c in symbols
        )
        print(row_str)

    # Optimised portfolios
    print("\n  Running scipy optimisation…")
    optimal = optimise_portfolios(mean_daily_ret, cov_annual, symbols)

    for label, key, colour in [
        ("Max Sharpe Ratio (Tangency Portfolio)", "max_sharpe", "⭐"),
        ("Minimum Volatility Portfolio",          "min_vol",    "🛡 "),
    ]:
        p = optimal[key]
        print(f"\n  {colour} {label}")
        print(f"    Expected Return  : {p['Return (%/yr)']:>7.2f}% p.a.")
        print(f"    Volatility       : {p['Volatility (%/yr)']:>7.2f}% p.a.")
        print(f"    Sharpe Ratio     : {p['Sharpe Ratio']:>7.4f}")
        print(f"    Allocation:")
        for sym, wi in p["Weights"].items():
            bar = "█" * max(1, int(wi * 32))
            print(f"      {sym:<14} {wi:>6.2%}  {bar}")

    # Improvement vs current portfolio
    ms = optimal["max_sharpe"]
    print(f"\n  Efficiency gap (Max Sharpe vs Current):")
    print(f"    Return  Δ : {ms['Return (%/yr)'] - port_ret*100:+.2f}% p.a.")
    print(f"    Vol     Δ : {ms['Volatility (%/yr)'] - port_vol*100:+.2f}% p.a.")
    print(f"    Sharpe  Δ : {ms['Sharpe Ratio'] - port_sharpe:+.4f}")

    # Monte Carlo simulation + chart
    print(f"\n  Simulating {N_PORTFOLIOS:,} random portfolios…")
    mc_df = monte_carlo_portfolios(mean_daily_ret, cov_annual, n=N_PORTFOLIOS)

    if plot:
        plot_efficient_frontier(
            mc_df, optimal, symbols, weights_dict,
            mean_daily_ret, cov_annual, save_path=save_path,
        )

    # ── FOOTER ────────────────────────────────────────────────────────────────
    print(f"\n{'═' * 68}")
    print("  Data source : yfinance (.NS)  |  Benchmark: NIFTY 50 (^NSEI)")
    print("  Assumptions : Normally distributed returns, long-only, no leverage")
    print("  Disclaimer  : Historical returns do not guarantee future performance")
    print(f"{'═' * 68}\n")

    return {
        "symbols":            symbols,
        "weights":            weights_dict,
        "betas":              betas,
        "portfolio_beta":     port_beta,
        "upside":             upside_data,
        "portfolio_stats": {
            "return_pct": round(port_ret * 100, 2),
            "vol_pct":    round(port_vol * 100, 2),
            "sharpe":     round(port_sharpe, 4),
        },
        "optimal_portfolios": optimal,
        "mc_simulations":     len(mc_df),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Portfolio Beta, Potential Upside, and Efficient Frontier (MPT) "
            "for NSE-listed stocks"
        )
    )
    parser.add_argument(
        "--symbols", "-s",
        nargs="+",
        default=["RELIANCE", "TCS", "INFY", "HDFCBANK", "WIPRO"],
        metavar="SYM",
        help="NSE ticker symbols  (default: RELIANCE TCS INFY HDFCBANK WIPRO)",
    )
    parser.add_argument(
        "--weights", "-w",
        nargs="+",
        type=float,
        default=None,
        metavar="W",
        help="Portfolio weights summing to 1; equal-weight if omitted",
    )
    parser.add_argument(
        "--benchmark",
        default=BENCHMARK,
        help=f"Benchmark index ticker  (default: {BENCHMARK})",
    )
    parser.add_argument(
        "--period",
        default=PRICE_PERIOD,
        help=f"Price history period  (default: {PRICE_PERIOD})",
    )
    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=RISK_FREE_RATE,
        dest="risk_free_rate",
        help=f"Annual risk-free rate as decimal  (default: {RISK_FREE_RATE})",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Skip generating the efficient frontier chart",
    )
    parser.add_argument(
        "--output",
        default="efficient_frontier.png",
        help="Output file for the frontier chart  (default: efficient_frontier.png)",
    )

    args = parser.parse_args()

    # Allow overriding the module-level constant from CLI
    RISK_FREE_RATE = args.risk_free_rate

    run_portfolio_analysis(
        symbols=args.symbols,
        weights=args.weights,
        benchmark=args.benchmark,
        period=args.period,
        plot=not args.no_plot,
        save_path=args.output,
    )
