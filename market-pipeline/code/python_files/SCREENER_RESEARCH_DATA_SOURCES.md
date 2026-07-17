# Screener Research — Data Source Registry

Single source of truth for every data source used in the multi-market
(US/India/Japan/Korea/China) factorial screener research program
(`factorial_screener_test*.py`, `collect_*.py`, the Postgres warehouse).
Every fact below was verified by directly loading the file or querying the
live source, not copied from prior documentation — update this file, don't
let the facts drift back into being re-derived in conversation each time.

Last verified: 2026-07-17.

---

## 1. OHLCV (price history)

| Market | Path | Rows | Symbols | Date range | Symbol format |
|---|---|---|---|---|---|
| US | `~/repos/global-stock-screener/cache_seed/ltm/US.parquet` | 16.2M | 9,278 | 2016-06-27 → 2026-07-02 | bare (`AAPL`) |
| India | `~/repos/global-stock-screener/cache_seed/ltm/IN.parquet` | 4.8M | 8,944 | 2016-06-27 → 2026-07-02 | bare NSE (`RELIANCE`) |
| Japan | `~/repos/global-stock-screener/cache_seed/ltm/JP.parquet` | 7.3M | 3,083 | 2016-06-27 → 2026-07-01 | `NNNN.T` |
| Korea | `~/repos/global-stock-screener/cache_seed/ltm/KR.parquet` | 5.3M | 2,597 | 2016-06-27 → 2026-07-02 | `NNNNNN.KS`/`.KQ` |
| China | `~/repos/global-stock-screener/cache_seed/ltm/CN.parquet` | 10.0M | 5,188 | 2016-06-27 → 2026-07-01 | `NNNNNN.SS`/`.SZ` |

Schema (all 5): `Date, Open, High, Low, Close, Volume, Symbol`.

A near-duplicate, independently-sourced OHLCV set exists at
`~/repos/global-market-data/cache_seed/ltm/{US,IN,JP,KR,CN}.parquet` (same
schema, slightly more current end date, no fundamentals counterpart) — not
currently used by the screener scripts, kept as a secondary source if the
primary needs cross-checking.

**Benchmarks** — none are bundled except US/India:
| Market | Benchmark | Source | Caveat |
|---|---|---|---|
| US | `SPY` | Already a row in `US.parquet` | Full range |
| India | `NIFTYBEES` (Nifty 50 ETF) | Already a row in `IN.parquet` | Only from **2021-07-02** — signals before that have no benchmark, `xret_*` comes out NaN |
| Japan | `^N225` (Nikkei 225) | **Fetch live via yfinance**, append to OHLCV frame before `_flag_split_days` | Not cached anywhere |
| Korea | `^KS11` (KOSPI) | **Fetch live via yfinance** | Not cached; no KOSPI/KOSPI200 ETF proxy found in either OHLCV file |
| China | `000001.SS` (SSE Composite) | **Fetch live via yfinance** | `000300.SS` (CSI 300) only has data from 2021 on Yahoo — rejected as inadequate; `^SSEC` 404s; akshare's `index_zh_a_hist` failed with a ConnectionError in this environment |

---

## 2. Fundamentals — point-in-time (PIT) status per market

**This is the single most important table in this file.** PIT discipline
(a genuine, variable filing/disclosure date — not a synthetic constant
offset from fiscal-year-end) is mandatory for any factorial regression to
mean what it claims to mean. Checked by computing `(filed − fy_end).std()`
on each file — a value of exactly `0.0` means the "filed" date is fake.

| Market | Path | Rows/tickers | PIT status |
|---|---|---|---|
| US | `~/repos/global-stock-screener/cache_seed/fundamentals_history/US.parquet` | 65,114 / 5,016 | **Genuine.** `filed` from SEC EDGAR, real variable lag (mean 241d, mode 59-60d) |
| India | `~/repos/global-stock-screener/cache_seed/fundamentals_history/IN.parquet` | 734 / 75 (screener.in-sourced) | **Not genuine** — no `filed` column at all; code uses fy_end+90d proxy. Also far too thin (75/8,944 tickers) |
| Japan | `~/repos/global-stock-screener/cache_seed/fundamentals_history/JP.parquet` | 7,472 / 1,833 | **Fake** — `filed` = fy_end + exactly 90 days, `std=0.0`. Traced to `yf_fundamentals.py:109`'s own reporting-lag-proxy docstring |
| Korea | `~/repos/global-stock-screener/cache_seed/fundamentals_history/KR.parquet` | 3,970 / 942 | **Fake** — same fy_end+90d constant, `std=0.0`. High null rates (~40% missing `long_term_debt`) |
| China | `~/repos/global-stock-screener/cache_seed/fundamentals_history/CN.parquet` | 3,852 / 932 | **Fake** — same fy_end+90d constant, `std=0.0` |

### 2a. Real PIT alternatives found/built this program

