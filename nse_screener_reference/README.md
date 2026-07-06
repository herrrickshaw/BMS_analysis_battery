# NSE Screener Reference Data

Reference dataset for the NSE stock analysis and backtesting system.  
Generated: **26 Jun 2026** | System: `~/Downloads/*.py`

> ⚠️ **DISCLAIMER**: All data is for **educational and research purposes only**.  
> It does NOT constitute financial advice. Past results do NOT guarantee future returns.  
> Consult a SEBI-registered advisor before making investment decisions.

---

## Directory Structure

```
nse_screener_reference/
├── README.md                              ← this file
│
├── ohlc_cache/                            ← Parquet OHLC cache (5-year daily)
│   ├── RELIANCE.NS.parquet
│   ├── TCS.NS.parquet
│   └── ... (15 Nifty 50 liquid stocks)
│
├── scan_results/
│   ├── indian_full_scan_latest.xlsx       ← Full NSE+BSE 6-screener scan
│   ├── backtest_1yr_full_NSE_latest.xlsx  ← 1-year walk-forward backtest (2,406 stocks)
│   └── walkforward_3y5y10y_latest.xlsx    ← Train/Test/Val framework (3y/5y/10y)
│
└── cache_meta/
    └── cache_index.json                   ← Cache manifest (ticker → rows/dates/updated)
```

---

## 1. OHLC Cache (`ohlc_cache/`)

### Format: Apache Parquet (snappy compression)
- **Library**: `pd.read_parquet("RELIANCE.NS.parquet")`
- **Columns**: `Open`, `High`, `Low`, `Close`, `Volume`
- **Index**: `DatetimeIndex` (daily trading days, UTC-naive)
- **Period**: ~5 years (Jun 2021 – Jun 2026, ~1,258 trading bars)
- **Source**: Yahoo Finance via yfinance (`.NS` suffix = NSE listing)

### Stocks included (15 Nifty 50 constituents)

| Symbol | Name | Sector |
|---|---|---|
| RELIANCE.NS | Reliance Industries | Energy / Conglomerate |
| TCS.NS | Tata Consultancy Services | IT Services |
| HDFCBANK.NS | HDFC Bank | Banking |
| ICICIBANK.NS | ICICI Bank | Banking |
| INFY.NS | Infosys | IT Services |
| AXISBANK.NS | Axis Bank | Banking |
| KOTAKBANK.NS | Kotak Mahindra Bank | Banking |
| WIPRO.NS | Wipro | IT Services |
| LT.NS | Larsen & Toubro | Infrastructure / Engineering |
| BAJFINANCE.NS | Bajaj Finance | NBFC |
| MARUTI.NS | Maruti Suzuki | Automobiles |
| BHARTIARTL.NS | Bharti Airtel | Telecom |
| SUNPHARMA.NS | Sun Pharmaceutical | Pharma |
| NESTLEIND.NS | Nestle India | FMCG |
| TITAN.NS | Titan Company | Consumer |

### Load example
```python
import pandas as pd

df = pd.read_parquet("ohlc_cache/RELIANCE.NS.parquet")
print(df.tail())
#             Open     High      Low    Close    Volume
# 2026-06-23  1305.0  1330.5  1290.8  1318.1  8521600
# 2026-06-24  1320.0  1325.0  1290.0  1295.3  7234400
# 2026-06-25  1310.0  1335.0  1305.0  1318.1  6012300
```

### Data quality
- **Missing values**: Forward-filled then backward-filled (AlQahtani et al. 2025)
- **Duplicates**: Removed (keep last)
- **Outliers**: Not removed (kept as-is — outliers may be real events like circuit breaks)

### Regenerate / update
```bash
cd ~/Downloads
python3 - << 'EOF'
from market_data_cache import warm_cache
from nse_data_fetcher import get_nse_symbols
symbols = [f"{s}.NS" for s in get_nse_symbols()]
warm_cache(symbols)  # ~12 min cold; <60s incremental
EOF
```

---

## 2. Full NSE+BSE Scan (`scan_results/indian_full_scan_latest.xlsx`)

**Universe**: 2,406 NSE EQ stocks  
**Run date**: 26 Jun 2026, 09:43  
**Source script**: `~/Downloads/full_indian_market_scan.py`

