# Repo Consolidation Report

Generated from `inventory.duckdb` (4 lineage clusters, min-overlap=0.3). File-level evidence (blob-sha matches, unique-file counts) is deterministic; canonical-repo judgment below is LLM-assisted (llama-3.3-70b-versatile) and should be spot-checked before archiving anything.


## Cluster 1: BMS_analysis_battery, ocaml-stock-screener


### BMS_analysis_battery
- description: Quantitative stock analysis system — NSE/BSE/NASDAQ/NYSE screeners, backtesting, ML, news sentiment & MPT portfolio construction
- language: HTML, size: 337010KB, fork: False
- updated_at: 2026-07-06T16:08:18Z, pushed_at: 2026-07-09T08:02:25Z
- total files: 758
- files unique to this repo (not byte-identical to any sibling): 290
  sample: .env.providers.example, .github/workflows/market_movers.yml, .gitignore, ASSUMPTIONS.md, BACKTEST_RESULTS_COMPREHENSIVE.txt, CASH_CONVERSION_CYCLE_FINAL_RESULTS.md, CHAT_SESSION_SUMMARY.md, CLAUDE.md, COLAB_QUICK_CHECK.ipynb, COMPLETE_STRATEGY_EXECUTION_PLAN.md, COMPREHENSIVE_DATA_SOURCE_INVENTORY.md, COMPREHENSIVE_STOCK_ANALYSIS_2026.md, DAILY_MAILER_QUICKSTART.md, DAILY_MAILER_README.md, DELIVERABLES_SUMMARY.txt, DEPLOYMENT_CHECKLIST.md, DEPLOYMENT_GUIDE_FULL_UNIVERSE.md, DEPLOYMENT_RESULTS_GERMAN_MOMENTUM_BREAKOUT.txt, DEPLOYMENT_TEST_REPORT.md, EUREX_DATA_EXTRACTION_COMPLETE.md

### ocaml-stock-screener
- description: (none)
- language: HTML, size: 64905KB, fork: False
- updated_at: 2026-07-06T05:17:42Z, pushed_at: 2026-07-06T16:14:05Z
- total files: 464
- files unique to this repo (not byte-identical to any sibling): 4
  sample: .gitignore, DEPLOYMENT_CHECKLIST.md, README.md, requirements.txt

**Verdict:**

BMS_analysis_battery appears to be the canonical version due to its recency, completeness, and matching description. 
ocaml-stock-screener seems to be an earlier snapshot, recommended action: archive.

The description of ocaml-stock-screener is empty, which is surprising given its content. 
BMS_analysis_battery's description matches its content, but ocaml-stock-screener's lack of description and limited unique files suggest it's not actively developed.


## Cluster 2: global-market-data, global-stock-screener, market-screener-backtests


### global-market-data
- description: Deep 10-year multi-geography equity OHLC (5 markets, ~44M rows) + screeners, ML, and backtests. Research/education only.
- language: Python, size: 875KB, fork: False
- updated_at: 2026-07-03T01:54:10Z, pushed_at: 2026-07-03T01:54:06Z
- total files: 312
- files unique to this repo (not byte-identical to any sibling): 86
  sample: .gitattributes, .github/workflows/integrity.yml, .gitignore, .pre-commit-config.yaml, .vcrud_bin/db_handler.py, .vcrud_bin/vcrud_manager.py, FINAL_DELIVERABLES.md, Quick_Start_Guide.md, README.md, SGX_ALL_COMMAND_GUIDE.md, SGX_FULL_SCAN_README.md, SG_STOCK_ANALYZER_README.md, auto_screener.py, backtest_screeners.py, backtest_weight_optimization.py, backtest_weight_validation.py, build_mailer.py, cache_seed/CHECKSUMS.sha256, com.umashankar.dailybrief.plist, daily_combined_report.py

### global-stock-screener
- description: 20-market stock screener with cached OHLCV, 11 strategies, liquidity tiers, cash-conversion-cycle, multi-source data & token-free daily mailer. Educational only.
- language: Python, size: 3163KB, fork: False
- updated_at: 2026-07-10T07:29:02Z, pushed_at: 2026-07-10T07:28:55Z
- total files: 447
- files unique to this repo (not byte-identical to any sibling): 46
  sample: .gitattributes, .gitignore, build_mailer.py, cache_seed/CHECKSUMS.sha256, cache_seed/fundamentals_history/AU.parquet, cache_seed/fundamentals_history/BR.parquet, cache_seed/fundamentals_history/CA.parquet, cache_seed/fundamentals_history/CH.parquet, cache_seed/fundamentals_history/CN.parquet, cache_seed/fundamentals_history/DE.parquet, cache_seed/fundamentals_history/DK.parquet, cache_seed/fundamentals_history/EU.parquet, cache_seed/fundamentals_history/FI.parquet, cache_seed/fundamentals_history/HK.parquet, cache_seed/fundamentals_history/IN.parquet, cache_seed/fundamentals_history/JP.parquet, cache_seed/fundamentals_history/KR.parquet, cache_seed/fundamentals_history/SA.parquet, cache_seed/fundamentals_history/SE.parquet, cache_seed/fundamentals_history/SG.parquet

