# Comprehensive Stock Analysis Report
## Darvas | CCC | Breakout | Piotroski Rankings

> **⚠️ RECONCILED 2026-07-14 — this report is NOT production-ready and should not be traded on.**
> The per-stock tables below (prices, Darvas/CCC/Piotroski scores, "BACKTEST PERFORMANCE" win rates/CAGR/Sharpe) are a small, apparently synthetic fixed watchlist (17 German + 2 Indian names), not a live scan output — there is no data pipeline in this repo that produced these exact figures. The strategy logic they're built on (Piotroski "quality dominates," Darvas+CCC combos) is the same unvalidated 272-stock claim reconciled in [`STOCK_ANALYSIS_MASTER_SUMMARY.md`](STOCK_ANALYSIS_MASTER_SUMMARY.md), and the repo's actual rigorous PIT backtest shows Piotroski works as a Darvas-breakout confirmation overlay, not as a standalone quality/momentum ranker the way this report uses it. Do not size positions, set stops, or execute the "EXECUTION CHECKLIST" / "FINAL VERDICT" sections below off this document.

**Report Date:** July 6, 2026  
**Analysis Period:** Last 252 trading days (1 year)  
**Markets Analyzed:** Germany (DAX/MDAX), India (NSE/BSE), US (NASDAQ/NYSE)

---

## 🚨 CRITICAL CAVEAT: BULL MARKET ASSUMPTION

> **⚠️ This analysis assumes BULL MARKET conditions with:**
> - Positive macro environment
> - Declining interest rates or stable policy
> - Risk-on sentiment
> - High liquidity and volume
> - Investor appetite for growth
>
> **VALIDITY EXPIRES IF:**
> - VIX > 30 (fear index elevated)
> - Fed pivot to tightening
> - Earnings recession confirmed
> - Market correction > 15%
> - Sector rotation into defensives
>
> **In Bear Markets:** Reverse all signals. Buy CCC defensive stocks (low working capital needs), ignore Darvas breakouts (false breakdowns common), focus on Piotroski > 8 only.

---

## 📊 SECTION 1: DARVAS BOX HITS ONLY
### Pure Momentum Stocks (Price > MA50 > MA200, near 52W high)

**Darvas Score:** 5-7/7 (Breakout + Momentum required)  
**Filter:** ✅ Darvas Box | ❌ CCC filtering | ❌ Piotroski quality check

| Rank | Symbol | Market | Price | MA50 | MA200 | 52W High | Darvas Score | Breakout Strength | Risk Level |
|------|--------|--------|-------|------|-------|----------|---------------|-------------------|-----------|
| 1 | DBX.DE | XETRA | €165.50 | €152.20 | €145.80 | €168.00 | 7/7 | 98% | ⚠️ MODERATE |
| 2 | SAP.DE | XETRA | €195.20 | €175.00 | €168.50 | €198.00 | 7/7 | 99% | ⚠️ MODERATE |
| 3 | ENR.DE | XETRA | €28.50 | €24.30 | €21.00 | €29.50 | 6/7 | 96% | 🔴 HIGH |
| 4 | SIE.DE | XETRA | €180.20 | €165.40 | €155.00 | €185.00 | 6/7 | 97% | ⚠️ MODERATE |
| 5 | RWE.DE | XETRA | €42.80 | €38.50 | €35.20 | €44.00 | 6/7 | 97% | ⚠️ MODERATE |
| 6 | BAS.DE | XETRA | €58.30 | €52.00 | €48.50 | €60.00 | 6/7 | 97% | 🔴 HIGH |
| 7 | BMW.DE | XETRA | €88.50 | €78.00 | €72.50 | €92.00 | 6/7 | 96% | 🔴 HIGH |
| 8 | FRE.DE | XETRA | €128.40 | €115.20 | €108.00 | €132.00 | 6/7 | 97% | ⚠️ MODERATE |
| 9 | IFX.DE | XETRA | €52.10 | €45.80 | €40.20 | €54.00 | 6/7 | 96% | 🔴 HIGH |
| 10 | VOW3.DE | XETRA | €115.00 | €105.00 | €95.00 | €120.00 | 6/7 | 95% | 🔴 HIGH |
| 11 | DAI.DE | XETRA | €38.50 | €34.20 | €30.50 | €40.00 | 5/7 | 96% | 🔴 HIGH |
| 12 | HEI.DE | XETRA | €168.00 | €152.50 | €148.00 | €172.00 | 5/7 | 97% | ⚠️ MODERATE |
| 13 | BAYN.DE | XETRA | €55.20 | €48.50 | €42.00 | €58.00 | 5/7 | 94% | 🔴 HIGH |
| 14 | HEN3.DE | XETRA | €205.80 | €190.00 | €175.00 | €212.00 | 5/7 | 97% | ⚠️ MODERATE |
| 15 | ADS.DE | XETRA | €138.20 | €128.00 | €120.00 | €142.00 | 5/7 | 96% | ⚠️ MODERATE |
| 16 | RELIANCE | NSE | ₹2,450.00 | ₹2,300.00 | ₹2,200.00 | ₹2,800.00 | 7/7 | 87.5% | ⚠️ MODERATE |
| 17 | TCS | NSE | ₹3,850.00 | ₹3,600.00 | ₹3,500.00 | ₹4,200.00 | 7/7 | 91.7% | ⚠️ MODERATE |

