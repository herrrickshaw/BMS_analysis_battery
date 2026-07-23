# Buy/Hold/Sell rule by market — what each market's data prefers

Each candidate zone rule scored by the forward-10d return SPREAD between the names it calls BUY and SELL, on each market's own 10y weekly panel (2018→). The rule with the largest positive, significant spread is what that market's zone logic should use — rather than the one trend rule applied everywhere.

| market | Trend-follow (close>EMA20>EMA50) | Mean-revert (buy oversold) | 6-month momentum | 1-month momentum | winner |
|---|---|---|---|---|---|
| **IN** | +0.15% (t+0.6) | +0.24% (t+1.4) | +0.20% (t+1.2) | -0.17% (t-0.8) | **Trend-follow** |
| **US** | -0.22% (t-1.5) | +0.41% (t+2.0) | **+0.38% (t+2.2)** | -0.28% (t-1.7) | **Mean-revert** |
| **JP** | -0.16% (t-1.6) | **+0.28% (t+3.1)** | -0.03% (t-0.4) | -0.23% (t-2.0) | **Mean-revert** |
| **KR** | **-0.29% (t-2.5)** | **+0.20% (t+2.4)** | **-0.33% (t-2.1)** | -0.17% (t-1.6) | **Mean-revert** |
| **EU** | -0.18% (t-1.8) | +0.24% (t+1.9) | +0.19% (t+1.4) | **-0.33% (t-3.1)** | **Mean-revert** |

**Bold** = |t| ≥ 2. Winner = largest positive spread with |t| ≥ 1.5, else defaults to trend (the incumbent). This is the spread a long-BUY/short-SELL book would have earned per 2 weeks — not a live strategy (no costs, weekly rebalance), but a clean read on which signal DISCRIMINATES in each market.

## How this maps to the digest
The zone engine can switch rule by market: a name is BUY if it passes its market's winning rule, SELL if it fails it, HOLD between. Eviction still runs off the SELL state, so a market whose winner is mean-reversion will evict on overbought-and-fading rather than below-EMA50 — which is what the literature (Balvers-Wu; emerging-market fast reversion; KOSPI contrarian) and our own signal-effectiveness analysis both point to.