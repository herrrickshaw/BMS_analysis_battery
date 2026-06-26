# Mathematical & Financial Basis of RSI Filters and Stock Screeners

The exact formulas, thresholds, and rationale behind every filter and screener
in this repository. This is the "why" behind the rules implemented in
`backtest_screeners.py`, `full_*_market_scan.py`, `ml_signal_engine.py`,
`intraday_monitor.py`, and `r_analysis.py`.

> ⚠️ Educational/research only. These are mechanical rules with known
> false-positive rates — NOT buy/sell signals, NOT investment advice.

---

## Part A — RSI (Relative Strength Index)

### A.1 Definition

RSI is a bounded momentum oscillator (0–100) introduced by J. Welles Wilder
(1978). It measures the **speed and magnitude** of recent price changes to judge
whether a stock is overbought or oversold.

**Formula** (period `n`, default 14):

```
        100
RSI = 100 − ─────────
            1 + RS

       average gain over last n periods
RS = ─────────────────────────────────────
       average loss over last n periods
```

Step by step (as implemented in `ml_signal_engine.py` / `r_analysis.py`):

1. `delta_t = close_t − close_{t−1}`
2. `gain_t  = max(delta_t, 0)`  ;  `loss_t = max(−delta_t, 0)`
3. `avg_gain = rolling_mean(gain, 14)`  ;  `avg_loss = rolling_mean(loss, 14)`
4. `RS = avg_gain / avg_loss`
5. `RSI = 100 − 100 / (1 + RS)`

Code (`ml_signal_engine.py`):
```python
delta = close.diff()
gain  = delta.clip(lower=0).rolling(14).mean()
loss  = (-delta.clip(upper=0)).rolling(14).mean()
rsi   = 100 - 100/(1 + gain/loss)
```

### A.2 Interpretation thresholds

| RSI range | State | Basis |
|---|---|---|
| **> 70** | Overbought | Gains have dominated; price may be extended → pullback risk |
| 50–70 | Bullish momentum | More up-moves than down; healthy uptrend |
| 30–50 | Bearish momentum | More down-moves than up |
| **< 30** | Oversold | Losses have dominated; mean-reversion bounce possible |

These are Wilder's original bands. Why 14 periods: long enough to smooth daily
noise, short enough to stay responsive — Wilder's empirically chosen default,
still the industry standard.

### A.3 How RSI is used here

- **ML feature** (`ml_signal_engine.py`): `rsi_14` is one of 12 inputs to the
  Ridge directional model — momentum state as a predictor.
- **Pattern feature** (`pattern_discovery.py`): part of the 24-feature
  fingerprint that KMeans clusters stocks by behaviour.
- **Archetype naming**: RSI > 65 + positive momentum → "Overbought Momentum"
  cluster label.
