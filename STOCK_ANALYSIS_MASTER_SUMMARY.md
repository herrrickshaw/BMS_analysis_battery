# Global Stock Analysis — Master Summary & Recommendations

**Compiled**: 2026-07-14
**Sources**: this repo's own docs (root `*.md`, `STRATEGY_ANALYSIS_INDEX.md`, `CASH_CONVERSION_CYCLE_FINAL_RESULTS.md`, `GERMAN_MOMENTUM_BREAKOUT_SCAN_RESULTS.md`, `reports/benchmark_results.csv`), Claude's cross-session memory of related repos (`market-screener-backtests`, `global-stock-screener`/`karz`, `event-driven-stock-analysis`), and prior debugging/error history.

## 0. How to read this document

Across ~90 markdown files in this repo and several sibling repos, the same handful of headline numbers get **restated as fact** without re-derivation. Before this summary, no single place distinguished *rigorously backtested* results from *small-sample projections*. This doc does that split explicitly — **Section 1 is the only tier you should act on**; Section 2 is documented so you know what to stop citing.

| Tier | Meaning | Example |
|---|---|---|
| 🟢 **Validated** | Point-in-time (PIT) data, fold-cross-validated or held-out tested, ≥100s of names, no look-ahead | US SEC Piotroski inversion, 19-market price sweep |
| 🟡 **Directional** | Real data but small sample / short window / no CV | India Piotroski (863 tickers, 4y) |
| 🔴 **Unvalidated / retire** | Small sample (<70 stocks) presented as "production-ready", or provably overfit | "Piotroski dominates 7 markets" (272 stocks), "Darvas+CCC 100% win rate" |

---

## 1. 🟢 What's Actually Validated (act on this)

This work lives in **`herrrickshaw/market-screener-backtests`** (a separate, isolated repo — not this one), using a consolidated DuckDB warehouse (`market_data.duckdb`, 55M price rows + 100k fundamental stock-years across 19 markets + US) and point-in-time SEC/yfinance fundamentals so there's no look-ahead bias.

### 1.1 Fundamentals — quality/value screens

| Market | Finding | Strength |
|---|---|---|
| **USA** | Piotroski F-Score **standalone is INVERTED** — high-F "quality" band *lags* baseline ~4pp (126d & 252d); low-F (esp. F=0) leads. US is mean-reverting, not quality-rewarding. | 🟢 SEC EDGAR PIT, 5,070 tickers, 124k filings |
| **USA** | Piotroski **as a breakout overlay works** — `Darvas × F≥7` median edge **+9.9pp**, 62% win, vs Darvas-alone +2.2pp. Quality fails as a standalone picker but confirms a breakout. | 🟢 |
| **USA** | **Magic Formula (Greenblatt) works** — EY(EBIT/EV) + ROC decile D1 (cheap+good): **+6.4pp median edge**, 63% win, near-monotonic decline to D10. | 🟢 |
| **USA** | Deep-value screens rank (252d median edge): **net_net (Graham NCAV) +12.4** > garp +5.9 > magic +5.8 > quality(ROCE≥15&D/E≤1) +4.3 > piotroski +3.4 > lowdebt +0.2. **Value beats quality alone on US.** | 🟢 |
| **USA** | Coffee Can (ROE≥15 + RevCAGR≥10 + D/E≤1): lower mean but **higher median (+4pp) + 60% win** — avoids blow-ups, forfeits lottery tail. Same signature as inverted Piotroski. | 🟢 |
| **India** | Piotroski is the **mirror image of the US** — F=8–9 band beats baseline **+1.7pp (126d) / +2.8pp (252d)**, high-F beats mid-F monotonically. India rewards quality/momentum where the US rewards value/mean-reversion. | 🟡 yfinance PIT, 863 tickers, 4y only |
| **13/19 non-US markets** | `Darvas × Piotroski(F≥7)` improves the base price screen (biggest: AU +13.6pp, CN +12.7pp, CA +12.2pp, SG +12.0pp @ 252d). The US "quality-as-overlay-not-picker" pattern **generalizes globally**. | 🟢 |
| **US-only fundamental screen that survives fold-CV** | `book/market ↑ top 10%` (deep value): **+4.0% OOS** — the *only* robust standalone fundamental screen across all 20 markets tested. Every other market's robust screen is a price/risk factor, because non-US fundamentals are only 4–5y deep (too shallow to clear cross-validation). | 🟢 |

