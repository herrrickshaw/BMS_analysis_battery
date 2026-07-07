# Global Multi-Market Index Deployment: Gaps & Roadmap

## Executive Summary

Current deployment covers **India NSE only** with extensions to US (Nifty comparison). To scale to a truly global portfolio analysis platform, we need to address **14 major deployment gaps** across data, infrastructure, compliance, and operations.

**Gap Severity Breakdown:**
- 🔴 **HIGH priority**: 5 gaps (data, liquidity, regulation, currency, tax)
- 🟡 **MEDIUM priority**: 7 gaps (settlement, trading hours, corp actions, dividend, rebalancing, hedging, backtesting)
- 🟢 **LOW priority**: 2 gaps (political risk, edge cases)

---

## Part 1: Market Coverage Assessment

### Current State ✓

| Market | Status | Coverage | Data Quality |
|--------|--------|----------|--------------|
| 🇮🇳 India (NSE) | ✅ COMPLETE | Nifty 50/100/500 + Sectoral | Excellent (NSE official) |
| 🇺🇸 USA (S&P) | ⚠️ PARTIAL | Nifty vs Nifty 50 only | Good (yfinance) |
| 🇬🇧 UK (FTSE) | ❌ MISSING | Not covered | N/A |
| 🇪🇺 Europe (Stoxx) | ❌ MISSING | Not covered | N/A |
| 🇯🇵 Japan (TSE) | ❌ MISSING | Not covered | N/A |
| 🇰🇷 Korea (KRX) | ❌ MISSING | Not covered | N/A |
| 🇨🇳 China (SSE) | ❌ MISSING | Not covered | N/A |
| 🇭🇰 Hong Kong (HKEX) | ❌ MISSING | Not covered | N/A |

### Proposed State (18-Month Roadmap)

| Market | Target | Phase | ETA |
|--------|--------|-------|-----|
| 🇮🇳 India (NSE) | COMPLETE | Now | ✅ Live |
| 🇺🇸 USA (S&P) | Nifty50 + SP500 + SP400 | Phase 1 | Q3 2026 |
| 🇬🇧 UK (FTSE) | FTSE100 + FTSE250 | Phase 1 | Q3 2026 |
| 🇪🇺 Europe (Stoxx) | Stoxx 600 + CAC/DAX | Phase 2 | Q4 2026 |
| 🇯🇵 Japan (TSE) | Nikkei + TOPIX | Phase 2 | Q4 2026 |
| 🇰🇷 Korea (KRX) | KOSPI200 + KOSDAQ | Phase 2 | Q4 2026 |
| 🇨🇳 China (SSE) | CSI300 + SSE50 | Phase 3 | Q2 2027 |
| 🇭🇰 Hong Kong (HKEX) | Hang Seng Index | Phase 3 | Q2 2027 |

---

## Part 2: Critical Gaps (🔴 HIGH Priority)

### Gap 1: Data Coverage & Quality

**Problem:** yfinance has spotty international coverage
```
✓ US stocks: Complete (7,500+)
✓ India stocks: Good (2,368 NSE)
⚠ Europe: Partial (some delisted symbols)
❌ Japan: Limited (major stocks OK, illiquid gaps)
❌ Korea: Limited (major 50 only)
❌ China: Very poor (trading halts not captured)
```

**Impact:**
- Can't build indices for emerging markets
- Backtesting unreliable for non-US markets
- Missing 3-4 years of historical data

**Solution Stack:**

| Data Source | Markets | Latency | Cost | Implementation |
|-------------|---------|---------|------|-----------------|
| **yfinance** | US, India | 15min | Free | Current |
| **Bloomberg** | All | Real-time | $$$$$ | Phase 2 (enterprise) |
| **Reuters** | All | Real-time | $$$$$ | Phase 2 (enterprise) |
| **Local APIs** | Each market | 30sec | $-$$ | Phase 1 |
| **Alpha Vantage** | US, Europe | 1min | $$ | Phase 1 |
| **FinanceDataReader** | Korea, Japan | 1day | Free | Phase 1 |
| **Akshare** | China | 1day | Free | Phase 1 |
| **LSE API** | UK, Europe | Real-time | $$ | Phase 2 |

**Roadmap:**
- **Month 1-2**: Integrate FinanceDataReader (Asia), Akshare (China), Alpha Vantage (Europe)
- **Month 3-4**: Build local exchange scrapers (TSE, KRX, SSE)
- **Month 5-6**: Add Bloomberg terminal integration (for enterprise clients)
- **Ongoing**: Validate data against exchange sources quarterly

