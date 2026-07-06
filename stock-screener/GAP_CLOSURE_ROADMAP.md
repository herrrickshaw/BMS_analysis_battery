# 🔧 GAP CLOSURE ROADMAP
## Action Plan to Address Critical Analysis Gaps

**Status**: Gap analysis scripts created  
**Date**: July 6, 2026  
**Objective**: Close identified gaps to make academic research publication-ready

---

## I. CRITICAL GAPS (Must Fix)

### 1. Transaction Costs & Market Impact ❌ NOT MODELED

**Original Gap**: Assumed zero transaction costs; states "conservative assumption favors findings"

**Analysis Script**: `gap_analysis_transaction_costs.py`

**Key Findings**:
- Brokerage fees: 0.1% (US) to 6% (Brazil)
- Bid-ask spreads: 1 bps (US large-cap) to 50+ bps (India small-cap)
- Market impact: Position size × illiquidity = 2-10% per trade in emerging markets
- **Total annual cost**: 4-12% depending on rebalancing frequency
- **Impact on 27.3% return**: Reduces to 20-24% (8-10% reduction)

**What Needs to Be Done**:
1. ✅ DONE: Create detailed cost model by market
2. ⏳ TODO: Apply costs to backtested portfolio
3. ⏳ TODO: Calculate quarterly rebalancing turnover
4. ⏳ TODO: Report net-of-cost returns (critical for publication)

**Timeline**: 2-3 days of implementation

---

### 2. Risk Metrics Missing 🔴 CRITICAL GAP

**Original Gap**: Reports return (27.3%) and win rates (54.5%) but NO:
- Sharpe ratio (required for academic papers)
- Maximum drawdown (required for risk assessment)
- Volatility / annualized std dev
- Calmar ratio (return / max drawdown)

**Analysis Script**: `gap_analysis_risk_metrics.py`

**Key Findings**:
- Estimated Sharpe ratio: 0.90-1.10 (good but not exceptional)
- Estimated max drawdown: 20-30% (comparable to S&P 500)
- Risk-adjusted returns may not exceed 60/40 portfolio
- Volatility estimated 18-25% annually

**What Needs to Be Done**:
1. ✅ DONE: Estimate likely risk metrics
2. ⏳ TODO: Calculate actual volatility from backtest returns
3. ⏳ TODO: Compute rolling Sharpe ratio across the period
4. ⏳ TODO: Identify maximum drawdown in the backtest
5. ⏳ TODO: Add Sharpe/Calmar to paper (essential)

**Timeline**: 1-2 days to calculate from backtest data

---

### 3. Survivorship Bias Not Quantified 🟡 MEDIUM-HIGH GAP

**Original Gap**: States "survivorship bias controlled" but provides NO magnitude

**Analysis Script**: `gap_analysis_survivorship_bias.py`

**Key Findings**:
- ~500-600 delistings across 20,000 stocks over 5 years
- Delistings average -35% to -50% return (vs. +27.3% survivors)
- Implied bias: 2-5% reduction in claimed return
- **Adjusted return: 22-25%** (vs. claimed 27.3%)
- Brazil: 4% annual delisting risk (highest)
- India: 1.5% annual risk (medium)

**What Needs to Be Done**:
1. ✅ DONE: Quantify delisting rates by market
2. ⏳ TODO: Reconstruct universe including delisted stocks
3. ⏳ TODO: Find delisted stock prices at delisting dates
4. ⏳ TODO: Calculate bias-adjusted returns
5. ⏳ TODO: Report before/after comparison

**Timeline**: 2-3 days (data gathering + calculation)

---

### 4. Only One Period Tested (2021-2026) ⚠️ MAJOR GAP

**Original Gap**: Claims 27.3% "annual return" based on 1 favorable regime

**Analysis Script**: `gap_analysis_regime_stability.py`

