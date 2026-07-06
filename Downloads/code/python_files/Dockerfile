# Bhavcopy screener — NSE+BSE EOD data, ships with a compact cache and builds the
# LMDB NoSQL store at image-build time so the container starts ready to query.
#
# Build:  docker build -t bhavcopy-screener -f Dockerfile .
# Run:    docker run --rm bhavcopy-screener                 # full bhavcopy scan
#         docker run --rm bhavcopy-screener python -c \
#             "import bhavcopy_store as s; print(s.info()); print(len(s.get('RELIANCE')))"
#
# The committed cache (cache_seed/cleaned_long.parquet, ~16 MB) is copied to
# $BHAV_CACHE and expanded into the LMDB store during build. No network needed to
# run against the shipped data; live fetch (nsepython/BSE) refreshes incrementally.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BHAV_CACHE=/app/cache

WORKDIR /app

# deps first (better layer caching)
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# application code
COPY *.py ./

# seed the cache and build the LMDB store inside the image
COPY cache_seed/ /app/cache/
RUN python bhavcopy_store.py --build && rm -rf /root/.cache

# default: run the full bhavcopy screener (uses the shipped cache offline)
CMD ["python", "scan_bhavcopy.py"]
