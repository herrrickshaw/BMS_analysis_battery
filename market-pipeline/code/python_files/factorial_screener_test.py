#!/usr/bin/env python3
"""
Universe-wide factorial hypothesis test: does combining multiple screener
signals produce better forward returns than single signals?

Design, per Montgomery "Design and Analysis of Experiments" Ch. 6/8/15:
  - 6 binary factors (one per screener): darvas, golden_cross, piotroski,
    coffee_can, magic_formula, bull_cartel. Each symbol-year is scored 0/1
    on each factor.
  - This is OBSERVATIONAL, not a randomized experiment -- screens are not
    randomly assigned to stocks. Reported as regression-based factorial
    ANOVA (main effects + testable pairwise interactions only), which is
    the standard adaptation for unbalanced/non-orthogonal factorial data
    (Montgomery Ch. 15's unbalanced-factorial discussion). No causal claim.
  - Response: forward return at T+63d/T+126d/T+252d from signal date.
  - HC3 robust standard errors (stock returns are fat-tailed/heteroskedastic).
  - Benjamini-Hochberg FDR correction across all effects tested.

Scope: US only. India's PIT fundamentals coverage is <1% of its OHLCV
universe (75/8944 symbols) -- cannot honestly run Piotroski/Coffee Can/
Magic Formula/Bull Cartel there at universe scale. Japan/Korea fundamentals
only cover 2021-2026 (too short for a real walk-forward). Europe OHLCV is
~1 year only. US has genuine point-in-time fundamentals (SEC `filed` date)
across 1967-2029 and 9,278-symbol OHLCV coverage 2016-2026 -- the only
market where "full 6-screener universe-wide" is honestly buildable today.

Bypasses the existing walk_forward_backtest.py/backtest_screeners.py
entirely: those loop yfinance per-symbol per-screener (14,500 symbols x
redundant fetches -> many hours, real rate-limit risk) and use "current
financials as proxy for point-in-time" (explicitly flagged as lookahead
bias in their own docstrings). This script reads the already-collected
parquet panels instead -- no network calls, genuine point-in-time via the
SEC `filed` date.

DATA-CONSISTENCY NOTE (2026-07-17): this is the one and only script that
builds the signal panel every downstream analysis (factorial_screener_
analysis.py, factorial_price_prediction.py) reads -- both consume
cache_seed/factorial_screener_signals_us.parquet, so there is exactly one
source of truth for OHLCV path, fundamentals path, date range, and
corporate-action handling. Previously the analysis stage patched over
split-contaminated returns with a post-hoc 1st/99th percentile winsorize,
which is a DIFFERENT convention than every other backtest in this repo
uses (backtest_circuit_breaker_darvas.py, backtest_liquidity_forward.py,
backtest_piotroski_plus.py, daily_breakout_combo_us.py all flag-and-
exclude specific likely-split days by matching the day's % change against
known split/bonus ratios). Ported that exact convention here
(_SPLIT_RATIOS/_SPLIT_TOL, same as backtest_circuit_breaker_darvas.py) so
every test in this repo now treats corporate actions the same way, and
switched from "winsorize after computing a contaminated return" to "detect
the split day and exclude any forward-return window that straddles it" --
strictly more correct, since winsorizing a split-inflated 2,517,572% return
down to the 99th percentile still leaves it polluting that percentile's
other, genuine members.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

OHLCV_PATH = "/Users/umashankar/repos/global-stock-screener/cache_seed/ltm/US.parquet"
FUND_PATH = "/Users/umashankar/repos/global-stock-screener/cache_seed/fundamentals_history/US.parquet"
MIN_YEARS_HISTORY = 5.0

HORIZONS = {"T+5d": 5, "T+21d": 21, "T+63d": 63, "T+126d": 126, "T+252d": 252}
# ~1 week, ~1 month, ~1 quarter, ~6 months, ~1 year in US trading days

# Same constants as backtest_circuit_breaker_darvas.py -- one shared
# convention for "this day's move looks like an unadjusted split/bonus,
# not a real price move" across every backtest in this repo.
_SPLIT_RATIOS = [-50.0, -66.7, -75.0, -80.0, -90.0, +100.0, +200.0, +300.0, +400.0]
_SPLIT_TOL = 3.0


# ── Load & filter ────────────────────────────────────────────────────────────

def _flag_split_days(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Per-symbol day-over-day %% change matched against known split/bonus
    ratios (same convention as backtest_circuit_breaker_darvas.py). Adds
    `likely_split` (bool) and, as ADDITIONAL DATA for the regression stage,
    `dollar_vol_63d` (63-trading-day mean Close*Volume, a liquidity proxy)
    and `vol_63d_ann` (63-trading-day annualized realized volatility of
    daily returns) -- both computed once here so every downstream signal
    reads the identical, already-validated series."""
    df = ohlcv.sort_values(["Symbol", "Date"]).copy()
    g = df.groupby("Symbol", sort=False)
    prev_close = g["Close"].shift(1)
    chg = (df["Close"] / prev_close - 1) * 100
    likely = pd.Series(False, index=df.index)
    for r in _SPLIT_RATIOS:
        likely |= (chg - r).abs() <= _SPLIT_TOL
    df["likely_split"] = likely.fillna(False)

    daily_ret = df.groupby("Symbol", sort=False)["Close"].pct_change()
    dollar_vol = df["Close"] * df["Volume"]
    df["dollar_vol_63d"] = (
        dollar_vol.groupby(df["Symbol"]).transform(lambda s: s.rolling(63, min_periods=20).mean())
    )
    df["vol_63d_ann"] = (
        daily_ret.groupby(df["Symbol"]).transform(lambda s: s.rolling(63, min_periods=20).std()) * np.sqrt(252)
    )
    n_flagged = df["likely_split"].sum()
    print(f"  flagged {n_flagged:,} likely-unadjusted-split days across {df.loc[df['likely_split'],'Symbol'].nunique():,} symbols "
          f"({n_flagged / len(df) * 100:.2f}% of rows) -- forward-return windows crossing these are excluded, not winsorized")
    return df


