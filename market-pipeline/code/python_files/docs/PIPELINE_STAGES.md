# Strategy pipeline — the 10 stages (and the modules that implement them)

An end-to-end systematic equity-research pipeline across India, US, Korea, Japan,
Europe. Each stage is evidence-backed by a point-in-time backtest in this repo;
the suitability of every factor/filter/ratio per market is tracked in a living
matrix that re-tests itself as new data arrives.

> Educational/research only. Not investment advice.

| # | Stage | What it does | Module(s) |
|---|-------|--------------|-----------|
| 1 | **Factor sourcing** | value (PE vs peers), quality (ROE/ROCE), momentum, low-vol, CCC, debt-reduction | `financial_ratios.py`, `profitability_optimizer.py` (factor library) |
| 2 | **Screener creation** | encode factors as scored screens + per-market **regime-conditional** zone rules (momentum in bull, mean-revert in bear) | `scanners/`, `backtest_zone_rules.py`, `strategy_regime_survival.py` |
| 3 | **Data extraction** | PIT OHLCV + fundamentals per market; split-adjusted; liquidity-gated (HIGH+MEDIUM turnover) | warehouse panels, `market_ingest.py`, `currency_matrix.py` (historical FX) |
| 4 | **Screener implementation** | run screens across the universe → ranked workbooks | daily scan steps of `daily_pipeline.sh` |
| 5 | **Signal × news matching** | cross mechanical picks with news sentiment; **sell signals linked to the tape** | `sell_news.py`, VIX/regime tags |
| 6 | **Finalise picks** | curate graded-A ∩ fundamentals ∩ buy-zone; validate vs screener.in | `watchlist_digest.py`, `validate_brief.py`, `learned_recommender.py` |
| 7 | **Buy & hold** | equal-weight / **inverse-vol** entry, sized within capacity; **impact-aware** cost | `paper_track.py`, `execution_cost_model.py`, `risk_management.py` |
| 8 | **Sell on signals** | per-market zone rule exit; evict >5 sessions, purge >15; `value-hold` tier is exempt | `watchlist_digest.py` (maintain) |
| 9 | **Backtest for edge** | 10y PIT validation; **regime survival**, **Deflated-Sharpe** (multiple-testing), valuation **reversion**, value+quality L/S | `strategy_regime_survival.py`, `deflated_sharpe.py`, `valuation_reversion_backtest.py`, `value_quality_ls_backtest.py`, `aws_sweep.py` |
| 10 | **Financials & selection** | trades → income statement / balance sheet; ROIC, cost of capital, alpha vs index; **quarterly earnings** | `trading_financials.py`, `quarterly_earnings.py`, `firm_benchmark.py` |

## The adaptive & synthesis layers (on top of the 10 stages)

- **Learned factor model** — Lasso factor selection + online SGD with a tunable
  learning rate; hyperparameters tuned by a joint grid sweep
  (`factor_learning.py`, `aws_sweep.py`).
- **Valuation clustering** — data-driven peer groups (business economics), then
  over/under-priced vs same-profile peers (`valuation_clustering.py`).
- **Suitability matrix** — market × factor × filter × ratio × regime → what works
  where, assembled from the backtests, self-testing with flip-detection
  (`strategy_matrix.py`).
- **Observability** — structured logger, clocks, append-only decision log
  (`obs.py`).
- **Delivery** — validated picks → watchlist + strategy digest email
  (`strategy_mailer.py`).

## The meta-finding: market character decides the playbook

| market | character | long book | short book |
|--------|-----------|-----------|------------|
| India | momentum/trend | breakout + sector-relative value (long-only) | ❌ don't short (bull runs shorts over) |
| US | mixed | golden-cross / cheap+quality, light | marginal |
| Korea | mean-reversion | cheap ∩ high-ROE (the Korea discount) | ✅ short hollow-overpriced (validated t 4.2) |
| Japan | mean-revert (weak) | momentum in bull, revert in bear | — value not significant |
| Europe | mean-revert | momentum in bull, revert in bear | — no fundamentals |

Valuation reversion (over/under-pricing corrects toward peer average) is validated
point-in-time in India (+5.3%/6M), US (+1.7%/3M) and Korea (+6.3%/6M); the multiple
converges toward the median in all four tested markets.
