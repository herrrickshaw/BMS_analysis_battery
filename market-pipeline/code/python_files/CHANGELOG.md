# CHANGELOG

Decisions and material changes to the pipeline, newest first.

**What belongs here:** a change that alters what the pipeline *produces* or what
a number *means* — a corrected signal, a new data source, a changed threshold, a
path or store that moves. Also the decisions themselves: what was chosen, what
was rejected, and why, so a future reader can tell a deliberate trade-off from an
accident.

**What does not:** refactors, formatting, dependency bumps, anything already
legible from `git log`. If the output is byte-identical and no number changed
meaning, it does not go here.

**Corrections are entries too.** Several below record findings that turned out to
be wrong. A changelog that only lists successes teaches nothing about how the
mistakes were made, and the mistakes here have repeated.

---

## 2026-07-21 (evening, collection)

### `--refresh-thin` was queueing the collector's own good data for re-fetch

(in `global-stock-screener`, commit `45afa1d`)

Its "usable" test required `source == "screener_in"`, but rows written by the
current collector path carry a **null** source. So 201 fully-populated tickers
— cfo 94.7%, borrowings 88.3%, median 10 fiscal years — were classed as thin and
queued for re-fetch. screener.in hard-blocks after roughly 50–155 requests per
session, so that is two entire sessions spent re-downloading data already held.

**Decision: drop the source condition entirely.** It was standing in for "not a
yfinance-only row", and cfo presence already establishes that (yfinance supplies
cfo on 2.9% of rows). Usable 281 → 524; re-fetch 1,575 → 1,332.

### Collection state — blocked, and the trickle is the only way forward

| | start of session | end |
|---|---|---|
| store | 8,429 rows / 1,846 tickers | 8,668 / 1,860 |
| complete-path tickers | 193 | 220 |
| ≥5 fully-populated years | 94 | 120 |
| panel tickers per rebalance | 108 | 135 |

The refresh run **aborted at 19 tickers** on a hard block; the circuit breaker
behaved correctly. The budget was already spent by the earlier concurrent
session (see above), so this is a self-inflicted ceiling for today rather than a
new limit.

⚠️ **The panel is still statistically thin.** Forward-return coverage is 60–110
firms per rebalance year, not the ~300–600 needed for the factor comparison to
separate signal from noise. Any factor result quoted off this panel remains
directionally suggestive at best — the same caveat as before, now with 135
tickers instead of 108. The launchd trickle is the mechanism that closes this,
over days, not in one session.

---

## 2026-07-21 (evening, post-close run)

### `technical` now capped at 5 per market — wiring it everywhere broke the watchlist

Direct consequence of wiring `breakout_quality` into all five scanners. The
post-close mailer returned **2,110** technical passes (US 1,044, JP 766, EU 185,
KR 110) and pushed the watchlist from 775 rows to **2,703** — a list nobody can
act on.

**The filter is not broken.** 2,110 of ~15,000 names is a ~14% hit rate, which
is what a grade-A/B breakout screen should return. It was never a shortlist; it
only looked like one while Korea was the sole market emitting `Quality_Grade`.

**Decision: rank and cap per market, not globally.** Grade alone is too weak a
bar (grade A is still 595 names/day, and daily intake compounds). A *global*
top-N would hand the list to whichever market scanned the most names — the Korea
skew again, pointed the other way. So: grade A, ranked by quality score, top 5
per market. 2,110 → 20, scores 90–100, evenly split across EU/JP/KR/US.

The ledger still records **every** pass (2,369 entries) — nothing is lost for
analysis. Only watchlist intake is bounded. Watchlist went +14 instead of +1,928.

⚠️ India contributed no technical signals: its scan step `[1/9]` failed again
this run, so `harvest_technical` had no India workbook to read.

### Do not run the screener.in collector alongside the mailer

The post-close brief failed validation with 3 of 8 sample stocks skipped on
`http 429`. Cause: a screener.in collection session was running concurrently,
and the mailer validates prices against the same host. Self-inflicted rate limit.

The collection also produced **zero rows** in five minutes (store mtime
unchanged) — so it contributed nothing while still degrading the brief. Worst of
both. Sequence these two against screener.in; never overlap them.

---

## 2026-07-21 (evening)

### 🔴 The India F-score is out of EIGHT, not nine — `f6_curratio_up` never fires

`f6_curratio_up` evaluates on **0.0%** of panel rows. `f_tested` maxes at 8.
Every "Piotroski score" in the India panel is therefore out of 8, and an `F≥7`
filter here does not mean what `F≥7` means in the literature.

