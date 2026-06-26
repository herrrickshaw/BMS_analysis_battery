# Stock Analysis & Backtesting System

**Author:** Uma Shankar  
**Last updated:** June 2026  
**Location:** `~/Downloads/` (scripts) | `~/wf_backtest/`, `~/backtest_results/`, `~/screener_results/`, `~/indian_full_scan/`, `~/us_full_scan/` (outputs)

---

## ⚠️ IMPORTANT DISCLAIMER

> This system is for **educational and research purposes only**.  
> It does **NOT** constitute financial advice, investment recommendations, or any form of solicitation to buy or sell securities.  
> Screener results are mechanical filters — they are **NOT** buy or sell signals.  
> Past screening results and backtest performance do **NOT** guarantee future returns.  
> Capital markets involve risk — you may lose part or all of your investment.  
> Always consult a **SEBI-registered investment advisor** before making any investment decision.

---

## 1. System Overview

A six-layer quantitative research platform covering the full NSE + BSE + NASDAQ + NYSE universe with six screeners, walk-forward backtesting, and live market regime detection.

```
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 1: Data          nse_data_fetcher.py                          │
│   nsepython (live) + yfinance (history) + nse-library (bhavcopy)   │
├─────────────────────────────────────────────────────────────────────┤
│ LAYER 2: Live Screen   screener_analysis.py                         │
│   6 screeners on screener.in pre-filtered lists (markitdown)        │
├─────────────────────────────────────────────────────────────────────┤
│ LAYER 3: Full Scan     full_indian_market_scan.py                   │
│                        full_us_market_scan.py                       │
│   All 6 screeners on full NSE+BSE (~2,700) and NASDAQ+NYSE (~8,000) │
├─────────────────────────────────────────────────────────────────────┤
│ LAYER 4: Backtest      backtest_screeners.py                        │
│   1-year walk-forward | 5 horizons | BULL/BEAR/SIDEWAYS regime      │
├─────────────────────────────────────────────────────────────────────┤
│ LAYER 5: Research      walk_forward_backtest.py                     │
│   3y/5y/10y periods | Train/Test/Val | 8 horizons | filing trends  │
├─────────────────────────────────────────────────────────────────────┤
│ LAYER 6: Scheduler     morning-stock-analysis-report (cron 8:30 AM) │
│   Runs all scripts | Emails HTML report | Strategy recommendations   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Sources

### 2.1 nsepython (live NSE data)

| Function | What it returns | Used for |
|---|---|---|
| `nse_eq_symbols()` | 2,372 live NSE EQ tickers | Symbol universe |
| `indiavix()` | India VIX (current float) | Regime classification |
| `get_bulkdeals()` | Today's bulk deals DataFrame | Institutional confirmation |
| `get_blockdeals()` | Today's block deals | High-conviction institutional |
| `nse_events()` | Upcoming board meetings / results (75 events) | Filing event calendar |
| `nse_get_index_quote()` | Live Nifty 50 last/52wH/52wL | Regime detection |
| `nse_fiidii()` | FII/DII net activity DataFrame | Macro sentiment |

**Limitations:**
- `equity_history()` fails on macOS (NSE Akamai bot protection — browser cookies required)
- Historical data endpoints return 503 intermittently (NSE server-side rate limiting)
- All live functions work reliably without authentication

### 2.2 yfinance (historical data via Yahoo Finance)

| Data type | Tickers | Used for |
|---|---|---|
| Daily OHLCV (1y, 5y, 10y) | `SYMBOL.NS` (NSE), `SYMBOL.BO` (BSE), bare ticker (US) | Darvas, Golden Cross, all price-based analysis |
| Annual income statement | `.NS` suffix | Piotroski F-Score, Coffee Can, Magic Formula |
| Annual balance sheet | `.NS` suffix | Piotroski F-Score, Coffee Can, Magic Formula |
| Annual cash flow | `.NS` suffix | Piotroski F-Score, Coffee Can, Magic Formula |
| Quarterly income statement | `.NS` suffix | Bull Cartel |
| `ticker.info` | `.NS` suffix | Market cap, debt/equity, book value |
| `ticker.fast_info` | `.NS` suffix | Market cap (fast path) |

**Assumptions:**
- Free tier provides ~4 years of annual financial statements
- Financial data uses US-standard GAAP row names (`Net Income`, `Total Revenue` etc.)
- Row names vary between yfinance versions — defensive fallback names used throughout
- `debtToEquity` in `ticker.info` is sometimes in % format (45.2 = 0.452×) — normalised if > 10
- Rate limit: ~200 tickers per minute in bulk mode; 100-ticker batches for 5y+ data
- Data quality: Yahoo Finance occasionally returns stale, missing, or restated data

### 2.3 NSE library (`nse` package — `nse[local]`)

| Function | What it returns |
|---|---|
| `nse.equityBhavcopy(date)` | Path to CSV of all traded instruments that day |
| CSV column `SctySrs=="EQ"` | Filter for equity series only |
| CSV column `TckrSymb` | NSE ticker symbol |

**New format (2025+):** Returns a `pathlib.Path` to a downloaded CSV rather than a DataFrame directly.

### 2.4 screener.in (via markitdown)

Used as a **speed optimisation**, not a primary data source:
- Fetches pre-filtered stock lists from public screener.in screens
- `markitdown` converts HTML tables to markdown for fast parsing
- Reduces fundamental screener universe from 2,600 → 26–100 stocks
- **35–100× faster** than computing from scratch for all stocks

**Screener.in screens used:**
- `/screens/59/magic-formula/` — Magic Formula
- `/screens/336509/golden-crossover/` — Golden Crossover
- `/screens/1/the-bull-cartel/` — Bull Cartel

### 2.5 NASDAQ FTP (US symbols)

- `https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt` — NASDAQ listings
- `https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt` — NYSE/AMEX listings
- Pipe-delimited; filtered to remove ETFs, test issues, warrants (symbols > 5 chars or containing `^/$/.`)
- Optional: Nasdaq Cloud Data Service (NCDS) SDK with paid credentials for real-time feed

---

## 3. Screeners

### 3.1 Darvas Box Breakout

**Source:** Nicolas Darvas, *How I Made $2,000,000 in the Stock Market* (1960)

**Algorithm:**
1. Scan backwards through historical highs (bars 0..i-1, EXCLUDING current bar)
2. **Box Top**: first high H[j] where the next 3 consecutive bars all have lower highs
3. **Box Bottom**: lowest low from the box-top bar onwards that held for 3 consecutive bars
4. Signal fires when `close[i] > box_top AND close[i-1] <= box_top` (first cross)
5. Volume confirmation: `volume[i] >= 1.2 × avg_volume(20 days)`

**Key design invariant:** Current bar is ALWAYS excluded from box formation.  
Including it makes breakdown detection impossible (the bar that closes below the bottom would also pull the bottom down, hiding the signal).

**Parameters:**
- `DARVAS_CONFIRM = 3` — days a high/low must hold to be "confirmed"
- `COOLDOWN_BARS = 10` — minimum bars between signals for same stock
- Volume threshold: 120% of 20-day average

**Assumptions:**
- Works on any OHLCV time series; period="1y" used (needs ≥210 bars)
- Volume data available (some BSE stocks have missing volume)
- Breakout must be the FIRST close above box top (not a re-entry)

**Risk notes:**
- ~47–52% hit rate in isolation (coin flip on Nifty 50 large caps)
- Works best as a **confirmation filter** for fundamental screeners, not standalone
- Expected value ≈ 0% after 0.2% transaction cost in BULL markets
- Best performance: BEAR market breakouts (stocks breaking up against the trend), T+63d–T+252d

**Output columns:** `Darvas_Signal` (BREAKOUT_BUY / BREAKDOWN_SELL / IN_BOX / NO_BOX), `Box_Top`, `Box_Bottom`, `Upside_to_Top%`, `Position_in_Box%`

---

### 3.2 Golden Crossover

**Source:** Classic technical analysis (widely used since 1920s)

**Algorithm:**
- Compute 50-day and 200-day simple moving averages of closing prices
- **Signal fires** on the day `DMA50[t] > DMA200[t] AND DMA50[t-1] < DMA200[t-1]`
- i.e., the 50 DMA crosses above the 200 DMA for the first time since the last death cross

**Assumptions:**
- Requires ≥ 201 trading days of history (else `INSUFFICIENT_DATA`)
- Signal is the **exact crossover day** — not "currently above 200 DMA"
- A second column `dma50_above_200` flags stocks currently above 200 DMA regardless of when the cross happened

**Risk notes:**
- Lagging indicator — the cross fires after the trend has already turned
- High overfitting risk at T+252d (1 year) across all periods tested
- Most reliable for SIDEWAYS → BULL transitions (not BEAR → BULL reversals)
- Do NOT trade on Golden Cross alone in BEAR markets — signal quality degrades significantly
- T+3d expected value is often negative (market makers push back against the obvious signal)

**Output columns:** `GC_Signal` (GOLDEN_CROSS / ABOVE_200DMA / BELOW_200DMA), `DMA50`, `DMA200`, `DMA_Gap%`

---

### 3.3 Piotroski F-Score

**Source:** Joseph Piotroski, *Value Investing: The Use of Historical Financial Statement Information* (2000)  
**Data:** Annual financial statements (yfinance `income_stmt`, `balance_sheet`, `cash_flow`)

**9 binary criteria (1 = pass, 0 = fail):**

| Group | Criterion | Test |
|---|---|---|
| **Profitability** | F1: ROA positive | Net Income / Total Assets > 0 |
| | F2: OCF positive | Operating Cash Flow > 0 |
| | F3: ROA improving | ROA(year 0) > ROA(year 1) |
| | F4: Cash-backed earnings | OCF/Assets > ROA (accruals low) |
| **Leverage** | F5: Debt ratio falling | LTD/Assets(year 0) < LTD/Assets(year 1) |
| | F6: Liquidity improving | Current Ratio(year 0) > Current Ratio(year 1) |
| | F7: No dilution | Shares issued(year 0) ≤ Shares issued(year 1) |
| **Efficiency** | F8: Gross margin improving | GP/Revenue(year 0) > GP/Revenue(year 1) |
| | F9: Asset turnover improving | Revenue/Assets(year 0) > Revenue/Assets(year 1) |

**Qualification threshold:** Score ≥ 7 / 9

**Assumptions:**
- Annual data from yfinance — only ~4 years available free
- Row names (`Net Income`, `Total Assets` etc.) may vary between yfinance versions
- F7 defaults to 1 (pass) when share data unavailable (conservative assumption)
- Financial companies excluded (ROCE/leverage ratios not comparable)
- Signal date = July 1 (annual reports released by June-end in India)

**Risk notes:**
- Based on backward-looking accounting data (up to 12 months old at signal)
- 90.9% hit rate at T+21d in BEAR markets (from 1-year backtest), but N=11 (LOW N)
- Best combined with a valuation screen (Magic Formula / Earnings Yield)
- In 10-year backtest: robust signal at T+126d (6 months) with LOW overfitting risk

---

### 3.4 Coffee Can Portfolio

**Source:** Robert Kirby (1984); popularised for India by Saurabh Mukherjea, Marcellus Investment Managers  
**Data:** Annual financial statements + `ticker.info` for market cap and D/E

**5 criteria (ALL must pass):**

| Criterion | Test | Threshold |
|---|---|---|
| C1: Revenue CAGR | Compound growth over available years | > 10% |
| C2: ROCE (avg) | EBIT / (Total Assets − Current Liabilities) | > 15% |
| C3: Debt/Equity | From `info.debtToEquity` or computed | < 1 |
| C4: Market Cap | From `fast_info.market_cap` | ≥ ₹500 Cr (India) / $1B (US) |
| C5: No loss year | All available years: Net Income > 0 | Consistently profitable |

**US variant adds C6:** Free Cash Flow > 0 (Operating CF − CapEx)

**Assumptions:**
- CAGR computed over all available years from yfinance (typically 3–4 years)
- For a true 10-year Coffee Can screen, a premium data source (Capitaline, Bloomberg) is needed
- `debtToEquity` in yfinance is sometimes expressed as percentage — normalised: `de = de_raw/100 if de_raw > 10`
- ROCE uses current liabilities as the working capital proxy (simplified from Mukherjea's original)
- Signal date = July 1 (annual results available)

**Risk notes:**
- These stocks almost always trade at premium valuations (P/E 40–80×)
- Entry timing matters enormously — buying at peak valuation dramatically reduces returns
- Designed for 10-year holding periods — 1-month backtest results are meaningless for this screener
- 100% hit rate at T+21d in BEAR markets (N=6, LOW N — directional but not statistically robust)

---

### 3.5 Magic Formula

**Source:** Joel Greenblatt, *The Little Book That Beats the Market* (2005)  
**Data:** Annual financial statements + `ticker.info` for market cap, debt, cash

**2 criteria (both must pass) + 2 exclusion rules:**

| Metric | Calculation | Threshold |
|---|---|---|
| ROIC (Return on Invested Capital) | EBIT / (Total Assets − Current Liabilities) × 100 | > 15% (relaxed from screener.in's 25%) |
| Earnings Yield | EBIT / Enterprise Value × 100 | > 8% (relaxed from 15%) |
| Exclusion: negative earnings | Net Income > 0 | Mandatory |
| Exclusion: financial companies | Banks, NBFCs excluded | Mandatory |

**Enterprise Value** = Market Cap + Total Debt − Cash  
**Capital Employed** = Total Assets − Current Liabilities

**Note on thresholds:** Greenblatt's original method uses **combined ranking** (ROIC rank + EY rank, lowest combined score = top pick). The binary threshold version is screener.in's simplification. Our thresholds (15%/8%) are relaxed to approximate the top-30 ranking behavior on a large universe. For the academic study (Preet et al. 2021), portfolios of 30 stocks rebalanced annually on July 1 using BSE 500 companies achieved CAGR 13.89% vs Sensex 9.31% over 8 years.

**Assumptions:**
- EV computation uses book-value total debt from balance sheet (not market-value debt)
- For financial companies, EV/EBIT is meaningless — these are excluded
- Signal date = July 1 (annual report published; forward-looking bias eliminated)
- Relaxed thresholds used in backtest to generate sufficient signals for statistical analysis

**Risk notes:**
- Magic Formula stocks are often cheap for a reason (cyclical downturn, management issues)
- Greenblatt recommends holding a diversified basket of 20–30 stocks for ≥12 months
- Short-term performance (T+1d to T+5d) is near zero — this is a long-term strategy
- Validated on Indian markets by Preet et al. (2021): BSE 500 backtest 2012–2020

---

### 3.6 Bull Cartel

**Source:** screener.in community screen  
**Data:** Quarterly financial statements (yfinance `quarterly_income_stmt`)

**3 criteria (all must pass):**

| Criterion | Test | Threshold |
|---|---|---|
| Sales Growth YoY | (Revenue Q0 − Revenue Q4) / |Revenue Q4| × 100 | > 15% |
| Profit Growth YoY | (Net Income Q0 − Net Income Q4) / |Net Income Q4| × 100 | > 20% |
| Net Profit | Latest quarter Net Income / 1e7 | > ₹1 Cr |

Where Q0 = most recent quarter, Q4 = same quarter 1 year ago (col index 4 in quarterly stmt)

**Assumptions:**
- Requires ≥ 5 quarters of data in yfinance quarterly statements
- YoY comparison avoids seasonality (Q0 vs Q4, not Q0 vs Q1)
- Net profit > ₹1 Cr filter removes shell companies and negligible-earnings micro-caps
- Signal date = quarterly result announcement date (from `quarterly_income_stmt.columns[0]`)

**Risk notes:**
- Earnings momentum is highly mean-reverting — verify it's not a base effect
- Stocks near cyclical peaks often appear in this screen
- Check sector tailwinds and order book before acting
- 92.9% hit rate, avg +11.33% at T+21d in BEAR markets (N=14 from 1-year backtest)

---

## 4. Market Regime Classification

Used throughout all scripts to condition screener recommendations.

```
Nifty 50 close price vs 200-day moving average:

  BULL     : price > 200 DMA   AND  200 DMA 5-bar slope > 0  (uptrend confirmed)
  BEAR     : price < 200 DMA   AND  200 DMA 5-bar slope < 0  (downtrend confirmed)
  SIDEWAYS : price within 1.5% of 200 DMA  OR  DMA slope near zero