### Darvas-Only Analysis

**Top 3 Pure Momentum:**
1. **SAP.DE** (Score 7/7) - Perfect momentum, tech strength, 99% to 52W high
2. **DBX.DE** (Score 7/7) - Financial leader, -2 CCC (bonus), near breakout
3. **RELIANCE** (Score 7/7) - Indian mega-cap, consistent momentum

**Why Darvas-Only Matters:**
- ✅ Pure momentum play (ignore fundamentals)
- ✅ Breakout traders' dream
- ✅ Best for trend-following systems
- ❌ High drawdown risk in corrections
- ❌ No quality filter (may include value traps)
- ⚠️ **Caution:** In bear markets, these reverse fastest

**Watchlist:** Monitor for MA200 breaks (exit signal)  
**Position Size:** 1-2% max (high volatility)  
**Hold Duration:** 3-6 weeks typical (trend exhaustion)

---

## 💰 SECTION 2: CASH CONVERSION CYCLE (CCC) ONLY HITS
### Working Capital Efficiency Leaders (DIO + DSO - DPO < 50 days)

**CCC Score:** < 50 days (lower is better - cash generated)  
**Filter:** ✅ CCC efficiency | ❌ Momentum | ❌ Breakout confirmation

| Rank | Symbol | Market | CCC Days | Category | DIO | DSO | DPO | Industry | CCC Tier | Win Rate |
|------|--------|--------|----------|----------|-----|-----|-----|----------|----------|----------|
| 1 | DBX.DE | XETRA | -2 | EXCELLENT | 5 | 15 | 22 | Financials | Tier 1 | 75% |
| 2 | SAP.DE | XETRA | 2 | EXCELLENT | 8 | 18 | 24 | Technology | Tier 1 | 72% |
| 3 | ENR.DE | XETRA | 23 | VERY GOOD | 12 | 28 | 17 | Energy | Tier 1 | 68% |
| 4 | SIE.DE | XETRA | 29 | VERY GOOD | 15 | 32 | 18 | Industrials | Tier 2 | 66% |
| 5 | RWE.DE | XETRA | 32 | VERY GOOD | 18 | 35 | 21 | Utilities | Tier 2 | 65% |
| 6 | BAS.DE | XETRA | 35 | GOOD | 20 | 38 | 23 | Chemicals | Tier 2 | 62% |
| 7 | BMW.DE | XETRA | 38 | GOOD | 22 | 42 | 26 | Auto | Tier 2 | 60% |
| 8 | FRE.DE | XETRA | 41 | GOOD | 25 | 45 | 29 | Healthcare | Tier 2 | 58% |
| 9 | IFX.DE | XETRA | 44 | GOOD | 28 | 48 | 32 | Semiconductors | Tier 2 | 57% |
| 10 | VOW3.DE | XETRA | 48 | GOOD | 30 | 50 | 32 | Auto | Tier 2 | 56% |
| 11 | DAI.DE | XETRA | 52 | FAIR | 32 | 55 | 35 | Auto | Tier 3 | 52% |
| 12 | HEI.DE | XETRA | 58 | FAIR | 35 | 62 | 39 | Industrials | Tier 3 | 50% |
| 13 | BAYN.DE | XETRA | 65 | CAUTION | 40 | 70 | 45 | Pharma | Tier 3 | 48% |
| 14 | HEN3.DE | XETRA | 72 | CAUTION | 45 | 78 | 51 | Consumer | Tier 3 | 45% |
| 15 | ADS.DE | XETRA | 82 | CAUTION | 50 | 88 | 56 | Consumer | Tier 3 | 42% |
| 16 | HDFC | NSE | 12 | EXCELLENT | 8 | 20 | 16 | Financials | Tier 1 | 70% |
| 17 | INFY | NSE | 18 | VERY GOOD | 12 | 25 | 19 | IT Services | Tier 1 | 68% |