def load_ohlcv() -> pd.DataFrame:
    df = pd.read_parquet(OHLCV_PATH)
    df = df.sort_values(["Symbol", "Date"]).reset_index(drop=True)
    span = df.groupby("Symbol")["Date"].agg(lambda s: (s.max() - s.min()).days / 365.25)
    keep = span[span >= MIN_YEARS_HISTORY].index
    df = df[df["Symbol"].isin(keep)].copy()
    df = _flag_split_days(df)
    print(f"OHLCV: {df['Symbol'].nunique()} symbols with >={MIN_YEARS_HISTORY}y history, "
          f"{len(df):,} rows, {df['Date'].min().date()} to {df['Date'].max().date()}")
    return df


def load_fundamentals() -> pd.DataFrame:
    df = pd.read_parquet(FUND_PATH)
    df["filed"] = pd.to_datetime(df["filed"], errors="coerce")
    df["fy_end"] = pd.to_datetime(df["fy_end"], errors="coerce")
    df = df.dropna(subset=["filed", "fy_end"]).sort_values(["ticker", "fy_end"]).reset_index(drop=True)
    print(f"Fundamentals: {df['ticker'].nunique()} tickers, {len(df):,} rows, "
          f"filed {df['filed'].min()} to {df['filed'].max()}")
    return df


# ── Technical screeners (vectorized per symbol) ─────────────────────────────