This is **structural, not a bug to fix in the mapping.** screener.in's Data
Sheet balance sheet is `Equity Capital / Reserves / Borrowings / Other
Liabilities / Total` against `Net Block / CWIP / Investments / Other Assets /
Total` — there is no current-vs-non-current split, so the current ratio has no
input path. Confirmed: neither `screener_history_collector.py` nor
`screener_in_auth.py` references `current_assets` or `current_liabilities`
anywhere.

Two consequences for any factor result quoted from this panel:
- Cross-study comparisons must say "8-test F-score", or they overstate
  strictness (7/8 is a higher bar than 7/9).
- `f8_margin_up` also only evaluates on 55.2% of rows, so the effective test
  count varies by firm-year. `f_tested` is already stored per row — use it as a
  denominator rather than assuming 9.

**Not fixed.** Getting F6 would mean sourcing the current-asset split from a
second provider per ticker, and the store shows why that is not free: see below.

### The two fundamental sources never overlap per ticker

`cache_seed/fundamentals_history/IN.parquet` holds 1,846 tickers / 8,429 rows,
but the factor panel builds from only ~108. Not a gate that is too strict — the
sources are complementary in aggregate and disjoint per name:

| source | rows | cfo | borrowings | total_assets |
|---|---|---|---|---|
| `screener_in` | 2,808 | 99.3% | 0.0% | 0.0% |
| `yfinance` | 3,769 | 2.9% | 0.0% | 98.9% |
| `None` (current collector) | 1,848 | 94.7% | 88.3% | 53.5% |

Tickers carrying **both** `screener_in` and `yfinance` rows: **0**. So the
281 screener-only names have cash-flow but no balance sheet, and the 1,443
yfinance-only names have the reverse; neither group can pass the panel gate.
Only the current collector's path produces rows complete enough to use — 193
tickers, median 10 fiscal years, of which 94 have ≥5 fully-populated years.

**Decision: expand by re-running the current collector, not by repairing old
rows.** A merge across the two legacy sources would need per-ticker fiscal-year
alignment between two providers with different restatement policies, and would
silently mix vintages inside one firm-year. Re-collecting produces one
provider's view per row, which is the thing a point-in-time panel requires.

---

## 2026-07-21 (later still)

### `breakout_quality` wired into all five scanners

Fixes the coverage defect recorded below. India, US, Japan and Europe now emit
the ten `breakout_quality` columns, so `harvest_technical()` can see them
instead of skipping them.

**Decision: one shared helper, not four copies.** Added
`breakout_quality.row_fields(df, price_round)`, mirroring the existing
`golden_cross.row_fields` idiom, and migrated Korea onto it too. Four pasted
copies of the same block is how two implementations drift apart, and this
repo has already paid for that once.

`price_round` is the only per-market difference: 0 for JPY/KRW where a decimal
on a price is noise, 2 for INR/USD/EUR. Everything else rounds identically.

**Two things found while doing it:**

*Korea's inline block had a latent bug.* It guarded with
`round(q["rel_volume"], 2) if q.get("rel_volume") else None` — falsy for a
genuine `0.0`, so a real zero became `None` in 15 of 353 sampled rows. Verified
before migrating that the signal-bearing fields (`Quality_Grade`,
`Above_EMA50`, `EMA50_Rising`, `Recomputed_Signal`, `Actionable`) are identical
across old and new; only `Rel_Volume` and `Body_Pct` change, and only where the
true value was zero. Korea's *signals* are therefore unaffected by the
migration.

*The import fallback returns keys, not `{}`.* An empty dict would omit the
`Quality_Grade` column and silently remove that market from the technical
filter — reproducing the exact bug being fixed. Returning all ten keys as
`None` means a row fails to qualify rather than a market disappearing.

**Verified end-to-end**, not just by import: a real 60-ticker US scan emitted
all ten columns with a sane grade spread (A 1, B 24, C 13, D 22), and
`harvest_technical()` picked up 11 US signals where it previously saw zero.
The test workbook was then deleted — being the newest US scan, it would have
had the mailer harvest signals from a 60-name universe.

⚠️ **India, Japan and Europe emit these columns only after their NEXT full
scan.** Their current workbooks predate this change, so the harvester still
sees Korea alone until then. The watchlist stays Korea-skewed in the meantime;
that is expected, not a regression.

---

## 2026-07-21 (later)

### `technical` filter can only ever fire for Korea