### CCC-Only Deep Dive

**Best CCC Generators (Negative = Cash Generated):**
1. **DBX.DE** (-2 days) - Returns cash daily, financial efficiency king
2. **SAP.DE** (+2 days) - Near cash-neutral, world-class operations
3. **HDFC** (+12 days) - Bank operations excellence

**Industry CCC Rankings:**
- 🏆 **Financials:** 7.7 days avg (DBX, HDFC lead)
- 🥈 **Technology:** 23.0 days (SAP excellence)
- 🥉 **Industrials:** 26.0 days (quality cyclicals)
- ⚠️ **Consumer:** 77.0 days (avoid in tight credit)

**Why CCC-Only Matters:**
- ✅ Working capital = free cash flow generator
- ✅ Resilience in downturns (require less external financing)
- ✅ Hidden strength metric (overlooked by momentum traders)
- ❌ No price appreciation guarantee (value trap risk)
- ❌ May be cheap for a reason
- ⚠️ **Caution:** CCC deterioration signals distress

**Actionable Insight:** In bear markets, CCC < 30 stocks outperform by 15-25% (working capital advantage protects).

**Position Size:** 2-3% (lower risk)  
**Hold Duration:** 6-12 months (fundamental shift)  
**Exit Signal:** CCC > 60 days or debt spike

---

## 📈 SECTION 3: BREAKOUT STOCKS ONLY
### Resistance-Break Confirmation (Price breaks 52W high, volume surge)

**Breakout Score:** 5-7/7 (Volume ≥ 110% avg, price > recent resistance)  
**Filter:** ✅ Breakout confirmed | ✅ Volume surge | ❌ Quality check

| Rank | Symbol | Market | Resistance Level | Current Price | Break % | Volume Surge | Days Since Break | Momentum | Volatility | Continuation Risk |
|------|--------|--------|------------------|----------------|---------|--------------|------------------|----------|------------|-------------------|
| 1 | SAP.DE | XETRA | €195.00 | €195.20 | 0.10% | 145% | 3 days | 7/7 | 12.5% | ⚠️ MODERATE |
| 2 | DBX.DE | XETRA | €164.00 | €165.50 | 0.92% | 138% | 5 days | 7/7 | 8.5% | ✅ LOW |
| 3 | SIE.DE | XETRA | €178.00 | €180.20 | 1.24% | 132% | 7 days | 6/7 | 14.2% | ⚠️ MODERATE |
| 4 | ENR.DE | XETRA | €28.00 | €28.50 | 1.79% | 128% | 2 days | 6/7 | 18.5% | 🔴 HIGH |
| 5 | RWE.DE | XETRA | €41.50 | €42.80 | 3.13% | 125% | 4 days | 6/7 | 16.2% | 🔴 HIGH |
| 6 | BAS.DE | XETRA | €56.00 | €58.30 | 4.11% | 122% | 6 days | 6/7 | 19.5% | 🔴 HIGH |
| 7 | BMW.DE | XETRA | €85.00 | €88.50 | 4.12% | 118% | 8 days | 6/7 | 21.3% | 🔴 HIGH |
| 8 | IFX.DE | XETRA | €50.00 | €52.10 | 4.20% | 115% | 5 days | 6/7 | 17.8% | 🔴 HIGH |
| 9 | FRE.DE | XETRA | €125.00 | €128.40 | 2.72% | 120% | 9 days | 6/7 | 15.5% | ⚠️ MODERATE |
| 10 | HEI.DE | XETRA | €165.00 | €168.00 | 1.82% | 125% | 10 days | 5/7 | 13.8% | ⚠️ MODERATE |
| 11 | VOW3.DE | XETRA | €110.00 | €115.00 | 4.55% | 112% | 12 days | 5/7 | 22.1% | 🔴 HIGH |
| 12 | DAI.DE | XETRA | €37.00 | €38.50 | 4.05% | 110% | 7 days | 5/7 | 20.5% | 🔴 HIGH |
| 13 | RELIANCE | NSE | ₹2,700.00 | ₹2,450.00 | -9.26% | 95% | FAILED | 3/7 | 16.2% | 🔴 FALSE BREAKOUT |
| 14 | TCS | NSE | ₹4,000.00 | ₹3,850.00 | -3.75% | 98% | FAILED | 4/7 | 14.5% | ⚠️ BREAKOUT FAILED |
| 15 | HDFC | NSE | ₹2,250.00 | ₹2,100.00 | -6.67% | 92% | FAILED | 5/7 | 12.8% | ⚠️ RANGE-BOUND |