Enhanced (nse_data_fetcher.py):
  BULL_VOLATILE  : Nifty > 200 DMA but India VIX ≥ 18
  BEAR_EXTREME   : Nifty < 200 DMA AND VIX > 25 (panic zone)
```

**India VIX interpretation:**
| VIX | Regime | Action |
|---|---|---|
| < 12 | COMPLACENCY | Consider taking partial profits |
| 12–15 | NORMAL | Trend-following works well |
| 15–18 | ELEVATED | Reduce position size 25% |
| 18–22 | HIGH_FEAR | Reduce 50%, widen stop-losses |
| 22–25 | EXTREME | Minimal new positions |
| > 25 | PANIC | Stop new positions, protect capital |

---

## 5. Transaction Cost Model

All return calculations in all scripts deduct **0.2% round-trip** cost:
- 0.1% STT (Securities Transaction Tax) on equity delivery
- ~0.1% brokerage + exchange charges + GST (estimated for discount broker)
- Slippage NOT modelled separately (assumed captured in 0.2%)

**Impact:** At 50% hit rate, this 0.2% cost eliminates any edge. Screeners need >55% hit rate to survive after costs.

---

## 6. Filing Trend Score (walk_forward_backtest.py)

Quantifies whether a stock's improvement in regulatory filings is structural or a one-off.

**5 components (each capped at 3 points, max total = 15):**

| Component | Measurement | Points |
|---|---|---|
| Revenue streak | Consecutive quarters YoY revenue growth > 10% | 0–3 |
| Profit streak | Consecutive quarters YoY net income growth > 15% | 0–3 |
| OCF streak | Consecutive quarters positive operating cash flow | 0–3 |
| Debt streak | Consecutive quarters of falling long-term debt | 0–3 |
| Piotroski trend | Current annual F-score vs prior year | 0–3 |

**Classification:**
- **STRONG** (score ≥ 9): Persistent structural improvement — hold through T+252d
- **EMERGING** (score 4–8): Recent turnaround — exit at T+63d, verify next quarter
- **WEAK** (score ≤ 3): One-off beat — exit at T+21d

**Data limitation:** yfinance provides only ~4 years of free quarterly data. For 8+ consecutive quarters (STRONG classification), a premium data provider (Capitaline, Bloomberg) is recommended.

---

## 7. Train/Test/Validation Framework

Implemented in `walk_forward_backtest.py` to prevent backtest overfitting.

### Split boundaries

| Period | Start | TRAIN ends | TEST ends | VAL ends |
|---|---|---|---|---|
| 3-year | Jan 2023 | Jan 2025 | Jul 2025 | Jun 2026 |
| 5-year | Jan 2021 | Jan 2024 | Jan 2025 | Jun 2026 |
| 10-year | Jan 2016 | Jan 2022 | Jan 2024 | Jun 2026 |

### Overfitting check (Bailey et al. 2014)

Sharpe ratio decay = `(Sharpe_TRAIN − Sharpe_VAL) / Sharpe_TRAIN × 100`

- **LOW** (< 20%): Signal is robust — confident it will generalise
- **MEDIUM** (20–50%): Moderate risk — use with additional confirmation
- **HIGH** (> 50%): Likely curve-fitted — use only with very strong fundamental support

### Key findings from 28-stock test (Nifty 500 liquid)

| Screener | Best horizon | Best regime | VAL EV% | Overfitting |
|---|---|---|---|---|
| Darvas Box | T+126d (6mo) | ALL | +13.05% | LOW |
| Golden Cross | T+252d (1yr) | BULL/SIDEWAYS | +30–68% | HIGH at 1yr |
| Coffee Can | T+21d (1mo) | BULL | +8.25% | LOW N |
| Piotroski | T+126d (6mo) | BULL | +9.74% | LOW N |

---

## 8. Return Horizons

| Label | Trading Days | Calendar Approx |
|---|---|---|
| T+1d | 1 | Next day |
| T+3d | 3 | 3 trading days |
| T+5d | 5 | 1 trading week |
| T+10d | 10 | 2 trading weeks |
| T+21d | 21 | 1 calendar month |
| T+63d | 63 | 1 calendar quarter |
| T+126d | 126 | 1 half-year |
| T+252d | 252 | 1 trading year |

---

## 9. Script Reference

| Script | Purpose | Key output | Run time |
|---|---|---|---|
| `nse_data_fetcher.py` | Live market data layer | Live context dict / dashboard print | < 5s |
| `screener_analysis.py` | Fast screener.in-augmented scan | `screener_results/screener_analysis_DATE.xlsx` | ~15 min |
| `full_indian_market_scan.py` | Full NSE+BSE 6-screener scan | `indian_full_scan/indian_full_scan_DATE.xlsx` | ~3–4 hrs |
| `full_us_market_scan.py` | Full NASDAQ+NYSE 6-screener scan | `us_full_scan/us_full_scan_DATE.xlsx` | ~6–8 hrs |
| `backtest_screeners.py` | 1-year backtest on full NSE | `backtest_results/backtest_IN_DATE.xlsx` | ~3 hrs |
| `walk_forward_backtest.py` | 3y/5y/10y train/test/val research | `wf_backtest/walk_forward_DATE.xlsx` | ~2–3 hrs |

### Daily scheduled run (8:30 AM weekdays)

Cron task: `morning-stock-analysis-report`  
Sequence: screener_analysis.py → full_indian_market_scan.py → full_us_market_scan.py  
Output: HTML email to umashankartd1991@gmail.com  
Contains: Live regime, VIX, FII/DII, strategy matrix, all screener results, risk/reward cards, disclaimer

---

## 10. Assumptions Summary

### Data assumptions
1. **yfinance financial data** uses current (latest) statements as a proxy for historical ones — introduces mild look-ahead bias for backtesting (unavoidable with free data)
2. **NSE symbols** from nsepython represent the current tradeable universe — survivorship bias: delisted stocks are NOT in the universe and their historical data is unavailable
3. **Bulk OHLC download** via yfinance `.NS` suffix — some stocks have data gaps or return stale prices; these are dropped silently
4. **Financial year** for Indian companies ends March 31; annual reports released by June; July 1 used as signal date (Preet et al. 2021 methodology)
5. **D/E normalisation**: `debtToEquity > 10` is treated as being in percentage format and divided by 100

### Screener assumptions
6. **Financial companies excluded** from ROIC/ROCE screeners — high leverage is normal for banks/NBFCs and would generate false positives
7. **Negative earnings companies excluded** from Magic Formula — PE ratio is undefined for loss-making companies
8. **Coffee Can** assumes the most recent 3–4 years of yfinance data are representative of 10-year track record — conservative undercount of qualifying stocks
9. **Darvas confirmation = 3 days** — standard from Darvas' original methodology; can be tightened to 2 for volatile stocks
10. **Transaction cost = 0.2%** round-trip — assumes discount broker (Zerodha/Groww), no STT exemptions, excludes SEBI fees and GST for simplicity

### Backtest assumptions
11. **Entry price** = closing price on signal day — assumes you can execute at or near close; early-session execution may differ
12. **Exit price** = closing price at T+N — no consideration for bid-ask spread at exit
13. **No position sizing** — equal weight assumed for all signals (1 rupee per signal)
14. **No compounding** — each signal is treated independently
15. **No market impact** — assumes signals can be executed at reported price regardless of order size

---

## 11. Known Limitations

1. **Survivorship bias**: Only currently-listed stocks are in the universe. Delisted stocks (often the worst performers) are excluded, making strategies look better than reality.

2. **Look-ahead bias in fundamentals**: Current financial statements are used as proxy for historical ones. A company that was poor in 2020 but improved by 2024 would have been flagged as "passing Piotroski" retroactively for 2020 signals.

3. **NSE API instability**: NSE frequently changes its API endpoints and adds bot protection. nsepython functions may stop working without notice. Always verify output before acting.

4. **yfinance data quality**: Yahoo Finance data is crowd-sourced and has known issues with corporate actions (incorrect split adjustments, dividend reinvestment errors). Use NSE direct data for production.

5. **Low N for fundamental screeners**: Most fundamental screeners have < 20 signals per regime/period combination in the backtest. Results are directionally correct but not statistically significant at 95% confidence.

6. **Single market test**: Backtests run on Indian markets only (NSE/BSE). US market logic is implemented but not fully backtested due to yfinance rate limits.

7. **Filing trend scoring**: Requires quarterly data for 8+ consecutive quarters. yfinance provides only ~4 years, making STRONG classifications rare. Premium data needed for meaningful trend analysis.

---

## 12. Dependencies

```bash
# Core
pip install yfinance pandas openpyxl numpy scipy