- **Technical indicator export** (`r_analysis.py` via R's TTR `RSI()`): for
  cross-validation against the Python implementation.

### A.4 RSI divergence (concept, used in interpretation)

- **Bearish divergence**: price makes a higher high but RSI makes a lower high
  → weakening momentum, reversal warning.
- **Bullish divergence**: price makes a lower low but RSI makes a higher low
  → selling exhausting, bounce likely.

### A.5 Known limitations

- In strong trends RSI can stay >70 (or <30) for long stretches — overbought is
  NOT an automatic sell. Best combined with trend context (200 DMA) and volume.
- It is a *price-only* oscillator: blind to fundamentals or news.

---

## Part B — The Six Stock Screeners

Each screener encodes a distinct, research-backed thesis. They split into
**technical** (price/volume) and **fundamental** (financial statements).

### B.1 Darvas Box Breakout  — *technical, momentum*

**Thesis (Nicolas Darvas, 1960):** stocks consolidate in price "boxes"; a
breakout above the box ceiling on rising volume signals the start of a new leg up.

**Construction:**
- **Box top**: a local high `H[j]` that is NOT exceeded for the next `confirm`
  (=3) consecutive bars.
- **Box bottom**: the lowest low after the box top that holds for 3 bars.
- **Breakout (BUY)**: `close_t > box_top` AND `close_{t−1} ≤ box_top` (first close
  above), with **volume confirmation**: `volume_t ≥ 1.2 × avg_volume(20)`.

**Critical invariant:** the *current* bar is excluded from box formation —
otherwise the bar that breaks down would also lower the box, hiding the signal.

**Basis for thresholds:** 3-bar confirmation filters out single-bar noise; the
1.2× volume gate enforces Darvas' rule that genuine breakouts carry conviction
(Dhanus & Amutha 2025 found volume confirmation materially cuts false signals).

**Risk profile:** ~47–52% standalone hit rate (a coin flip on large caps);
shines as a *confirmation filter* and at long horizons in BEAR regimes
(T+252d EV +72% in the 10-yr walk-forward).

### B.2 Golden Crossover  — *technical, trend*

**Thesis:** when the medium-term trend overtakes the long-term trend, a durable
uptrend is beginning.

**Rule:** the 50-day simple moving average crosses **above** the 200-day SMA:
```
DMA50_t   > DMA200_t   AND   DMA50_{t−1} < DMA200_{t−1}
```
(`DMA_n = mean(close, n)`.) Requires ≥201 bars.

**Basis:** 50/200 are the most-watched institutional averages, making the cross
partly self-fulfilling. It is a **lagging** confirmation, not a leading signal.

**Risk profile:** strong at the 1-year horizon (EV +30–68% in BULL/SIDEWAYS) but
near-random short-term (T+3d often negative); HIGH overfitting risk at 1yr in
some periods — use only with fundamental support.

### B.3 Piotroski F-Score  — *fundamental, quality*

**Thesis (Joseph Piotroski, 2000):** within cheap stocks, those with improving
fundamentals outperform. A 9-point binary checklist scores accounting quality.

**The 9 criteria (1 point each):**

| # | Group | Test |
|---|---|---|
| 1 | Profitability | Net Income / Total Assets (ROA) > 0 |
| 2 | | Operating Cash Flow > 0 |
| 3 | | ROA improving year-on-year |
| 4 | | OCF/Assets > ROA (earnings backed by cash, low accruals) |
| 5 | Leverage/Liquidity | Long-term debt ratio falling |
| 6 | | Current ratio improving |
| 7 | | No new shares issued (no dilution) |
| 8 | Efficiency | Gross margin improving |
| 9 | | Asset turnover improving |

**Qualification:** **F-Score ≥ 7 / 9.** Financial companies excluded (their
leverage and asset structure make these ratios non-comparable).

**Basis:** Piotroski's 2000 paper showed a high-F-score value portfolio beat a
low-F-score one by ~23%/yr. Signal date = July 1 (after annual reports release).

**Risk profile:** 79–91% hit rate at T+21d in BEAR regimes (full-NSE backtest);
backward-looking (data up to 12 months old) — best with a valuation screen.

### B.4 Coffee Can Portfolio  — *fundamental, quality compounders*

**Thesis (Robert Kirby 1984; Saurabh Mukherjea / Marcellus for India):** buy a
handful of high-quality, consistently growing businesses and hold for ~10 years.

**All 5 must hold:**

| Criterion | Rule | Why |
|---|---|---|
| Revenue CAGR | `(rev_0/rev_n)^(1/n) − 1 > 10%` | sustained top-line growth |
| ROCE (avg) | `EBIT / (Assets − Current Liab) > 15%` | efficient capital use |
| Debt/Equity | `< 1` | balance-sheet safety |
| Market cap | `≥ ₹500 Cr` (US: ≥ $1B) | liquidity / survivability |
| No loss year | Net Income > 0 every available year | consistency |

(US variant adds: Free Cash Flow > 0.)

**Basis:** Marcellus research shows portfolios meeting these "clean compounding"
filters compounded ~20–26%/yr over rolling decades. Designed for **long holds** —
short-horizon backtests are not meaningful for it.

**Risk profile:** stocks almost always trade at premium P/E (40–80×); entry
valuation dominates 10-year returns.

### B.5 Magic Formula  — *fundamental, quality + value*

**Thesis (Joel Greenblatt, 2005):** systematically buy good businesses at cheap
prices by ranking on two factors.

**Two metrics + exclusions:**

```
ROIC           = EBIT / (Total Assets − Current Liabilities)         > 15%
Earnings Yield = EBIT / Enterprise Value                             > 8%
   where Enterprise Value = Market Cap + Total Debt − Cash
Exclusions: negative earnings; financial companies; MCap < ₹100 Cr
```

**Original method:** rank all stocks by ROIC and by Earnings Yield separately,
sum the ranks, buy the lowest combined rank (~top 30), rebalance annually. This
repo uses relaxed pass/fail thresholds as a top-30 proxy on a large universe.

**Basis:** Greenblatt's backtest (1988–2004) showed ~30%/yr; Preet et al. (2021)
replicated on India — BSE 500 CAGR 13.89% vs Sensex 9.31% over 8 years.
ROIC = "is it a good business"; Earnings Yield = "is it cheap".

**Risk profile:** cheap stocks are often cheap for a reason; hold a diversified
basket ≥12 months; short-term performance is near-zero.

### B.6 Bull Cartel  — *fundamental, earnings momentum*

**Thesis (screener.in community):** accelerating quarterly earnings precede price
re-rating.

**All 3 must hold (YoY, latest quarter vs same quarter last year):**
```
Sales growth  = (Rev_Q0 − Rev_Q4) / |Rev_Q4| × 100   > 15%
Profit growth = (NI_Q0  − NI_Q4)  / |NI_Q4|  × 100   > 20%
Net profit    = NI_Q0 / 1e7                           > ₹1 Cr
```
Uses YoY (Q0 vs Q4) to neutralise seasonality. Requires ≥5 quarters of data.

**Basis:** post-earnings-announcement drift — markets under-react to earnings
surprises, so growth acceleration tends to persist for a quarter or two.

**Risk profile:** highest BEAR-regime expected value in the full-NSE backtest
(EV +21.3% at T+21d, 80.5% hit rate) — but earnings momentum mean-reverts;
verify it's organic growth, not a base effect.

---

## Part C — Composite Screeners

| Composite | Rule | Meaning |
|---|---|---|
| **Triple Hit** | Darvas breakout AND Piotroski ≥7 AND Coffee Can pass | technical momentum + quality + compounding — highest conviction (≈8 of 2,400 NSE stocks) |
| **Multi-Screen Hit** | passes ≥3 of the 6 screeners | confluence across independent theses |

**Basis:** the screeners have *uncorrelated failure modes* (a Darvas breakout can
be a head-fake; a Piotroski stock can be expensive; a Coffee Can name can be
overvalued). Requiring agreement across them filters out each one's blind spot.

---

## Part D — Intraday Filters (`intraday_monitor.py`)

| Filter | Basis |
|---|---|
| **Opening Range Breakout (ORB)** | the first 15–30 min sets the day's reference range; a break implies institutional commitment to a direction |
| **VWAP deviation** | VWAP = Σ(price×vol)/Σ(vol) is the day's volume-weighted fair value; large deviation = mean-reversion setup |
| **Volume surge** | current bar > 3× rolling average → real participation behind a move |
| **Momentum burst** | 3+ consecutive same-direction bars → intraday trend persistence |
| **Bollinger squeeze** | bands narrow (low volatility) → volatility-expansion breakout often follows |
| **Intraday Darvas** | the Darvas box logic on 15-min bars for short-term breakouts |

**Confluence score** = how many of the six agree — higher = stronger conviction.

---

## Part E — Why thresholds are what they are (summary)

| Threshold | Value | Source |
|---|---|---|
| RSI period | 14 | Wilder (1978) default |
| RSI overbought/oversold | 70 / 30 | Wilder bands |
| Darvas confirmation | 3 bars | Darvas (1960) |
| Darvas volume gate | 1.2× 20-day avg | Dhanus & Amutha (2025) |
| Golden cross | 50 / 200 DMA | institutional convention |
| Piotroski pass | ≥7 / 9 | Piotroski (2000) |
| Coffee Can ROCE / CAGR / D-E | 15% / 10% / <1 | Mukherjea / Marcellus |
| Magic Formula ROIC / EY | 15% / 8% | Greenblatt (2005), relaxed proxy |
| Bull Cartel sales / profit | 15% / 20% YoY | screener.in |
| Transaction cost | 0.2% round-trip | STT + brokerage (Indian discount broker) |

---

*See [APPROACHES.md](APPROACHES.md) for the fundamental-vs-news framework,
[GLOSSARY.md](GLOSSARY.md) for definitions, and
[STOCK_ANALYSIS_SYSTEM.md](STOCK_ANALYSIS_SYSTEM.md) for full methodology.
Research citations are listed in the CHANGELOG and STOCK_ANALYSIS_SYSTEM.md.*