### Excel sheets

| Sheet | Content | Rows |
|---|---|---|
| `All_Stocks` | All 2,406 stocks: price + Darvas signal + GC DMA data | 2,406 |
| `Darvas_Signals` | Breakout (BUY) and breakdown (SELL) alerts | ~500 |
| `All_Fundamentals` | Piotroski + Coffee Can + Magic Formula + Bull Cartel per stock | ~1,800 |
| `Piotroski_Strong` | Stocks with F-Score ≥ 7/9 | ~82 |
| `Coffee_Can` | Quality compounders (5/5 criteria) | ~24 |
| `Magic_Formula` | ROIC>15%, Earnings Yield>8% | ~7 |
| `Bull_Cartel` | YoY quarterly sales+profit growth leaders | ~66 |
| `Golden_Crossover` | 50 DMA crossed above 200 DMA (today) | ~650 |
| `Triple_Hits` | Darvas BREAKOUT + Piotroski≥7 + Coffee Can PASS | **8** |
| `Multi_Screen_Hits` | Any 3+ of 6 screeners simultaneously | varies |

### Column dictionary (All_Stocks sheet)

| Column | Type | Description |
|---|---|---|
| `Symbol` | str | NSE ticker |
| `Suffix` | str | `.NS` or `.BO` |
| `LTP` | float | Last traded price (₹) |
| `Change%` | float | Day change % |
| `Darvas_Signal` | str | `BREAKOUT_BUY` / `BREAKDOWN_SELL` / `IN_BOX` / `NO_BOX` |
| `Box_Top` | float | Darvas box ceiling (₹) — resistance level |
| `Box_Bottom` | float | Darvas box floor (₹) — natural stop-loss |
| `Upside_to_Top%` | float | % gap from LTP to box top (negative = already broken out) |
| `Position_in_Box%` | float | Where price sits within box (0%=bottom, 100%=top) |
| `GC_Signal` | str | `GOLDEN_CROSS` / `ABOVE_200DMA` / `BELOW_200DMA` |
| `DMA50` | float | 50-day moving average |
| `DMA200` | float | 200-day moving average |
| `DMA_Gap%` | float | % gap between DMA50 and DMA200 |
| `Piotroski_Score` | int | F-Score 0–9 (≥7 = financially strengthening) |
| `Piotroski_Strong` | str | `YES` if F-Score ≥ 7 |
| `CoffeeCan` | str | `PASS` / `FAIL` |
| `CC_Score` | str | e.g. `4/5` |
| `Revenue_CAGR_%` | float | Compound revenue growth rate (available history) |
| `ROCE_avg_%` | float | Average ROCE over available years |
| `MagicFormula` | str | `PASS` / `FAIL` |
| `ROIC_%` | float | Return on Invested Capital |
| `Earnings_Yield_%` | float | EBIT / Enterprise Value × 100 |
| `BullCartel` | str | `PASS` / `FAIL` |
| `Sales_Growth_YoY_%` | float | YoY quarterly sales growth |
| `Profit_Growth_YoY_%` | float | YoY quarterly profit growth |
| `Net_Profit_Cr` | float | Latest quarter net profit (₹ crore) |

---

## 3. Backtest Results (`scan_results/backtest_1yr_full_NSE_latest.xlsx`)

**Universe**: 2,406 NSE EQ stocks  
**Lookback**: 1 year (Jun 2025 – Jun 2026)  
**Source script**: `~/Downloads/backtest_screeners.py`  
**Methodology**: Walk-forward, zero lookahead for technical screeners

### Excel sheets

| Sheet | Content |
|---|---|
| `DISCLAIMER` | Full methodology notes and limitations |
| `HitRate_Heatmap` | Hit rate % grid: Screener × Horizon (BULL/BEAR/SIDEWAYS) |
| `AvgReturn_Heatmap` | Avg return % grid: Screener × Horizon |
| `Screener_Ranking` | Composite score (Avg Hit Rate × Sharpe 1mo) per screener per regime |
| `Full_Stats` | Complete statistics: N, Hit%, Avg%, Median%, Sharpe, Sortino, Profit Factor, Max DD |
| `darvas` | Per-signal stats for Darvas screener |
| `golden_cross` | Per-signal stats for Golden Cross |
| `piotroski` | Per-signal stats for Piotroski |
| `coffee_can` | Per-signal stats for Coffee Can |
| `bull_cartel` | Per-signal stats for Bull Cartel |
| `All_Signals` | Every signal with 5 forward returns + alpha vs Nifty 50 |

