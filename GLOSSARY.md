# Glossary of Trading & Quant Terms

A reference for every domain term used across this repository — screeners,
metrics, ML methods, market structure, and architecture concepts.

> ⚠️ Educational/research use only. Nothing here is investment advice.

---

## 1. Market Structure & Data

| Term | Meaning |
|------|---------|
| **OHLCV** | Open, High, Low, Close, Volume — the five values describing one trading bar (day or intraday). The base unit of all price data here. |
| **Bar / Candle** | One period's OHLCV. A "daily bar" = one trading day; a "15-min bar" = 15 minutes of trading. |
| **NSE** | National Stock Exchange of India — the primary Indian equity exchange (~2,400 EQ stocks). |
| **BSE** | Bombay Stock Exchange — India's other main exchange; "BSE-only" = listed on BSE but not NSE. |
| **NASDAQ / NYSE** | The two main US exchanges (~7,600 stocks combined). |
| **EQ series** | NSE "Equity" series — normal delivery-based stocks (excludes bonds, ETFs, T-segment). |
| **Bhavcopy** | NSE's official end-of-day CSV of every instrument traded that day. Used here to fetch the symbol universe and detect new listings. |
| **Ticker / Symbol** | A stock's short code (e.g. `RELIANCE`, `AAPL`). yfinance suffixes: `.NS` (NSE), `.BO` (BSE), none (US). |
| **Index** | A basket tracking a market segment — **Nifty 50** (top 50 NSE stocks), **S&P 500** (top 500 US), used as benchmarks. |
| **Ticker universe** | The full set of symbols being scanned (NSE 2,406 + BSE 317 + NASDAQ 4,320 + NYSE 2,831). |
| **Corporate action** | Events changing a stock: splits, dividends, bonus, rights issues. Can distort raw price history. |
| **Auto-adjust** | yfinance setting that back-adjusts prices for splits/dividends so the series is continuous. |
| **Survivorship bias** | The error of only studying stocks that still exist today — delisted (often worst) stocks are invisible, making strategies look better than reality. |
| **Look-ahead bias** | Using information in a backtest that wouldn't have been available at the time — inflates results. Fixed here via "as-of" feature cutoffs. |

---

## 2. Price & Return Concepts

| Term | Meaning |
|------|---------|
| **Return** | % change in price over a period. `(end − start) / start × 100`. |
| **Forward return** | Return measured *after* a signal date — e.g. "T+21d return" = return 21 trading days later. The thing backtests try to predict. |
| **Horizon (T+N)** | How far ahead a return is measured. Used here: T+1d, T+3d, T+5d (1wk), T+10d (2wk), T+21d (1mo), T+63d (3mo), T+126d (6mo), T+252d (1yr). |
| **CAGR** | Compound Annual Growth Rate — the smoothed yearly return: `(end/start)^(1/years) − 1`. Used in the Coffee Can screen. |
| **Alpha** | Return *above a benchmark*. Strategy return − Nifty/S&P buy-and-hold return over the same window. The "edge". |
| **Buy-and-hold (BH)** | The passive baseline: buy and never sell. A strategy must beat this to be worth the effort. |
| **Drawdown** | The drop from a peak to a subsequent trough. **Max drawdown** = the worst such drop — the key pain metric. |
| **Transaction cost** | Real-world friction (STT + brokerage ≈ 0.2% round-trip in India) deducted from backtest returns so they're realistic. |
| **Slippage** | The gap between expected and actual execution price; worse for illiquid stocks. |
| **Liquidity** | How easily a stock trades without moving the price. Proxied here by dollar volume (`Close × Volume`). |

---

## 3. The Six Screeners

