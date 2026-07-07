# 🎯 Rewards Optimization & Analysis Guide

## Overview

The Rewards Optimization module identifies exceptional 5-year performers that beat typical stock screeners. It goes beyond standard filtering to find **hidden gems** — stocks with exceptional risk-adjusted returns outside conventional criteria.

---

## 🚀 Quick Start

### Run the Analysis

```bash
cd /Users/umashankar/stock-screener

# Run analysis on sample portfolio
python rewards_optimization.py

# Export detailed report
python rewards_optimization.py --report rewards_report.txt
```

### Open Web Dashboard

```
file:///Users/umashankar/stock-screener/rewards_dashboard.html
```

---

## 📊 What This Does

### Analyzes 5-Year Performance

- **CAGR**: Compound Annual Growth Rate (total return annualized)
- **Total Return**: Absolute gain/loss over 5 years
- **Volatility**: Price fluctuation (annualized standard deviation)
- **Sharpe Ratio**: Risk-adjusted returns (higher = better)
- **Sortino Ratio**: Downside-adjusted returns (only negative volatility counts)
- **Maximum Drawdown**: Peak-to-trough loss
- **Win Rate**: % of positive trading days
- **Recovery Time**: Days to bounce back from max drawdown

### Identifies Outliers

**Exceptional Performers**:
- CAGR > 20% (top 15-20% of universe)
- Outstanding risk-adjusted returns
- Beaten typical screeners

**Hidden Gems**:
- High returns + low volatility (rare combo)
- Best Sharpe ratio (risk-adjusted)
- Consistency (high win rate)

**Ultra-Rare Discovery**:
- Stocks beating ALL typical filters simultaneously
- Perhaps 1-2 per universe of 20+ stocks

---

## 🎯 Typical Screeners (What This Beats)

### Momentum Screener
**Criteria**: CAGR > 25%
**Purpose**: Find fast-growing companies
**Weakness**: Ignores volatility (risky)

### Value Screener
**Criteria**: Low volatility (<30%)
**Purpose**: Find stable, low-risk stocks
**Weakness**: May miss growth opportunities

### Quality Screener
**Criteria**: Sharpe Ratio > 1.0
**Purpose**: Find best risk-adjusted performers
**Weakness**: Complex metric, hard to interpret

### Growth Screener
**Criteria**: Win rate > 55% (positive days)
**Purpose**: Find most consistent upside
**Weakness**: Doesn't measure size of moves

---

## 📈 Key Metrics Explained

### CAGR (Compound Annual Growth Rate)
```
Formula: (End Price / Start Price)^(1/Years) - 1
Example: ₹100 → ₹250 in 5 years = 20.1% CAGR

Interpretation:
- <10%: Below market average
- 10-20%: Market average
- 20-30%: Good performance
- >30%: Exceptional (rare)
```

### Sharpe Ratio
```
Formula: (Annual Return - Risk-Free Rate) / Volatility
Example: (25% return - 6% risk-free) / 20% volatility = 0.95

Interpretation:
- <0.5: Poor risk-adjusted returns
- 0.5-1.0: Average
- 1.0-2.0: Good risk-adjusted
- >2.0: Exceptional (extremely rare)

What it means: How much return per unit of risk taken
Higher = better, regardless of absolute return
```

### Sortino Ratio
```
Like Sharpe, but only counts downside volatility
Penalizes only negative swings, not positive ones
Usually higher than Sharpe ratio
Better measure of actual risk (downside loss risk)
```

### Maximum Drawdown
```
Worst peak-to-trough loss during period
Example: Stock hits ₹100, drops to ₹75 = -25% max DD

Interpretation:
- -10% to -20%: Stable, lower risk
- -20% to -40%: Moderate risk
- >-40%: Volatile, higher risk

What it means: How much value lost in worst scenario
Important for emotional tolerance ("Can you handle -30%?")
```

### Win Rate
```
% of trading days with positive returns
Example: Up on 130 out of 250 trading days = 52%

Interpretation:
- <50%: Down more often than up (rare)
- 50-55%: Average market (slight upside)
- >55%: Consistent upside (good)
- >60%: Exceptional (rarely sustained)

What it means: Consistency and upside reliability
High win rate = lower chance of panic/loss
```

---

## 🏆 Rewards Optimization Score

**Composite Score** (0-100):
```
35% → Return Score        (5-year CAGR)
25% → Sharpe Score        (Risk-adjusted)
20% → Stability Score     (Low max drawdown)
20% → Consistency Score   (High win rate)
───────────────────────────────────
= Rewards Optimization Score (0-100)
```

**Interpretation**:
- <40: Underperformer
- 40-60: Market average
- 60-80: Good performer
- >80: Exceptional performer (rare)

