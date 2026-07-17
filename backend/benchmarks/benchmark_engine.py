"""
Portfolio benchmark engine.

Kaggle data sources:
  benchmark/sp500-daily          — andrewmvd/sp-500-stocks (daily OHLCV, all members)
  benchmark/sp500-h1-2025        — codebynadiia/s-and-p-500-stocks-dataset-first-half-2025
  benchmark/sp500-nasdaq-5y      — 5-year S&P 500 & NASDAQ 100 (5-min intervals)
  benchmark/portfolio-with-indices — nikitamanaenkov/stock-portfolio-data-with-prices-and-indices
  benchmark/sp500-fundamentals   — ilyaryabov/financial-performance-of-companies-from-sp500

Metrics computed per portfolio vs benchmark:
  - Total return (portfolio vs benchmark)
  - Alpha (Jensen's alpha, annualised)
  - Beta (market sensitivity)
  - Sharpe ratio (annualised, risk-free = 5%)
  - Max drawdown
  - Correlation with benchmark
  - Tracking error (annualised std of excess returns)
  - Information ratio
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

log = logging.getLogger(__name__)

_KAGGLE_DIR = Path(__file__).parent.parent.parent / 'data' / 'kaggle' / 'benchmark'
_RISK_FREE_RATE = 0.05    # 5% annual
_TRADING_DAYS = 252


class BenchmarkEngine:
    def __init__(self):
        self._sp500: Optional[pd.DataFrame] = None        # (date, ticker) → close
        self._sp500_index: Optional[pd.Series] = None     # date → S&P 500 index level
        self._nasdaq_index: Optional[pd.Series] = None    # date → NASDAQ index level
        self._fundamentals: Optional[pd.DataFrame] = None # ticker → 72 indicators
        self._portfolio_ref: Optional[pd.DataFrame] = None
        self._datasets_loaded: list[str] = []

    # ── public API ─────────────────────────────────────────────────────────────

    def load_all(self) -> None:
        self._load_sp500_prices()
        self._load_sp500_nasdaq_index()
        self._load_fundamentals()
        self._load_portfolio_reference()
        log.info('BenchmarkEngine ready — datasets: %s',
                 self._datasets_loaded or ['none (download with scripts/download_kaggle_datasets.py)'])

    @property
    def loaded_datasets(self) -> list[str]:
        return list(self._datasets_loaded)

    def portfolio_metrics(
        self,
        holdings: list[dict],   # [{ticker, market, purchase_date, purchase_price, quantity}]
        benchmark: str = 'sp500',
    ) -> dict:
        """
        Compare a portfolio against a benchmark index.
        Holdings need purchase_date to compute holding-period returns.
        Returns a dict with all metrics plus per-holding contribution.
        """
        if not holdings:
            return {'error': 'No holdings provided'}

        # Determine date range
        dates = [h.get('purchase_date') for h in holdings if h.get('purchase_date')]
        if not dates:
            return {'error': 'Holdings missing purchase_date — cannot compute returns'}

        start = min(dates)
        end = pd.Timestamp.now().strftime('%Y-%m-%d')

        bench_returns = self._get_benchmark_returns(benchmark, start, end)
        if bench_returns is None or bench_returns.empty:
            return {'error': f'No benchmark data available for {benchmark}. '
                             f'Run scripts/download_kaggle_datasets.py first.'}

        port_returns = self._compute_portfolio_returns(holdings, bench_returns.index)
        if port_returns is None or port_returns.empty:
            return {'error': 'Could not fetch portfolio price history from yfinance'}

        metrics = _compute_metrics(port_returns, bench_returns)
        metrics['benchmark'] = benchmark
        metrics['start_date'] = start
        metrics['end_date'] = end
        metrics['holding_count'] = len(holdings)

        # Per-holding fundamentals from S&P 500 dataset
        metrics['holdings_fundamentals'] = self._enrich_holdings(holdings)

        return metrics

    def ticker_vs_benchmark(
        self,
        ticker: str,
        market: str = 'us',
        period_days: int = 365,
        benchmark: str = 'sp500',
    ) -> dict:
        """Single ticker vs benchmark metrics over the last N days."""
        from fetchers.history import fetch_price_series
        end = pd.Timestamp.now()
        start = end - pd.Timedelta(days=period_days)

        try:
            prices = fetch_price_series(ticker, market, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
            if prices is None or len(prices) < 5:
                return {'error': f'No price data for {ticker}'}
            ticker_returns = prices.pct_change().dropna()
        except Exception as exc:
            return {'error': f'Price fetch failed: {exc}'}

        bench_returns = self._get_benchmark_returns(benchmark, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
        if bench_returns is None or bench_returns.empty:
            return {'error': f'No benchmark data for {benchmark}'}

        aligned = ticker_returns.align(bench_returns, join='inner')
        if len(aligned[0]) < 10:
            return {'error': 'Insufficient overlapping data points'}

        metrics = _compute_metrics(aligned[0], aligned[1])
        metrics['ticker'] = ticker
        metrics['benchmark'] = benchmark
        metrics['period_days'] = period_days

        fundamentals = self._get_ticker_fundamentals(ticker.upper())
        if fundamentals:
            metrics['fundamentals'] = fundamentals

        return metrics

    def benchmark_summary(self) -> dict:
        """Return available benchmark series and their date ranges."""
        summary: dict = {'datasets': self._datasets_loaded}
        if self._sp500_index is not None and not self._sp500_index.empty:
            summary['sp500_index'] = {
                'rows': len(self._sp500_index),
                'start': str(self._sp500_index.index.min()),
                'end': str(self._sp500_index.index.max()),
            }
        if self._nasdaq_index is not None and not self._nasdaq_index.empty:
            summary['nasdaq_index'] = {
                'rows': len(self._nasdaq_index),
                'start': str(self._nasdaq_index.index.min()),
                'end': str(self._nasdaq_index.index.max()),
            }
        if self._sp500 is not None and not self._sp500.empty:
            summary['sp500_stocks'] = {
                'tickers': self._sp500.columns.tolist()[:10],
                'total_tickers': len(self._sp500.columns),
            }
        if self._fundamentals is not None:
            summary['sp500_fundamentals'] = {
                'tickers': len(self._fundamentals),
                'indicators': len(self._fundamentals.columns),
            }
        return summary

    # ── loaders ────────────────────────────────────────────────────────────────

    def _load_sp500_prices(self) -> None:
        """Load daily S&P 500 stock prices (andrewmvd dataset)."""
        import glob
        for subdir in ['sp500-daily', 'sp500-h1-2025']:
            files = glob.glob(str(_KAGGLE_DIR / subdir / 'sp500_stocks.csv')) or \
                    glob.glob(str(_KAGGLE_DIR / subdir / '*.csv'))
            if not files:
                continue
            try:
                frames = []
                # The dataset may be one big CSV or one CSV per ticker
                for fpath in files[:1]:  # start with the main file
                    df = pd.read_csv(fpath, parse_dates=True, low_memory=False)
                    date_col = _find_col(df, ['Date', 'date', 'Datetime'])
                    close_col = _find_col(df, ['Close', 'close', 'Adj Close'])
                    ticker_col = _find_col(df, ['Symbol', 'Ticker', 'symbol', 'ticker'])
                    if date_col and close_col and ticker_col:
                        df[date_col] = pd.to_datetime(df[date_col])
                        pivot = df.pivot_table(index=date_col, columns=ticker_col,
                                               values=close_col, aggfunc='last')
                        frames.append(pivot)
                    elif date_col and close_col:
                        # Single ticker CSV
                        s = df.set_index(date_col)[close_col]
                        frames.append(pd.DataFrame({'price': s}))
                if frames:
                    self._sp500 = pd.concat(frames, axis=1)
                    self._sp500.sort_index(inplace=True)
                    self._datasets_loaded.append(subdir)
                    log.info('Loaded S&P 500 prices from %s: %s tickers, %s rows',
                             subdir, len(self._sp500.columns), len(self._sp500))
                    break
            except Exception as exc:
                log.warning('Failed to load %s: %s', subdir, exc)

    def _load_sp500_nasdaq_index(self) -> None:
        """Load S&P 500 and NASDAQ 100 index level data (5-year dataset)."""
        import glob
        dir_ = _KAGGLE_DIR / 'sp500-nasdaq-5y'
        files = glob.glob(str(dir_ / '*.csv'))
        if not files:
            return
        try:
            for fpath in files:
                df = pd.read_csv(fpath, parse_dates=True, low_memory=False)
                date_col = _find_col(df, ['Date', 'date', 'Datetime', 'Time'])
                close_col = _find_col(df, ['Close', 'close', 'Adj Close'])
                name = Path(fpath).stem.lower()
                if date_col and close_col:
                    df[date_col] = pd.to_datetime(df[date_col])
                    series = df.set_index(date_col)[close_col].sort_index()
                    if 'nasdaq' in name or 'ndx' in name:
                        self._nasdaq_index = series
                    else:
                        self._sp500_index = series
            if self._sp500_index is not None or self._nasdaq_index is not None:
                self._datasets_loaded.append('sp500-nasdaq-5y')
                log.info('Loaded index data: sp500=%s nasdaq=%s',
                         len(self._sp500_index) if self._sp500_index is not None else 'n/a',
                         len(self._nasdaq_index) if self._nasdaq_index is not None else 'n/a')
        except Exception as exc:
            log.warning('Failed to load sp500-nasdaq-5y: %s', exc)

    def _load_fundamentals(self) -> None:
        """Load 72-indicator S&P 500 fundamental data."""
        import glob
        files = glob.glob(str(_KAGGLE_DIR / 'sp500-fundamentals' / '*.csv'))
        if not files:
            return
        try:
            df = pd.read_csv(files[0], low_memory=False)
            ticker_col = _find_col(df, ['Ticker', 'Symbol', 'ticker', 'symbol'])
            if ticker_col:
                df = df.set_index(ticker_col)
            self._fundamentals = df
            self._datasets_loaded.append('sp500-fundamentals')
            log.info('Loaded S&P 500 fundamentals: %d tickers, %d indicators',
                     len(df), len(df.columns))
        except Exception as exc:
            log.warning('Failed to load sp500-fundamentals: %s', exc)

    def _load_portfolio_reference(self) -> None:
        """Load pre-structured portfolio with index comparison data."""
        import glob
        files = glob.glob(str(_KAGGLE_DIR / 'portfolio-with-indices' / '*.csv'))
        if not files:
            return
        try:
            df = pd.read_csv(files[0], parse_dates=True, low_memory=False)
            self._portfolio_ref = df
            self._datasets_loaded.append('portfolio-with-indices')
            log.info('Loaded portfolio reference data: %d rows, cols: %s',
                     len(df), list(df.columns[:8]))
        except Exception as exc:
            log.warning('Failed to load portfolio-with-indices: %s', exc)

    # ── internals ──────────────────────────────────────────────────────────────

    def _get_benchmark_returns(self, benchmark: str, start: str, end: str) -> Optional[pd.Series]:
        """Get daily returns for the chosen benchmark over [start, end]."""
        # Try loaded data first
        index_series = self._sp500_index if benchmark == 'sp500' else self._nasdaq_index
        if index_series is not None and not index_series.empty:
            sliced = index_series.loc[start:end]
            if len(sliced) >= 10:
                return sliced.pct_change().dropna()

        # Try individual stock prices from the sp500 dataset
        if self._sp500 is not None:
            proxy = 'SPY' if benchmark == 'sp500' else 'QQQ'
            if proxy in self._sp500.columns:
                sliced = self._sp500[proxy].loc[start:end].dropna()
                if len(sliced) >= 10:
                    return sliced.pct_change().dropna()

        # Fall back to yfinance
        try:
            import yfinance as yf
            sym = '^GSPC' if benchmark == 'sp500' else '^IXIC'
            hist = yf.Ticker(sym).history(start=start, end=end, auto_adjust=True)
            if not hist.empty:
                return hist['Close'].pct_change().dropna()
        except Exception as exc:
            log.warning('yfinance benchmark fetch failed: %s', exc)

        return None

    def _compute_portfolio_returns(
        self, holdings: list[dict], benchmark_dates: pd.DatetimeIndex
    ) -> Optional[pd.Series]:
        """Weighted daily portfolio returns over the benchmark date range."""
        try:
            import yfinance as yf
            weights, return_series = [], []
            for h in holdings:
                ticker = h.get('yf_ticker') or h.get('ticker', '')
                qty = float(h.get('quantity') or 1)
                price = float(h.get('purchase_price') or 0)
                cost = qty * price if price else qty  # use qty as weight if no price

                hist = yf.Ticker(ticker).history(
                    start=benchmark_dates.min().strftime('%Y-%m-%d'),
                    end=benchmark_dates.max().strftime('%Y-%m-%d'),
                    auto_adjust=True,
                )
                if hist.empty:
                    continue
                r = hist['Close'].pct_change().dropna()
                r.index = pd.to_datetime(r.index).tz_localize(None)
                weights.append(cost)
                return_series.append(r)

            if not return_series:
                return None

            # Align all series to benchmark dates
            aligned = pd.concat(return_series, axis=1)
            aligned.index = pd.to_datetime(aligned.index).tz_localize(None)
            bench_idx = pd.DatetimeIndex([d.tz_localize(None) if hasattr(d, 'tz_localize') else d
                                          for d in benchmark_dates])
            aligned = aligned.reindex(bench_idx, method='nearest', tolerance='1D')
            aligned = aligned.fillna(0)

            total_w = sum(weights)
            w = [wi / total_w for wi in weights]
            portfolio_ret = sum(aligned.iloc[:, i] * w[i] for i in range(len(w)))
            return portfolio_ret
        except Exception as exc:
            log.warning('Portfolio return computation failed: %s', exc)
            return None

    def _enrich_holdings(self, holdings: list[dict]) -> list[dict]:
        if self._fundamentals is None:
            return []
        enriched = []
        for h in holdings:
            ticker = (h.get('yf_ticker') or h.get('ticker', '')).upper()
            if ticker in self._fundamentals.index:
                row = self._fundamentals.loc[ticker]
                enriched.append({
                    'ticker': ticker,
                    'pe_ratio': _safe_float(row.get('P/E', row.get('PE', row.get('priceEarnings')))),
                    'pb_ratio': _safe_float(row.get('P/B', row.get('PB', row.get('priceBook')))),
                    'roe': _safe_float(row.get('ROE', row.get('returnOnEquity'))),
                    'market_cap': _safe_float(row.get('Market Cap', row.get('marketCapitalization'))),
                    'sector': str(row.get('Sector', row.get('sector', ''))),
                })
        return enriched

    def _get_ticker_fundamentals(self, ticker: str) -> Optional[dict]:
        if self._fundamentals is None or ticker not in self._fundamentals.index:
            return None
        row = self._fundamentals.loc[ticker]
        return {k: _safe_float(v) if not isinstance(v, str) else v
                for k, v in row.items() if pd.notna(v)}


# ── metric computation ─────────────────────────────────────────────────────────

def _compute_metrics(port_ret: pd.Series, bench_ret: pd.Series) -> dict:
    port_ret, bench_ret = port_ret.dropna(), bench_ret.dropna()
    common = port_ret.index.intersection(bench_ret.index)
    p = port_ret.loc[common]
    b = bench_ret.loc[common]

    if len(p) < 5:
        return {'error': 'Insufficient data for metric computation'}

    n = len(p)
    rf_daily = _RISK_FREE_RATE / _TRADING_DAYS

    # Cumulative returns
    port_total = float((1 + p).prod() - 1)
    bench_total = float((1 + b).prod() - 1)

    # Annualised returns
    years = n / _TRADING_DAYS
    port_ann = float((1 + port_total) ** (1 / max(years, 0.01)) - 1)
    bench_ann = float((1 + bench_total) ** (1 / max(years, 0.01)) - 1)

    # Volatility (annualised)
    port_vol = float(p.std() * math.sqrt(_TRADING_DAYS))
    bench_vol = float(b.std() * math.sqrt(_TRADING_DAYS))

    # Beta
    cov = float(np.cov(p, b)[0][1])
    bench_var = float(b.var())
    beta = round(cov / bench_var, 3) if bench_var > 0 else None

    # Alpha (Jensen's)
    alpha = round(port_ann - (_RISK_FREE_RATE + (beta or 0) * (bench_ann - _RISK_FREE_RATE)), 4) \
        if beta is not None else None

    # Sharpe ratio
    excess = p - rf_daily
    sharpe = round(float(excess.mean() / excess.std() * math.sqrt(_TRADING_DAYS)), 3) \
        if excess.std() > 0 else None

    # Max drawdown
    cum = (1 + p).cumprod()
    rolling_max = cum.cummax()
    drawdowns = cum / rolling_max - 1
    max_dd = round(float(drawdowns.min()), 4)

    # Correlation
    corr = round(float(p.corr(b)), 3)

    # Tracking error
    excess_vs_bench = p - b
    tracking_error = round(float(excess_vs_bench.std() * math.sqrt(_TRADING_DAYS)), 4)

    # Information ratio
    info_ratio = round(float(excess_vs_bench.mean() / excess_vs_bench.std() * math.sqrt(_TRADING_DAYS)), 3) \
        if excess_vs_bench.std() > 0 else None

    return {
        'portfolio_total_return': round(port_total, 4),
        'benchmark_total_return': round(bench_total, 4),
        'portfolio_annualised_return': round(port_ann, 4),
        'benchmark_annualised_return': round(bench_ann, 4),
        'portfolio_volatility': round(port_vol, 4),
        'benchmark_volatility': round(bench_vol, 4),
        'alpha': alpha,
        'beta': beta,
        'sharpe_ratio': sharpe,
        'max_drawdown': max_dd,
        'correlation': corr,
        'tracking_error': tracking_error,
        'information_ratio': info_ratio,
        'data_points': n,
    }


# ── helpers ────────────────────────────────────────────────────────────────────

def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return round(f, 4) if not math.isnan(f) else None
    except (TypeError, ValueError):
        return None


# Global singleton
engine = BenchmarkEngine()