The 15:19 mailer recorded 110 `technical` passes, all Korean, and pushed +101
names into the watchlist — taking KR from 3 signal names to 110, the largest
block in the book. This is **not** a signal about Korea.

`harvest_technical()` skips any market whose scan lacks a `Quality_Grade`
column, and only the Korea scanner emits it:

| market | latest scan | `Quality_Grade` |
|---|---|---|
| IN | `indian_full_scan_20260721_1336` | no — skipped |
| US | `us_full_scan_20260721_1513` | no — skipped |
| **KR** | `korea_market_scan_20260721_1518` | **yes** |
| JP | `japan_market_scan_20260721_1517` | no — skipped |
| EU | `european_market_scan_broad_20260721_1515` | no — skipped |

**Decision: recorded, not silently accepted.** The filter's conjunction
(grade A/B ∧ above EMA-50 ∧ EMA-50 rising ∧ recomputed `BREAKOUT_BUY`) admits
4.3% of Korean names, which is a sane hit rate — the defect is coverage, not
threshold. Until `breakout_quality` is wired into the other four scanners, any
cross-market comparison of `technical` is measuring instrumentation, not
markets. **Not yet fixed.**

### `symbol_master` wrote 21,902 rows to the stale tree — during a live run

`symbol_master.py` used `os.environ.get("MARKET_CACHE", ~/Downloads/...)`.
`mailer.sh` does not export `MARKET_CACHE` (only the plists do), so the 15:19
mailer wrote the symbol master to `~/Downloads/market_cache` while every other
step of the same run read the live tree.

### Semgrep rule 6 exemption removed — it was hiding the bugs it existed to find

The rule exempted anything inside `os.environ.get("MARKET_CACHE"/"BHAV_CACHE",
...)`, on the assumption that reading the env var made a line safe. Backwards:
the **default** is the hazard. Removing the exemption immediately surfaced 10
further real findings, including `market_data_cache.py` — the file whose
hardcoded path caused the original nightly US-scan `PermissionError` that
started this work — plus `liquidity.py` and `ohlcv_cache.py`.

**Decision:** a filter that excludes the cases a rule exists to find is worse
than no rule, because it reports zero findings and reads as a clean bill of
health. Blocking count went 0 → 10; that is the rule working, not a regression.

### Re-running the mailer for past dates: rejected as unsound

Asked to re-run the mailer for the days when data was stale. **Not done, by
decision.** No scanner accepts an as-of date; they read the latest bar, and for
US/JP/KR/EU they fetch live from yfinance rather than reading persisted history.
Generating a "17 July brief" from data through 20 July would use bars that did
not exist on the 17th — lookahead, producing picks that cannot be falsified.

The ledger also shows there is nothing to recover: every date from 13–20 Jul
holds *only* `golden_cross_hist` signals. Piotroski, debt-reduction, ROCE and
technical did not exist then. A backdated piotroski signal would need
point-in-time fundamentals as of that date, which no backfill can synthesise.

What the re-run *did* fix: `mailer.sh` never exported `MARKET_CACHE`, so the
13:52 manual run read the stale tree. The 15:19 run was the first manual run on
live stores. Both runs ended in a suppressed send — 13:52 because screener.in
was serving live intraday quotes, 15:19 because HDFCBANK drifted 2.18% against
screener.in with 11 minutes left in the session. **A sendable brief requires a
post-close run.**

---

## 2026-07-21

### Cache roots resolve from the repo, not `~/Downloads`

`data_registry` defaulted `MARKET_CACHE`/`BHAV_CACHE` to `~/Downloads/...` "so
interactive use is unchanged", with launchd overriding via plist. That split
every store in two, and the halves diverged silently:

| store | `~/Downloads` | `~/market-pipeline` |
|---|---|---|
| `market_cache` | 7,656 parquets, 20 Jul 04:59 | 7,657 parquets, **21 Jul 13:50** |
| `bhavcopy_cache` | 795M | 856M |

Scheduled runs wrote the second; anything run by hand read the first, a day or
more behind, with no error. **Decision:** defaults derive from `__file__`, so
they equal the plist value by construction rather than by two places agreeing,
and land outside TCC's reach. An override pointing back into `~/Downloads` warns
on stderr. Rejected the alternative of failing hard on an unset variable — it
would break interactive use for no gain once the default is correct.

Same fix applied to `bhavcopy_history` and `bhavcopy_store`, which had their own
`~/Downloads` defaults behind `os.environ.get`.

