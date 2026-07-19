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
# v8: S&P 500-scope only (484-503 symbols), NOT the full universe above -- see
# collect_insider_form4.py / collect_short_interest.py docstrings for the scope decision.
INSIDER_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/insider_transactions_us.parquet"
SHORT_INTEREST_PATH = "/Users/umashankar/market-pipeline/code/python_files/cache_seed/short_interest_us.parquet"
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
    df["daily_ret"] = daily_ret  # persisted (was previously a local-only var) -- low_beta_signals (v6) needs it
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

def golden_cross_signals(ohlcv: pd.DataFrame, min_price: float = 5.0) -> pd.DataFrame:
    """50-DMA crosses above 200-DMA. Both MAs computed from bars strictly
    before the signal day is not required here (MAs are inherently trailing,
    no lookahead by construction). min_price floor (same convention as
    short_term_reversal_signals/low_beta_signals) added after finding this
    screener firing on sub-$0.0001 OTC tickers (ECXJ, IBIDF -- the SAME
    penny-stock percentage-explosion pattern already caught on MNBEF in
    v3, undetected here because this screener never had the floor -- one
    signal produced a +18,999,884% T+252d "excess return")."""
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
            if c[i] < min_price:
                continue
            out.append((sym, g["Date"].iloc[i]))
    return pd.DataFrame(out, columns=["symbol", "signal_date"])


def darvas_signals(ohlcv: pd.DataFrame, box_window: int = 63, min_hold: int = 10,
                    min_price: float = 5.0) -> pd.DataFrame:
    """Darvas box breakout: box_top/box_bottom = rolling max(High)/min(Low)
    over the PRIOR box_window bars, EXCLUDING the current bar (this account's
    own established rule -- see feedback_darvas_box_design.md: including the
    current bar in box formation makes breakdown detection impossible).
    Breakout = today's Close > box_top, where box_top has been stable
    (unchanged) for at least min_hold bars -- a genuine consolidation, not a
    single-day high being immediately "broken" by the next day's noise.
    min_price floor added after finding this screener firing on sub-cent
    OTC tickers (MNBEF, IBIDF, SGIPF, OBIIF, KELRF, TOKCF) that produced
    T+252d "excess returns" in the hundreds of thousands to millions of
    percent -- the same percentage-explosion pattern already caught (and
    fixed) elsewhere this session, missing here until now."""
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
            if close[i] < min_price:
                continue
            out.append((sym, g["Date"].iloc[i]))
    return pd.DataFrame(out, columns=["symbol", "signal_date"])


def new_high_signals(ohlcv: pd.DataFrame, near_pct: float = 0.98, min_price: float = 5.0) -> pd.DataFrame:
    """"Companies Creating New Highs": Close within near_pct of the trailing
    252-trading-day (52-week) high, EXCLUDING the current bar from the
    rolling max (same anti-lookahead convention as the Darvas box -- the
    high a stock is "near" must be a high it had already made, not one this
    bar itself sets). Signal = the first day in a run that crosses into
    that zone, not every day it stays there. min_price floor added after
    finding this screener firing on sub-cent OTC tickers (ECXJ at $0.00001,
    MNBEF, NOFCF) producing T+252d "excess returns" up to +18,999,884% --
    same percentage-explosion pattern caught elsewhere this session."""
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
            if close[i] < min_price:
                continue
            out.append((sym, g["Date"].iloc[i]))
    return pd.DataFrame(out, columns=["symbol", "signal_date"])


def below_200dma_signals(ohlcv: pd.DataFrame, min_price: float = 5.0) -> pd.DataFrame:
    """"Stocks below 200-DMA": Close crosses below the 200-day moving
    average -- a contrarian/value-timing entry, the mirror image of Golden
    Cross's confirmation logic rather than a momentum signal. min_price
    floor added after finding this screener firing on sub-cent OTC tickers
    (IBIDF, BECEF) producing T+252d "excess returns" up to +11,545,300% --
    same percentage-explosion pattern caught elsewhere this session."""
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
            if c[i] < min_price:
                continue
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