**Why this weighting?**
- 35% returns: What actually matters most (profit)
- 25% risk-adjusted: How efficiently you earned it
- 20% stability: Confidence the strategy works
- 20% consistency: Reliability day-to-day

---

## 🎯 Real-World Examples

### Example 1: High Growth, High Volatility (Momentum Play)
```
Stock: Growth Tech Company
CAGR: 45% (Exceptional)
Volatility: 35% (High)
Sharpe Ratio: 1.10 (Average)
Max Drawdown: -48% (Severe)
Win Rate: 51% (Below average)
Rewards Score: 72/100

Analysis: 
- Great returns but rollercoaster ride
- Loses half its value in drawdowns
- More 51% days than 49% days
- For risk-tolerant investors only
```

### Example 2: Balanced Quality Stock
```
Stock: Blue-Chip Company
CAGR: 18% (Good)
Volatility: 15% (Low)
Sharpe Ratio: 1.50 (Excellent)
Max Drawdown: -12% (Minimal)
Win Rate: 57% (Good)
Rewards Score: 85/100

Analysis:
- Best risk-adjusted performer
- Steady, predictable growth
- Never loses >12% (emotionally easy)
- Ideal for conservative investors
```

### Example 3: Hidden Gem (High Return, Low Volatility)
```
Stock: Hidden Gem
CAGR: 26% (Exceptional)
Volatility: 14% (Very Low)
Sharpe Ratio: 1.65 (Outstanding)
Max Drawdown: -18% (Moderate)
Win Rate: 58% (Good)
Rewards Score: 92/100

Analysis:
- RARE COMBINATION: High return + low volatility
- Extremely efficient capital deployment
- Sharpe ratio >1.6 is exceptional
- These stocks are golden (invest heavily)
```

---

## 💡 Investment Strategies Based on Rewards Analysis

### Strategy 1: Growth Seeking
**Focus On**: Momentum Filter Beaters
- CAGR > 25%
- Ignore volatility
- Suitable for: Long time horizon, risk tolerance

**Example Stocks**:
- Tech companies with compound growth
- Strong earnings trajectory
- Market tailwinds

**Action**: Core holdings for 5-10 year wealth building

### Strategy 2: Risk-Adjusted
**Focus On**: Sharpe Ratio > 1.2
- Best risk-adjusted returns
- Ignore absolute volatility
- Suitable for: Balanced portfolio, salary earners

**Example Stocks**:
- Quality blue chips
- Consistent dividend + growth
- Low-volatility performers

**Action**: Largest portfolio weight

### Strategy 3: Stability Play
**Focus On**: Low Max Drawdown (<-15%)
- Most emotionally comfortable
- Never lose >15% even in crashes
- Suitable for: Conservative, near-retirement

**Example Stocks**:
- Defensive sectors (healthcare, utilities)
- Market leaders with pricing power
- Dividend aristocrats

**Action**: Preserve capital, sleep well at night

### Strategy 4: Hidden Gem Hunting
**Focus On**: High CAGR + Low Volatility
- Rarest combination (1-2 per 20 stocks)
- Exceptional risk-adjusted returns
- Suitable for: All investors (free money)

**Example Stocks**:
- Reward Optimization Score > 85
- Beating all typical screeners
- Undervalued by market

**Action**: Maximum position sizing

---

## 📊 Dashboard Features

### Overview Tab
- **Summary Cards**: Stocks analyzed, exceptional performers, beating filters, avg Sharpe
- **Ultra-Rare Discovery**: Stocks beating ALL typical screeners
- **Risk Analysis**: Average volatility, drawdown, win rate, Sharpe across universe

### Exceptional Performers Tab
- Table of all stocks with CAGR > 20%
- Sorted by Rewards Optimization Score
- Full metrics: CAGR, volatility, Sharpe, max DD, win rate

### Screener Beating Tab
- **Breakdown**: How many stocks beat each filter
- **Rare Discovery**: Stocks beating all filters
- **Filter Comparison**: Why some beat, why others don't

### Recommendations Tab
- **Top Pick**: Highest overall score
- **Quality Outlier**: Best Sharpe ratio
- **Stability Pick**: Lowest max drawdown
- **Consistency Pick**: Highest win rate
- **Hidden Gem**: Best combo of return + stability
- **Sector Strength**: Which market/sector leading

### Detailed Metrics Tab
- Top 10 by Rewards Score
- Full metrics: CAGR, volatility, Sharpe, Sortino, max DD, win rate

---

## 🔍 Analysis Interpretation

### "INFY beats momentum screener"
```
Means: INFY has 28.5% CAGR (>25% threshold)
Action: Consider as growth core holding
Risk: Higher volatility may accompany

Check: Sharpe ratio for risk-adjustment
```

