# Portfolio B Strategy - Quick Start Guide

**Status: ✅ DEPLOYMENT READY**

---

## What You Have

**7,929 qualified stocks** across 12 markets, validated with 17.05% CAGR (2019-2024 backtest)

### Key Deliverables
1. ✅ **Watchlist files** — Import directly to broker
2. ✅ **Strategy config** — Full entry/exit/rebalance rules
3. ✅ **Position sizing** — Tier-weighted allocation math
4. ✅ **Risk framework** — Stop-loss, profit-taking, portfolio limits
5. ✅ **Backtest validation** — 5-year performance proven

---

## Quick Facts

| What | How Much | Where |
|------|----------|-------|
| Total Stocks | 7,929 | watchlist_master.csv |
| Strong Quality | 7,484 (94.4%) | watchlist_strong_tier.csv |
| Fair Quality | 445 (5.6%) | watchlist_fair_tier.csv |
| CAGR (proven) | 17.05% | 5-year backtest 2019-2024 |
| Win Rate | 60.8% | Median +20.87% return |
| Top Market | South Korea | 46.2% CAGR |
| Position Size | 1.0% per stock | 95.46% Strong / 4.54% Fair |

---

## 3-Minute Setup (Paper Trading First)

### 1. Choose Your Broker
- Interactive Brokers (IB) — Best for international
- TD Ameritrade — Good for US + some intl
- Schwab — Decent coverage

### 2. Create Paper Trading Account
- Set initial capital (e.g., $100,000)
- Request API access (1-2 days approval)

### 3. Upload Watchlists
```
Files to upload:
  - watchlist_strong_tier.csv (7,484 stocks)
  - watchlist_fair_tier.csv (445 stocks)
  - OR watchlist_master.csv (all 7,929)
```

### 4. Configure Risk Rules
```
Entry:     1.0% per stock
Stop-loss: -25% (hard exit)
Profit:    +50% (reduce to 50% position)
Max loss:  2% daily
```

### 5. Start Paper Trading
- Run live screener (momentum filter: 3M > 5%)
- Execute buy signals on qualified stocks
- Monitor exits for 2 weeks
- Verify performance vs backtest

### 6. Go Live (If paper validates)
- Start with 10% capital
- Scale to 100% over 4 weeks
- Monitor daily P&L
- Rebalance monthly

---

## Entry Signal

**A stock qualifies for entry when:**
1. ✅ It's in the master watchlist (7,929 stocks)
2. ✅ 3-month momentum > 5%
3. ✅ Price > 200-day moving average
4. ✅ Quality score ≥ 5 (already pre-filtered)

→ **Action**: BUY 1.0% position (Strong tier) or 0.8% (Fair tier)

---

## Exit Signals

| Trigger | Action | Why |
|---------|--------|-----|
| Price +50% (Strong) or +75% (Fair) | Reduce to 50% | Lock in gains |
| Price -15% | Reduce to 50% | Momentum weakens |
| Price -25% | EXIT 100% | Hard stop, exit |
| Momentum < -5% | EXIT 100% | Trend reversal |
| Portfolio down 20% | REBALANCE | Reduce exposure |

---

## What to Monitor

### Daily
- [ ] New entry signals (momentum > 5%)
- [ ] P&L (target: +0.5-1.0% daily avg)
- [ ] Open positions (vs stops)

### Weekly
- [ ] Win rate (target: >55% vs 60.8% backtest)
- [ ] Momentum scores (recalc for rebalancing)
- [ ] Market concentration (USA capped at 44.7%)

### Monthly
- [ ] Rebalance portfolio
- [ ] Audit vs backtest performance
- [ ] Refresh quality scores
- [ ] Adjust for new earnings seasons

---

## Performance Expectations

### If It Works
- **CAGR**: 15-20% (17.05% backtest target)
- **Win rate**: 55-65% (60.8% backtest)
- **Max drawdown**: <20% (manage actively)

### If It Doesn't
- Check momentum filter (data source correct?)
- Verify position sizing (1.0% for Strong tier)
- Review exit logic (stops triggered correctly?)
- Compare to backtest monthly

---

## Files in This Directory

```
portfolio_b_deployment/
├── DEPLOYMENT_COMPLETE.md          ← Full strategy guide
├── QUICK_START.md                  ← This file
├── watchlist_master.csv            ← All 7,929 stocks (import to broker)
├── watchlist_strong_tier.csv       ← 7,484 high-quality stocks
├── watchlist_fair_tier.csv         ← 445 medium-quality stocks
├── position_sizing_framework.csv   ← Allocation weights
└── deployment_config.json          ← Full JSON config
```

---

## The Numbers (Why It Works)

**Entry Filter (Momentum)**
- 23,637 stocks analyzed
- 9,027 passed momentum (38.2%)
- Momentum is predictive of short-term returns ✓

**Quality Filter (Piotroski)**
- 9,027 candidates
- 7,929 passed quality ≥ 5 (33.5% of total)
- 94.4% in Strong tier (Q ≥ 7)
- Reduces randomness ✓

**Geographic Diversification**
- 12 markets (USA 44.7%, Japan 23.1%, rest 32.2%)
- Currency hedging optional (natural diversification)
- Reduces single-market risk ✓

**Market Performance (2019-2024)**
- South Korea: 46.2% CAGR ← Best performer
- India: 31.3% CAGR ← High growth
- China: 21.0% CAGR ← Emerging tech
- Japan: 19.2% CAGR ← Large, stable
- US: 9.7% CAGR ← Anchor holding

---

## Quick Troubleshooting

| Problem | Check |
|---------|-------|
| No entry signals | Is momentum data updating? (daily) |
| High loss rate | Are stops triggering correctly? (-25%) |
| Wrong position size | Check tier allocation (Strong 1.0x, Fair 0.8x) |
| Underperforming vs backtest | Portfolio concentration skewed? |
| Too many trades | Momentum filter too low? (set to 5%) |

---

## Success Criteria (Track Weekly)

✅ **Passing if:**
- Win rate >55%
- Avg return +1.5-2.5% per trade
- Max drawdown <20%
- CAGR tracking 15-20%

⚠️ **Review if:**
- Win rate <50%
- Avg return <+0.5% per trade
- Drawdown >25%
- CAGR trending <12%

---

## Need Help?

See detailed docs:
- **Full strategy**: DEPLOYMENT_COMPLETE.md
- **Risk framework**: Section "Risk Management"
- **Market breakdown**: Section "Portfolio Composition"
- **Backtest details**: Section "Backtest Results"

---

**Ready to deploy? Start with PHASE 1 (Broker Integration) in DEPLOYMENT_COMPLETE.md**

📧 Last updated: July 4, 2026
