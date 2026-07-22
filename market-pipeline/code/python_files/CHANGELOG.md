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

## 2026-07-21 (night, sampling)

### 🔴 EVERY India factor result so far is an ALPHABETICAL sample

Found while checking why the news-convergence output was all A-names. The India
factor panel held 135 tickers:

    {'2': 1, '3': 3, '5': 1, '6': 1, 'A': 127, 'B': 2}

**127 of 135 begin with "A"**, and the list stops at `BAGFILMS`.

`screener_history_collector._universe()` returned `sorted(set(...))` and the
caller takes `universe[:limit]`. screener.in hard-blocks after ~50-155 requests
per session, so every session ever run collected an alphabetical PREFIX.

**This invalidates the factor work to date.** Piotroski, ROCE, debt-cycle and
every combination test was a statement about companies whose name starts with A,
presented as a statement about the Indian market. Worse, the panel growing
108 → 135 earlier today *looked* like progress while adding only more A's — the
sample appeared to improve while staying exactly as biased.

Alphabetical order correlates with nothing financial, which is precisely why a
truncated alphabetical sample looks random until the first letters are counted.
This is the **same defect already recorded for the US price panel** (an
interrupted alphabetical collection missing CME/CMI). Second occurrence, same
root cause, different dataset.

**Fixed** (`global-stock-screener` `b785dec`): the universe is ordered by symbol
hash. Deterministic — same universe, same sequence, so runs stay reproducible
and resumption still works via the `done` set — but uncorrelated with the
alphabet, so a session that dies early leaves a representative sample. Verified:
first 150 names span **28 distinct first letters, was 2**.

⚠️ The existing 220 collected tickers remain alphabetically skewed. The panel
only becomes representative as the trickle collects under the new ordering.
**Do not quote a factor result off the current panel.**

### `news_convergence.py` — do the headlines contradict the picks?

For each stock passing a filter, pull Moneycontrol/ET/Mint coverage and report
`CONVERGENT` / `NEUTRAL` / `DIVERGENT` / `NO_NEWS`.

**Decision: the useful output is DIVERGENCE, not convergence.** "The filter
picked it and the news is good, so the filter worked" is confirmation bias — it
would make every filter look good on a day the market rose. What earns its keep
is a technically immaculate stock carrying a fraud probe or an auditor
resignation, i.e. something public the filter cannot see. Only forward returns
can say a filter works; `signal_tracker.py` does that.

Two guards that materially change the output:

- **Stricter matching than `sentiment_pipeline`.** The RSS feeds are
  market-wide. The default matcher scored RELIANCE `POSITIVE` off two copies of
  *"Market wrap: Top gainers and losers on Nifty and Sensex today"* — a headline
  naming dozens of companies and characterising none. Here a headline counts
  only if the company is named in the **title**, market-wraps are excluded, and
  duplicates collapse. Recall traded for precision deliberately.
- **Red-flag terms outrank the average.** VADER is general-purpose: "SEBI probe"
  and "CFO resigns" score near-neutral in ordinary English, and those are exactly
  the headlines that matter. Three routine positives must not bury one auditor
  resignation, which is what averaging does.

`NO_NEWS` is its own category, never folded into `NEUTRAL`: 20 of 30 names had
no company-specific coverage, and "nothing bad was written" versus "nobody was
looking" are different facts.

### Export mined — little there for the mailer

The supplied 59MB export is **claude.ai web chats**; the pipeline engineering
happened in Claude Code, whose transcripts live in `~/.claude/projects/` and are
not in it. 39 of 180 conversations mention the mailer/pipeline, but the
moneycontrol references are all generic (Moneycontrol as a website for screening
or FII/DII flows) and the `convergence` hits are unrelated (Navier-Stokes,
policy convergence). No pipeline decisions recovered.

---

## 2026-07-22 (liquidity framing + staleness guard)

### The brief now says what its universe IS: high-liquidity picks

The fundamental screeners run on ~1,350 of ~7,800 listed Indian equities. The
missing ~4,500 are not a gap — they are removed by a deliberate ₹1cr/day
median-turnover floor applied BEFORE any fundamental test (measured funnel:
7,842 equities → 5,203 with enough history → ~1,400 clear the floor). The brief
previously implied this; it now states it outright: **liquidity is a screening
criterion alongside Piotroski and the rest**, and lower-liquidity names are
deliberately out of scope until their collection is reliable — at which point
they arrive as a separately-tagged tier, not mixed in.

Floor sensitivities, for when that day comes: ₹1cr → 1,480 names · ₹10L → 2,253
· ₹1L → 3,665. The cost/capacity work says the illiquid edge is real at retail
size, so ₹10L is the plausible next tier.

### Fundamentals staleness is now monitored, not assumed

"Collect regularly and avoid stale data" needs machinery, not intent:

- Both stores registered in `data_registry` (`fundamentals.in_annual`,
  `fundamentals.in_quarterly`, writer `fundamentals_offhours.py`, tolerance
  10d) — so `data_index` and the ingest gate report them like every other
  dataset. 10 days means the SCHEDULE broke, not that quarterly filings moved.
- The brief's coverage note shows the store's **median** age — median, not
  newest, so one fresh ticker cannot make 1,300 stale ones look current (the
  max-mtime bug, third appearance) — and switches to a bold STALE warning past
  10 days.

---

## 2026-07-22 (fundamentals — all four screeners store-served)

Phases 2-3 completing Phase 1. All four fundamental screeners now run from the
off-hours store with zero yfinance calls per store hit, so none throttle-truncate
alphabetically. Final coverage: 1,287 usable tickers, 26 first-letters, ~10%
A-share — the market's real distribution, replacing the 89-96% A the screeners
showed.

- **Piotroski** — bit-identical store-vs-live (8/8).
- **Coffee Can / Magic Formula** — never worse than live; MORE complete on 5 of
  13 tested. Needed 6 extra fields (equity, EBIT, FCF, capex, total debt, cash)
  and market cap computed from stored shares x the scan's price.
- **Bull Cartel** — bit-identical YoY quarterly growth (4/4); quarterly income
  statement collected alongside annual in the same fetch, stored in
  IN_quarterly.parquet.

**🔴 Finding: the live Stage-4 path was DEGRADED, not just truncated.** Chasing a
CoffeeCan mismatch (store 6/6 vs live 5/6 for EICHERMOT) proved the integrated
per-ticker fetch (statements + quarterly + info + fast_info, in a thread pool)
silently drops individual rows under load — e.g. a near-zero Long Term Debt —
so it scored tickers it DID process slightly wrong, on top of dropping later
tickers entirely. The store fixes both.

**Three bugs caught by verifying before shipping:** substring field-matching
(grabbed "Total Current Assets" 218B for "Current Assets" 56B); stale
statement-routing (new fields silently empty — now an explicit map + assert);
and the fresh-skip being annual-only (would never collect quarterly for an
annually-fresh name — now requires quarterly presence).

Fallback to the live path is intact throughout: a store miss is byte-identical
to before, so every change can only ADD coverage.

---

## 2026-07-22 (fundamentals coverage)

### 🔴 The A-bias was TWO bugs, not one — and the live scan was the bigger

Confirmed the brief's Piotroski/CoffeeCan/BullCartel/MagicFormula picks are
89-96% A-names, and isolated the cause precisely: the Darvas/GoldenCross picks
span the full alphabet (25 first-letters), but the FUNDAMENTAL screeners do not,
because fundamentals come from two paths that both truncate alphabetically:

  * screener.in PIT collector — blocked after 50-155 requests (already fixed,
    hash ordering).
  * the LIVE scan's Stage 4 — fetches one yfinance Ticker() per stock in
    PARALLEL, Yahoo throttles after ~250, and the survivors are the
    alphabetically-first. Measured: the Fundamentals sheet stops at BAJAJELEC;
    the fundamentals store is 161 usable tickers, 133 of them A.

### Off-hours multi-source collector + store-first Piotroski (Phase 1)

`fundamentals_offhours.py` pre-collects current fundamentals for the clean
equity universe (~1,348 names) from yfinance, hash-ordered, off-hours (weekends
+ weeknights), into a store the scan reads. Verified yfinance returns full
Piotroski inputs for the non-A names screener.in never reached.

The scan's `fundamental_scan` is now STORE-FIRST with fallback: a store hit costs
zero yfinance calls (never throttles) and computes Piotroski identically; a store
miss is byte-identical to before. Piotroski becomes alphabet-complete; the other
three screeners abstain on a store hit (they need mcap/EBIT/equity/quarterly not
yet stored) — Phases 2-3.

**Decision: bhavcopy is NOT a fundamentals source.** It is price data; listing it
would create a field that never populates. yfinance is primary; screener.in is
optional deep-history enrichment.

### Verification caught a field-extraction bug before it shipped

First wired run: store f=5 vs live f=4 for AADHARHFC. The collector's `_pick`
used SUBSTRING matching, so "current assets" matched "Total/Net/Other Current
Assets" (218B stored vs 56B real) and "borrowings" grabbed "Total Debt" (187B)
where the scan reads "Long Term Debt" (152B). Fixed to exact-match-first; field
renamed borrowings->long_term_debt. Re-verified 8/8 tickers now score
identically store-vs-live. The wrong store was cleared and re-seeded.

⚠️ Coverage fills over hours/days as the collector runs. A self-correcting
caveat on the brief's fundamentals section states current coverage so an A-heavy
list is not read as 'the best fundamental names in India'.

---

## 2026-07-21 (night, correction)

### 🔴 CORRECTION: the daily mailer was never failing — I was breaking it

Recorded because the earlier entries in this file assert the opposite, and a
changelog that keeps a wrong diagnosis is worse than one with a gap.

Full run history for 2026-07-21:

| run ended | failed steps | outcome |
|---|---|---|
| 04:10 | 0 | **SENT** |
| 06:59 | 0 | **SENT** |
| 13:52 | 0 | not sent — market open, screener.in serving live quotes |
| 15:19 | 2 | not sent |
| 16:39 | 2 | not sent |
| 18:56 | 2 | not sent |
| 19:04 | 2 | not sent |
| 19:12 | 0 | **SENT** |

The scheduled runs sent cleanly. Every failure was a manually-invoked run.

**Cause: `pipeline_lib.sh` resolved its interpreter from the caller's PATH**
(`PY="${PY:-python3}"`). The launchd plists put `.venv/bin` first, so scheduled
runs used the venv; a plain shell used `/usr/bin/python3`, which lacks
`bseindia`. `[1/9] India full screener scan` therefore died instantly in manual
runs only — and since no fresh India scan was produced, the brief validated a
stale **13:36 intraday** workbook, where HDFCBANK showed 777.6 against
screener.in's 761.0 close. That identical 2.18% "mismatch" recurred in four
consecutive runs and read as a data fault; it was a wrong-interpreter fault.

Consequences: four wasted runs, five spurious failure-alert emails, and a
defect recorded against `[1/9]` that never existed.

**Fixed:** `pipeline_lib.sh` resolves `$HERE/.venv/bin/python` by construction,
warns if it is absent, and still honours an explicit `$PY`. Same defect class as
the two cache trees and the two bhavcopy stores — one thing, two resolutions,
silent divergence — and the third time today it produced a confident wrong
answer rather than an error.

**Validation was right every time.** Widening the tolerance to clear HDFCBANK
would have shipped an intraday brief as a daily one.

---

## 2026-07-21 (night)

### Signal tracking now works — it was structurally empty before

`--report` printed "no aged entries could be priced" and returned nothing. Not a
data outage: it required `price_at_signal`, and **all 121 trackable entries were
backfilled `golden_cross` rows that never recorded an entry price**. The report
could never have produced a number, and said so in a way that read like missing
data.

Applied the watchlist model — the same `basis` distinction `watchlist_pnl`
already uses:

- `signal-price` — recorded when the filter fired (a record)
- `panel-close` — the panel's close on the signal date (an estimate: no fill, no
  slippage, and for a backfilled row only *close to* what the brief quoted)

All 138 currently-tracked rows are `panel-close`. That is labelled on every row
and called out in the summary rather than presented as measured entry prices.

**Skips are now counted and named, not silent.** 1,152 entries are stamped today
and have no forward bar — that is what forward tracking *means*, so it is
reported as "too early, by design" rather than dropped.

### 🔴 The India benchmark was filtered out of its own panel

`vs mkt` was `nan` for every India entry. `NIFTYBEES` is in the panel but its
last bar is **2026-07-13**, a week behind the panel itself: it is an ETF (ISIN
prefix `INF`) and the equity-only bhavcopy filter — added after an ETF shipped
as a golden-cross pick — stopped updating it. The benchmark was removed as
collateral damage from a correct fix.

**Decision: fall back to the panel's cross-sectional median, and label it.**
That is a *different* benchmark — equal-weighted market, not NIFTY 50 — so
substituting it silently would misrepresent what the comparison is. India now
reads +0.67% vs mkt / 62% win, with the substitution printed above the table.

### EU/JP/KR tracking via `--fetch-missing`

Those markets have no persisted panel, which hid 1,119 of the ledger's entries —
most of the shortlist. Opt-in yfinance fetch, reusing the watchlist's symbol
resolver (Korea's codes need zero-padding to six digits plus a .KS/.KQ board
suffix; Japan needs .T).

Entries stamped today are filtered out **before** the network calls: 1,069 of
the 1,119 could not have a forward bar, so fetching the group would mean 1,119
sequential requests to track 50.

No benchmark for these markets — there is no index series in any local store,
and synthesising one from the handful of shortlisted names would compare each
signal against itself. `xret_pct` stays NaN and shows as `nan%`.

Output: `reports/signal_tracking.csv`, one row per shortlisted name with
`signal_date`, `as_of`, `held_days`, `entry_used`, `basis`, `ret_pct`.

⚠️ 138 tracked rows over 3-6 days is a diary, not a result. Every row is
`golden_cross` — the newer filters were all stamped today.

### Trickle confirmed working

`runs = 1`, exit 0, logged at 17:30:06. The earlier `runs = 0` was the counter
resetting when the job was booted out and back in — **not** the never-fired
failure seen on the daily-pipeline job. The 17:30 run was refused (screener.in
still blocking this machine after the 16:45 hard block); gate unchanged at 143.

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

⚠️ India contributed no technical signals this run. **Correction (see the
`night` entry): this was NOT a pipeline defect.** `[1/9]` failed only in
manually-invoked runs, because of the interpreter split — the scheduled 04:10
and 06:59 runs completed with 0 failed steps and sent normally.

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