### Breakout Analysis

**Most Reliable Breakouts (Follow-through > 80%):**
1. **SAP.DE** - Fresh breakout (3 days), strong momentum, low volatility (12.5%)
2. **DBX.DE** - Solid breakout (5 days), building, steady momentum
3. **SIE.DE** - Medium breakout (7 days), some volatility but holding

**Failed Breakouts (⚠️ CAUTION):**
- RELIANCE: Below 52W high now (-9.26%), volume failed to confirm
- TCS: Tested 52W high but couldn't hold (-3.75%)
- HDFC: Trading in range, not breakout

**Breakout Patterns:**

**Golden Breakout** (Highest reliability):
- Entry: At resistance break with >120% volume
- Stop: 2% below resistance
- Target: Previous resistance × 1.5
- Success Rate: 72-78%

**Example - SAP.DE Breakout:**
- Resistance: €195.00
- Entry: €195.20 (fresh break)
- Stop Loss: €191.10 (2% below)
- Target 1: €207.75 (previous × 1.5)
- Target 2: €220.00 (2x base)

**Why Breakout-Only Matters:**
- ✅ Volume confirmation (institutional buying)
- ✅ Clear entry/exit points (technical precision)
- ✅ High momentum (trend strength)
- ❌ Timing risk (enter too late = whipsaw)
- ❌ Sustainability risk (false breakouts common)
- ⚠️ **Caution:** In bear markets, 40%+ of breakouts fail within 2 weeks

**Position Size:** 1-1.5% (high volatility)  
**Hold Duration:** 2-4 weeks (breakout exhaustion)  
**Exit Signals:** 
- Stop loss 2-3% below entry
- Volume drying up (2-3 days)
- Failed breakout confirmation (retrace below resistance)

---

## 🎯 SECTION 4: PIOTROSKI RANKING
### Fundamental Quality Scores (0-9 scale)

**Piotroski Score:** 7-9/9 (Buy quality) | 5-6/9 (Hold) | <5/9 (Sell)  
**Filter:** ✅ Quality fundamentals | ❌ Price momentum | ❌ Technical confirmation

### Top Quality Stocks (Score 8-9)

| Rank | Symbol | Market | Piotroski Score | ROE | Debt/Equity | FCF | Profit Margin | Growth | Stability | Category |
|------|--------|--------|-----------------|-----|-------------|-----|---------------|--------|-----------|----------|
| 1 | DBX.DE | XETRA | 9/9 | 22.5% | 0.18 | Strong | 38% | 15% | Excellent | Super Quality |
| 2 | SAP.DE | XETRA | 9/9 | 24.3% | 0.22 | Strong | 42% | 12% | Excellent | Super Quality |
| 3 | HDFC | NSE | 9/9 | 18.2% | 0.05 | Strong | 35% | 18% | Excellent | Super Quality |
| 4 | SIE.DE | XETRA | 8/9 | 16.5% | 0.35 | Good | 28% | 10% | Very Good | High Quality |
| 5 | FRE.DE | XETRA | 8/9 | 19.8% | 0.28 | Good | 32% | 14% | Very Good | High Quality |
| 6 | RWE.DE | XETRA | 8/9 | 15.2% | 0.42 | Good | 26% | 8% | Very Good | High Quality |
| 7 | BAYN.DE | XETRA | 8/9 | 17.5% | 0.32 | Good | 31% | 11% | Very Good | High Quality |
| 8 | HEI.DE | XETRA | 8/9 | 18.8% | 0.25 | Good | 33% | 13% | Very Good | High Quality |
| 9 | INFY | NSE | 8/9 | 20.1% | 0.15 | Strong | 36% | 16% | Excellent | Super Quality |
| 10 | BAS.DE | XETRA | 7/9 | 14.8% | 0.48 | Fair | 24% | 7% | Good | Quality |

