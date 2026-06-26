# Dockerfile — Stock Analysis System v1.0.0
# ==========================================
# Multi-stage build for a reproducible, self-contained analysis environment.
#
# STAGES
# ──────
# Stage 1 (deps):    Install Python packages — cached layer, rarely re-built
# Stage 2 (data):    Bake in Nifty 500 5-year OHLC Parquet data
# Stage 3 (runtime): Final lean image with scripts + data + cron
#
# BUILD
# ─────
#   docker build -t stockscan:1.0.0 .
#   docker build -t stockscan:latest .
#
# RUN — Full daily scan
#   docker run --rm \
#     -v $(pwd)/output:/app/output \
#     -e EMAIL_TO=umashankartd1991@gmail.com \
#     stockscan:1.0.0 scan
#
# RUN — Backtest
#   docker run --rm -v $(pwd)/output:/app/output stockscan:1.0.0 backtest --market IN
#
# RUN — IPO tracker
#   docker run --rm -v $(pwd)/output:/app/output stockscan:1.0.0 ipo --days 90
#
# RUN — Walk-forward research
#   docker run --rm -v $(pwd)/output:/app/output stockscan:1.0.0 walkforward --period 5y
#
# RUN — Interactive shell
#   docker run -it --rm stockscan:1.0.0 shell
#
# RUN — Intraday monitor daemon (v2.0.0+)
#   docker run -d --name intraday-monitor \
#     -v $(pwd)/output:/app/output \
#     stockscan:1.0.0 monitor --interval 15
#
# VOLUMES
# ───────
#   /app/output     — scan results, Excel reports (mount for persistence)
#   /app/cache      — Parquet OHLC cache (mount to preserve across runs)
#
# ENVIRONMENT VARIABLES
# ─────────────────────
#   EMAIL_TO           — destination email for daily report
#   MARKET             — IN | US | BOTH (default: BOTH)
#   WORKERS            — parallel workers (default: 8)
#   LOG_LEVEL          — DEBUG | INFO | WARNING (default: INFO)

# ── Stage 1: Dependencies ─────────────────────────────────────────────────────
FROM python:3.11-slim AS deps

# System packages needed for pyarrow, scipy, lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ libffi-dev libssl-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies first (layer-cached until requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Data init ────────────────────────────────────────────────────────
FROM deps AS data-init

# Copy reference data (Nifty 500 Parquet, scan results)
# These are the 5-year OHLC files baked into the image at build time.
# Full NSE/BSE/NASDAQ universe is downloaded at runtime and cached to /app/cache volume.
COPY nse_screener_reference/ /app/data/reference/

# Download Nifty 50 index data during build (10-year for backtest warm-up)
# This runs once at build time and is baked in.
RUN python3 -c "
import warnings; warnings.filterwarnings('ignore')
import yfinance as yf, pandas as pd
from pathlib import Path
Path('/app/data/index').mkdir(parents=True, exist_ok=True)
for sym, fname in [('^NSEI','NSEI'), ('^GSPC','GSPC'), ('^VIX','VIX')]:
    try:
        df = yf.download(sym, period='10y', auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs(sym, axis=1, level=1)
        df.to_parquet(f'/app/data/index/{fname}.parquet', compression='snappy')
        print(f'  {sym}: {len(df)} bars → {fname}.parquet')
    except Exception as e:
        print(f'  {sym} failed: {e}')
print('Index data baked in.')
" || echo "Index download skipped (offline build)"

# ── Stage 3: Runtime ──────────────────────────────────────────────────────────
FROM data-init AS runtime

# Copy all analysis scripts
COPY Downloads/market_data_cache.py      /app/scripts/
COPY Downloads/nse_data_fetcher.py       /app/scripts/
COPY Downloads/stock_enricher.py         /app/scripts/
COPY Downloads/ml_signal_engine.py       /app/scripts/
COPY Downloads/screener_analysis.py      /app/scripts/
COPY Downloads/full_indian_market_scan.py /app/scripts/
COPY Downloads/full_us_market_scan.py    /app/scripts/
COPY Downloads/backtest_screeners.py     /app/scripts/
COPY Downloads/walk_forward_backtest.py  /app/scripts/
COPY Downloads/ipo_tracker.py            /app/scripts/
COPY Downloads/intraday_monitor.py       /app/scripts/
COPY Downloads/stock_utils.py            /app/scripts/
COPY Downloads/symbol_master.py          /app/scripts/
COPY Downloads/pattern_discovery.py      /app/scripts/
COPY Downloads/sector_analysis.py        /app/scripts/
COPY Downloads/dl_strategy_eval.py       /app/scripts/
COPY Downloads/sentiment_pipeline.py     /app/scripts/
COPY Downloads/sentiment_price_link.py   /app/scripts/
COPY Downloads/pipeline_historical.py    /app/scripts/
COPY Downloads/pipeline_news.py          /app/scripts/
COPY Downloads/daily_combined_report.py  /app/scripts/
COPY Downloads/r_analysis.py             /app/scripts/

# Metadata
COPY VERSION    /app/VERSION
COPY CHANGELOG.md /app/CHANGELOG.md
COPY STOCK_ANALYSIS_SYSTEM.md /app/STOCK_ANALYSIS_SYSTEM.md

# Entry point
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create runtime directories
RUN mkdir -p /app/output /app/cache/ohlc /app/cache/fundamentals \
             /app/cache/index /app/cache/meta /app/logs

# Set working directory so scripts find each other
WORKDIR /app/scripts

# Environment
ENV PYTHONPATH=/app/scripts \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/app/output \
    CACHE_DIR=/app/cache \
    LOG_LEVEL=INFO

# Expose version
LABEL version="1.0.0" \
      description="NSE/BSE/NASDAQ/NYSE Stock Analysis System" \
      maintainer="umashankartd1991@gmail.com" \
      research.papers="10" \
      screeners="6" \
      universes="NSE+BSE+NASDAQ+NYSE"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["help"]
