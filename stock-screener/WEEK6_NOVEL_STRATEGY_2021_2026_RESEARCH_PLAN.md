# 🎯 WEEK 6: NOVEL STRATEGY RESEARCH - 2021-2026 MARKET ANALYSIS
## Developing New Reward Optimization Beyond Existing Screener Approaches

**Objective**: Create a completely novel reward-optimized strategy using 5-year market data (Jan 2021 - Jun 2026) that differs fundamentally from existing Darvas/Buffett/Piotroski/Coffee Can frameworks.

---

## PROBLEM STATEMENT: WHY EXISTING STRATEGIES NEED EVOLUTION

### What Existing Screeners Cover
```
✅ Darvas/Buffett     → Technical breakouts + quality filtering
✅ Piotroski          → Financial statement health (9 metrics)
✅ Coffee Can         → Long-term quality hold (ROE, growth, FCF)
❌ ???                → What works in 2021-2026 specifically?
```

### Market Environment Changed (2021-2026)
- **2021**: Recovery rally, inflation heating
- **2022**: Rate shock (0% → 4.25%), 40-year high inflation
- **2023**: Credit fears, banking crisis, AI euphoria boom
- **2024**: Valuation compression, mega-cap concentration
- **2025-2026**: Continuation of rate normality, AI reality check

**Key Insight**: A strategy optimized for 2008/2000/2022 crises may NOT be optimal for sustained high-rate, AI-disrupted, supply-shock recovery environment.

---

## PROPOSED: 5 NEW REWARD DIMENSIONS FOR 2021-2026

### 1. **AI Disruption Resilience** (r_ai_safe)
**Hypothesis**: Companies with AI-resistant moats + AI exposure outperformed.

- **r_ai_safe** = (AI-proof business + AI adoption score) / 2
  - AI-proof: Recurring revenue, customer switching costs, proprietary data
  - AI adoption: Cloud spending %, automation capex %, digital revenue %
  
**Expected Signal**: 
- Banks (AI-proof but slow adoption) = +0.6
- Cloud infrastructure (AI-exposed, adoption-heavy) = +0.9
- Retail (AI-disrupted) = +0.2

---

### 2. **Inflation Pricing Power** (r_pricing_power)
**Hypothesis**: In 40-year-high inflation, companies that raised prices without volume loss won.

- **r_pricing_power** = (Gross margin expansion + Revenue growth consistency) / 2
  - Gross margin: Compare 2021 vs 2022-2024 (did it expand?)
  - Revenue growth: Did revenue compound despite macro headwinds?
  
**Expected Signal**:
- Energy stocks (commodity leverage) = +0.9
- Luxury goods (pricing power) = +0.85
- Commodities (price-taker) = +0.3

---

### 3. **Supply Chain Resilience** (r_supply_chain)
**Hypothesis**: Post-COVID, companies with diversified suppliers + local sourcing outperformed.

- **r_supply_chain** = (Inventory turnover stability + supplier diversification proxy) / 2
  - Inventory turnover: Did it stay consistent 2021-2024 vs pre-2021?
  - Supplier proxy: R&D spend (indicates proprietary supply)
  
**Expected Signal**:
- Semiconductor supply chain companies = +0.8
- Automotive with diverse sourcing = +0.75
- Fashion with single-source risk = +0.3

---

### 4. **Rate Hike Resilience** (r_rate_resilient)
**Hypothesis**: In rising-rate environment (2022-2024), companies with low refinancing risk + high FCF outperformed.

- **r_rate_resilient** = (Debt maturity profile + FCF/Debt ratio) / 2
  - Debt maturity: % of debt due >5 years (avoid roll-over risk)
  - FCF/Debt: Free cash flow coverage of total debt
  
**Expected Signal**:
- Utilities (low-leverage, stable FCF) = +0.85
- Financial services (rising rates = wider spreads) = +0.9
- Tech (debt heavy, rising rates = pain) = +0.4

---

### 5. **Insider Accumulation Signal** (r_insider_smart)
**Hypothesis**: Insider buying during market downturns (Mar 2020, Mar-Jun 2022, Sep-Oct 2023) predicted recovery.

- **r_insider_smart** = (Insider buy-sell ratio in downturns + magnitude of buys) / 2
  - Buy-sell ratio: >2.0 = strong conviction
  - Magnitude: Large percentage position buys vs small trades
  
**Expected Signal**:
- Stock with 5%+ insider buys during 2022 crash = +0.85
- Stock with routine option exercises = +0.3

---

## COMPOSITE REWARD: "MODERN RESILIENCE" FRAMEWORK

```
r_modern = w₁·r_ai_safe 
         + w₂·r_pricing_power 
         + w₃·r_supply_chain 
         + w₄·r_rate_resilient 
         + w₅·r_insider_smart

Baseline weights (will optimize):
w₁ = 0.20  (AI Resilience: 20% — emerging but critical)
w₂ = 0.25  (Pricing Power: 25% — dominated 2021-2024)
w₃ = 0.15  (Supply Chain: 15% — secondary in recovery)
w₄ = 0.30  (Rate Resilience: 30% — primary 2022-2024 signal)
w₅ = 0.10  (Insider Smart: 10% — late-stage confirmation)
```