### 1.2 Price/technical screens (whole 19-market sweep)

| Regime | Markets | 
|---|---|
| **Mean-reversion (RSI-oversold) wins** | US, KR, CN, JP, + DK, SG, ZA |
| **Breakout/trend (near-52w-high, Golden Cross, momentum) wins** | India + most of Europe + HK, TW, CA, BR, SA, AU |
| **Weakest screen everywhere** | Golden Cross (moving-average crossover) — worst performer in every single market tested |
| **Low-volatility factor** | Dominant near-universal edge in 10/20 markets once liquidity-gated (drop least-liquid 50%) — **US +6.2%, JP, HK +8.6%, TW, CA +21%, AU +20%, UK +9.7%, SG, SE +10%** |
| **Near-52w-high wins on liquid names** | SG, SE, DE, SA, FI |
| **India's ">200dma trend" edge (+4.8%) is a microcap artifact** — it **disappears once liquidity-gated**. India's tradeable price edge is genuinely weak; the earlier "India is momentum-friendly" claim only holds on illiquid names. | ⚠️ correction to 1.2 row above |
| **Liquidity as a confirmation overlay** (not standalone signal) improves realized OOS alpha in 8/9 markets tested: HK +8.9pp, UK +3.5, JP +3.1, TW +2.8, CA +2.6, SE +2.6, SG +2.3. Same "overlay not picker" pattern as fundamentals. | 🟢 |

### 1.3 Net-of-cost reality check
Near-52w-high / Darvas-proximity screens go **negative standalone in every market** once realistic round-trip costs are applied (India 0.30%, US 0.10%, Japan 0.20%, Korea 0.25%, EU 0.40%). Any "backtest" that doesn't net out costs is overstating the edge.

### 1.4 Bottom-line recommendation matrix (validated tier only)

| Market | Primary edge | Overlay | Avoid |
|---|---|---|---|
| **US** | Value (net_net/Magic Formula) or mean-reversion (RSI-oversold) | Confirm breakouts with Piotroski F≥7, not stand-alone quality picking | Standalone high-Piotroski "quality" picking; Golden Cross |
| **India** | Quality (Piotroski F=8–9) on *liquid* names | — | Treating microcap trend/momentum edges as tradeable; check liquidity-gated results before sizing |
| **Japan/Korea/China** | Mean-reversion (RSI-oversold) | — | Golden Cross |
| **Europe (most)/HK/TW/CA/BR/AU/SA** | Breakout/trend, low-volatility once liquidity-gated | — | Golden Cross |
| **All markets** | — | Liquidity-trend as a confirmation filter on top of the primary price screen | Any screen without transaction-cost netting |

---

## 2. 🔴 Claims to stop repeating

These are the numbers copy-pasted across `STRATEGY_ANALYSIS_INDEX.md`, `COMPREHENSIVE_STOCK_ANALYSIS_2026.md`, `CASH_CONVERSION_CYCLE_FINAL_RESULTS.md`, and `GERMAN_MOMENTUM_BREAKOUT_SCAN_RESULTS.md` in **this** repo:

- **"Piotroski F-Score dominates all 7 markets"** — this is a *variance* observation (Piotroski scores are more dispersed than momentum scores) computed on a **272-stock sample**, not a return-edge finding. It does not mean high Piotroski beats the market. The rigorous 19-market backtest above contradicts it directly for the US (inverted) and shows it's overlay-only elsewhere.
- **"Darvas + CCC = 100% win rate, 1.0 Sharpe"** — a 100% win rate on any nontrivial sample size is a textbook overfitting/survivorship red flag, not a result to size a portfolio on.
- **Japan/UK/Germany "new screens"** (Piotroski≥4+P/B<1.2 Japan; Piotroski≥3+P/E<15 UK; Piotroski≥1+FCF>3% Germany) — each validated on 32–42 stock samples, explicitly labeled "MEDIUM confidence, Phase-1 test needed" in the source doc itself, and **that Phase-1 full-universe test was never run**. Treat as untested hypotheses.
- **CCC filter "65-70% win rate" and German scan "18-22% CAGR"** — both stated as ranges from an 18-stock test set, no CV, no cost-netting.
- **The projected "+1.7% portfolio uplift from reallocating into Japan/UK"** in `STRATEGY_ANALYSIS_INDEX.md` is downstream of the above and should be treated as fiction until re-run against the real warehouse.

## 3. Architecture / where the actual code and data live

This home-directory repo (`origin` = `herrrickshaw/BMS_analysis_battery`, mismatched name — flagged previously as a hygiene issue) is one of several repos covering overlapping ground. Know which repo has the real backtest engine before trusting a doc:

| Repo | Role | Trust level |
|---|---|---|
| **This repo** (multi-market FastAPI+React app, per `CLAUDE.md`) | Live screening UI, Cassandra-backed daily scanner (Darvas/Buffett + Piotroski), portfolio P&L, put-call parity trading | Application layer — correct architecture, but its scanner *thresholds* haven't been backtested in-repo (see `reports/benchmark_results.csv`, which is a pure-Python-vs-pandas *speed* benchmark, not a strategy backtest) |
| `herrrickshaw/market-screener-backtests` | **The actual rigorous backtest engine** — PIT SEC/yfinance fundamentals, DuckDB warehouse, fold-CV reward-optimized screener discovery, liquidity overlay | 🟢 Source of everything in Section 1 |
| `herrrickshaw/global-stock-screener` (branch `karz`) | `BACKTEST_FINDINGS.md` — the original 15-market technical-screen sweep that first surfaced the mean-reversion/breakout regime split and the "Golden Cross is weakest everywhere" finding | 🟢 |
| `herrrickshaw/event-driven-stock-analysis` | K8s deployment package, 20,738-stock data pipeline, 15 REST endpoints — infrastructure, not strategy validation | Infra layer only |
| `herrrickshaw/BazaarTalks` | Public dashboard/pipeline + graphics, live Trendlyne/Screener.in feeds | Presentation layer |