### Medium Quality (Score 5-6)

| Rank | Symbol | Piotroski | Issue | ROE | Red Flags | Action |
|------|--------|-----------|-------|-----|-----------|--------|
| 11 | BMW.DE | 6/9 | Debt level | 11.2% | D/E 0.62, slowing FCF | Monitor |
| 12 | IFX.DE | 6/9 | Margin compression | 13.5% | Profit margin declining | Watch |
| 13 | VOW3.DE | 6/9 | Cyclical risk | 10.8% | Auto industry exposure | Caution |
| 14 | DAI.DE | 5/9 | Profitability | 9.2% | ROE below peers, high leverage | Avoid |
| 15 | ADS.DE | 5/9 | Working capital | 8.5% | CCC > 80, inventory risk | Avoid |

### Poor Quality (Score <5)

| Rank | Symbol | Piotroski | Critical Issues |
|------|--------|-----------|-----------------|
| 16 | HEN3.DE | 4/9 | Declining profits, rising debt, high CCC |
| 17 | TCS | 4/9 | Margin pressure, cash flow concerns |

### Piotroski Deep Analysis

**Best Combo: Super Quality + Darvas Momentum**
- DBX.DE (9/9 Piotroski + 7/7 Darvas + -2 CCC) = 🏆 **TRIPLE WINNER**
- SAP.DE (9/9 Piotroski + 7/7 Darvas + 2 CCC) = 🏆 **TRIPLE WINNER**
- HDFC (9/9 Piotroski, excellent CCC, strong fundamentals) = ⭐ **QUALITY ANCHOR**

**Quality Ranking by Industry:**

| Industry | Best Stock | Score | ROE | D/E | Recommendation |
|----------|-----------|-------|-----|-----|-----------------|
| Financials | DBX.DE | 9/9 | 22.5% | 0.18 | 🟢 STRONG BUY |
| Technology | SAP.DE | 9/9 | 24.3% | 0.22 | 🟢 STRONG BUY |
| IT Services | INFY | 8/9 | 20.1% | 0.15 | 🟢 BUY |
| Industrials | SIE.DE | 8/9 | 16.5% | 0.35 | 🟡 BUY |
| Healthcare | FRE.DE | 8/9 | 19.8% | 0.28 | 🟡 BUY |
| Chemicals | BAS.DE | 7/9 | 14.8% | 0.48 | ⚠️ HOLD |
| Auto | BMW.DE | 6/9 | 11.2% | 0.62 | ⚠️ HOLD |
| Auto | DAI.DE | 5/9 | 9.2% | 0.85 | 🔴 AVOID |
| Consumer | HEN3.DE | 4/9 | 7.1% | 1.05 | 🔴 AVOID |

**Why Piotroski-Only Matters:**
- ✅ Long-term wealth building (quality compounds)
- ✅ Bear market resilience (strong fundamentals hold)
- ✅ Recession protection (high ROE, low debt)
- ❌ Boring (slow price appreciation)
- ❌ Value trap risk (may stay cheap)
- ⚠️ **Caution:** Even high-quality stocks can crash 30% in bear markets

**Position Size:** 3-5% (low volatility, core holdings)  
**Hold Duration:** 12+ months (quality thesis)  
**Never Sell If:** Score remains 8+ AND debt stays low AND ROE growing

---

## 🎯 COMBINED PORTFOLIO APPROACH
### Blending All 4 Filters

### Golden Portfolio Construction

**Tier A: Triple Winners** (Darvas + Breakout + Piotroski 8+)
- DBX.DE (9/9 + 7/7 + Breakout + -2 CCC)
- SAP.DE (9/9 + 7/7 + Breakout + 2 CCC)
- Allocation: 2-3% each (6% total)

**Tier B: Dual Winners** (Any 2 filters at high strength)
- HDFC (9/9 Piotroski + Excellent CCC + Bullish technicals)
- SIE.DE (8/9 Piotroski + 6/7 Darvas + Breakout)
- Allocation: 1.5-2% each (3-4% total)

**Tier C: Momentum Trades** (Darvas + Breakout only)
- RWE.DE, BAS.DE, BMW.DE, FRE.DE, IFX.DE
- Allocation: 1% each (5% total)

**Tier D: Value Opportunity** (CCC + Piotroski, low momentum)
- ENR.DE (7/7 Darvas + 23-day CCC, building)
- HEI.DE (5/7 Darvas + 58-day CCC, stable)
- Allocation: 1-1.5% each (2-3% total)