| Screener | What it looks for | Key thresholds (this repo) |
|----------|-------------------|----------------------------|
| **Darvas Box** | Price breaking *above* a confirmed consolidation box, on rising volume. A momentum-breakout signal (Nicolas Darvas, 1960). | Box top held 3 days; breakout volume ≥ 1.2× 20-day avg. Current bar excluded from box. |
| **Golden Crossover** | The 50-day moving average crossing *above* the 200-day — a classic bullish trend signal. | 50 DMA > 200 DMA (cross today = signal). Needs ≥ 200 bars. |
| **Piotroski F-Score** | A 9-point accounting-quality score (Piotroski 2000): profitability, leverage, efficiency. Higher = financially strengthening. | F-Score ≥ 7 / 9. Financial companies excluded. |
| **Coffee Can** | Long-term quality compounders (Mukherjea/Marcellus): consistent growth + high returns + low debt. Buy and forget for 10 years. | CAGR > 10%, ROCE > 15%, D/E < 1, MCap ≥ ₹500 Cr, no loss year. |
| **Magic Formula** | Joel Greenblatt (2005): good businesses at cheap prices — high return on capital + high earnings yield. | ROIC > 15%, Earnings Yield > 8%, MCap > ₹100 Cr, positive earnings, ex-financials. |
| **Bull Cartel** | Strong quarterly earnings momentum (screener.in screen). | YoY sales growth > 15%, profit growth > 20%, net profit > ₹1 Cr. |
| **Triple Hit** | Composite: Darvas Breakout **AND** Piotroski ≥7 **AND** Coffee Can pass. Highest-conviction signal. | All three simultaneously (≈8 of 2,400 stocks). |
| **Multi-Screen Hit** | Passes 3 or more of the 6 screeners at once. | ≥ 3 of 6. |

---

## 4. Technical Indicators

| Term | Meaning |
|------|---------|
| **DMA / SMA** | (Daily/Simple) Moving Average — the average close over N days. Smooths price to reveal trend. |
| **50 DMA / 200 DMA** | The two most-watched averages. Price above 200 DMA = long-term uptrend; 50 above 200 = "golden cross". |
| **EMA** | Exponential Moving Average — like SMA but weights recent prices more. |
| **RSI (14)** | Relative Strength Index — momentum oscillator 0–100. >70 = overbought, <30 = oversold. |
| **MACD** | Moving Average Convergence Divergence — trend/momentum indicator (12-EMA − 26-EMA, with a 9-EMA signal line). **MACD histogram** = MACD − signal. |
| **Bollinger Bands** | A 20-day average ± 2 standard deviations. **%B** = where price sits within the bands (0 = lower, 1 = upper). **Squeeze** = bands narrow → big move often follows. |
| **ATR** | Average True Range — a volatility measure (typical daily price range). |
| **VWAP** | Volume-Weighted Average Price — the day's average price weighted by volume; an intraday fair-value anchor. |
| **OBV** | On-Balance Volume — cumulative volume that adds on up-days, subtracts on down-days; confirms trends. |
| **Box top / bottom** | The ceiling/floor of a Darvas Box — resistance and support. Box bottom doubles as a natural stop-loss. |

---

## 5. Fundamental Metrics

| Term | Meaning |
|------|---------|
| **PE (Price/Earnings)** | Price ÷ earnings per share. How much you pay per ₹1 of profit. High = expensive (or high-growth). |
| **PE Zone** | This repo's sector-aware label: 🟢 BUY (cheap), 🟡 FAIR, 🟠 CAUTION, 🔴 SELL (expensive). Thresholds differ by sector (banks ~12–22×, FMCG ~40–80×). |
| **Forward PE** | PE using *projected* next-year earnings instead of trailing. |
| **ROIC** | Return on Invested Capital — EBIT ÷ (assets − current liabilities). How efficiently capital generates profit. |
| **ROCE** | Return on Capital Employed — similar to ROIC; core of the Coffee Can quality test. |
| **ROA / ROE** | Return on Assets / Equity — profit relative to assets / shareholder equity. |
| **Earnings Yield** | EBIT ÷ Enterprise Value — the inverse of PE; higher = cheaper. Core of Magic Formula. |
| **EBIT** | Earnings Before Interest & Taxes — operating profit. |
| **Enterprise Value (EV)** | Market cap + debt − cash. The true cost to "buy the whole company". |
| **D/E (Debt-to-Equity)** | Total debt ÷ equity. Lower = safer balance sheet. (yfinance sometimes reports as %, normalised here.) |
| **Market Cap** | Share price × shares outstanding. Total company value. Crore (₹, India) = 10 million; reported in ₹Cr here. |
| **Free Cash Flow (FCF)** | Operating cash flow − capital expenditure. Cash a business actually generates. |
| **Book Value** | Net asset value per share (assets − liabilities). |
| **Bull/Bear** | Bull = rising market/optimism; Bear = falling market/pessimism. |