**Key Findings**:
- 2021-2026: Perfect storm of earnings growth + multiple expansion + Fed pivot
- Return decomposition: +10% base + +8% earnings + +5% multiples + +4% momentum = 27.3%
- Most of these tailwinds were one-time post-COVID recovery
- Forward expectation: 10-15% (not 27%)
- NOT tested on: 2008 crisis, 2000 crash, 2022 rate shock

**What Needs to Be Done**:
1. ✅ DONE: Identify why 2021-2026 was favorable
2. ⏳ TODO: Backtest on 2008-2009 financial crisis
3. ⏳ TODO: Backtest on 2000-2002 dot-com crash
4. ⏳ TODO: Backtest on 2022-2023 rate hiking
5. ⏳ TODO: Report Sharpe ratio across periods
6. ⏳ TODO: Identify if strategy is regime-dependent

**Timeline**: 4-5 days (data collection + backtesting each period)

---

## II. HIGH-PRIORITY GAPS (Strongly Recommended)

### 5. Rebalancing Frequency & Turnover Not Specified

**Current State**: No clarity on when signals trigger trades

**What Needs**:
- Specify: Quarterly Piotroski? Daily Darvas? Weekly earnings?
- Calculate portfolio turnover % per year
- Map turnover to transaction costs
- Test sensitivity: What if monthly instead of quarterly?

**Timeline**: 1 day

---

### 6. Liquidity Constraints Not Modeled

**Current State**: Assumes 20,000-stock portfolio tradeable at $50K per position

**Reality**:
- Many emerging market stocks: <$1M daily volume
- Your $50K position = 5-50% of daily volume (impossible)
- Creates market impact not captured in transaction costs

**What Needs**:
- Add liquidity filter: Min $10M-$50M daily volume
- Recalculate returns with liquidity-constrained universe
- Test if strategy still works

**Timeline**: 1-2 days

---

### 7. Sector Concentration Not Analyzed

**Current State**: Unknown portfolio sector weights

**What Needs**:
- Identify which sectors over/underweight (likely Financial, Healthcare, Industrial)
- Test: Is return driven by sector tilt or stock selection?
- Compare against sector benchmarks
- Report sector exposure explicitly

**Timeline**: 1-2 days

---

### 8. Multiple Testing Corrections Incomplete

**Current State**: States Benjamini-Hochberg correction but 150+ tests reported

**What Needs**:
- Explicit false discovery rate calculation
- Bonferroni correction for comparison
- Report: What % of findings survive multiple testing?
- Identify results with p > 0.05 even after correction

**Timeline**: 1 day

---

## III. MEDIUM-PRIORITY GAPS (Recommended for Completeness)

### 9. Interaction Effects (Size, Regime, Currency)

**What Needs**:
- Does strategy work equally well for large vs. small-cap?
- Does it work in high-volatility vs. low-volatility regimes?
- Currency impact: Does strong USD vs. weak USD matter?

**Timeline**: 2-3 days

---

### 10. Correlation Stability in Crises

**Current Finding**: Japan-India correlation 0.32 (stated as diversification benefit)

**Reality**: Correlations spike to 0.70+ in crises → diversification fails when needed

**What Needs**:
- Report rolling correlations (3-month, 12-month windows)
- Test portfolio performance if all correlations became 0.80
- Stress test diversification benefit

**Timeline**: 1-2 days

---

### 11. Earnings Surprise Heterogeneity

**Current Finding**: +0.82% post-earnings drift (aggregate)

**What Needs**:
- Separate drift for small vs. large surprises
- Separate drift for positive vs. negative surprises
- Is drift exploitable or just measurement error?

**Timeline**: 1 day

---

## EXECUTION TIMELINE

### **Week 1-2 (July 8-19): CRITICAL FIXES**
- [ ] Transaction cost implementation (apply to backtest)
- [ ] Risk metrics calculation (Sharpe, drawdown, volatility)
- [ ] Survivorship bias quantification (include delisted stocks)
- **Deliverable**: Risk-adjusted returns + transaction costs = realistic return estimate

### **Week 3-4 (July 22-Aug 2): REGIME STABILITY**
- [ ] 2008 crisis backtest
- [ ] 2000 crash backtest
- [ ] 2022 rate hiking backtest
- **Deliverable**: Sharpe ratio comparison across regimes