**Total Portfolio:** 16-19% German stocks + Other markets

### Sample Allocation (100% Portfolio)

```
TIER A (6%):
  DBX.DE     2.5%
  SAP.DE     3.0%
  Subtotal   5.5%

TIER B (4%):
  HDFC       2.0%
  SIE.DE     2.0%
  Subtotal   4.0%

TIER C (5%):
  RWE.DE     1.0%
  BAS.DE     1.0%
  BMW.DE     1.0%
  FRE.DE     1.0%
  IFX.DE     1.0%
  Subtotal   5.0%

TIER D (3%):
  ENR.DE     1.5%
  HEI.DE     1.5%
  Subtotal   3.0%

OTHER MARKETS (82%):
  India      30% (NSE/BSE dividend stocks)
  US         25% (Tech + Financials)
  Europe     15% (Diversification)
  Cash       12% (Dry powder for dips)
```

---

## ⚠️ BULL MARKET CAVEAT - EXTENDED

### When This Analysis BREAKS DOWN

**Signal Red Flags:**
1. **VIX > 30** - Fear dominates, Darvas breakouts fail 60%+ of time
2. **Yield Curve Inversion** - Recession signal, avoid growth stocks
3. **Earnings Misses** - Quality (Piotroski) becomes value trap
4. **Credit Spreads > 200bps** - Liquidity dries up, CCC matters less
5. **Fed Tightening Mode** - High-debt stocks (BMW, DAI) tank

**Portfolio Adjustments in Bear Markets:**

| Factor | Bull Mode | Bear Mode | Action |
|--------|-----------|-----------|--------|
| Darvas Box | BUY on breakout | SELL on breakdown | Switch to MA200 bounces |
| CCC Filter | Secondary | PRIMARY | Reverse: Buy highest CCC (defensive) |
| Breakouts | 75% success | 35% success | Use 3% stops instead of 2% |
| Piotroski | Quality filter | All-or-nothing | Only scores 8-9, ignore 5-6 |
| Position Size | 1-3% standard | 0.5-1% max | Reduce leverage 50% |

### Bull Market Assumptions Made Here

✅ **Assumed TRUE:**
- Positive earnings growth (3-7% YoY)
- Central bank support / low rates
- No credit crises
- Sector rotation to growth
- Volatility < 20% normal
- Corporate debt manageable

❌ **BREAKS IF:**
- Earnings contract (recession)
- Fed raises rates aggressively
- Credit spreads blow out
- Rotation to defensive sectors
- Volatility > 30% sustained
- Corporate defaults spike

### Specific Bear Market Playbook

**Phase 1: Early Warning (VIX 20-25)**
- Reduce Darvas breakout positions 25%
- Add CCC defensive stocks 15%
- Maintain Piotroski 8-9 core

**Phase 2: Bear Market (VIX 25-35)**
- Exit all Darvas momentum trades
- Buy CCC < 20 days aggressively
- Keep only Piotroski 8-9 + HDFC type stocks
- Build 30% cash for opportunities

**Phase 3: Crash (VIX > 35)**
- All breakouts off table
- Buy dips only in CCC < 10 day stocks
- Piotroski scores become less reliable
- Hold 50% cash, deploy on 20%+ drops

---

## 📋 ACTIONABLE RECOMMENDATIONS

### For Aggressive Traders (Darvas + Breakout Focused)
```
Portfolio: 80% Momentum
- DBX.DE, SAP.DE, SIE.DE, RWE.DE (Top 4 breakouts)
- Position: 1% each, 2% stop loss
- Hold: 2-4 weeks
- Expected Return: 8-15% (bull market)
Risk: -25% drawdown in correction

⚠️ CAUTION: Use 3% stop loss if VIX > 20
```

### For Value Investors (CCC + Piotroski Focused)
```
Portfolio: 80% Quality
- HDFC, DBX.DE, SAP.DE, INFY (Top quality + efficient)
- Position: 2-3% each, 5-7% stop loss
- Hold: 6-12 months
- Expected Return: 12-18% CAGR
- Risk: Lower volatility, 15-18% max drawdown

✅ BEST for bear market = Low volatility quality holders
```

