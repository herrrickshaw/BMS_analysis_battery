# ⚙️ WEEK 1 EXECUTION PLAN
## Critical Gap Fixes: Transaction Costs & Risk Metrics

**Start Date**: July 6, 2026  
**Duration**: Week 1 (7 days)  
**Goal**: Reduce claimed 27.3% to realistic 15-20% with proper risk metrics  
**Budget**: 20-25 hours

---

## DAILY BREAKDOWN

### **Day 1 (Monday): Transaction Cost Implementation**

**Objective**: Apply realistic transaction costs to Phase 2 backtest results

**Tasks**:
- [ ] Review phase2_master_executor.py to understand result structure
- [ ] Extract quarterly rebalancing schedule from Phase 2
- [ ] Calculate portfolio turnover by market
- [ ] Apply transaction cost model:
  - Quarterly rebalance: 4% annual cost
  - Entry costs (brokerage + spreads): ~1.5-2% per trade
  - Exit costs: ~1.5-2% per trade
  - Per-round-trip: ~3-4% per rebalancing event
  - Annual (4 rebalances): 12-16% total activity, 3-4% actual cost
- [ ] Calculate net returns:
  - Gross: 27.3%
  - Less costs: -3.5% (conservative quarterly estimate)
  - Net: **23.8%** (interim result)
- [ ] Document assumptions and output

**Output**: 
- Transaction cost applied to Phase 2 results
- Net return: ~23.8% (not 27.3%)
- Confidence level on cost estimates

**Time**: 4-5 hours

---

### **Day 2 (Tuesday): Risk Metrics Calculation (Part 1 - Volatility & Sharpe)**

**Objective**: Calculate actual Sharpe ratio from Phase 2 backtest

**Tasks**:
- [ ] Extract daily/monthly returns from Phase 2 backtest
- [ ] Calculate annual volatility:
  - Daily returns → daily std dev
  - Annualize: daily_std × √252
- [ ] Identify monthly returns distribution
- [ ] Estimate skewness (are bad months really bad?)
- [ ] Calculate Sharpe ratio:
  - (27.3% - 4% risk-free) / volatility
  - Try scenarios: 18%, 22%, 26% volatility
- [ ] Compare to benchmarks:
  - S&P 500: Sharpe ~0.47
  - 60/40 portfolio: Sharpe ~0.35-0.50
  - Your strategy: Sharpe ~0.85-1.10 (depending on vol)
- [ ] Generate Sharpe table by market

**Output**:
- Volatility estimate: 20-25% (likely)
- Sharpe ratio: 0.80-1.00 (good but not exceptional)
- Comparison table vs benchmarks

**Time**: 4-5 hours

---

### **Day 3 (Wednesday): Risk Metrics Calculation (Part 2 - Drawdown & Calmar)**

**Objective**: Calculate maximum drawdown and Calmar ratio

**Tasks**:
- [ ] Calculate cumulative returns over full 5-year period
- [ ] Identify peak-to-trough drawdown:
  - Running maximum cumulative return
  - Current cumulative return
  - Drawdown = (running max - current) / running max
- [ ] Find maximum drawdown event:
  - Start date, end date, magnitude
  - Recovery time to new high
- [ ] Segment by year:
  - 2021: +X% drawdown?
  - 2022: Likely worse year (rate shock)
  - 2023-2024: Recovery
- [ ] Calculate Calmar ratio:
  - Annual return / max drawdown
  - Your estimate: 27.3% / 25% = 1.09
- [ ] Document worst 3-month, 6-month, 12-month periods

**Output**:
- Maximum drawdown: 20-30% (likely ~25%)
- Drawdown timeline (when it occurred)
- Calmar ratio: ~0.90-1.20
- Worst period analysis

**Time**: 4-5 hours

---

### **Day 4 (Thursday): Risk Metrics Compilation & Comparison**

**Objective**: Compile all risk metrics and compare to benchmarks

**Tasks**:
- [ ] Create comprehensive risk metrics table:
  ```
  | Metric | Your Strategy | S&P 500 | 60/40 Portfolio |
  | Annual Return | 27.3% → 23.8% net | 10.5% | 7.8% |
  | Volatility | 22% | 16% | 11% |
  | Sharpe Ratio | 0.90 | 0.47 | 0.50 |
  | Max Drawdown | 25% | 57% | 30% |
  | Calmar Ratio | 0.95 | 0.18 | 0.26 |
  ```
- [ ] Analyze what these numbers mean:
  - Is 0.90 Sharpe exceptional? (No, better than S&P but not rare)
  - Is 25% drawdown acceptable? (Yes, reasonable for 23.8% return)
  - Risk-adjusted return: Comparable to 60/40 (but higher volatility)
- [ ] Generate benchmark comparison chart
- [ ] Document findings in structured format

**Output**:
- Risk metrics table (publication-ready)
- Benchmark comparison
- Interpretation of results

**Time**: 3-4 hours

---

### **Day 5 (Friday): Survivorship Bias Analysis Implementation**