### **Week 5 (Aug 5-9): POLISH & HIGH-PRIORITY GAPS**
- [ ] Rebalancing frequency specification
- [ ] Liquidity constraint testing
- [ ] Sector concentration analysis
- [ ] Multiple testing robustness check

### **Week 6+ (Aug 12+): OPTIONAL ENHANCEMENTS**
- [ ] Interaction effect analysis
- [ ] Correlation stress testing
- [ ] Earnings heterogeneity decomposition

---

## REALISTIC RETURN EXPECTATIONS

### Current Claim
**27.3% annual return** (before costs, pre-tax, before slippage)

### After Critical Gap Fixes
```
Base return (backtest):              27.3%
Less: Transaction costs (-4 to -12%) -8.0% (midpoint)
Less: Survivorship bias (-2 to -5%)  -3.5% (midpoint)
─────────────────────────────────────
Realistic return:                    15.8% annually

After regime adjustment:
(Account for 2021-2026 being exceptional)
More realistic forward return:        12-16% annually
(Still 1.2-1.5x market, but not 2.6x)
```

### With Full Risk Metrics
```
Return:                              15.8% (realistic, post-costs)
Volatility:                          20-22% (estimated)
Sharpe ratio:                        0.65-0.70 (good but not exceptional)
Max drawdown:                        25-35% (similar to S&P 500)
Calmar ratio:                        0.45-0.65 (acceptable)
```

---

## PUBLICATION READINESS CHECKLIST

### For Top-Tier Journal Submission

**MUST HAVE**:
- [x] Literature review (32+ citations)
- [x] Research questions clearly stated
- [x] Methodology detailed
- [ ] Risk metrics (Sharpe, drawdown, volatility)
- [ ] Transaction costs modeled
- [ ] Survivorship bias quantified
- [ ] Multiple regime testing (at least 3 periods)
- [ ] Multiple testing correction

**STRONGLY RECOMMENDED**:
- [ ] Out-of-sample validation
- [ ] Robustness checks (sensitivity analysis)
- [ ] Limitations clearly acknowledged
- [ ] Results compared to published factors
- [ ] Code and data reproducibility statement

**NICE TO HAVE**:
- [ ] Interaction effect analysis
- [ ] Sector concentration analysis
- [ ] Liquidity constraint testing
- [ ] Geographic subsample analysis

---

## EFFORT ESTIMATE

**Total hours to publication-ready**: 25-35 hours
- Critical fixes (transaction costs, risk metrics, survivorship, regime stability): 12-18 hours
- High-priority gaps (rebalancing, liquidity, sector): 6-10 hours
- Polish and finalization: 4-6 hours

**Timeline**: 4-6 weeks part-time (10-15 hrs/week)

---

## SUCCESS CRITERIA

**Paper is publication-ready when**:
1. ✓ Sharpe ratio reported (≥0.60 for acceptance)
2. ✓ Maximum drawdown quantified (<40%)
3. ✓ Transaction costs explicit (shows -4 to -12%)
4. ✓ Tested on 3+ market regimes (crisis + normal)
5. ✓ Survivorship bias estimated (2-5%)
6. ✓ Realistic returns disclosed (15-20%, not 27%)
7. ✓ Limitations acknowledged (period-specific, regime-dependent)
8. ✓ Reproducible (code + data specs provided)

---

## NEXT STEPS

1. **Review gap analysis reports** (4 Python scripts created)
2. **Prioritize fixes** (transaction costs = highest impact)
3. **Start Week 1 work**: Transaction costs + risk metrics
4. **Iterate**: Each week adds new tests/validations
5. **Target submission**: Late August / early September (4-6 weeks)

**Recommended Journal Targets** (after gaps closed):
- Journal of Finance
- Financial Analysts Journal
- Review of Financial Studies

---

*Gap closure roadmap created: July 6, 2026*  
*Status: Ready to begin implementation*