# NSE data
pip install nsepython "nse[local]" bse

# US data
pip install requests
# Optional: pip install "git+https://github.com/Nasdaq/NasdaqCloudDataService-SDK-Python.git"

# Performance
pip install markitdown  # For screener.in pre-filtering
```

### Version notes
- Python ≥ 3.9 (type hints use string annotations for 3.9 compatibility)
- yfinance ≥ 0.2.0 (uses `income_stmt` not `financials`)
- nsepython ≥ 0.9 (uses `nse_eq_symbols` API)
- pandas ≥ 2.0 (MultiIndex column handling in yfinance bulk download)

---

## 13. Output File Guide

### Excel sheets (all scan outputs)

| Sheet | Content | Sort order |
|---|---|---|
| `All_Stocks` | All scanned stocks: price + Darvas + GC columns | Change% descending |
| `Darvas_Signals` | Breakout and breakdown alerts | Upside_to_Top% descending |
| `Golden_Crossover` | Stocks where 50 DMA just crossed above 200 DMA | DMA_Gap% descending |
| `All_Fundamentals` | Complete 4-screener results for every scanned stock | Piotroski_Score descending |
| `Piotroski_Strong` | Stocks with F-Score ≥ 7 | Score descending |
| `Coffee_Can` | Stocks passing all 5 Coffee Can criteria | Revenue_CAGR% descending |
| `Magic_Formula` | Stocks with ROIC > 15% and EY > 8% | ROIC% descending |
| `Bull_Cartel` | Stocks with YoY quarterly growth > 15%/20% | Profit_Growth% descending |
| `Triple_Hits` | Darvas BREAKOUT + Piotroski ≥7 + Coffee Can PASS | Piotroski_Score |
| `Multi_Screen_Hits` | Any 3+ of 6 screeners simultaneously | Screens_Passed descending |

### Walk-forward backtest output (wf_backtest/)

| Sheet | Content |
|---|---|
| `Strategy_Matrix` | Best screener per (Period × Regime × Horizon) — VAL set only |
| `Overfitting_Check` | Sharpe decay TRAIN→VAL for each strategy |
| `HitRate_Heatmap_VAL` | Hit rate % grid: Screener × Horizon (VAL set) |
| `EV_Heatmap_VAL` | Expected value % grid: Screener × Horizon (VAL set) |
| `Filing_Trends` | Filing trend score per stock |
| `All_Signals` | Every signal with 8-horizon returns + alpha vs Nifty |

---

## 14. Research References

1. Greenblatt, J. (2005). *The Little Book That Beats the Market*. Wiley.
2. Piotroski, J. (2000). Value Investing: The Use of Historical Financial Statement Information. *Journal of Accounting Research*, 38(S1), 1–41.
3. Darvas, N. (1960). *How I Made $2,000,000 in the Stock Market*. Lyle Stuart.
4. Mukherjea, S. (2018). *Coffee Can Investing*. Penguin Random House.
5. Bailey, D., Borwein, J., López de Prado, M., & Zhu, Q. (2014). Pseudo-mathematics and financial charlatanism: The effects of backtest overfitting. *Notices of the AMS*.
6. Preet, S., Gulati, A., Gupta, A., & Aggarwal, A. (2021). Back Testing Magic Formula on Indian Stock Markets. *Paideuma Journal*, XIV(10).
7. Bhute, A. et al. (2024). Backtesting Brilliance: Leveraging Analytics for Comparing Buy & Hold vs. Trading Strategies. *JIER*, 4(3).
8. Liu, B. & Zhu, H. (2024). Analysis of Market Efficiency in Main Stock Markets Using Karman-Filter. *arXiv:2404.16449*.
9. Dhanus, S. & Amutha, G. (2025). Back-Testing Super Trend in 15 Mins Time Frame among Top 5 Contributors of Nifty 50 Stocks. *IJARCMSS*, 8(2).

---

*⚠️ For educational and research purposes only. NOT investment advice.*

## Screener & RSI Basis

See [SCREENER_BASIS.md](SCREENER_BASIS.md) for the exact formulas, thresholds, and financial rationale behind RSI and all six screeners.