### Darvas `.fillna(0)` — sixth site found

`.fillna(0)` on a close series makes a missing bar a price of zero, and zero is
below every Darvas box bottom, so the whole universe reports `BREAKDOWN_SELL`
(Korea: 2,472 of 2,480 on 21 Jul). Five market scans were fixed at 05:09;
`us_market_screener.py` was a sixth site, missed because nothing schedules it.

**Decision:** trim to the last settled bar (`last_valid_index()`) and return
`NO_DATA` explicitly rather than falling through — falling through makes every
comparison `False` and silently reports `IN_BOX`, a different wrong answer
rather than a right one. Verified genuine `BREAKOUT_BUY`/`BREAKDOWN_SELL` still
fire, and that a breakdown series with a NaN tail now reads `IN_BOX` off the last
settled bar instead of `BREAKDOWN_SELL` off a zero.

### Two scripts were already broken, found via lint

- `build_market_seeds.py` — `OHLC_DIR` had `market_cache` doubled inside
  `data/`; the path never existed, so it raised `FileNotFoundError` on every
  run. Now resolves 7,657 parquets.
- `assemble_email.py` — `PF` pointed at `~/Downloads/code/python_files`, a stale
  copy of this repo, so its "latest" scan was `combined_US_20260714` while the
  live tree had `20260721`. Its scratchpad mirror pointed at a session UUID that
  no longer exists, so two of four write targets had been failing into a broad
  `except`. Outputs now go to `<repo>/reports`.

### Bug-history lint ruleset (`.semgrep.yml`, `lint.sh`)

Eight rules, each encoding a bug that actually shipped here, with the measured
cost in the message. **Decision:** deliberately *not* the generic AI-code
ruleset — `eval()` and `pickle` do not appear in this repo and never have. The
shared shape of the real bugs is that they are syntactically valid, semantically
wrong, and return a plausible number, which is why review kept passing them.

Blocking findings: 13 → 0. 22 WARNING-level findings from rules 3 and 5 remain
**untriaged** and are not enforced.

**Known gap:** rule 6 (`hardcoded-downloads-path`) exempts anything inside
`os.environ.get("MARKET_CACHE"/"BHAV_CACHE", ...)`, on the assumption that
reading the env var makes it safe. It does not — the *default* still pointed at
`~/Downloads`. The rule would not have caught either registry bug above. Not yet
fixed.

### Watchlist can be priced as-of a date (`--asof`, `--fetch-missing`)

Today's bar is an unsettled intraday tick until the close prints, so a mark
dated today is not comparable to an entry dated on a close. **Decision:** an
explicit `--asof` cap makes "priced to yesterday" a property of the run rather
than an accident of when the stores last updated.

`--fetch-missing` fills EU/JP/KR from yfinance. Those markets have **no
persisted price store** — their scans fetch live and retain nothing — so 50 of
651 names had no mark at all. Opt-in, because it reaches the network from an
otherwise pure reporting tool; unsuitable for a scheduled path as-is.

The summary now splits `n` from `held>0d`. 45 rows were added on the as-of date
itself, so their 0.0% is arithmetic, not performance; folding them into one
median made a barely-held list look like a list that went nowhere.

### Corrections — two findings of mine were wrong

**"India's LMDB is 3 sessions stale" — false.** I compared market-pipeline's
parquet against `~/Downloads`' LMDB. Two different trees. The real store was at
2026-07-20 throughout. The `_lmdb_behind_cleaned` guard added in response is
kept, but on honest grounds: the fast path genuinely returns before the LMDB
sync, so a crash between writing `cleaned` and syncing the LMDB would strand
them. That window is real; my evidence for it was not.

**Zero-day return bug reintroduced — by me, in the fix.** `_fetch_missing`
computed `pct_since` without the guard `build()` already had. Japan was shut
2026-07-20 (Marine Day), so 15 JP names entered on the 20th resolved entry *and*
mark to the same 17 Jul bar, and differencing a bar against itself printed a
confident `+0.0%`. This is a variant of the `+26.2% on a zero-day holding` bug
documented in the same file. Fixed; verified 0 rows now carry a mark preceding
their entry.

**Pattern worth naming:** three of the day's bugs were *cross-tree or
cross-store comparisons* that produced a plausible number instead of an error.
Neither a type checker nor a test catches these, because both operands are
valid — they just come from different places.

---

## Earlier

Not backfilled. `git log` before 2026-07-21 is the record; entries above start
from the first day this file existed.