---

## PHASE 1: DATA COLLECTION (Week 6A)

### Data Sources Required

| Signal | Source | Availability |
|---|---|---|
| r_ai_safe | 10-K/10-Q cloud %, automation %, digital revenue % | ✅ SEC filings |
| r_pricing_power | Gross margin, revenue from 10-K | ✅ SEC filings |
| r_supply_chain | Inventory turnover, R&D, from 10-K | ✅ SEC filings |
| r_rate_resilient | Debt maturity schedule, FCF from 10-K | ✅ SEC filings |
| r_insider_smart | Insider transactions from Form 4 filings | ✅ SEC Edgar |

**Data gaps to fill**:
- Historical insider trading (Form 4): Need 2020-2024 archives
- 10-K historical GL data: Need processed financials for 3,000+ stocks
- Cloud/automation proxies: Need text mining of 10-K disclosures

---

## PHASE 2: SIGNAL VALIDATION (Week 6B)

### Test Hypothesis 1: "Pricing Power Dominated"
```
Compare 2021-2026 returns:
- Top 20% by r_pricing_power  vs  Bottom 20%
- Expected outperformance: +15-25pp

Markets:
- USA (S&P 500): Primary test
- Europe: Secondary test (DAX, CAC 40)
- India (Nifty 500): Tertiary test
```

### Test Hypothesis 2: "Rate Resilience Mattered Most"
```
Split 2022 (rate shock year):
- Top 20% by r_rate_resilient  vs  S&P 500
- Expected outperformance: +20-30pp (bear market protection)

Then 2023-2024:
- Did rate-resilient stocks stabilize or lagged?
```

### Test Hypothesis 3: "Insider Buying Was Prescient"
```
Identify insider accumulation windows:
- Q1-Q2 2020 (pandemic crash)
- Q2 2022 (inflation peak)
- Q3 2023 (banking crisis)

Stocks with >2.0 buy-sell ratio during these → 12-month forward returns?
```

---

## PHASE 3: PORTFOLIO CONSTRUCTION (Week 6C)

### Candidate Universe
```
USA:    S&P 500 (500 stocks)
Europe: DAX + CAC + FTSE top 100 (300 stocks)  
India:  Nifty 50 + BSE-listed (500 stocks)
Japan:  Nikkei 225 (225 stocks)
Korea:  KOSPI (100 stocks)
```

### Filter Pipeline
```
Step 1: Minimum liquidity ($50M daily volume)
Step 2: Calculate r_ai_safe, r_pricing_power, r_supply_chain, r_rate_resilient, r_insider_smart
Step 3: Create composite r_modern score
Step 4: Select top 20 per market (weighted by market cap)
Step 5: Backtest 2021-2026
```

### Expected Portfolio Composition
```
Energy            20%  (High pricing power + rate resilience)
Financials        18%  (Rate benefits + insider smart)
Healthcare        15%  (AI-resilient, pricing power)
Industrials       15%  (Supply chain recovery plays)
Technology        12%  (Selective AI exposure)
Utilities         10%  (Rate-resilient, dividend yield)
```

---

## PHASE 4: BACKTEST SCENARIO (Week 6D)

### Test Portfolio: "Modern Resilience 2021-2026"
```
Initial Capital: $100,000
Rebalance: Quarterly
Positions: 20 stocks (5% each)

Benchmark:
- S&P 500 (primary)
- Nifty 50 (secondary)
- MSCI World ex-US (tertiary)
```

### Expected Results
```
2021:  +25% (recovery rally bonus)
2022:  -5%  (bear market, but +20pp vs S&P 500)
2023:  +35% (AI rally, rate recovery)
2024:  +12% (valuation compression)
2025-26: TBD (forward test)

CAGR Target: 18-22% vs 10-12% S&P 500
Sharpe Ratio: 1.8-2.2 vs 0.9-1.1 S&P 500
Max Drawdown: -12% vs -35% S&P 500
```

---

## SUCCESS CRITERIA

✅ **Novel**: Uses signals not in Darvas/Buffett/Piotroski/Coffee Can  
✅ **Data-Driven**: Grounded in 2021-2026 specific market regime  
✅ **Outperformance**: Beats S&P 500 + Nifty 50 in all markets  
✅ **Repeatable**: Portfolio rules are systematic, not discretionary  
✅ **Validated**: Hypothesis testing shows statistical significance  

---

## TIMELINE

| Week | Task | Deliverable |
|------|------|---|
| **Week 6A** | Data collection from SEC Edgar, Yahoo Finance | Raw signals CSV |
| **Week 6B** | Hypothesis validation via historical backtest | Test results + percentile rankings |
| **Week 6C** | Portfolio construction + optimization | Weights + expected returns |
| **Week 6D** | Full 2021-2026 backtest | Returns, Sharpe, max DD |
| **Week 6E** | Sensitivity analysis + robustness testing | Parameter ranges |
| **Week 6F** | Academic write-up + publication ready | Research paper |

---

**Status**: Ready to begin Phase 1A data collection  
**Next Step**: Confirm data sources and begin SEC Edgar mining for insider trading + 10-K financials

