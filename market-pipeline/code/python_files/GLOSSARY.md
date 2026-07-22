# Glossary

Terms, thresholds and traps specific to this pipeline. Written down because most
of these were learned from a failure, and the failure is the useful part.

---

## Pipeline sections

| Section | Script | Cadence | Produces |
|---|---|---|---|
| **ingest** | `ingest.sh` | weekdays 00:15 | bhavcopy, OHLC cache, FX, symbol master, CCC screen |
| **mailer** | `mailer.sh` | weekdays 00:30 | 5 market scans → audit → validate → the brief |
| **modelling** | `modelling.sh` | Sat 02:00 | correlation clusters, factor panel, PPO weights, walk-forward |
| **factor_tests** | `factor_tests.sh` | Sat 06:00 | factorial screener grids, forward-return backtests |

Sections link through `data_index.py --require <section>`. The mailer gates
**hard** on ingest (a stale brief is worse than no brief); modelling and
factor_tests gate **advisory** (a day-old panel is still a fine research input).

---

## Core infrastructure

| Name | What it is |
|---|---|
| `data_registry.py` | THE one place that knows where data lives, who writes it, and how stale it may get. Import paths from here; do not re-derive them. |
| `data_index.py` | Live freshness report over the registry, and the inter-section gate. |
| `run_monitor.py` | Parses `[STEP]` markers out of section logs → per-step durations, slowest steps, per-section trend. |
| `repo_tracker.py` | Section wiring, unwired scripts, and the hardcoded-path audit. |
| `pipeline_lib.sh` | Shared `step()`/`run()`/`require_fresh()`/alerting for the four sections. |

---

## Liquidity

| Term | Meaning |
|---|---|
| **Structural floor** | $10k/day median turnover — below which a listing is not transacted in *any* market. Applies everywhere. |
| **Policy floor** | A floor a human chose. **Only India has one**: ₹1 crore/day (~$120k). |
| **Capital floor** | Deliberately *not* in the scans. A scan produces a universe; only the consumer knows how much money is being deployed. |
| **Liquidity_Tier** | Per-market **percentile** band (`T1_MOST_LIQUID` … `T5_MOST_ILLIQUID`) assigned by `adaptive_liquidity.retier()` as a post-pass over the whole universe. |
| **UNKNOWN tier** | Liquidity was *unmeasurable* (no Volume column, or no FX rate) — **not** the same as illiquid. The gate fails open on purpose so a broken feed reads as a broken feed, not as "nothing qualified today". |

> 🔴 **Unit trap.** India's `Median_Turnover` is in **RUPEES**; every other market's
> `Turnover_USD` is in **USD**. Comparing India's column to a USD constant is a
> unit error that *silently passes* — rupee turnover is ~87× the USD figure, so
> everything clears. `consistency_audit.FLOORS` now carries the currency per market.

> 🔴 **The edge is ILLIQUIDITY, not size.** A double-sort showed turnover~market-cap
> correlate at +0.797, which conflated them. LARGE+ILLIQUID is the strongest cell
> (+33.7pp). Capacity is ~$300–500k; the edge survives $100k and is dead by $10M.

---

## Data

| Term | Meaning |
|---|---|
| **Bhavcopy** | Official NSE/BSE end-of-day file. India lags one day **by design** — that is not staleness. |
| `assembled_long.parquet` | Raw appended bhavcopy. |
| `cleaned_long.parquet` | 🔴 **Load India from HERE.** NSE and BSE share bare symbols and 2,534 collide; the cleaned pivot resolves the exchange. Loading from `assembled` lets `ON CONFLICT` silently keep a random exchange's close. |
| **PIT** | Point-in-time. Fundamentals as they were *known* on the date, not as later restated. |
| **MARKET_CACHE / BHAV_CACHE** | Env vars that relocate the data tree. Set in the launchd plist. |

> 🔴 **TCC.** macOS denies launchd **all** access to `~/Downloads`. Anything rooted
> there is unreadable to the scheduled run. This is why the tree moved to
> `~/market-pipeline/` and why every path must resolve through the env idiom.
> `repo_tracker.py --paths` is the regression guard.

---

## Screeners

| Term | Meaning |
|---|---|
| **Darvas/Buffett** | 0–7 momentum + quality overlay. BUY ≥ 5, WATCH ≥ 3. |
| **Piotroski F-score** | Canonical 9-point fundamental quality score. |
| **ROCE block** | A **separate** 3-point block (level ex-cash >15%, 5y CV <0.30, trend). 🔴 Never merge it into the F-score — corr(F, ROCE) ≈ +0.24, so it *complements* rather than duplicates. |
| **CCC** | Cash conversion cycle; scraped from screener.in. |
| **Golden Cross** | 50-DMA crossing above 200-DMA. |

> 🔴 **US Piotroski is INVERTED** — high-F underperforms. Do not assume a factor
> ports across markets.

---

## Validation

| Term | Meaning |
|---|---|
| **Internal consistency** | The brief agrees with our own scan. Necessary, **not sufficient**. |
| **External validation** | `validate_brief.py` checks picks against screener.in before sending. On 2026-07-15 every internal check passed while the pipeline shipped a **seven-week-old** price; only screener.in disagreed. Failure **suppresses the send** and falls back to `--draft`. |
| **Cross-market audit** | `consistency_audit.py`. A market can look healthy alone and be the obvious outlier side-by-side. |
| **`\|\| failed (continuing)`** | Every step is guarded so one market cannot block the rest. The cost: a crash and a bad network day look identical. Read `[ALERT]` in the trailer, not the absence of errors. |

---

## Instruments (India)

ISIN prefix is the instrument-type key — `SctySrs`/`FinInstrmTp` do **not** filter these:

| Prefix | Type |
|---|---|
| `INE` | Equity |
| `INF` | Mutual fund / ETF |
| `IN0`–`IN3` | G-Secs / SDLs |

> 🔴 `LIQUIDSBI` (an ETF) once shipped as a golden-cross pick. The ₹1cr floor
> removes most non-equity without needing an instrument-type rule, but the ISIN
> prefix is the actual key.

---

## Reading a run

```bash
./ingest.sh && ./mailer.sh          # weekday chain
data_index.py                       # is anything stale, and who writes it
run_monitor.py                      # what ran, how long, getting slower?
run_monitor.py --slowest 15         # where the time actually goes
repo_tracker.py --paths             # path-drift regression guard
```

**`launchctl list` showing the job is not evidence it ran.** Check `runs =` in
`launchctl print gui/$(id -u)/<label>` — it read `runs = 0` for a job that had
never once fired.