| Source | Market | What it gives | Status |
|---|---|---|---|
| `earnings_dates_dart.py` → `cache_seed/earnings_dates_dart/KR.parquet` | Korea | 22,642 rows, 2,592/2,597 tickers, real DART filing dates | Exists, only ~2yr history (2024-07→2026-07), **not yet joined** to `fundamentals_history/KR.parquet`'s numbers |
| `~/repos/global-stock-screener/collect_nse_results.py` (built this session) | India | NSE's own `results-comparision` API — genuine variable filing lag (verified: 9-53 days, std 9.7d on a 25-row sample), structured quarterly numbers (revenue, net income, EPS, D/E, etc.) | **Currently blocked** (NSE WAF 403 "Access Denied", domain-wide, confirmed on a completely unrelated endpoint too). 403/1,679 liquid-equity universe collected before the block. See §4 for the two false-block bugs already fixed in this collector (bond/NCD tickers, then Gold-ETF tickers) |
| **`yfinance` `Ticker.earnings_dates`** (discovered this session) | **US, India, Japan, Korea confirmed working**; China untested | Real historical earnings-announcement dates (not fiscal-period-end), 25 quarters back to ~2019, actual reported EPS + consensus estimate. Paired with `quarterly_income_stmt`/`quarterly_balance_sheet`/`quarterly_cashflow` (40+ line items) for the actual figures | **Not blocked, not yet built into a collector.** This is the most promising path to fix ALL FOUR non-US markets' fake-PIT problem in one build — not yet done, flagged as the clear next step |

### 2b. Dead ends (checked, ruled out)