---

## 6. Market Regime & Sentiment

| Term | Meaning |
|------|---------|
| **Market Regime** | The prevailing market state, classified here from the index vs its 200 DMA: **BULL** (above, rising), **BEAR** (below, falling), **SIDEWAYS** (near the DMA / flat). |
| **VIX** | Volatility Index — the market's "fear gauge". India VIX / CBOE VIX. <12 complacency, 12–17 normal, 17–22 elevated, >25 panic. Drives position-size scaling here. |
| **FII / DII** | Foreign / Domestic Institutional Investors. Their net buy/sell flow is a macro sentiment signal. |
| **Bulk deal / Block deal** | Large institutional trades disclosed by NSE. Confirmation of conviction buying/selling. |
| **Breadth** | How broadly the market is participating (advances vs declines, % above 200 DMA). |

---

## 7. Backtesting & Statistics

| Term | Meaning |
|------|---------|
| **Backtest** | Simulating a strategy on historical data to estimate how it *would* have performed. |
| **Walk-forward** | A backtest that only ever uses past data at each point — no peeking ahead. The gold standard for realism. |
| **Train / Test / Validation** | Chronological data splits (60/20/20 here). Train = learn; Test = tune; Validation = final unseen check. |
| **Hit rate** | % of signals that produced a positive return. |
| **Expected Value (EV)** | `hit_rate × avg_win − miss_rate × avg_loss`. The single best summary of edge — accounts for both odds and magnitude. |
| **Sharpe ratio** | Return ÷ volatility (risk-adjusted return). Higher = more return per unit of risk. >1 good, >2 excellent. |
| **Sortino ratio** | Like Sharpe but only penalises *downside* volatility — fairer for asymmetric returns. |
| **Calmar ratio** | Annual return ÷ max drawdown — return per unit of worst-case pain. |
| **Profit factor** | Gross wins ÷ gross losses. >1.5 = healthy strategy. |
| **VaR / CVaR** | Value at Risk — the loss not exceeded with X% confidence (e.g. 95%). CVaR = average loss *beyond* that. |
| **Max drawdown** | Largest peak-to-trough equity drop (see §2). |
| **Overfitting** | A model learning noise instead of signal — looks great on history, fails live. Detected here via Sharpe decay from Train→Val (Bailey et al. 2014). |
| **Non-stationarity** | The fact that market behaviour changes over time, so models must be periodically retrained. |
| **Benchmark** | The yardstick (buy-and-hold Nifty/S&P) a strategy is measured against. |

---

## 8. Machine Learning & AI

| Term | Meaning |
|------|---------|
| **Supervised learning** | Training a model on labelled examples (features → known outcome), e.g. predict next-month return. |
| **Unsupervised learning** | Finding structure with *no* labels, e.g. clustering stocks by behaviour. |
| **Feature** | An input variable describing a stock (momentum, volatility, RSI, etc.). |
| **Feature engineering** | Crafting features from raw OHLCV that carry predictive information. |
| **Z-score normalisation** | Rescaling a feature to mean 0, std 1: `(x − μ) / σ`. Standard ML preprocessing. |
| **Sliding window** | Feeding the last N bars as a sequence (60 days here) to a time-series model. |
| **Linear / Ridge Regression** | Simple predictive models. Ridge adds a penalty to prevent overfitting. (Found to beat LSTM here — AlQahtani 2025.) |
| **GradientBoosting** | An ensemble of decision trees built sequentially; strong tabular learner. Used for both return prediction and directional classification. |
| **KMeans** | Unsupervised clustering into K groups by feature similarity — finds "behavioural archetypes". |
| **DBSCAN** | Density-based clustering that also flags **anomalies** (points fitting no cluster). |
| **PCA** | Principal Component Analysis — compresses many features into a few that capture most variance. |
| **LSTM / RNN / CNN** | Deep-learning architectures for sequences (LSTM/RNN) or grids (CNN). Common in the literature; simpler models matched them on this data. |
| **R² (R-squared)** | Fraction of variance a model explains. ~0 here for return prediction = markets are hard to predict. |
| **RMSE / MAE** | Root Mean Squared Error / Mean Absolute Error — prediction-accuracy metrics (smaller = better). |
| **Directional classification** | Predicting *up vs down* (a class) instead of the exact return (a number) — an easier, more useful framing for trading. |
| **Confluence** | How many independent signals agree at once (e.g. 4 of 6 intraday patterns firing) — higher = stronger conviction. |
| **Ensemble** | Combining several models for better, more stable predictions. |