### Key results (1-year backtest, full NSE 2,406 stocks)

| Screener | Regime | N Signals | Hit Rate | Avg T+21d | EV T+21d |
|---|---|---|---|---|---|
| **Bull Cartel** | BEAR | 66 | **80.5%** | +8.38% | **+21.34%** |
| **Piotroski ≥7** | BEAR | 82 | **79.1%** | +6.71% | **+15.59%** |
| Darvas | BEAR | 2,847 | 52.9% | +3.75% | +4.22% |
| Darvas | BULL | 11,789 | 38.2% | -1.51% | -2.32% |
| Golden Cross | BULL | 650 | 32.3% | -2.87% | -9.28% |

> **Current regime (26 Jun 2026): BEAR** (Nifty 24,056 — 3.33% below 200 DMA 24,885)  
> Optimal screener in BEAR: Bull Cartel + Piotroski for T+21d to T+63d entries

### Column dictionary (All_Signals sheet)

| Column | Description |
|---|---|
| `screener` | Which screener fired the signal |
| `symbol` | NSE ticker |
| `signal_date` | Date signal fired |
| `entry_price` | Close price on signal date (₹) |
| `regime` | BULL / BEAR / SIDEWAYS (Nifty 50 vs 200 DMA at signal date) |
| `T+1d` … `T+3mo` | Net return % after transaction cost (0.2% round-trip) |
| `bh_T+1d` … `bh_T+3mo` | Nifty 50 buy-and-hold return over same period |
| `filing_class` | STRONG / EMERGING / WEAK (consecutive-quarter filing trend) |

---

## 4. Walk-Forward Results (`scan_results/walkforward_3y5y10y_latest.xlsx`)

**Universe**: 28 liquid Nifty 500 stocks (rate-limited subset)  
**Periods**: 3y (2023–2026), 5y (2021–2026), 10y (2016–2026)  
**Split**: 60% TRAIN / 20% TEST / 20% VAL (chronological, no leakage)  
**Horizons**: T+1d, T+3d, T+5d, T+10d, T+21d, T+63d, T+126d, T+252d  
**Source script**: `~/Downloads/walk_forward_backtest.py`

### Excel sheets

| Sheet | Content |
|---|---|
| `Strategy_Matrix` | Best screener per (Period × Regime × Horizon) — VAL set only |
| `Overfitting_Check` | Sharpe ratio decay TRAIN→VAL (HIGH/MEDIUM/LOW risk) |
| `HitRate_Heatmap_VAL` | Hit rate % grid on VAL set |
| `EV_Heatmap_VAL` | Expected value % grid on VAL set |
| `Filing_Trends` | Filing trend score per stock |
| `All_Signals` | Every signal with 8-horizon returns + alpha vs Nifty |

### Strategy matrix summary (VAL set, 10-year window)

| Regime | Short (T+5d) | Medium (T+63d) | Long (T+252d) |
|---|---|---|---|
| **BULL** | Darvas EV +0.9% | Darvas EV +7.4% | Golden Cross EV **+33.5%** |
| **BEAR** | Golden Cross EV +3.4% | Darvas EV **+17.6%** | Darvas EV **+72.3%** |
| **SIDEWAYS** | Golden Cross EV +0.7% | Golden Cross EV +6.9% | Golden Cross EV **+67.6%** |

### Overfitting risk (from Bailey et al. 2014 test)
- **Darvas at T+126d (6mo)**: LOW overfitting risk — signal is robust
- **Golden Cross at T+252d**: HIGH overfitting risk in 5-year period — use with caution
- Rule: Sharpe decay > 50% from TRAIN→VAL = HIGH overfitting risk

---

## 5. Cache Index (`cache_meta/cache_index.json`)

JSON file tracking all cached tickers:
```json
{
  "ohlc:RELIANCE.NS": {
    "rows": 1258,
    "from": "2021-06-28",
    "to":   "2026-06-25",
    "updated": "2026-06-26T13:xx:xx",
    "file": "...market_cache/ohlc/RELIANCE.NS.parquet"
  },
  ...
}
```