def low_beta_signals(ohlcv: pd.DataFrame, lookback: int = 252, beta_threshold: float = 0.8,
                      min_price: float = 5.0) -> pd.DataFrame:
    """v6 addition: the "Market & Price" category's Beta parameter,
    Screener.in-style, applied here as the low-volatility/low-beta anomaly
    (Ang, Hodrick, Xing & Zhang 2006, 2009; Frazzini & Pedersen 2014
    "Betting Against Beta") -- low-beta stocks have historically earned
    risk-adjusted returns disproportionate to their low market sensitivity.
    Flagged as a genuine literature gap in this account's own research
    (v3's docstring never closed it); closed here.

    Rolling `lookback`-day beta vs SPY (cov(stock,bench)/var(bench)),
    shifted by one bar so the beta measured on day t never includes day
    t's own return (same anti-lookahead convention as every other
    screener here). Same min_price floor as short_term_reversal_signals
    for the same reason (a low-beta reading on a near-zero-price stock is
    a data artifact, not a real defensive characteristic)."""
    bench = ohlcv[ohlcv["Symbol"] == BENCHMARK_SYMBOL].sort_values("Date")[["Date", "daily_ret"]]
    bench = bench.rename(columns={"daily_ret": "bench_ret"}).set_index("Date")["bench_ret"]

    out = []
    for sym, g in ohlcv.groupby("Symbol", sort=False):
        if sym == BENCHMARK_SYMBOL or len(g) < lookback + 5:
            continue
        g = g.sort_values("Date")
        merged = g[["Date", "Close", "daily_ret"]].merge(bench, left_on="Date", right_index=True, how="inner")
        if len(merged) < lookback + 5:
            continue
        stock_r = merged["daily_ret"].shift(1)
        bench_r = merged["bench_ret"].shift(1)
        roll_cov = stock_r.rolling(lookback).cov(bench_r)
        roll_var = bench_r.rolling(lookback).var()
        beta = roll_cov / roll_var
        eligible = merged["Close"].shift(1) >= min_price
        low = (beta < beta_threshold) & eligible
        fresh = low & ~low.shift(1, fill_value=False)
        for i in merged.index[fresh.fillna(False)]:
            out.append((sym, merged.loc[i, "Date"]))
    return pd.DataFrame(out, columns=["symbol", "signal_date"])


# ── v8 additions: insider Form 4 + FINRA short interest (S&P 500 scope only,
# see collect_insider_form4.py / collect_short_interest.py) ─────────────────

def insider_buying_signals(insider_path: str = INSIDER_PATH, min_transactions: int = 2,
                            min_buy_share: float = 0.30, max_price_per_share: float = 50_000.0) -> pd.DataFrame:
    """Net insider buying (Form 3/4 open-market P/S transactions only, no
    grants/exercises/gifts -- filtered upstream by the collector). Aggregated
    to one row per (symbol, calendar quarter) -- Form 4s cluster in bursts
    (a 10b5-1 plan can file weekly), so per-transaction signals would badly
    overlap; quarterly matches this repo's fundamental-screener cadence.

    Signal = net dollar value of P minus S is POSITIVE, buy-side is >=30%
    of gross dollar volume in the quarter (catches genuine net conviction,
    not one small purchase offsetting a much larger routine sale), and
    >=2 filings in the quarter (a single transaction is too thin a sample).

    CAVEAT (real limitation, not hidden): the collector didn't pull the
    reporting-owner CIK, so "n_transactions" can't distinguish multiple
    DIFFERENT insiders buying from one insider filing multiple tranches --
    weaker than an ideal "breadth of insiders" signal.

    max_price_per_share caps ~17 known bad TRANS_PRICEPERSHARE rows (raw
    SEC Form 4 data-entry errors, e.g. AMD showing $525M/share in 2017 --
    no S&P 500 constituent has traded anywhere near $50k/share in this
    window) before they can distort dollar-value aggregation.

    Point-in-time: signal_date = the LAST FILING_DATE within the quarter
    that produced the pass -- known to an observer at that moment, uses
    no information from later quarters."""
    df = pd.read_parquet(insider_path)
    df = df[df["TRANS_PRICEPERSHARE"].between(0.01, max_price_per_share)].copy()
    dollar_value = df["TRANS_SHARES"] * df["TRANS_PRICEPERSHARE"]
    df["buy_value"] = np.where(df["TRANS_CODE"] == "P", dollar_value, 0.0)
    df["sell_value"] = np.where(df["TRANS_CODE"] == "S", dollar_value, 0.0)
    df["fy_quarter"] = df["FILING_DATE"].dt.to_period("Q")

    g = df.groupby(["symbol", "fy_quarter"]).agg(
        n_trans=("buy_value", "size"),
        buy_value=("buy_value", "sum"),
        sell_value=("sell_value", "sum"),
        signal_date=("FILING_DATE", "max"),
    ).reset_index()
    g["gross_value"] = g["buy_value"] + g["sell_value"]
    g = g[g["gross_value"] > 0]
    g["buy_share"] = g["buy_value"] / g["gross_value"]
    passed = g[(g["n_trans"] >= min_transactions) & (g["buy_value"] > g["sell_value"])
               & (g["buy_share"] >= min_buy_share)][["symbol", "signal_date"]].copy()
    return passed.reset_index(drop=True)