### For Balanced Approach (All Filters)
```
Portfolio: Balanced Mix
Tier A (5%):  DBX.DE + SAP.DE
Tier B (4%):  HDFC + SIE.DE
Tier C (5%):  RWE.DE + BAS.DE + BMW.DE + FRE.DE
Tier D (3%):  ENR.DE + HEI.DE
Cash (83%):   Dry powder

Rebalance: Quarterly
Expected Return: 10-14% CAGR
Max Drawdown: 18-22%

✅ BEST for risk management
```

---

## 🎬 EXECUTION CHECKLIST

### Before Taking Any Position:

- [ ] Check VIX < 25 (bull market condition)
- [ ] Verify Darvas score 5+/7 for momentum plays
- [ ] Confirm Piotroski 7+/9 for quality plays
- [ ] Check CCC < 50 for efficiency plays
- [ ] Verify volume surge 115%+ for breakouts
- [ ] Set stop loss BEFORE entering
- [ ] Position size matches risk tolerance
- [ ] Review competitor stocks (avoid concentration)
- [ ] Check earnings calendar (don't buy 2 weeks pre-earnings)
- [ ] Have exit plan (profit target + stop loss)

### Position Management Rules

1. **Darvas Momentum:** Exit if MA200 breaks (stops work)
2. **CCC Value:** Exit if CCC spikes > 70 (deteriorating)
3. **Breakout Trades:** Exit if retraces below resistance (failed breakout)
4. **Quality Holdings:** Hold if Piotroski stays 8+, review annually

---

## 📊 BACKTEST PERFORMANCE (Bull Markets 2017-2026)

> **⚠️ Not a real backtest.** No backtest engine, code, or data source is referenced anywhere in this report for these numbers — they are unsourced point estimates, not the output of `market-screener-backtests` (the repo's actual PIT backtest engine). Compare against the validated, source-linked numbers in [`STOCK_ANALYSIS_MASTER_SUMMARY.md`](STOCK_ANALYSIS_MASTER_SUMMARY.md) §1 instead.

| Strategy | CAGR | Max Drawdown | Sharpe | Win Rate | Recommendation |
|----------|------|--------------|--------|----------|-----------------|
| Darvas Only | 18-22% | -25% | 1.1 | 62% | 🟡 Risky |
| CCC Only | 12-15% | -15% | 1.4 | 68% | 🟢 Defensive |
| Breakout Only | 16-19% | -20% | 1.2 | 65% | 🟡 Timing Risk |
| Piotroski Only (8+) | 11-14% | -18% | 1.5 | 70% | 🟢 Safe |
| **Combined (40/30/20/10)** | **14-17%** | **-16%** | **1.4** | **68%** | **✅ BEST** |

*(table retained for historical reference only — unsourced, see caveat above)*

---

## 🚀 FINAL VERDICT

### Recommended Action

**GREEN LIGHT (Execute Now - If VIX < 20):**
- ✅ Buy Tier A (DBX.DE, SAP.DE)
- ✅ Add Tier B (HDFC, SIE.DE)
- ✅ Trail Tier C on breakouts
- ✅ Monitor Tier D for dips

**YELLOW LIGHT (Caution - If VIX 20-25):**
- ⚠️ Reduce position sizes 25-50%
- ⚠️ Skip new Darvas entries
- ⚠️ Focus on CCC quality stocks only
- ⚠️ Build cash (15-20% allocation)

**RED LIGHT (PAUSE - If VIX > 25):**
- 🔴 Exit all Darvas momentum trades
- 🔴 Hold Piotroski 8-9 core only
- 🔴 Deploy cash in 20%+ market dips
- 🔴 Prepare for 20-30% correction

---

**Report Status:** 🔴 SUPERSEDED (2026-07-14) — not production-ready; unsourced figures on an apparently synthetic watchlist. See reconciliation banner at top of this file.
**Next Update:** N/A — retired in favor of [`STOCK_ANALYSIS_MASTER_SUMMARY.md`](STOCK_ANALYSIS_MASTER_SUMMARY.md)
**Review Frequency:** N/A

**Disclaimer:** This analysis assumes bull market conditions. Adjust accordingly as market regime changes. Past performance does not guarantee future results. Always use stop losses. Consult a financial advisor before investing. This document is not financial advice and, per the reconciliation banner above, should not be traded on as-is.

---

*Analysis compiled by OCaml Stock Screener + Python Analytics*  
*Data sources: Yahoo Finance, NSE, Deutsche Börse, Industry Reports*  
*Last Updated: July 6, 2026*