**Recommendation**: if the goal is to ship live signals from *this* repo's `scanners/daily_scanner.py` (Darvas/Buffett + Piotroski, 0–7/0–6 point scales), re-derive its BUY/WATCH thresholds from the `market-screener-backtests` warehouse results in Section 1 rather than the 272-stock projections in Section 2 — e.g. weight the Piotroski component down for US-listed names (it's inverted there) and up for India names (it's real there), and treat it as a breakout-confirmation overlay everywhere else rather than a standalone filter.

## 4. Cross-cutting engineering lessons (apply to any new screener work)

- **yfinance DataFrame truthiness**: never `or` between two DataFrame results — `bool(df)` raises `ValueError`. Use a `_first_df()` helper checking `is not None and not df.empty`.
- **yfinance `debtToEquity`**: sometimes returned as a raw percentage (`45.2` = 0.452×) depending on version. Normalize with `de/100 if de > 10 else de`.
- **Darvas Box**: box top/bottom must be computed from **historical bars only** (`highs[:-1]`, `lows[:-1]`) — including the current bar makes `BREAKDOWN_SELL` mathematically unreachable, since the breakdown bar's own low pulls the box bottom below its own close.
- **nsepython `equity_history()`** fails on macOS (no browser cookies, returns `{}`). Use `yfinance.Ticker("SYMBOL.NS").history()` instead for OHLC.
- **Point-in-time discipline**: any backtest using yfinance/screener.in fundamentals without a real filing date is look-ahead-biased; entry date should be `FY-end + 90d` proxy at best, true `filed` date (SEC EDGAR) where available. This is *why* the US results (SEC-backed) are trusted 🟢 and most non-US fundamental results are capped at 🟡/null.
- **Cross-validate, don't just backtest**: the reward-optimized screener work only counted a factor "robust" if an early-fold/late-fold split *and* a true held-out year both agreed — this is why 15/20 markets honestly returned "no robust fundamental screener" instead of a fabricated positive.
- **Liquidity-gate before trusting a "whole universe" result**: 8/20 markets (including India's >200dma trend) look robust on the full listed universe but collapse once the illiquid bottom 50% is dropped — a classic microcap-return artifact.
- **Rate limiting / data collection**: NSE Bhavcopy direct archives are ~100x faster than yfinance for India OHLC (2-3h vs 2-3 days for 15y); `curl_cffi` with `impersonate="chrome"` bypasses Yahoo's datacenter-IP throttle for yfinance fundamentals collection; screener.in throttles to ~2.6 names/min and blocks after ~164 — don't rely on it as a primary source.
- **Never use Kaggle datasets** for market data recovery — prefer official direct archives (NSE Bhavcopy, SEC EDGAR, JPX, KRX). No third-party redistribution risk, no license ambiguity, $0 cost, no rate limiting.
- **Data leakage checklist** (from the repo's `data_validator.py`/`data_config.py` framework): chronological train/val/test splits only (no shuffled splits on time series), exhaustive validation over sampled `.head()`/`.sample()` testing, cross-source consistency checks (<2% price discrepancy tolerance) before merging data sources.

## 5. Key Recommendations (priority order)

1. **Stop citing the 272-stock "Piotroski dominates 7 markets" claim and the "Darvas+CCC 100% win rate" number in any forward-looking doc** — replace with the Section 1 matrix. This affects `STRATEGY_ANALYSIS_INDEX.md`, `COMPREHENSIVE_STOCK_ANALYSIS_2026.md`, `CASH_CONVERSION_CYCLE_FINAL_RESULTS.md`, `GERMAN_MOMENTUM_BREAKOUT_SCAN_RESULTS.md` in this repo.
2. **Re-tune `scanners/daily_scanner.py`'s Piotroski weighting per market** — down-weight/invert for US, up-weight for India, treat as a Darvas-breakout confirmation overlay (not a standalone filter) for the other 17 markets, matching the validated warehouse findings.
3. **Retire Golden Cross** as a scoring component anywhere it's used — it's the weakest screen in literally every one of the 19 markets tested.
4. **Add a liquidity gate** to any screener output before it's shown as a "signal" — India's trend edge and 7 other markets' apparent edges are microcap artifacts that vanish once you require tradeable liquidity.
5. **Net out transaction costs before displaying any win-rate/CAGR** — near-52w-high/proximity screens flip negative once realistic per-market costs are applied; the current UI/reports likely overstate edges by not doing this.
6. **If Japan/UK/Germany screens are still wanted**, actually run the Phase-1 full-universe validation that was scoped but never executed (3,709 / 436 / 142 stocks respectively) against the PIT warehouse — don't ship the 32–42-stock projections as production thresholds.
7. **Consolidate documentation** — this repo alone has ~90 root-level `*.md` files with overlapping/restated claims across at least 5 different projects (stock screening, BMS battery, dashboard, event-driven platform). Given the repo naming mismatch already flagged (`BMS_analysis_battery` hosting stock-mailer content), consider moving stock-analysis docs to the correct dedicated repo(s) to stop the restatement drift that produced Section 2.
8. **Keep US SEC-based work as the gold standard** for any future market — it's the only market with a real 15-year point-in-time filing history, which is why it's the only market to clear cross-validation on a *fundamental* factor. For markets without a SEC-equivalent, expect the robust edge to always be a price/risk factor, not fundamentals, until deeper dated fundamentals are collected (India: only 4y depth today via yfinance; EU/JP/KR/SG: no dated fundamentals source exists at all yet).