def short_interest_decline_signals(short_interest_path: str = SHORT_INTEREST_PATH,
                                    min_decline_pct: float = -10.0, min_prior_position: int = 10_000,
                                    publication_lag_days: int = 11) -> pd.DataFrame:
    """FINRA consolidated short interest: a sharp DECLINE in short interest
    is the contrarian-friendly signal (Asquith, Pathak & Ritter 2005; Desai,
    Ramesh, Thiagarajan & Balachandran 2002 -- high short interest predicts
    UNDERperformance, so unwinding shorts is the bullish direction).

    min_prior_position (>=10,000 shares) excludes the same "tiny-base
    percentage explosion" pattern this session has hit before on price
    data (v3 reversal, v5 blended portfolio): 115 of 97,555 rows here have
    previousShortPositionQuantity <10,000 (mostly spinoff/re-listing
    tickers with no real prior short base) and produce changePercent up
    to +4,405,230% -- economically meaningless, not a real signal. This
    gate matters most for the DECLINE side too: a drop from 200 to 20
    shares is a genuine -90% but on a base too small to mean anything.

    publication_lag_days (~11 calendar days = FINRA's documented ~8
    trading-day settlement-to-publication gap, see collect_short_interest.py)
    shifts settlementDate to an approximate public-availability date -- a
    genuine simplification (not the exact publication calendar), flagged
    not hidden."""
    df = pd.read_parquet(short_interest_path)
    eligible = df["previousShortPositionQuantity"] >= min_prior_position
    declined = df["changePercent"] <= min_decline_pct
    passed = df[eligible & declined][["symbol", "settlementDate"]].copy()
    passed["signal_date"] = passed["settlementDate"] + pd.Timedelta(days=publication_lag_days)
    return passed[["symbol", "signal_date"]].reset_index(drop=True)


# ── Fundamental screeners (from point-in-time SEC filings) ─────────────────