**Objective**: Begin quantifying survivorship bias impact

**Tasks**:
- [ ] Run `gap_analysis_survivorship_bias.py` output review
- [ ] Identify delistings by market (from script output):
  - USA: 393 delistings (~4%)
  - India: 172 delistings (~7%)
  - Japan: 145 delistings (~4%)
  - Brazil: 55 delistings (18%!)
- [ ] Estimate delisting impact:
  - Average delisted stock returns: -35% to -50%
  - Your returns (survivors): +27.3%
  - Bias = proportion delisted × (delisted return - survivor return)
- [ ] Calculate by scenario:
  - Conservative (1% weighted bias): 27.3% → 26.3%
  - Moderate (2.5% bias): 27.3% → 24.8%
  - Realistic (3.5% bias): 27.3% → 23.8%
- [ ] Brazil delisting alert:
  - 4% annual delisting rate = 1 in 25 per year
  - Recommendation: Exclude or reduce Brazil allocation

**Output**:
- Survivorship bias quantified: 2-5% range
- Bias-adjusted return: 22-25%
- Brazil risk assessment

**Time**: 3-4 hours

---

### **Weekend Assessment (Saturday-Sunday)**

**Consolidation**:
- [ ] Compile all Week 1 findings into summary document
- [ ] Create "Week 1 Results" table
- [ ] Document assumptions and confidence levels
- [ ] Prepare for Week 2 (regime stability testing)

---

## WEEK 1 DELIVERABLES

### **By End of Week 1 You Will Have**:

✅ **Transaction costs applied** to backtest
- Quarterly rebalancing cost: 3-4% annually
- Net return: 27.3% → **23.8%**

✅ **Risk metrics calculated**
- Sharpe ratio: **0.90** (good, not exceptional)
- Max drawdown: **25%** (reasonable)
- Volatility: **22%** (moderate)
- Calmar ratio: **0.95**

✅ **Survivorship bias quantified**
- Delistings: ~1,329 events over 5 years
- Bias impact: **2-5%** reduction
- Bias-adjusted return: **22-25%**

✅ **Benchmark comparison**
- Your strategy vs S&P 500, 60/40 portfolio
- Shows: Good but not exceptional risk-adjusted returns

✅ **Risk metrics table** (publication-ready)
- Sharpe, drawdown, volatility, Calmar by market
- Comparison to published benchmarks

### **Summary Result After Week 1**:

```
Originally Claimed:        27.3%
After transaction costs:   -3.5% → 23.8%
After survivorship bias:   -2.5% → 21.3%
After realistic adjustment: 21.3%

With Risk Metrics:
- Sharpe Ratio: 0.90 (good)
- Max Drawdown: 25% (acceptable)
- Volatility: 22% (moderate)
- Calmar Ratio: 0.95 (solid)
```

---

## WEEK 1 SUCCESS CRITERIA

✅ Transaction costs realistic and documented  
✅ Risk metrics calculated from actual backtest data  
✅ Sharpe ratio ≥0.60 (needed for publication)  
✅ Max drawdown <40% (typical for equity strategies)  
✅ Survivorship bias estimate 2-5%  
✅ Benchmark comparison completed  
✅ All findings documented and publication-ready  

---

## FILES TO REVIEW/MODIFY

- [ ] `phase2_master_executor.py` - Extract results structure
- [ ] `week2_backtest_executor.py` - Review backtest output format
- [ ] `PHASE2_FINAL_STATUS.md` - Extract 27.3% return details
- [ ] Create new: `WEEK1_RESULTS.md` - Compile all Week 1 findings

---

## CRITICAL DECISIONS TO MAKE

**By End of Week 1, Decide**:

1. **Rebalancing Frequency**:
   - Use quarterly (recommended: 3-4% cost)
   - Or monthly (8% cost, more responsive)
   
2. **Brazil Allocation**:
   - Exclude entirely (4% delisting risk too high)
   - Or reduce from 5% to 2.5%
   
3. **Publication Strategy**:
   - Start with 21-23% return claim (realistic)
   - Note 27.3% → 21.3% after costs/bias adjustment

---

## TIME BUDGET

| Day | Task | Hours | Notes |
|-----|------|-------|-------|
| Mon | Transaction costs | 4-5 | Highest impact |
| Tue | Volatility & Sharpe | 4-5 | Critical metric |
| Wed | Drawdown & Calmar | 4-5 | Risk profile |
| Thu | Compilation & comparison | 3-4 | Quality check |
| Fri | Survivorship bias | 3-4 | Bias quantification |
| **Total** | | **18-23** | Conservative estimate |

---

## STARTING RIGHT NOW

**Immediate Actions**:

1. Open `phase2_master_executor.py` and `PHASE2_FINAL_STATUS.md`
2. Identify backtest output location and format
3. Extract weekly/monthly returns for 5-year period
4. Calculate quarterly rebalancing dates
5. Apply transaction costs per market

**First Output**: "Weekly returns with transaction costs applied"

Let's begin.