### "MSFT beats ALL screeners"
```
Means: MSFT achieves:
  ✓ CAGR > 25% (momentum)
  ✓ Volatility < 30% (value)
  ✓ Sharpe > 1.0 (quality)
  ✓ Win Rate > 55% (growth)

This is EXCEPTIONAL - very rare
Action: Strongly consider overweight
Confidence: High

Why rare: Takes exceptional execution
to achieve ALL metrics simultaneously
```

### "HDFC beats value screener only"
```
Means: HDFC has low volatility
But: Didn't beat momentum, quality, or growth filters

Interpretation: 
- Stable, defensive holding
- Good for risk management
- Limited upside potential
- Suitable for: Conservative allocation

Action: Complement with growth stocks
```

---

## 🎓 Workflow

### Step 1: Run Analysis
```bash
python rewards_optimization.py
```

### Step 2: Review Dashboard
```
file:///Users/umashankar/stock-screener/rewards_dashboard.html
```

### Step 3: Identify Categories

1. **Exceptional Performers** (CAGR >20%)
   - These are your growth core
   - Monitor closely
   - Maintain position

2. **Beating All Filters** (Ultra-rare)
   - Hidden gems
   - Undervalued by market
   - Consider overweight

3. **Quality Outliers** (Best Sharpe)
   - Risk-adjusted plays
   - Most reliable
   - Build positions

4. **Consistency Players** (High win rate)
   - Steady performers
   - Emotional comfort
   - Hold long-term

### Step 4: Build Position Map

```
Portfolio Allocation Strategy:

40% → Exceptional Performers
   (High growth, accept volatility)

30% → Quality Outliers
   (Best risk-adjusted returns)

20% → Consistency Plays
   (Steady upside, low worry)

10% → Cash/Dry Powder
   (For rebalancing opportunities)
```

### Step 5: Monitor & Rebalance

- Quarterly: Check if scores change
- Annually: Recalculate 5-year metrics
- As needed: Rebalance based on shifts

---

## ⚠️ Important Caveats

### Past Performance ≠ Future Results
- 5-year returns are historical
- Market conditions change
- Industries evolve
- Recommendation: Use as part of analysis, not sole decision

### Survivorship Bias
- Analysis only includes stocks still trading
- Delisted stocks not included
- This can overstate returns (good and bad)

### Look-Ahead Bias
- Using current data when past data should be used
- Recommendation: Rerun analysis with trailing 5-year windows

### Market Regime Changes
- 2020 crash changed volatility metrics
- Interest rate environment shifts
- Sector rotations happen
- Recommendation: Compare to benchmarks, not absolute

---

## 🚀 Next Steps

### Immediate
1. Run `python rewards_optimization.py`
2. Review top 5 exceptional performers
3. Compare against current holdings
4. Identify 1-2 new candidates to add

### This Week
1. Deep dive into beating-all-filters stocks
2. Review why they excel (fundamentals)
3. Assess fit for your portfolio
4. Consider sizing

### This Month
1. Rebalance portfolio based on scores
2. Reduce underperformers
3. Add quality outliers
4. Monitor performance

### Quarterly
1. Recalculate 5-year metrics
2. Check for shifts in rankings
3. Rebalance if needed
4. Update holdings plan

---

## 📈 Integration with Portfolio Analyzer

The Rewards Optimization works alongside Portfolio Analyzer:

**Portfolio Analyzer** → **Rewards Optimizer** → **Rebalancing Tracker**

1. **Portfolio Analyzer**: Shows current holdings health
2. **Rewards Optimizer**: Identifies what to buy (exceptional performers)
3. **Rebalancing Tracker**: Plans execution (how to rebalance)

---

## 🎯 Key Takeaways

1. **CAGR alone isn't enough** - Must consider risk (volatility, drawdown)
2. **Sharpe Ratio is key** - Tells you return per unit of risk
3. **Consistency matters** - High win rate provides emotional comfort
4. **Hidden gems exist** - Stocks beating ALL screeners are rare but real
5. **Rewards Score simplifies** - Composite metric makes comparison easier
6. **Past performance guides** - Not guarantees, but useful indicators
7. **Diversification remains** - Don't over-concentrate even in best performers

---

## 📚 Resources

- **Full Analysis**: Run `python rewards_optimization.py --report output.txt`
- **JSON Export**: `rewards_analysis.json` has full raw data
- **Dashboard**: Interactive web interface for exploration
- **API**: Integration endpoints for programmatic use

---

**Version**: 1.0.0  
**Last Updated**: 07-Jul-2026  
**Status**: 🟢 Production Ready