| Source | Why ruled out |
|---|---|
| `bsedata` (PyPI) | Only wraps BSE live quotes/bhavcopy — no financial-results method at all |
| `jugaad_data.bse.live.BSELive.corporate_announcements*` | Different host than blocked NSE (works), gives real precise timestamps (down to the second), but only announcement **metadata + PDF link** — not structured numbers. `category="Result"` filter doesn't reliably isolate results filings from board-meeting/credit-rating/general disclosures either. Would need PDF-parsing to get actual figures — bigger lift than yfinance |
| Trendlyne (`~/BazaarTalks/trendlyne_session.py`) | No PyPI package. Requires the user's own paid-account session cookie, manually extracted from a logged-in browser (deliberately never automates login — Trendlyne's login is behind reCAPTCHA v3). Even when authenticated, only returns a **live current snapshot** (PE/PB/mkt cap/sector) — not historical, so doesn't solve PIT backtesting regardless of auth |
| `db/` Cassandra app fundamentals (`market-pipeline`'s live backend) | No fundamentals table exists in the live schema at all — `stock_quotes` is a live-quote cache only |
| `/Users/umashankar/data/market_data.duckdb`'s `nse_stocks_fundamental`/`bse_stocks_fundamental` | 5 rows each, columns are just `symbol, exchange, ticker, fetch_ts` — a stub, no actual financial figures |

---

## 3. US-only v8 datasets (not fundamentals, event data)

| Dataset | Path | Rows | Coverage | Source |
|---|---|---|---|---|
| FINRA short interest | `.../cache_seed/short_interest_us.parquet` | 97,555 | S&P 500 only (501/503 symbols), 2017-12-29 → 2026-06-30 | `collect_short_interest.py`, FINRA's public `consolidatedShortInterest` REST API, no auth needed |
| SEC Form 4 insider transactions | `.../cache_seed/insider_transactions_us.parquet` | 208,930 | S&P 500 only (495/503 symbols), 2017-01-03 → 2025-12-31 | `collect_insider_form4.py`, SEC's bulk quarterly Form 3/4/5 data sets, P/S codes only |

Both deliberately scoped to the S&P 500 pool, not the full 6,480-symbol
universe — a stated scope decision, not an oversight (see the collectors'
own docstrings).

---

## 4. Credentials & external-source status (check before assuming a source works)

| Source | Credential location | Status as of 2026-07-17 |
|---|---|---|
| screener.in | `SCREENER_EMAIL`/`SCREENER_PASSWORD` in `~/repos/global-stock-screener/.env` | **Blocked** — hard block hit at ticker 502986 during a full-universe run (232/8,944 collected before block); confirmed still blocked on retest (`ABBOTINDIA` returns empty even in a fresh session) |
| NSE (`collect_nse_results.py`) | None needed (public API) | **Blocked** — domain-wide WAF 403 "Access Denied", confirmed on an unrelated endpoint (`quote-equity`) too, not specific to the results endpoint. 403/1,679 collected before the block (two prior false-block bugs already fixed: (1) bond/NCD tickers like `07AGG`/`0KFL25` clustering at the alphabetical start, not caught by `screener_history_collector.py`'s `is_non_equity()` regex — fixed with a liquidity gate; (2) Gold-ETF tickers like `GOLDBEES`/`GOLDETF` clustering mid-alphabet — fixed with a name-based filter + raised circuit-breaker tolerance (15→40)) |
| yfinance | None needed | **Working**, not blocked, confirmed across US/India/Japan/Korea |
| DART (Korea) | `DART_KEY` in `.env` | Working (used by `earnings_dates_dart.py`) |
| FINRA / SEC EDGAR (US) | None needed, just a declared User-Agent | Working |
| Trendlyne | `TRENDLYNE_SESSIONID`/`TRENDLYNE_CSRFTOKEN` in `~/BazaarTalks/.env` — user must extract manually from browser | Not attempted (would only give a live snapshot anyway, see §2b) |

**Recurring lesson**: when a collector aborts with "N consecutive tickers
returned nothing," don't assume it's a real host block — check what those
specific tickers actually are first. Two of three aborts hit in this
program were universe-composition bugs (non-equity instruments), not real
blocks. Verify with a fresh-session direct test on a KNOWN-GOOD, definitely-
has-data ticker (e.g. `ABBOTINDIA`, `RELIANCE`) before concluding it's a
genuine block.

---

## 5. Postgres warehouse

`market_data` database, `psql -h /tmp -U umashankar -d market_data` (peer
auth, no password; Postgres 16, confirmed running). Star schema:

| Table | Role | Notes |
|---|---|---|
| `markets` | Dimension | 8 rows: india=1, usa=2, uk=3, germany=4, europe=5, japan=6, korea=7, china=8 |
| `stocks` | Dimension | `UNIQUE(ticker, market_id)`, **bare tickers only** (no `.T`/`.KS`/`.SS` suffix — strip before joining) |
| `ohlcv_history` | Fact (pre-existing) | 2,058,800 rows total; india=1,233,718, china=825,082, **usa/uk/germany/europe/japan/korea = 0** |
| `fundamentals` | Fact (pre-existing) | Current-snapshot only, one row per stock, no date column — not PIT, don't use for backtesting |
| `fact_screener_signal` | Fact (built v8) | 3,860,427 rows — usa 1.38M, china 902K, japan 755K, korea 464K, india 360K. `UNIQUE(stock_id, signal_date, screener)`, `ON CONFLICT DO UPDATE` |
| `fact_short_interest` | Fact (built v8) | 97,555 rows, usa only. `UNIQUE(stock_id, settlement_date)` |
| `fact_insider_transaction` | Fact (built v8) | 204,977 rows, usa only. `UNIQUE(accession_number, stock_id, trans_date, trans_code, trans_shares, trans_price_per_share)`, `ON CONFLICT DO NOTHING` (immutable filings) |

DDL: `warehouse_schema_signals.sql`. Loader: `load_signals_to_warehouse.py`
(handles ticker-suffix stripping + stock_id resolution/upsert, uses
`psycopg2.copy_expert` staged through a temp table, not row-by-row).

No TimescaleDB. `duckdb` module only in `/usr/bin/python3`, absent from
project venvs — not the warehouse anyway, Postgres is authoritative.

---

## 6. Established mandatory conventions (apply to any NEW collector/screener)

1. **`min_price` floor on every price-crossing screener**, calibrated per
   market's actual price level (not blindly reused as $5 USD) — US $5,
   India ₹5 (kept unscaled, documented reasoning in-file), Japan ¥100,
   Korea ₩1,000, China ¥2. This bug alone has been independently
   re-discovered and fixed **five separate times** across this program
   (v3, v5, v8 US ×4 screeners, and would have recurred in every cross-
   market replication if the fixed functions hadn't been imported directly
   rather than reimplemented).
2. **Split-day exclusion**: day-over-day % change vs. known split ratios
   (±3% tolerance), applied once in `_flag_split_days()`, reused by every
   downstream screener AND the benchmark.
3. **Verify `filed` has real variance** before trusting any fundamental
   screener — `(filed − fy_end).std() == 0.0` means it's fake. See §2.
4. **Smoke test on ~200 symbols before a full run.** Then, separately,
   **sort the full run's excess-return column descending and eyeball the
   top 10-15 rows** — this is the only check that catches rare tail
   contamination a small smoke sample won't (proven: a handful of corrupt
   rows out of 1.4M dragged the US v8 headline mean from a realistic -6.7%
   to a fabricated +644%).
5. **A `nohup ... &` background launch's own "completed" notification only
   means the launcher command returned** (the shell forked and moved on)
   — it does NOT mean the actual long-running process finished. Always
   verify with `ps -p <pid>` before trusting a background "done" signal.
6. **Don't assume a scraper abort is a host block** — see §4's recurring
   lesson.

---

## 7. Open item

Build a yfinance-`earnings_dates`-based PIT fundamentals collector
(§2a) to replace the NSE/screener.in approach for India and fix the fake-
date problem for Japan/Korea/China in one pass — the clear best next step,
not yet started.