**Effort:** 60-80 hours | **Cost:** $0 (free APIs) → $5k+/month (Bloomberg)

---

### Gap 2: Liquidity Verification

**Problem:** Each market defines liquidity differently
```
NSE: Impact cost ≤0.50% for ₹10 Cr basket
S&P: Min $500k daily volume
FTSE: Min £500k daily turnover
TSE: No formal requirement (assumed liquid)
KRX: Min trading value (variable)
SSE: No requirement (all listed eligible)
```

**Impact:**
- Can't reliably filter eligible stocks per market
- Index may include illiquid names (can't trade)
- Rebalancing cost overestimated

**Solution:**

```python
# Liquidity check per market
class LiquidityChecker:
    def check_nse(ticker, volume, price):
        impact_cost = calculate_impact(volume, price)
        return impact_cost <= 0.50

    def check_sp500(ticker, volume):
        return volume >= 500_000  # in USD

    def check_ftse(ticker, turnover_gbp):
        return turnover_gbp >= 500_000

    def check_tse(ticker):
        # All listed assumed liquid
        return True

    def check_krx(ticker, turnover_krw):
        return turnover_krw >= min_threshold  # varies
```

**Roadmap:**
- **Month 1**: Map liquidity criteria for all 8 markets
- **Month 2**: Implement liquidity filters per market
- **Month 3**: Validate against historical constituents
- **Month 4**: Build dashboard showing which stocks qualify per market

**Effort:** 20-30 hours | **Cost:** $0

---

### Gap 3: Regulatory Compliance

**Problem:** Each market has different reporting, trading, and disclosure rules

```
🇮🇳 NSE:        SEBI Act, Stock Exchange Rules
🇺🇸 S&P:        SEC Regulations, Dodd-Frank
🇬🇧 FTSE:       FCA Rules, Listing Rules
🇪🇺 STOXX:      MiFID II, ESMA Guidelines
🇯🇵 TSE:        FSA Rules, Japan Exchange Group Rules
🇰🇷 KRX:        FSC Regulations, Korea Exchange Rules
🇨🇳 SSE:        CSRC Rules, China Exchange Rules
🇭🇰 HKEX:       SFC Rules, Hong Kong Exchange Rules
```

**Impact:**
- Can't legally operate in some markets
- Liability exposure for non-compliance
- Products may not be registerable

**Solution:**

| Compliance Aspect | Implementation | Timeline | Owner |
|------------------|-----------------|----------|-------|
| **India** | SEBI registration, AIF license | Now | Legal team |
| **US** | SEC Form 13F, institutional class | Q3 2026 | Compliance |
| **UK** | FCA authorization, COBS rules | Q4 2026 | Compliance |
| **EU** | PRIIPS KID, MiFID II | Q4 2026 | Legal |
| **Japan** | FSA registration, J-Gate approval | Q1 2027 | Legal |
| **Korea** | FSC registration, KRX listing | Q1 2027 | Compliance |
| **China** | CSRC approval, QFII quota | Q2 2027 | Government relations |
| **Hong Kong** | SFC license, Stock Exchange listing | Q2 2027 | Legal |

**Roadmap:**
- **Month 1-2**: Conduct gap analysis with external legal counsel
- **Month 3-6**: Obtain India (SEBI) and US (SEC) clearances
- **Month 7-12**: UK/EU compliance; file with local regulators
- **Month 13-18**: Emerging market registrations

**Effort:** 100+ hours | **Cost:** $50k-200k (legal fees) + regulatory filing fees

---

### Gap 4: Multi-Currency Handling

**Problem:** Portfolio returns affected by FX movements
```
Return = Stock Return + FX Impact
Example:
  Nifty 50 up 15% but INR depreciated 8%
  → USD return only 7%
```

**Impact:**
- Can't compare returns across currencies
- FX hedging costs not accounted for
- Risk metrics incomplete

**Solution:**

| Component | Current | Needed | Timeline |
|-----------|---------|--------|----------|
| **FX Rates** | None | Bloomberg + XE API | Month 1 |
| **Hedging Costs** | Not tracked | Add futures pricing | Month 2 |
| **Portfolio FX Exposure** | Mixed | Build FX calculator | Month 2 |
| **Rebalancing FX Impact** | Ignored | Model transaction costs | Month 3 |
| **Tax on FX Gains** | Not modeled | Add per-market tax rules | Month 3 |

**Code Example:**
```python
def calculate_fx_adjusted_return(stock_return, fх_return, is_hedged=False):
    """
    USD return = (1 + stock_return) * (1 + fx_return) - 1
    With hedge: FX return set to hedging cost (~0.5-1% annually)
    """
    if is_hedged:
        fx_impact = -0.007  # 70bps hedging cost
    else:
        fx_impact = fx_return
    return (1 + stock_return) * (1 + fx_impact) - 1
```

**Roadmap:**
- **Month 1**: Implement FX rate feed
- **Month 2**: Add hedging cost calculator
- **Month 3**: Build FX-adjusted portfolio dashboard
- **Month 4**: Publish FX impact analysis with portfolios

**Effort:** 30-40 hours | **Cost:** $500-1000/month (FX data)

---

### Gap 5: Tax Treatment

**Problem:** Each country/investor has different tax rules
```
India:       LTCG 20%, STCG per slab, TDS 20% on foreign dividends
US:          LTCG 15-20%, STCG ordinary income, withholding on div
UK:          CGT 20%, dividend allowance £500, withholding 20%
Japan:       Flat 20.315%, no LTCG/STCG distinction
Korea:       Progressive 6-42%, separate treatment
China:       20% on gains, 10% withholding on dividends
```

**Impact:**
- After-tax returns not comparable across markets
- Portfolio optimization doesn't account for taxes
- Rebalancing triggers ignored (tax-loss harvesting)

**Solution:**

```python
class TaxCalculator:
    def calculate_after_tax_return(gross_return, country, investor_type, holding_period):
        if country == 'India':
            if holding_period > 365:
                tax_rate = 0.20  # LTCG
            else:
                tax_rate = get_slab_rate(investor_type)
        elif country == 'US':
            if holding_period > 365:
                tax_rate = 0.15 if investor_type == 'individual' else 0.21
            else:
                tax_rate = get_ordinary_income_rate(investor_type)
        # ... more countries
        return gross_return * (1 - tax_rate)
```

**Roadmap:**
- **Month 1**: Map tax rules for all 8 markets
- **Month 2**: Implement per-investor tax calculator
- **Month 3**: Add tax-loss harvesting module
- **Month 4**: Build after-tax performance dashboard

**Effort:** 40-50 hours | **Cost:** $0

---

## Part 3: Important Gaps (🟡 MEDIUM Priority)

### Gap 6: Settlement Timing & Cash Flow
- **Issue**: NSE T+1, S&P T+2, FTSE T+2, TSE T+2, KRX T+2, SSE T+1, HKEX T+2
- **Solution**: Build settlement calendar, adjust rebalancing dates
- **Timeline**: Month 2 | **Effort**: 15-20 hours

### Gap 7: Trading Hours Coordination
- **Issue**: NYSE 9:30-16:00 EST, TSE 8:30-15:00 JST, SSE 9:30-15:00 CST (12-15 hour gaps!)
- **Solution**: Implement global trading calendar, execution strategy per market
- **Timeline**: Month 3 | **Effort**: 20-25 hours

### Gap 8: Corporate Actions Handling
- **Issue**: US: buybacks distort returns; Japan: cross-holding; China: trading halts
- **Solution**: Market-specific adjustment rules
- **Timeline**: Month 4 | **Effort**: 30-40 hours

### Gap 9: Dividend Treatment
- **Issue**: Ex-dividend dates, withholding tax, payout frequency vary
- **Solution**: Map per-market dividend calendars
- **Timeline**: Month 3 | **Effort**: 15-20 hours

### Gap 10: Index Reconstitution Coordination
- **Issue**: NSE Q1/Q2/Q3/Q4; S&P Feb/May/Aug/Nov; different months mean different impacts
- **Solution**: Unified global rebalancing calendar
- **Timeline**: Month 2 | **Effort**: 10-15 hours

### Gap 11: Hedging Instruments Availability
- **Issue**: Can't hedge all exposures (some emerging markets lack futures)
- **Solution**: Map available derivatives per market
- **Timeline**: Month 3 | **Effort**: 15-20 hours

### Gap 12: Backtesting Data Quality
- **Issue**: Some markets lack 5 years reliable history
- **Solution**: Establish minimum data requirements, warn on gaps
- **Timeline**: Month 4 | **Effort**: 20-25 hours

---

## Part 4: Implementation Roadmap

### Phase 1: Foundation (Q3 2026 - 3 Months)

**Deliverables:**
- ✅ Multi-market data pipeline (yfinance + local APIs)
- ✅ Liquidity checker for all 8 markets
- ✅ FX rate feed + hedging cost model
- ✅ Global trading calendar
- ✅ Tax calculator for major markets (India, US, UK, Japan)

**Effort:** ~200-250 hours
**Cost:** $5k-10k
**Milestone:** Can build & backtest global portfolios

### Phase 2: Compliance & Production (Q4 2026 - 3 Months)

**Deliverables:**
- ✅ SEBI + SEC + FCA compliance
- ✅ Corporate actions handlers
- ✅ Settlement calendar integration
- ✅ Dividend adjustment automation
- ✅ Production-grade data validation

**Effort:** ~150-200 hours
**Cost:** $50k-150k (legal + regulatory)
**Milestone:** Production-ready for regulated distribution

### Phase 3: Advanced Features (Q1-Q2 2027 - 6 Months)

**Deliverables:**
- ✅ China + Hong Kong support
- ✅ Derivative hedging automation
- ✅ Tax-loss harvesting engine
- ✅ Political risk assessment
- ✅ Advanced backtesting framework

**Effort:** ~200-250 hours
**Cost:** $10k-20k
**Milestone:** Full global portfolio optimization

---

## Part 5: Resource Plan

### Team Composition

| Role | Hours/Month | Duration | Cost |
|------|------------|----------|------|
| **Data Engineer** | 80 | 18 months | $200k |
| **Compliance Officer** | 40 | 6 months | $60k |
| **QA/Validator** | 60 | 12 months | $120k |
| **Product Manager** | 40 | 18 months | $150k |
| **External Legal** | 100 | 6 months | $200k |
| **External Compliance** | 60 | 6 months | $100k |

**Total Investment:** $830k | **Timeline:** 18 months | **Effort:** ~1,000 hours

---

## Part 6: Dependency Map

```
Start
  ├─ [PARALLEL] Gap 1: Data Coverage
  │   └─ Enables: All other gaps
  │   └─ Blocks: Phase 1 completion
  │
  ├─ [PARALLEL] Gap 2: Liquidity Verification
  │   └─ Enables: Index constitution
  │   └─ Blocks: Backtesting accuracy
  │
  ├─ [SEQUENTIAL] Gap 3: Regulatory Compliance
  │   └─ Prerequisite for: Gap 5 (Tax), Gap 4 (FX)
  │   └─ Blocks: Production deployment
  │
  ├─ [PARALLEL] Gap 4: Multi-Currency Handling
  │   └─ Enables: Return comparison
  │
  └─ [PARALLEL] Gap 5: Tax Treatment
      └─ Enables: After-tax optimization

                          ↓
                    Phase 1 Complete
                          ↓
            Gap 6-12: Medium Priority Gaps
                          ↓
                    Phase 2 Complete
                          ↓
             Emerging Markets (China, HK)
                          ↓
                    Phase 3 Complete
```

---

## Part 7: Success Metrics

### Phase 1 Success
- ✅ Can pull data for all 8 markets
- ✅ Backtest 5-year portfolio returns (±0.5% accuracy)
- ✅ Compare after-tax returns across markets
- ✅ Build indices per NSE/S&P/FTSE/etc methodology

### Phase 2 Success
- ✅ Zero compliance violations
- ✅ Regulatory approvals in India + US
- ✅ Zero manual data adjustments (automated)
- ✅ Production dashboard live

### Phase 3 Success
- ✅ Global retail distribution available
- ✅ Tax-efficient rebalancing running
- ✅ AUM > $100M in global portfolios
- ✅ Outperformance > 5pp vs benchmarks

---

## Part 8: Risk Assessment

### Technical Risks
| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Data feed disruption | Medium | High | Redundant data sources |
| FX calculation error | Low | High | Rigorous testing, external audit |
| Settlement mismatch | Low | Medium | Conservative rebalancing buffers |
| Backtesting errors | Medium | High | 3rd-party validation |

### Operational Risks
| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Regulatory rejection | Low | Critical | Early engagement, expert counsel |
| Compliance violation | Low | Critical | Dedicated compliance team |
| Market disruption (China) | Medium | Medium | Geopolitical monitoring |
| Tax law change | Low | Medium | Quarterly tax reviews |

### Market Risks
| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Index delisting | Low | High | Automatic reconstitution |
| Corporate action shock | Medium | Medium | Event-based handlers |
| Currency crisis | Low | Medium | Hedging options |
| Liquidity dry-up | Low | High | Diversification, liquidity buffers |

---

## Conclusion

**Current State:** India-only, comparison to US Nifty

**18-Month Plan:** Full global coverage (8 markets, 50+ indices)

**Investment Required:** $830k team + $50-100k annual software/data

**Revenue Potential:** $2-5M annually (AUM × 0.5-1% fee)

**ROI Timeline:** 12-18 months to breakeven

**Strategic Value:** Enables global portfolio optimization, differentiates from competitors, positions for institutional distribution