---

## 9. Intraday Patterns

| Term | Meaning |
|------|---------|
| **ORB (Opening Range Breakout)** | The first 15–30 min defines a range; a break above/below it signals the day's likely direction. |
| **VWAP deviation** | Price stretched far from VWAP → mean-reversion setup. |
| **Volume surge** | Current bar volume ≫ recent average (≥3×) — confirms a real move. |
| **Momentum burst** | 3+ consecutive bars in the same direction — sustained intraday trend. |
| **BB squeeze breakout** | Price breaking out after Bollinger Bands narrow — volatility expansion. |

---

## 10. IPO & New Listings

| Term | Meaning |
|------|---------|
| **IPO** | Initial Public Offering — a company's first listing on an exchange. |
| **Listing gain** | Return since the first trading day. |
| **DRHP** | Draft Red Herring Prospectus — the pre-IPO disclosure document (financials may be projections, not audited). |
| **Lock-in period** | Time (6–18 months) during which promoter shares cannot be sold post-IPO; affects liquidity. |
| **Screener gate** | This repo's rule that a screener only applies once an IPO has enough history (Darvas ≥35 bars, Golden Cross ≥200, etc.). |
| **Bhavcopy diff** | The method here to discover new listings: today's symbols minus those from N days ago. |

---

## 11. Architecture & Engineering (this repo)

| Term | Meaning |
|------|---------|
| **Parquet** | A columnar file format — fast, compressed storage for the 5-year OHLC cache. |
| **3-tier cache** | Memory → Parquet disk → network, tried in order. 334× faster than re-downloading. |
| **DDD (Domain-Driven Design)** | Architecture (v3.1) splitting code into Domain (rules), Application (orchestration), Infrastructure (yfinance/Parquet). |
| **Specification pattern** | Each screener as a composable, testable object (`MagicFormulaSpec.is_satisfied_by(stock)`). |
| **Repository (interface)** | A contract for data access; the Domain says *what* it needs, Infrastructure decides *how*. |
| **Domain event** | A "something happened" message (e.g. `BreakoutDetected`) that decouples parts of the system. |
| **Aggregate root** | The single entry point to a cluster of related objects (here, `Stock` owns its price bars). |
| **ctypes / C extension** | Calling compiled C from Python for speed (Darvas Box runs 313× faster in C). |
| **rpy2 / Rscript** | Bridges to R for battle-tested stats (PerformanceAnalytics, HMM regime detection). |
| **Semantic versioning** | `MAJOR.MINOR.PATCH` (e.g. v3.1.0) — breaking / feature / fix. |

---

## 12. Research References Used

| Author (year) | Contribution applied here |
|---------------|---------------------------|
| Greenblatt (2005) | Magic Formula |
| Piotroski (2000) | F-Score |
| Darvas (1960) | Box breakout method |
| Mukherjea (2018) | Coffee Can portfolio |
| Bailey et al. (2014) | Backtest overfitting test (Sharpe decay) |
| Preet et al. (2021) | Magic Formula on Indian markets |
| Bhute et al. (2024) | Transaction costs, Sortino, benchmark comparison |
| Liu & Zhu (2024) | Market efficiency (US efficient, India less so) |
| Dhanus & Amutha (2025) | Super Trend, volume confirmation |
| AlQahtani et al. (2025) | LR/Ridge beats LSTM/RNN; Z-score; rolling retrain |
| Fister et al. (2019) | Strategy-vs-buy-hold evaluation; risk-adjusted edge |
| Olorunnimbe & Viktor (2022) | Backtesting + economic metrics over RMSE |
| Toichatturat (2024) | Factor models + ensemble, Sharpe scoring |
| Sharma et al. (2025) | DL survey; classification framing; retraining |
| Miao (Stanford CS230) | LSTM hyperparameter study |

---

*See [STOCK_ANALYSIS_SYSTEM.md](STOCK_ANALYSIS_SYSTEM.md) for full methodology and
[Downloads/stock_ddd/README.md](Downloads/stock_ddd/README.md) for architecture.*