def compute_fundamental_screens(fund: pd.DataFrame) -> pd.DataFrame:
    df = fund.copy()
    df = df.sort_values(["ticker", "fy_end"])
    g = df.groupby("ticker")

    # CFA Institute convention (Robinson et al., International Financial
    # Statement Analysis, Ch.7 p.267-268): "Because operating income occurs
    # throughout the period... it generally makes sense to use some average
    # measure of assets... Most ratio databases use a simple average of the
    # beginning- and end-of-year balance sheet amounts." roa/roe/asset_turnover
    # pair an income-statement FLOW (net income, revenue) with a balance-sheet
    # STOCK (assets, equity) -- using the ending value alone (the prior
    # convention here) overstates the ratio whenever the balance sheet grew
    # during the period. No average is possible for a ticker's first filing
    # (no prior period) -- left NaN, same "missing stays missing" convention
    # as total_debt_strict elsewhere in this file, not silently defaulted.
    df["total_assets_prior_bal"] = g["total_assets"].shift(1)
    df["avg_total_assets"] = (df["total_assets"] + df["total_assets_prior_bal"]) / 2
    df["equity_prior_bal"] = g["equity"].shift(1)
    df["avg_equity"] = (df["equity"] + df["equity_prior_bal"]) / 2

    df["roa"] = df["net_income"] / df["avg_total_assets"]
    df["roe"] = df["net_income"] / df["avg_equity"]
    df["current_ratio"] = df["current_assets"] / df["current_liabilities"]
    df["leverage"] = df["long_term_debt"] / df["total_assets"]
    df["gross_margin"] = df["gross_profit"].fillna(df["revenue"] - df["cost_of_revenue"]) / df["revenue"]
    df["asset_turnover"] = df["revenue"] / df["avg_total_assets"]
    df["fcf"] = df["cfo"] - df["capex"]
    df["total_debt"] = df["long_term_debt"].fillna(0) + df["short_term_debt"].fillna(0)
    df["de_ratio"] = df["total_debt"] / df["equity"]

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

    # v8 addition: Asset Growth anomaly (Cooper, Gulen & Schill 2008,
    # Journal of Finance) -- companies that grow TOTAL ASSETS aggressively
    # tend to UNDERPERFORM subsequently (over-investment/empire-building),
    # the OPPOSITE prediction from "growth is good." Deliberately a
    # DIFFERENT metric from capacity_expansion (capex growth specifically,
    # tested above) -- total asset growth captures acquisitions, working-
    # capital buildup, and everything else, not just new plant/equipment.
    # pass = LOW asset growth (<10% YoY), a CONTRARIAN screen: this
    # anomaly predicts low-growth companies outperform, not high-growth
    # ones -- so the "pass" flag intentionally selects the low-growth tail.
    df["total_assets_prior"] = g["total_assets"].shift(1)
    df["asset_growth"] = (df["total_assets"] - df["total_assets_prior"]) / df["total_assets_prior"].abs()
    df["low_asset_growth_pass"] = ((df["asset_growth"] < 0.10) & (df["asset_growth"] > -0.50)).astype(int)

    # v8 addition: Buyback Yield -- net YoY share-count REDUCTION, a
    # magnitude-aware "shareholder yield" component commonly cited
    # alongside dividend yield in financial media. Distinct from
    # Piotroski's f_no_dilution (a binary "shares didn't increase" check
    # with no magnitude threshold) -- this requires a MEANINGFUL buyback
    # (>=2% net reduction), not just "flat or down."
    df["shares_prior"] = g["shares"].shift(1)
    df["buyback_pct"] = -(df["shares"] - df["shares_prior"]) / df["shares_prior"].abs()
    df["buyback_yield_pass"] = (df["buyback_pct"] > 0.02).astype(int)

    # --- v4 addition (2026-07-17): PEAD proxy + debt reduction ---------------
    # PEAD (post-earnings-announcement drift, Ball & Brown 1968; Bernard &
    # Thomas 1989/1990): a positive earnings surprise keeps drifting the
    # price up for weeks afterward, already directly testable here since
    # every screener's forward return is measured from the `filed` date.
    # Surprise proxy = D-12's own convention from pead_sector_spillover.py
    # (this account's already-established methodology when no analyst
    # consensus exists): a "seasonal random walk" expectation -- this
    # year's net income is expected to equal last year's, so ni_growth>0
    # is a "beat" of that naive expectation. Deliberately NOT reusing
    # Bull Cartel's own ni_growth>0.20 threshold -- PEAD's literature
    # claim is about beating a flat expectation, not about high-growth
    # names specifically, so the bar here is 0%, not 20%.
    df["pead_positive_surprise_pass"] = (df["ni_growth"] > 0).astype(int)

    # "Stepping out of debt": literal deleveraging -- TOTAL DEBT (long +
    # short term) fell >=10% YoY, not just a de_ratio improvement that
    # could come from equity growth alone with debt flat.
    #
    # total_debt (above) uses .fillna(0) on each component, a fine
    # convention for LEVEL screens (de_ratio, invested_capital) but
    # dangerous for a CHANGE calc: a SEC EDGAR tag that's simply missing
    # for one year -- not the company actually having zero debt -- would
    # register as a fake "-100% reduction" when it's absent, or a fake
    # spike when it reappears. Caught on VZ specifically (a company that
    # always carries substantial debt): total_debt swung from $61B to a
    # LITERAL $0 and back across consecutive filings purely from tag
    # gaps. total_debt_strict requires BOTH components present (non-null)
    # in a given year -- missing data stays missing, not zero.
    debt_data_complete = df["long_term_debt"].notna() & df["short_term_debt"].notna()
    df["total_debt_strict"] = df["total_debt"].where(debt_data_complete)
    df["total_debt_strict_prior"] = df.groupby("ticker")["total_debt_strict"].shift(1)
    df["debt_change_pct"] = (
        (df["total_debt_strict"] - df["total_debt_strict_prior"]) / df["total_debt_strict_prior"].abs())
    df["debt_reduction_pass"] = (
        (df["debt_change_pct"] < -0.10) & (df["total_debt_strict_prior"] >= 1e6)  # ignore near-zero-base noise
    ).astype(int)

    # EPS for the Graham 10-year-average-earnings screen (computed here so the
    # rolling window is available before the price join). Fresh groupby call
    # (not reusing `g` above) since `eps` didn't exist when `g` was created.
    df["eps"] = df["net_income"] / df["shares"]
    df["eps_10y_avg"] = (
        df.groupby("ticker")["eps"].rolling(10, min_periods=5).mean().reset_index(level=0, drop=True)
    )

    # --- v7 addition: EPS Growth -- the number every earnings headline
    # leads with ("beat/missed EPS estimates"), distinct from ni_growth
    # (net income growth): EPS growth is diluted by share-count changes
    # (buybacks push EPS growth above NI growth; dilution pushes it below)
    # in a way NI growth alone can't capture. Fresh groupby (eps didn't
    # exist when `g` above was created), same convention as eps_10y_avg.
    df["eps_prior"] = df.groupby("ticker")["eps"].shift(1)
    df["eps_growth"] = (df["eps"] - df["eps_prior"]) / df["eps_prior"].abs()
    df["eps_growth_pass"] = (df["eps_growth"] > 0.15).astype(int)

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
    # v7 addition: ROIC as its OWN screener, not just a Magic Formula input --
    # one of the most-cited profitability metrics in market commentary
    # ("high-ROIC business"). 15% matches ROCE-Plus's own level threshold,
    # kept identical for direct comparability between the two capital-
    # efficiency metrics rather than picking a different number.
    df["roic_pass"] = (df["roic"] > 0.15).astype(int)

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

    # --- v6 addition (2026-07-17): Screener.in "Profitability & Returns" /
    # "Margins" category, applied to US SEC EDGAR data. User-requested
    # follow-up to debt_reduction: work through the standard Screener.in
    # parameter taxonomy (screener.in/screens/298558) for combinations not
    # yet tested. Net Margin and Operating Margin are the two margin
    # ratios that need no price join (pure income-statement), so computed
    # here alongside gross_margin (already used inside Piotroski).
    df["net_margin"] = df["net_income"] / df["revenue"]
    df["operating_margin"] = df["ebit"] / df["revenue"]
    df["net_margin_pass"] = (df["net_margin"] > 0.10).astype(int)
    df["operating_margin_pass"] = (df["operating_margin"] > 0.15).astype(int)

    # v7 addition: FCF Margin (FCF/Revenue) -- an EFFICIENCY metric, distinct
    # from FCF Yield (FCF/market cap, a VALUATION metric already computed
    # in attach_market_cap). A company can have a healthy FCF margin while
    # looking expensive on FCF yield, or vice versa -- two different claims.
    df["fcf_margin"] = df["fcf"] / df["revenue"]
    df["fcf_margin_pass"] = (df["fcf_margin"] > 0.10).astype(int)

    # --- 2026-07-18 addition: screener.in field-list gap-fill (Bucket B) --
    # Every field below is derived from columns already computed in this
    # function -- no new data collection. See the "Recent"/"Preceding"/
    # "Historical" screener.in field list this responds to (session notes).
    # Window periods (3/5/7/10yr, or a subset) match exactly what that list
    # asked for per metric -- not applied uniformly to every metric.

    # Preceding-year values ("Preceding" column group). Same shift(1)
    # pattern as equity_prior_bal/total_assets_prior_bal above.
    df["roa_prior"] = g["roa"].shift(1)
    df["roe_prior"] = g["roe"].shift(1)
    df["roce_prior"] = g["roce"].shift(1)

    # Earning Power (Graham): EBIT / total assets -- a pre-tax, pre-leverage
    # profitability measure, distinct from ROA (which uses net income).
    df["earning_power"] = df["ebit"] / df["total_assets"]

    # Real Graham Number: sqrt(22.5 x EPS x BVPS) -- the textbook Benjamin
    # Graham fair-value estimate. NOT the same test as graham_10y_pass
    # (attach_market_cap, below) -- that implements a DIFFERENT Graham
    # screen (P/E vs 10yr-avg-EPS < 15). Both are legitimate Graham
    # screens under the same author's name; don't collapse them.
    df["bvps"] = df["equity"] / df["shares"]
    df["graham_number"] = (22.5 * df["eps"] * df["bvps"]).clip(lower=0) ** 0.5

    # DuPont Financial Leverage: avg total assets / avg equity -- the
    # textbook multiplier in ROE = net margin x asset turnover x financial
    # leverage. Distinct from the existing `leverage` field above
    # (long_term_debt / total_assets, a simplified debt-only proxy --
    # flagged as a VARIANT in RATIO_DEFINITIONS_CFA.md). Do not conflate
    # the two under one name.
    df["financial_leverage_dupont"] = df["avg_total_assets"] / df["avg_equity"]

    # Historical averages/medians ("Historical" column group). Same
    # rolling(N, min_periods=...) pattern as roce_5y_mean above.
    # CAVEAT: median fiscal-period depth per India ticker is only 3 --
    # 10yr windows resolve for a minority of tickers (~16% per the
    # 2026-07-18 gap analysis). min_periods already returns NaN rather
    # than a fabricated average for thin history -- don't "fix" this by
    # lowering min_periods to force more coverage out of less data.
    def _min_periods(n):
        return max(2, -(-n * 6 // 10))  # ceil(n * 0.6), floored at 2

    for _n in (3, 5, 7, 10):
        _mp = _min_periods(_n)
        df[f"roe_{_n}y_mean"] = g["roe"].rolling(_n, min_periods=_mp).mean().reset_index(level=0, drop=True)
        df[f"roce_{_n}y_mean"] = g["roce"].rolling(_n, min_periods=_mp).mean().reset_index(level=0, drop=True)
    for _n in (5, 10):
        df[f"roce_{_n}y_median"] = g["roce"].rolling(_n, min_periods=_min_periods(_n)).median().reset_index(level=0, drop=True)
    for _n in (5, 10):
        df[f"opm_{_n}y_mean"] = g["operating_margin"].rolling(_n, min_periods=_min_periods(_n)).mean().reset_index(level=0, drop=True)
    for _n in (3, 5):
        df[f"roic_{_n}y_mean"] = g["roic"].rolling(_n, min_periods=_min_periods(_n)).mean().reset_index(level=0, drop=True)
        df[f"roa_{_n}y_mean"] = g["roa"].rolling(_n, min_periods=_min_periods(_n)).mean().reset_index(level=0, drop=True)

    # ROE 5-year growth: current ROE vs ROE 5 periods back.
    df["roe_5y_ago"] = g["roe"].shift(5)
    df["roe_5y_growth"] = (df["roe"] - df["roe_5y_ago"]) / df["roe_5y_ago"].abs()

    # N-years-back raw values ("Historical" group: Number of equity shares
    # 10 years back, Book value 3/5/10 years back).
    df["shares_10y_back"] = g["shares"].shift(10)
    for _n in (3, 5, 10):
        df[f"bvps_{_n}y_back"] = g["bvps"].shift(_n)

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

    # --- v6 addition: Screener.in "Valuation Multipliers" category, the
    # mcap-dependent ratios (need the price join above) -----------------------
    # P/B: mcap / book value (equity). <3 is a standard "not overpriced
    # relative to net assets" value threshold (screener.in and Graham-style
    # value screens commonly use 3-5x as the ceiling).
    merged["pb_ratio"] = merged["mcap"] / merged["equity"]
    merged["pb_pass"] = ((merged["pb_ratio"] > 0) & (merged["pb_ratio"] < 3)).astype(int)

    # P/S: mcap / revenue. <2 is a standard moderate-value threshold (deep
    # value screens sometimes use <1; this uses the more common, less
    # restrictive convention).
    merged["ps_ratio"] = merged["mcap"] / merged["revenue"]
    merged["ps_pass"] = ((merged["ps_ratio"] > 0) & (merged["ps_ratio"] < 2)).astype(int)

    # EV/EBITDA: (mcap + total_debt - cash) / (EBIT + D&A). <10 is the
    # standard "reasonably priced" ceiling used across both US and Indian
    # value-investing convention -- capital-structure-neutral, unlike P/E.
    merged["ebitda"] = merged["ebit"] + merged["d_and_a"].fillna(0)
    merged["ev"] = merged["mcap"] + merged["total_debt"] - merged["cash"]
    merged["ev_ebitda"] = merged["ev"] / merged["ebitda"]
    merged["ev_ebitda_pass"] = (
        (merged["ebitda"] > 0) & (merged["ev_ebitda"] > 0) & (merged["ev_ebitda"] < 10)
    ).astype(int)

    # v7 addition: Net Debt/EBITDA -- the standard credit/leverage metric
    # in financial-media coverage ("net debt to EBITDA of 3.5x"), distinct
    # from D/E (which uses book equity, not cash-earnings capacity). <2.0x
    # is a common "conservatively levered" threshold in credit analysis.
    # A LEVEL screen (is leverage currently low), complementary to
    # debt_reduction (a CHANGE screen -- is leverage falling).
    merged["net_debt"] = merged["total_debt"] - merged["cash"]
    merged["net_debt_ebitda"] = merged["net_debt"] / merged["ebitda"]
    merged["net_debt_ebitda_pass"] = (
        (merged["ebitda"] > 0) & (merged["net_debt_ebitda"] < 2.0)
    ).astype(int)

    # v7 addition: EV/Sales -- commonly cited for growth/unprofitable
    # companies where P/E and EV/EBITDA don't work (no earnings yet).
    # Distinct from P/S: uses EV (capital-structure-neutral), not just
    # market cap. <3 is a looser, more growth-oriented convention than
    # ps_pass's <2 P/S ceiling (deliberately different thresholds for two
    # different valuation lenses).
    merged["ev_sales"] = merged["ev"] / merged["revenue"]
    merged["ev_sales_pass"] = ((merged["ev_sales"] > 0) & (merged["ev_sales"] < 3)).astype(int)

    # PEG (Peter Lynch): trailing P/E / trailing earnings growth. <1 is
    # Lynch's own classic "attractively priced relative to its own growth"
    # threshold. Documented approximation: PEG's textbook definition uses
    # FORWARD growth (analyst estimates), not available here -- ni_growth
    # (trailing YoY, already computed) is used instead, same "no consensus
    # data, use the trailing/seasonal proxy" convention as D-12's PEAD
    # surprise proxy elsewhere in this file.
    merged["pe_ttm"] = merged["mcap"] / merged["net_income"]
    merged["peg_ratio"] = merged["pe_ttm"] / (merged["ni_growth"] * 100)
    merged["peg_pass"] = (
        (merged["net_income"] > 0) & (merged["ni_growth"] > 0)
        & (merged["peg_ratio"] > 0) & (merged["peg_ratio"] < 1)
    ).astype(int)

    # FCF Yield: free cash flow / market cap. >5% is a common institutional
    # "cheap relative to real cash generation" screening bar -- distinct
    # from Coffee Can's raw fcf>0 binary (this is a YIELD, not a sign check).
    merged["fcf_yield"] = merged["fcf"] / merged["mcap"]
    merged["fcf_yield_pass"] = (merged["fcf_yield"] > 0.05).astype(int)

    # --- 2026-07-18 addition: screener.in field-list gap-fill (Bucket B),
    # market-cap-dependent part -- these need the price join above, so they
    # live here rather than in compute_fundamental_screens(). `merged` is
    # sorted by `filed` (from the merge_asof above), and each ticker's own
    # rows are a monotonic ascending subsequence of that sort, so
    # groupby("ticker").shift(N) below correctly walks N filings back per
    # ticker -- same ordering guarantee compute_fundamental_screens()
    # relies on via its own explicit sort_values(["ticker", "fy_end"]).
    g2 = merged.groupby("ticker")

    # Expose PE as its own screener (pe_ttm was already computed above,
    # but only ever consumed as an intermediate for peg_ratio until now).
    # <25 is a conventional "not obviously expensive" ceiling; loss-makers
    # (net_income<=0) produce a negative/undefined PE and are excluded,
    # same convention as peg_pass's net_income>0 gate above.
    merged["pe_pass"] = ((merged["net_income"] > 0) & (merged["pe_ttm"] > 0) & (merged["pe_ttm"] < 25)).astype(int)

    # Historical PE / PBV N-years-back and Market Cap N-years-back
    # ("Historical" column group).
    for _n in (3, 5, 7, 10):
        merged[f"pe_{_n}y_back"] = g2["pe_ttm"].shift(_n)
        merged[f"pbv_{_n}y_back"] = g2["pb_ratio"].shift(_n)
        merged[f"mcap_{_n}y_back"] = g2["mcap"].shift(_n)

    return merged


# ── Build the symbol-year factor table ──────────────────────────────────────

def build_fundamental_signal_dates(fund_scored: pd.DataFrame) -> pd.DataFrame:
    """One row per (symbol, filed-date) where >=1 fundamental screen passed,
    tagged with WHICH screens passed on that filing."""
    cols = ["piotroski_pass", "coffee_can_pass", "magic_formula_pass", "bull_cartel_pass",
            "roce_plus_pass", "sloan_pass", "not_distress",
            "capacity_expansion_pass", "growth_stocks_pass", "graham_10y_pass", "small_cap_growth_pass",
            "pead_positive_surprise_pass", "debt_reduction_pass",
            "net_margin_pass", "operating_margin_pass", "pb_pass", "ps_pass",
            "ev_ebitda_pass", "peg_pass", "fcf_yield_pass",
            "eps_growth_pass", "roic_pass", "fcf_margin_pass", "net_debt_ebitda_pass", "ev_sales_pass",
            "low_asset_growth_pass", "buyback_yield_pass", "pe_pass"]
    df = fund_scored.dropna(subset=["filed"]).copy()
    df["any_pass"] = df[cols].sum(axis=1) > 0
    df = df[df["any_pass"]]
    out = df[["ticker", "filed"] + cols].rename(columns={"ticker": "symbol", "filed": "signal_date"})
    return out


BENCHMARK_SYMBOL = "SPY"  # US scope only -- see factorial_screener_test_IN.py (technical) and
# factorial_screener_test_IN_full.py (technical + fundamental, added once a genuine
# balance-sheet-bearing India fundamentals panel existed) for the India equivalents,
# both of which monkeypatch this module-level global to NIFTYBEES at import time.


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
    lb = low_beta_signals(ohlcv)
    lb["screener"] = "low_beta"
    print(f"  golden_cross: {len(gc):,} signals across {gc['symbol'].nunique():,} symbols")
    print(f"  darvas: {len(dv):,} signals across {dv['symbol'].nunique():,} symbols")
    print(f"  new_highs: {len(nh):,} signals across {nh['symbol'].nunique():,} symbols")
    print(f"  below_200dma: {len(b200):,} signals across {b200['symbol'].nunique():,} symbols")
    print(f"  reversal_weekly: {len(rev_w):,} signals across {rev_w['symbol'].nunique():,} symbols")
    print(f"  reversal_monthly: {len(rev_m):,} signals across {rev_m['symbol'].nunique():,} symbols")
    print(f"  low_beta: {len(lb):,} signals across {lb['symbol'].nunique():,} symbols")

    print("\nComputing v8 insider Form 4 / FINRA short interest signals (S&P 500 scope only)...")
    ins = insider_buying_signals()
    ins["screener"] = "insider_buying"
    print(f"  insider_buying: {len(ins):,} signals across {ins['symbol'].nunique():,} symbols")
    shi = short_interest_decline_signals()
    shi["screener"] = "short_interest_decline"
    print(f"  short_interest_decline: {len(shi):,} signals across {shi['symbol'].nunique():,} symbols")

    print("\nComputing fundamental signals...")
    fund_scored = compute_fundamental_screens(fund)
    fund_scored = attach_market_cap(fund_scored, ohlcv)
    fund_sig = build_fundamental_signal_dates(fund_scored)
    for c in ["piotroski_pass", "coffee_can_pass", "magic_formula_pass", "bull_cartel_pass",
              "roce_plus_pass", "sloan_pass", "not_distress",
              "capacity_expansion_pass", "growth_stocks_pass", "graham_10y_pass", "small_cap_growth_pass",
              "pead_positive_surprise_pass", "debt_reduction_pass",
              "net_margin_pass", "operating_margin_pass", "pb_pass", "ps_pass",
              "ev_ebitda_pass", "peg_pass", "fcf_yield_pass",
            "eps_growth_pass", "roic_pass", "fcf_margin_pass", "net_debt_ebitda_pass", "ev_sales_pass",
              "low_asset_growth_pass", "buyback_yield_pass", "pe_pass"]:
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
                     ("small_cap_growth_pass", "small_cap_growth"),
                     ("pead_positive_surprise_pass", "pead_positive_surprise"),
                     ("debt_reduction_pass", "debt_reduction"),
                     ("net_margin_pass", "net_margin"),
                     ("operating_margin_pass", "operating_margin"),
                     ("pb_pass", "pb_value"),
                     ("ps_pass", "ps_value"),
                     ("ev_ebitda_pass", "ev_ebitda_value"),
                     ("peg_pass", "peg_value"),
                     ("fcf_yield_pass", "fcf_yield"),
                     ("eps_growth_pass", "eps_growth"),
                     ("roic_pass", "roic_value"),
                     ("fcf_margin_pass", "fcf_margin"),
                     ("net_debt_ebitda_pass", "net_debt_ebitda"),
                     ("ev_sales_pass", "ev_sales"),
                     ("low_asset_growth_pass", "low_asset_growth"),
                     ("buyback_yield_pass", "buyback_yield"),
                     ("pe_pass", "pe_value")]:
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
                              lb[["symbol", "signal_date", "screener"]],
                              ins[["symbol", "signal_date", "screener"]],
                              shi[["symbol", "signal_date", "screener"]],
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