---

## 6. How to Use This Data

### Load OHLC + run ML signal (paper methodology)
```python
import pandas as pd
from ml_signal_engine import MLSignalEngine, compare_models

# Load any Nifty 50 stock
df = pd.read_parquet("ohlc_cache/RELIANCE.NS.parquet")

# Compare LR vs Ridge vs naive (replicates AlQahtani et al. 2025 Tables III-IV)
compare_models(df, symbol="RELIANCE")

# Generate directional signal
engine = MLSignalEngine(model_type="ridge")
signal = engine.predict("RELIANCE.NS", df)
print(signal)
# {'symbol': 'RELIANCE.NS', 'direction': 'BULLISH', 'predicted_ret%': 0.043,
#  'confidence': 0.008, 'model': 'ridge', 'train_rmse': 0.0391}
```

### Load scan results and filter
```python
import pandas as pd

f = "scan_results/indian_full_scan_latest.xlsx"

# Triple hits
triple = pd.read_excel(f, sheet_name="Triple_Hits")
print(triple[["Symbol","Piotroski_Score","CC_Score","Upside_to_Top%"]])

# All stocks with Darvas breakout + Piotroski strong
all_stocks = pd.read_excel(f, sheet_name="All_Stocks")
candidates = all_stocks[
    (all_stocks["Darvas_Signal"] == "BREAKOUT_BUY") &
    (all_stocks["Piotroski_Strong"] == "YES")
]

# Backtest results — what happened to Bull Cartel stocks in BEAR regime?
signals = pd.read_excel(
    "scan_results/backtest_1yr_full_NSE_latest.xlsx",
    sheet_name="All_Signals"
)
bc_bear = signals[(signals["screener"]=="bull_cartel") & (signals["regime"]=="BEAR")]
print(f"Bull Cartel BEAR: {(bc_bear['T+21d']>0).mean()*100:.0f}% hit rate, "
      f"avg {bc_bear['T+21d'].mean():+.1f}% at 1mo")
```

### Run backtest on this reference OHLC
```python
from backtest_screeners import run_screener_backtest, download_index
from nse_data_fetcher import NSEDataFetcher

# Load cached stocks
import pandas as pd
from pathlib import Path
ohlc = {
    p.stem: pd.read_parquet(p)
    for p in Path("ohlc_cache").glob("*.parquet")
}
sym_data = [(sym.replace(".NS",""), ".NS", df) for sym, df in ohlc.items()]

# Get Nifty index and run Darvas backtest
index_df = NSEDataFetcher().get_regime()  # simplified; use cache.get_index() for full
signals  = run_screener_backtest("darvas", sym_data, index_df, technical=True)
```

---

## Research Papers Referenced

| # | Paper | Key finding applied |
|---|---|---|
| 1 | Greenblatt (2005) — Magic Formula | ROIC + Earnings Yield ranking |
| 2 | Piotroski (2000) — F-Score | 9-point accounting quality |
| 3 | Darvas (1960) — Box method | Price breakout + volume confirmation |
| 4 | Mukherjea (2018) — Coffee Can | ROCE, CAGR, D/E quality filter |
| 5 | Bailey et al. (2014) — Overfitting | Sharpe decay TRAIN→VAL test |
| 6 | Preet et al. (2021) — Magic Formula India | July 1 signal date; BSE 500 CAGR 13.89% |
| 7 | Bhute et al. (2024) — Backtesting Brilliance | Transaction costs; Sortino; benchmark |
| 8 | Liu & Zhu (2024) — Kalman Filter | Indian market inefficiency; emerging market alpha |
| 9 | Dhanus & Amutha (2025) — Super Trend | Win rates 43-56%; volume confirmation |
| **10** | **AlQahtani et al. (2025) — ML/DL Models** | **LR > LSTM > RNN; Z-score; 60d window; rolling retraining; 5y data** |

---

*Data generated by the stock analysis system in `~/Downloads/`.  
For methodology details see [STOCK_ANALYSIS_SYSTEM.md](../STOCK_ANALYSIS_SYSTEM.md).*