### market-screener-backtests
- description: Point-in-time multi-market screener backtests (price + fundamental), ML factor weights, regime picks, and daily briefing. Research/education only.
- language: Python, size: 759KB, fork: False
- updated_at: 2026-07-10T07:40:51Z, pushed_at: 2026-07-10T07:40:23Z
- total files: 422
- files unique to this repo (not byte-identical to any sibling): 40
  sample: .gitattributes, .gitignore, build_mailer.py, cache_seed/CHECKSUMS.sha256, colab_collect.py, colab_yf_fundamentals.ipynb, daily_pipeline.sh, data/curated/daily_checklist_2026-07-09.md, data/curated/exchange_reference.parquet, data_validator.py, deep_prices.py, emerging_fundamentals.py, exchange_reference.py, india_fundamentals_yf.py, local_collect.py, market_data.duckdb, phased_expansion_screener_11d.py, price_correlation_analysis.py, quarterly_data_analyzer.py, quarterly_data_collector.py

**Verdict:**

global-stock-screener appears to be the canonical version due to its recency, completeness, and matching description. 
global-market-data seems to be an earlier snapshot, recommended action: merge-into-canonical.
market-screener-backtests appears to be a mislabeled dumping ground, recommended action: archive.
The descriptions of global-market-data and market-screener-backtests don't fully match their content, which is surprising.


## Cluster 3: cell-guardian, quant-stock-trading, working-files


### cell-guardian
- description: BMS EKF SOC/SOH, 8 chemistries, Kaggle validation
- language: Python, size: 258698KB, fork: False
- updated_at: 2026-07-03T03:36:25Z, pushed_at: 2026-07-03T03:35:47Z
- total files: 7603
- files unique to this repo (not byte-identical to any sibling): 0

### quant-stock-trading
- description: NSE/BSE/US/Europe screener, FastAPI+React, put-call parity
- language: Python, size: 258698KB, fork: False
- updated_at: 2026-07-03T03:41:06Z, pushed_at: 2026-07-03T03:40:31Z
- total files: 7603
- files unique to this repo (not byte-identical to any sibling): 0

### working-files
- description: (none)
- language: Python, size: 266132KB, fork: False
- updated_at: 2026-07-04T05:59:44Z, pushed_at: 2026-07-10T02:30:30Z
- total files: 23308
- files unique to this repo (not byte-identical to any sibling): 15691
  sample: BMS_analysis_battery/.env.providers.example, BMS_analysis_battery/.gitattributes, BMS_analysis_battery/.github/workflows/market_movers.yml, BMS_analysis_battery/.gitignore, BMS_analysis_battery/ASSUMPTIONS.md, BMS_analysis_battery/CLAUDE.md, BMS_analysis_battery/README.md, BMS_analysis_battery/SEBI_web_scraper.ipynb, BMS_analysis_battery/Stock_reporting.ipynb, BMS_analysis_battery/backend/benchmarks/__init__.py, BMS_analysis_battery/backend/benchmarks/benchmark_engine.py, BMS_analysis_battery/backend/column_map.py, BMS_analysis_battery/backend/config/__init__.py, BMS_analysis_battery/backend/config/providers.py, BMS_analysis_battery/backend/damodaran.py, BMS_analysis_battery/backend/db/__init__.py, BMS_analysis_battery/backend/db/bulk_fetcher.py, BMS_analysis_battery/backend/db/cassandra_client.py, BMS_analysis_battery/backend/db/quote_updater.py, BMS_analysis_battery/backend/db/schema.cql

**Verdict:**

working-files appears to be the canonical version due to its recency, completeness, and unique file count. 
cell-guardian seems to be an earlier snapshot, recommended action: archive. 
quant-stock-trading seems to be a mislabeled dumping ground, recommended action: delete-candidate. 
It's surprising that quant-stock-trading's description doesn't match its content, which seems to be identical to cell-guardian.


## Cluster 4: BazaarTalks, global-market-scanners


### BazaarTalks
- description: Multi-market quant research platform — DuckDB warehouse, Cassandra store, ticker dashboard
- language: Python, size: 963KB, fork: False
- updated_at: 2026-07-10T10:58:34Z, pushed_at: 2026-07-10T10:58:27Z
- total files: 162
- files unique to this repo (not byte-identical to any sibling): 17
  sample: .env.example, .gitignore, README.md, TRENDLYNE_SCREENER_ACCESS.md, build_india_seed.py, cache_seed_local/cleaned_long_IN.parquet, charts.py, dashboard.py, live_fundamentals.py, marketdata.py, pipeline.py, requirements.txt, screener_session.py, serve.py, ticker_view.py, trendlyne_session.py, warehouse.py

### global-market-scanners
- description: Standalone full-universe equity scanners (Darvas + Piotroski + Coffee Can) across 5 markets — US, Europe, India, Japan, Korea — plus the derived industry/peer parquet dataset
- language: Python, size: 1201KB, fork: False
- updated_at: 2026-07-09T09:59:42Z, pushed_at: 2026-07-09T09:59:28Z
- total files: 152
- files unique to this repo (not byte-identical to any sibling): 7
  sample: .gitignore, README.md, dashboard.py, marketdata.py, requirements.txt, serve.py, warehouse.py

**Verdict:**

BazaarTalks appears to be the canonical version due to its more recent update and push times, as well as a higher number of unique files suggesting active development. 
global-market-scanners seems to be an earlier snapshot, recommended action: merge-into-canonical.
The descriptions of both repos generally match their content, but global-market-scanners lacks some files present in BazaarTalks, suggesting it may not be fully up-to-date.