def golden_cross_signals(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """50-DMA crosses above 200-DMA. Both MAs computed from bars strictly
    before the signal day is not required here (MAs are inherently trailing,
    no lookahead by construction)."""
    out = []
    for sym, g in ohlcv.groupby("Symbol", sort=False):
        g = g.sort_values("Date")
        if len(g) < 210:
            continue
        c = g["Close"].values
        dma50 = pd.Series(c).rolling(50).mean().values
        dma200 = pd.Series(c).rolling(200).mean().values
        above = dma50 > dma200
        cross = above & ~np.roll(above, 1)
        cross[:200] = False
        idx = np.where(cross)[0]
        for i in idx:
            out.append((sym, g["Date"].iloc[i]))
    return pd.DataFrame(out, columns=["symbol", "signal_date"])


def darvas_signals(ohlcv: pd.DataFrame, box_window: int = 63, min_hold: int = 10) -> pd.DataFrame:
    """Darvas box breakout: box_top/box_bottom = rolling max(High)/min(Low)
    over the PRIOR box_window bars, EXCLUDING the current bar (this account's
    own established rule -- see feedback_darvas_box_design.md: including the
    current bar in box formation makes breakdown detection impossible).
    Breakout = today's Close > box_top, where box_top has been stable
    (unchanged) for at least min_hold bars -- a genuine consolidation, not a
    single-day high being immediately "broken" by the next day's noise."""
    out = []
    for sym, g in ohlcv.groupby("Symbol", sort=False):
        g = g.sort_values("Date")
        if len(g) < box_window + min_hold + 5:
            continue
        high = g["High"].values
        low = g["Low"].values
        close = g["Close"].values
        # box formed from bars [i-box_window, i-1] -- shift(1) then rolling,
        # so bar i's box never includes bar i itself
        box_top = pd.Series(high).shift(1).rolling(box_window).max().values
        box_stable_start = pd.Series(box_top).groupby((pd.Series(box_top) != pd.Series(box_top).shift(1)).cumsum()).cumcount().values
        breakout = (close > box_top) & (box_stable_start >= min_hold)
        # only the FIRST breakout day of a run counts as "fresh"
        fresh = breakout & ~np.roll(breakout, 1)
        idx = np.where(fresh)[0]
        for i in idx:
            if i < box_window + min_hold:
                continue
            out.append((sym, g["Date"].iloc[i]))
    return pd.DataFrame(out, columns=["symbol", "signal_date"])


def new_high_signals(ohlcv: pd.DataFrame, near_pct: float = 0.98) -> pd.DataFrame:
    """"Companies Creating New Highs": Close within near_pct of the trailing
    252-trading-day (52-week) high, EXCLUDING the current bar from the
    rolling max (same anti-lookahead convention as the Darvas box -- the
    high a stock is "near" must be a high it had already made, not one this
    bar itself sets). Signal = the first day in a run that crosses into
    that zone, not every day it stays there."""
    out = []
    for sym, g in ohlcv.groupby("Symbol", sort=False):
        g = g.sort_values("Date")
        if len(g) < 260:
            continue
        close = g["Close"].values
        high = g["High"].values
        trailing_high = pd.Series(high).shift(1).rolling(252).max().values
        near = close >= near_pct * trailing_high
        fresh = near & ~np.roll(near, 1)
        idx = np.where(fresh)[0]
        for i in idx:
            if i < 252:
                continue
            out.append((sym, g["Date"].iloc[i]))
    return pd.DataFrame(out, columns=["symbol", "signal_date"])


def below_200dma_signals(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """"Stocks below 200-DMA": Close crosses below the 200-day moving
    average -- a contrarian/value-timing entry, the mirror image of Golden
    Cross's confirmation logic rather than a momentum signal."""
    out = []
    for sym, g in ohlcv.groupby("Symbol", sort=False):
        g = g.sort_values("Date")
        if len(g) < 205:
            continue
        c = g["Close"].values
        dma200 = pd.Series(c).rolling(200).mean().values
        below = c < dma200
        cross = below & ~np.roll(below, 1)
        cross[:200] = False
        idx = np.where(cross)[0]
        for i in idx:
            out.append((sym, g["Date"].iloc[i]))
    return pd.DataFrame(out, columns=["symbol", "signal_date"])


def short_term_reversal_signals(ohlcv: pd.DataFrame, lookback: int, bottom_quantile: float = 0.10,
                                 min_universe: int = 200, min_price: float = 5.0) -> pd.DataFrame:
    """v3 addition (2026-07-17): short-term reversal, per Lehmann (1990)
    (lookback=5, weekly) and Jegadeesh (1990) (lookback=21, monthly) --
    the two canonical short-horizon contrarian anomalies: stocks in the
    bottom decile of trailing return earn abnormal returns going forward
    ("buy last week's/month's losers"). Literature review for this
    account's own factorial screener test found this was the one
    well-established "what works in US markets" strategy family with NO
    representative in the original 15 screeners -- below_200dma is a
    trend-REGIME marker (200-day distance), a different mechanism from
    the cross-sectional short-horizon reversal these two papers document.

    UNLIKE every other screener in this file, this one is inherently
    CROSS-SECTIONAL (a stock is a "loser" relative to the OTHER stocks
    trading that day, not relative to its own history) -- see this
    account's own D-14 decision (cross_sectional_momentum.py) for the
    same cross-sectional-vs-time-series distinction applied to momentum.
    That requires ranking across the whole panel per date rather than a
    per-symbol rolling window, hence the vectorized (not per-symbol-loop)
    implementation below.

    MIN_PRICE FLOOR (added after the first run blew up to a +53,609% mean
    return across the panel): a "bottom decile of trailing return" filter
    disproportionately selects stocks whose price has collapsed toward
    zero -- and once Close is a few tenths of a cent, a genuinely tiny
    absolute bounce produces an astronomical PERCENTAGE return (one OTC
    ticker, MNBEF, showed a +31 BILLION percent forward return; this is
    percentage-math on a near-zero denominator, not a real trade anyone
    could have made). Academic reversal studies standardly exclude sub-$5
    names for exactly this reason (microstructure/bid-ask-bounce
    dominance at low price levels) -- not an ad hoc fix invented to hide
    an inconvenient number, a well-established convention this
    implementation should have had from the start.

    Signal = the first day a stock ENTERS the bottom `bottom_quantile` of
    trailing `lookback`-day return, cross-sectionally ranked among all
    OTHER stocks with a valid (non-split-contaminated, >=min_price)
    trailing return that same day (same "fresh" convention as every other
    screener here). `min_universe` guards against forming a percentile
    rank from too few eligible names on days early in the panel."""
    df = ohlcv.sort_values(["Symbol", "Date"]).copy()
    g = df.groupby("Symbol", sort=False)
    df["trail_ret"] = g["Close"].pct_change(lookback)
    # a split inside the trailing window fakes an extreme negative "loser"
    # return that isn't a real overreaction to revert from -- exclude it,
    # same convention as _flag_split_days/attach_forward_returns elsewhere
    split_in_window = g["likely_split"].transform(
        lambda s: s.rolling(lookback + 1, min_periods=1).max().astype(bool))
    df.loc[split_in_window, "trail_ret"] = np.nan
    df.loc[df["Close"] < min_price, "trail_ret"] = np.nan

    valid = df["trail_ret"].notna()
    df["pct_rank"] = df.loc[valid].groupby("Date")["trail_ret"].rank(pct=True)
    n_valid_that_date = df.loc[valid].groupby("Date")["trail_ret"].transform("count")
    in_bottom = valid & (df["pct_rank"] <= bottom_quantile) & (n_valid_that_date >= min_universe)

    fresh = in_bottom & ~in_bottom.groupby(df["Symbol"]).shift(1, fill_value=False)
    out = df.loc[fresh, ["Symbol", "Date"]].rename(columns={"Symbol": "symbol", "Date": "signal_date"})
    return out.reset_index(drop=True)


# ── Fundamental screeners (from point-in-time SEC filings) ─────────────────

def compute_fundamental_screens(fund: pd.DataFrame) -> pd.DataFrame:
    df = fund.copy()
    df["roa"] = df["net_income"] / df["total_assets"]
    df["roe"] = df["net_income"] / df["equity"]
    df["current_ratio"] = df["current_assets"] / df["current_liabilities"]
    df["leverage"] = df["long_term_debt"] / df["total_assets"]
    df["gross_margin"] = df["gross_profit"].fillna(df["revenue"] - df["cost_of_revenue"]) / df["revenue"]
    df["asset_turnover"] = df["revenue"] / df["total_assets"]
    df["fcf"] = df["cfo"] - df["capex"]
    df["total_debt"] = df["long_term_debt"].fillna(0) + df["short_term_debt"].fillna(0)
    df["de_ratio"] = df["total_debt"] / df["equity"]

    df = df.sort_values(["ticker", "fy_end"])
    g = df.groupby("ticker")
    df["d_roa"] = g["roa"].diff()
    df["d_leverage"] = g["leverage"].diff()
    df["d_current_ratio"] = g["current_ratio"].diff()
    df["d_gross_margin"] = g["gross_margin"].diff()
    df["d_asset_turnover"] = g["asset_turnover"].diff()
    df["d_shares"] = g["shares"].diff()
    df["rev_prior"] = g["revenue"].shift(1)
    df["ni_prior"] = g["net_income"].shift(1)
    df["rev_growth"] = (df["revenue"] - df["rev_prior"]) / df["rev_prior"].abs()
    df["ni_growth"] = (df["net_income"] - df["ni_prior"]) / df["ni_prior"].abs()

    # "Capacity Expansion": YoY capex growth > 25% -- a company meaningfully
    # investing in new plant/equipment, not routine maintenance capex.
    df["capex_prior"] = g["capex"].shift(1)
    df["capex_growth"] = (df["capex"] - df["capex_prior"]) / df["capex_prior"].abs()
    df["capacity_expansion_pass"] = (df["capex_growth"] > 0.25).astype(int)

    # EPS for the Graham 10-year-average-earnings screen (computed here so the
    # rolling window is available before the price join). Fresh groupby call
    # (not reusing `g` above) since `eps` didn't exist when `g` was created.
    df["eps"] = df["net_income"] / df["shares"]
    df["eps_10y_avg"] = (
        df.groupby("ticker")["eps"].rolling(10, min_periods=5).mean().reset_index(level=0, drop=True)
    )

    # 3y revenue CAGR for Coffee Can
    df["rev_3y_ago"] = g["revenue"].shift(3)
    df["rev_cagr_3y"] = (df["revenue"] / df["rev_3y_ago"]).pow(1 / 3) - 1

    # Piotroski F-score (9 binary signals)
    f = pd.DataFrame(index=df.index)
    f["f_roa_pos"] = (df["roa"] > 0).astype(int)
    f["f_cfo_pos"] = (df["cfo"] > 0).astype(int)
    f["f_droa_pos"] = (df["d_roa"] > 0).astype(int)
    f["f_accrual"] = (df["cfo"] > df["net_income"]).astype(int)
    f["f_leverage_down"] = (df["d_leverage"] < 0).astype(int)
    f["f_current_up"] = (df["d_current_ratio"] > 0).astype(int)
    f["f_no_dilution"] = (df["d_shares"].fillna(0) <= 0).astype(int)
    f["f_margin_up"] = (df["d_gross_margin"] > 0).astype(int)
    f["f_turnover_up"] = (df["d_asset_turnover"] > 0).astype(int)
    df["piotroski_f"] = f.sum(axis=1)
    df["piotroski_pass"] = (df["piotroski_f"] >= 7).astype(int)

    # Coffee Can: Rev CAGR>10%, ROE>15%, D/E<1, no loss, FCF>0 (MCap gate applied after price join)
    df["coffee_can_pass"] = (
        (df["rev_cagr_3y"] > 0.10) & (df["roe"] > 0.15) & (df["de_ratio"] < 1)
        & (df["net_income"] > 0) & (df["fcf"] > 0)
    ).astype(int)

    # Bull Cartel: YoY revenue growth>15%, profit growth>20% (annual proxy for
    # the original quarterly rule -- SEC fundamentals_history is annual-
    # resolution here, documented approximation, not the exact quarterly test)
    df["bull_cartel_pass"] = ((df["rev_growth"] > 0.15) & (df["ni_growth"] > 0.20)).astype(int)

    # ROIC proxy for Magic Formula: EBIT / (equity + total_debt - cash)
    df["invested_capital"] = df["equity"] + df["total_debt"] - df["cash"]
    df["roic"] = df["ebit"] / df["invested_capital"]

    # --- ROCE block from piotroski_plus.py (reused verbatim, not reinvented) --
    # +1 level:   roce_ex_cash > 15%  (ROCE = EBIT / (Total Assets - Current
    #             Liabilities); ex-cash subtracts cash from the capital-employed
    #             denominator too, so a cash-rich company isn't penalized for
    #             capital it hasn't deployed)
    # +1 stable:  5y coefficient of variation < 0.30 (sustained, not a cyclical peak)
    # +1 trend:   latest ROCE >= 5y mean (not quietly deteriorating)
    # roce_plus_pass = all 3 (mirrors the "canonical" preset's hard-pass spirit;
    # piotroski_plus.py's actual weighted presets blend these, this binary
    # factor is a simplification for the factorial design's 0/1 requirement)
    df["capital_employed"] = df["total_assets"] - df["current_liabilities"]
    df["capital_employed_ex_cash"] = df["capital_employed"] - df["cash"]
    df["roce"] = df["ebit"] / df["capital_employed"]
    df["roce_ex_cash"] = df["ebit"] / df["capital_employed_ex_cash"]
    roll = g["roce"].rolling(5, min_periods=3)
    roce_5y_mean = roll.mean().reset_index(level=0, drop=True)
    roce_5y_std = roll.std().reset_index(level=0, drop=True)
    df["roce_5y_mean"] = roce_5y_mean
    df["roce_cv"] = (roce_5y_std / roce_5y_mean).abs()
    df["roce_level_pass"] = df["roce_ex_cash"] > 0.15
    df["roce_stable_pass"] = df["roce_cv"] < 0.30
    df["roce_trend_pass"] = df["roce"] >= df["roce_5y_mean"]
    df["roce_plus_pass"] = (
        df["roce_level_pass"] & df["roce_stable_pass"] & df["roce_trend_pass"]
    ).astype(int)

    # --- Sloan accrual-quality flag, from factor_valuation_quality.py --------
    # sloan_ratio = (net_income - cfo) / total_assets; pass (good quality) if < 0
    # -- i.e. cash flow, not accruals, is driving reported earnings.
    df["sloan_ratio"] = (df["net_income"] - df["cfo"]) / df["total_assets"]
    df["sloan_pass"] = (df["sloan_ratio"] < 0).astype(int)

    return df


def attach_market_cap(fund: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Join each filing to the closest available Close price ON/AFTER the
    `filed` date (a filing's market-cap-dependent screens can only use a
    price that existed once the filing was public)."""
    px = ohlcv[["Symbol", "Date", "Close"]].rename(columns={"Symbol": "ticker"}).sort_values("Date")
    fund = fund.sort_values("filed")
    merged = pd.merge_asof(
        fund.sort_values("filed"), px.rename(columns={"Date": "filed"}),
        by="ticker", on="filed", direction="forward", tolerance=pd.Timedelta(days=14),
    )
    merged["mcap"] = merged["shares"] * merged["Close"]
    merged["earnings_yield"] = merged["ebit"] / (merged["mcap"] + merged["total_debt"] - merged["cash"])
    merged["coffee_can_pass"] = (merged["coffee_can_pass"].astype(bool) & (merged["mcap"] >= 1e9)).astype(int)
    merged["magic_formula_pass"] = (
        (merged["roic"] > 0.25) & (merged["earnings_yield"] > 0.15) & (merged["mcap"] > 5e7)
    ).astype(int)

    # --- Altman (1968) 5-factor Z-Score, from factor_growth_risk.py ----------
    # Used as an EXCLUSION screen here (not_distress), matching this account's
    # own established usage in sweep_growth_risk_us.py: "nobody buys the
    # SAFEST company, they avoid the DISTRESSED ones."
    wc = merged["current_assets"] - merged["current_liabilities"]
    x1 = wc / merged["total_assets"]
    x2 = merged["retained_earnings"] / merged["total_assets"]
    x3 = merged["ebit"] / merged["total_assets"]
    x4 = merged["mcap"] / merged["total_liabilities"]
    x5 = merged["revenue"] / merged["total_assets"]
    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
    # Same sanity bound as factor_growth_risk.py: a stale filing paired with a
    # split-contaminated price can blow X4 up to an absurd multiple -- no real
    # company scores outside +/-100, so treat that as data artifact, not safety.
    z = z.where(z.abs() <= 100)
    merged["altman_z"] = z
    # DISTRESS zone is z<1.81 (Altman's own thresholds); untested (NaN) does
    # NOT count as a signal, consistent with every other screen here -- a
    # missing Z-Score is "unknown," not "safe."
    merged["not_distress"] = (z >= 1.81).astype(float).fillna(0).astype(int)

    # "Growth Stocks": fast growth + good value -- rev_growth > 20% AND
    # earnings_yield > 8% (not overpriced for that growth).
    merged["growth_stocks_pass"] = (
        (merged["rev_growth"] > 0.20) & (merged["earnings_yield"] > 0.08)
    ).astype(int)

    # "Low on 10-year average earnings" (Graham): Price / (10y avg EPS) < 15,
    # positive earnings required (Graham's own methodology excludes loss-makers
    # from this test entirely, not just penalizes them).
    merged["pe_10y_avg"] = merged["Close"] / merged["eps_10y_avg"]
    merged["graham_10y_pass"] = (
        (merged["eps_10y_avg"] > 0) & (merged["pe_10y_avg"] < 15)
    ).astype(int)

    # "Small Cap - High Growth": mcap < $2B, rev_growth > 15%, D/E < 0.5, ROE > 15%.
    merged["small_cap_growth_pass"] = (
        (merged["mcap"] < 2e9) & (merged["rev_growth"] > 0.15)
        & (merged["de_ratio"] < 0.5) & (merged["roe"] > 0.15)
    ).astype(int)

    return merged


# ── Build the symbol-year factor table ──────────────────────────────────────

def build_fundamental_signal_dates(fund_scored: pd.DataFrame) -> pd.DataFrame:
    """One row per (symbol, filed-date) where >=1 fundamental screen passed,
    tagged with WHICH screens passed on that filing."""
    cols = ["piotroski_pass", "coffee_can_pass", "magic_formula_pass", "bull_cartel_pass",
            "roce_plus_pass", "sloan_pass", "not_distress",
            "capacity_expansion_pass", "growth_stocks_pass", "graham_10y_pass", "small_cap_growth_pass"]
    df = fund_scored.dropna(subset=["filed"]).copy()
    df["any_pass"] = df[cols].sum(axis=1) > 0
    df = df[df["any_pass"]]
    out = df[["ticker", "filed"] + cols].rename(columns={"ticker": "symbol", "filed": "signal_date"})
    return out


BENCHMARK_SYMBOL = "SPY"  # US scope only -- Nifty 50 is the equivalent for an India version of
# this test, but this script's own docstring already documents why India can't run the full
# screener universe honestly today (75/8944 symbols with PIT fundamentals); not added here.


def benchmark_lookup(ohlcv: pd.DataFrame) -> tuple:
    """SPY's own Date/Close/likely_split series, from the SAME parquet and
    SAME split-detection pass as every stock -- so the benchmark is held to
    the identical data-quality bar, not a separately-sourced index level."""
    g = ohlcv[ohlcv["Symbol"] == BENCHMARK_SYMBOL].sort_values("Date").reset_index(drop=True)
    if g.empty:
        raise ValueError(f"{BENCHMARK_SYMBOL} not found in OHLCV panel -- cannot benchmark returns")
    return g["Date"].values, g["Close"].values, g["likely_split"].values


def forward_returns(ohlcv: pd.DataFrame) -> dict:
    """Per-symbol Date/Close/likely_split/liquidity/volatility lookups for
    fast forward-return computation (trading-day offset, not calendar-day)."""
    lookups = {}
    for sym, g in ohlcv.groupby("Symbol", sort=False):
        g = g.sort_values("Date").reset_index(drop=True)
        lookups[sym] = (g["Date"].values, g["Close"].values, g["likely_split"].values,
                         g["dollar_vol_63d"].values, g["vol_63d_ann"].values)
    return lookups


def _window_return(dates, closes, split_flag, pos, fpos) -> float:
    """Return over [pos, fpos] on ONE series (stock or benchmark), NaN if the
    window is out of range or crosses a likely-split day on that series."""
    if fpos >= len(dates):
        return np.nan
    entry = closes[pos]
    if not entry or entry <= 0:
        return np.nan
    if split_flag[pos:fpos + 1].any():
        return np.nan
    return (closes[fpos] / entry - 1) * 100


def attach_forward_returns(signals: pd.DataFrame, lookups: dict, bench: tuple) -> pd.DataFrame:
    """Every return is computed two ways: `ret_{h}` (raw, used for absolute
    price prediction) and `xret_{h}` (raw minus the S&P 500's OWN return over
    the identical [entry, entry+h] trading-day window -- the "did this beat
    the index" number every downstream hypothesis test/prediction is built
    on, per this account's own instruction that returns must always be
    benchmarked, not read in isolation against an unstated market regime)."""
    bench_dates, bench_closes, bench_split = bench
    rows = {h: [] for h in HORIZONS}
    bench_rows = {h: [] for h in HORIZONS}
    xrows = {h: [] for h in HORIZONS}
    liq_col, vol_col = [], []
    excluded_split = 0
    for sym, sig_date in zip(signals["symbol"], signals["signal_date"]):
        entry_dates, closes, split_flag, dollar_vol, rvol = lookups.get(sym, (None, None, None, None, None))
        if entry_dates is None:
            for h in HORIZONS:
                rows[h].append(np.nan)
                bench_rows[h].append(np.nan)
                xrows[h].append(np.nan)
            liq_col.append(np.nan)
            vol_col.append(np.nan)
            continue
        pos = np.searchsorted(entry_dates, np.datetime64(sig_date))
        bench_pos = np.searchsorted(bench_dates, np.datetime64(sig_date))
        if pos >= len(entry_dates):
            for h in HORIZONS:
                rows[h].append(np.nan)
                bench_rows[h].append(np.nan)
                xrows[h].append(np.nan)
            liq_col.append(np.nan)
            vol_col.append(np.nan)
            continue
        entry = closes[pos]
        liq_col.append(dollar_vol[pos])
        vol_col.append(rvol[pos])
        for h, n in HORIZONS.items():
            fpos = pos + n
            # exclude (not winsorize) any window where the entry day, the
            # exit day, or any day between them is a likely unadjusted
            # split/bonus -- that price move is a data artifact, not
            # something a real position would have earned or lost.
            stock_r = _window_return(entry_dates, closes, split_flag, pos, fpos)
            bench_r = _window_return(bench_dates, bench_closes, bench_split, bench_pos, bench_pos + n)
            if pd.isna(stock_r) and fpos < len(entry_dates) and entry and entry > 0:
                excluded_split += 1
            rows[h].append(stock_r)
            bench_rows[h].append(bench_r)
            xrows[h].append(stock_r - bench_r if pd.notna(stock_r) and pd.notna(bench_r) else np.nan)
    for h in HORIZONS:
        signals[f"ret_{h}"] = rows[h]
        signals[f"bench_ret_{h}"] = bench_rows[h]
        signals[f"xret_{h}"] = xrows[h]
    signals["dollar_vol_63d"] = liq_col
    signals["log_liquidity"] = np.log1p(signals["dollar_vol_63d"])
    signals["volatility_63d"] = vol_col
    print(f"  excluded {excluded_split:,} signal-horizon windows for crossing a likely-split day")
    for h in HORIZONS:
        print(f"  {h}: mean stock return {np.nanmean(rows[h]):+.2f}%, mean {BENCHMARK_SYMBOL} return "
              f"{np.nanmean(bench_rows[h]):+.2f}%, mean excess {np.nanmean(xrows[h]):+.2f}%")
    return signals


def main():
    ohlcv = load_ohlcv()
    fund = load_fundamentals()

    print("\nComputing technical signals...")
    gc = golden_cross_signals(ohlcv)
    gc["screener"] = "golden_cross"
    dv = darvas_signals(ohlcv)
    dv["screener"] = "darvas"
    nh = new_high_signals(ohlcv)
    nh["screener"] = "new_highs"
    b200 = below_200dma_signals(ohlcv)
    b200["screener"] = "below_200dma"
    rev_w = short_term_reversal_signals(ohlcv, lookback=5)
    rev_w["screener"] = "reversal_weekly"
    rev_m = short_term_reversal_signals(ohlcv, lookback=21)
    rev_m["screener"] = "reversal_monthly"
    print(f"  golden_cross: {len(gc):,} signals across {gc['symbol'].nunique():,} symbols")
    print(f"  darvas: {len(dv):,} signals across {dv['symbol'].nunique():,} symbols")
    print(f"  new_highs: {len(nh):,} signals across {nh['symbol'].nunique():,} symbols")
    print(f"  below_200dma: {len(b200):,} signals across {b200['symbol'].nunique():,} symbols")
    print(f"  reversal_weekly: {len(rev_w):,} signals across {rev_w['symbol'].nunique():,} symbols")
    print(f"  reversal_monthly: {len(rev_m):,} signals across {rev_m['symbol'].nunique():,} symbols")

    print("\nComputing fundamental signals...")
    fund_scored = compute_fundamental_screens(fund)
    fund_scored = attach_market_cap(fund_scored, ohlcv)
    fund_sig = build_fundamental_signal_dates(fund_scored)
    for c in ["piotroski_pass", "coffee_can_pass", "magic_formula_pass", "bull_cartel_pass",
              "roce_plus_pass", "sloan_pass", "not_distress",
              "capacity_expansion_pass", "growth_stocks_pass", "graham_10y_pass", "small_cap_growth_pass"]:
        print(f"  {c}: {fund_sig[c].sum():,} filing-level passes")

    # --- Melt fundamental wide-passes into long screener rows -----------------
    fund_long = []
    for c, name in [("piotroski_pass", "piotroski"), ("coffee_can_pass", "coffee_can"),
                     ("magic_formula_pass", "magic_formula"), ("bull_cartel_pass", "bull_cartel"),
                     ("roce_plus_pass", "roce_plus"), ("sloan_pass", "sloan_quality"),
                     ("not_distress", "not_distress"),
                     ("capacity_expansion_pass", "capacity_expansion"),
                     ("growth_stocks_pass", "growth_stocks"),
                     ("graham_10y_pass", "graham_10y"),
                     ("small_cap_growth_pass", "small_cap_growth")]:
        sub = fund_sig[fund_sig[c] == 1][["symbol", "signal_date"]].copy()
        sub["screener"] = name
        fund_long.append(sub)
    fund_long = pd.concat(fund_long, ignore_index=True)

    all_signals = pd.concat([gc[["symbol", "signal_date", "screener"]],
                              dv[["symbol", "signal_date", "screener"]],
                              nh[["symbol", "signal_date", "screener"]],
                              b200[["symbol", "signal_date", "screener"]],
                              rev_w[["symbol", "signal_date", "screener"]],
                              rev_m[["symbol", "signal_date", "screener"]],
                              fund_long], ignore_index=True)
    all_signals["signal_date"] = pd.to_datetime(all_signals["signal_date"])
    all_signals["year"] = all_signals["signal_date"].dt.year
    n_bench_signals = (all_signals["symbol"] == BENCHMARK_SYMBOL).sum()
    all_signals = all_signals[all_signals["symbol"] != BENCHMARK_SYMBOL].reset_index(drop=True)
    print(f"  dropped {n_bench_signals:,} technical-screener signals fired on {BENCHMARK_SYMBOL} itself "
          f"-- it's the benchmark, not a stock under test")
    print(f"\nTotal signals (all screeners): {len(all_signals):,}")
    print(all_signals["screener"].value_counts())

    print("\nComputing forward returns (this reads the full OHLCV panel into memory per symbol -- may take a few minutes)...")
    lookups = forward_returns(ohlcv)
    bench = benchmark_lookup(ohlcv)
    all_signals = attach_forward_returns(all_signals, lookups, bench)

    all_signals.to_parquet("/Users/umashankar/market-pipeline/code/python_files/cache_seed/factorial_screener_signals_us.parquet", index=False)
    print(f"\nSaved {len(all_signals):,} signal rows -> cache_seed/factorial_screener_signals_us.parquet")


if __name__ == "__main__":
    main()
