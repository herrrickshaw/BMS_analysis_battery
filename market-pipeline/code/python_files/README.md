# NSE Stock Screening Pipeline

This package converts the attached concept note and notebook into a practical Python workflow.

## Files
- `data_fetch.py` — fetch NSE universe, price history, quote snapshot, and bulk deals CSV fallback.
- `screening_engine.py` — compute technical/liquidity factors and rank stocks.
- `report_generator.py` — export JSON, CSV, XLSX, and Markdown reports.
- `run_pipeline.py` — main CLI entry point.

## Install
```bash
pip install nsepython pandas openpyxl requests tabulate
```

## Run on full NSE universe
```bash
python run_pipeline.py
```

## Run on your own symbols file
```bash
python run_pipeline.py --symbols-file my_symbols.xlsx
```

## Run with bulk deals CSV fallback
```bash
python run_pipeline.py --bulk-deals-csv bulk_deals.csv
```

## Output
- `output/pipeline_results/nse_full_universe_ranked.csv`
- `output/pipeline_results/nse_shortlist.csv`
- `output/pipeline_results/nse_screening_report.xlsx`
- `output/pipeline_results/screening_summary.md`
- `output/pipeline_results/stock_reports/*.json`

## Notes
- This is the Phase-1 practical screener from the attached ML design: momentum, liquidity, 200-DMA strength, delivery %, and drawdown filters.
- The attached document's later supervised, unsupervised, and RL layers can be added on top of this base.
- The attached notebook's reporting idea is preserved through per-stock JSON exports and a bulk-deals CSV fallback.
