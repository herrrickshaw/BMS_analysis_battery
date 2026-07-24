# Systematic strategy platform — reference

A multi-market (India, US, Korea, Japan, Europe) systematic equity-research system.
Every strategy claim below is backed by a point-in-time backtest in this repo, and a
living **suitability matrix** re-tests which factor/filter/ratio works in which market
as new data arrives. **Educational/research only — not investment advice.**

See `PIPELINE_STAGES.md` for the 10-stage pipeline (factor sourcing → … → financials).

---

## 1. The core finding — market character decides the playbook

| market | character | long book | short book | evidence |
|--------|-----------|-----------|-----------|----------|
| **India** | momentum / trend | breakout + **sector-relative** value (long-only) | ❌ don't short — bull runs shorts over | value+quality L/S −1.0%/6M |
| **US** | mixed | golden-cross / cheap+quality, light | marginal | L/S +1.7%/6M, t 1.0 |
| **Korea** | mean-reversion | cheap ∩ high-ROE (the "Korea discount") | ✅ short hollow-overpriced | **L/S +4.8%/6M, t 4.2** |
| **Japan** | mean-revert (weak) | momentum in bull, revert in bear | — value not significant | reversion t≈0 |
| **Europe** | mean-revert | momentum in bull, revert in bear | — no fundamentals | regime survival |

**Valuation reversion is real** (over/under-pricing corrects toward the peer/sector
average): India +5.3%/6M (t 2.5, sector-rel), US +1.7%/3M (t 2.3), Korea +6.3%/6M
(t 3.3). The *multiple itself* converges toward the median in all four tested markets.
Nuance: convergence is **partial** — rich-PE names deliver faster EPS growth, so only
the *expensive + low-ROE (hollow)* names truly correct; *expensive + high-ROE* keep
their earned premium.

**Regime-conditional rules** (per market, Deflated-Sharpe checked): momentum/trend in
bull, mean-revert in bear. Only India-bull `trend`, Korea-bull `breakout`, EU-bull
`mom252` survive multiple-testing robustly; the bear-regime picks are statistically
fragile — treat as directional, not high-conviction.

---

## 2. Module reference

| Function | Module | Run |
|----------|--------|-----|
| Regime survival (factor × market × regime) | `strategy_regime_survival.py` | `… .py` (full) / `--refresh-regime` (fast daily) |
| Overfitting guard (multiple-testing) | `deflated_sharpe.py` | after profitability_optimizer |
| Reward-optimised factor selection | `profitability_optimizer.py` | standalone |
| Joint hyperparameter sweep (α × η × vol-target) | `aws_sweep.py` | `MARKET_WH=… python aws_sweep.py` |
| Learned factor model (Lasso + online SGD) | `factor_learning.py` | standalone |
| Long/short + take-profit | `long_short_tp.py` | standalone |
| Impact-aware execution & capacity | `execution_cost_model.py` | standalone |
| Risk overlay (inverse-vol · vol-target · kill-switch) | `risk_management.py` | standalone |
| Historical FX matrix | `currency_matrix.py` | `--refresh` |
| Valuation clustering (peer groups → over/under-priced) | `valuation_clustering.py` | standalone |
| Valuation reversion backtest (PIT) | `valuation_reversion_backtest.py {US,KR,JP}` | per-market |
| Value+quality long/short | `value_quality_ls_backtest.py` | IN/US/KR |
| Trading income stmt / balance sheet | `trading_financials.py` | standalone |
| Quarterly earnings (brokerage-style) | `quarterly_earnings.py` | standalone |
| Real-firm benchmark | `firm_benchmark.py` | standalone (yfinance) |
| Learned recs → digest (shadow) | `learned_recommender.py` | offline scorer |
| Current picks (tuned model) | `generate_recommendations.py IN,US` | per-market |
| **Suitability matrix (synthesis, self-testing)** | `strategy_matrix.py` | after backtests |
| DART Korea deep-history collector | `dart_history_collect.py` | resumable, multi-hour |
| Observability (logger/clock/decision-log) | `obs.py` | imported by all |
| Strategy digest email + watchlist | `strategy_mailer.py` | sends to MAIL_TO |

---

## 3. Data map

| Data | Location | Notes |
|------|----------|-------|
| OHLCV panels (10y, 6 markets) | `repos/global-market-data/warehouse/ohlcv/{MKT}` | env `MARKET_WH`; US/KR/JP/CN split-adjusted; **India raw → use `ohlcv_adj/IN`** |
| Fundamentals history (PIT) | `repos/global-stock-screener/cache_seed/fundamentals_history/` | 🔴 India: use `IN_screener_only_backup.parquet` (the merged `IN.parquet` has a 4× EPS error); KR/JP only 2021→ (yfinance), extend via DART/EDINET |
| Latest fundamentals snapshot | `reports/financial_ratios.csv` | IN/US/KR, PE/PB/ROE/margins |
| Backup | Dropbox `market-data-archive/` + local | warehouse.tar + folder; S3 removed |

**Caveats:** survivorship-biased universes (read spreads, not levels); no historical
GICS sectors for the IN/US/KR fundamentals universe (peers are data-driven clusters);
US valuation has near-zero-PE micro-cap data noise; yfinance marketCap is local-currency.

---

## 4. Keep-testing workflow

1. Refresh the backtests (monthly, or when data updates):
   `strategy_regime_survival.py` · `deflated_sharpe.py` · `valuation_reversion_backtest.py`
   · `value_quality_ls_backtest.py` · `pe_anomaly` etc.
2. Rebuild the matrix: `python strategy_matrix.py` — re-stamps every cell's last-tested
   date and **alerts on any suitability that FLIPPED** (a factor that stopped working).
3. Wire step 2 into `daily_pipeline.sh [16d]` (monthly) after the backtests.
4. Deepening data (DART/EDINET) auto-refreshes the KR/JP cells on the next run.

Observability: all runs log to `logs/` (gitignored) with a decision-log audit trail
(`logs/decisions_<UTCdate>.jsonl`), replayable by run id — the record the algo-trading
literature requires.

---

## 5. Open items

- **DART Korea deep-history** collection extends KR fundamentals 5y→~7y (2019→); re-run
  the KR reversion/L-S backtests on completion.
- **Japan EDINET** collector not built (public API, no key) — would give Japan real
  statistical power (currently directional-only).
- **Deflated-Sharpe fragile** bear-regime factor picks — re-test out-of-sample / with
  purged CV before trusting.
- **Colab notebook** (`market_sweep_colab.ipynb`, in Dropbox) reproduces the sweep
  bit-for-bit from the GitHub-LFS data reference.
