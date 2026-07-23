# CHANGELOG

Decisions and material changes to the pipeline, newest first.

## 2026-07-23 — Annual IMD rainfall refresh as [18/18] (self-guarded no-op)

- **`~/iudx-flood-collector/annual_refresh.py` appended as [18/18]** — each
  Jan/Feb, once (marker file), re-pulls the two newest IMD 0.25° grids
  (prior year revised + finalized year), rewrites the 12-city daily series,
  recomputes metrics/charts, mails the summary, pushes kalki_flooding.
  DECISION: guard lives inside the script, pipeline calls it daily — a
  standalone January launchd date would fire while the Mac sleeps (the
  market_ingest lesson, third time). DECISION: refresh re-pulls TWO years —
  IMD revises its real-time product after the fact, so last year's
  "final" numbers change; single-year refresh would freeze the revision.
  E2E-tested 2026-07-23 with --force --no-mail (dup-free rewrite verified,
  test marker removed so Jan-2026 still fires).

## 2026-07-23 — IUDX flood-sensor collector rides the pipeline as [17/17]

- **`~/iudx-flood-collector/collector.py` appended as step [17/17]** — archives
  India's 77-sensor urban flood fleet (Pune 46 / Chennai 27+3 / Kalyan-Dombivli 1)
  from IUDX into `flood.duckdb`. DECISION: ride `daily_pipeline.sh` instead of
  its own launchd job — a separate schedule would fire while the Mac sleeps
  (the market_ingest lesson; same reasoning as [16]). DECISION: keep it in the
  run even though it archives 0 rows today — all 3 provider access requests are
  PENDING (filed 2026-07-23 via ACL-APD), and the daily run doubles as the
  approval-checker: first run after approval starts archiving with no config
  change. Rejected alternative: wait for approval before scheduling — that
  turns "approved" into a fact someone must notice manually.

## 2026-07-23 — Korea fundamentals from DART; J-Quants V2 validator; EC2 gap-fill

- **Korea joins financial_ratios via official DART filings** (`dart_kr_store.py`
  → `fundamentals/KR_current.parquet`, MARKETS gained `korea`). Shares from
  `stockTotqySttus` (unlocks mcap/pe/pb). DECISION: `ebit`/`fcf`/`total_debt`
  left NULL — the single-account endpoint has no borrowings/EBIT tags, and
  mapping total liabilities to "debt" would overstate D/E (provisions + deferred
  tax counted as debt). Rejected alternative: `noncurrent_liabs` as
  `long_term_debt` — same mislabeling, quieter. Absent beats wrong.
- **`jquants_validator.py` (new)** — validates JP panels against official JPX
  J-Quants **V2** (V1 is 410 Gone; V2 = `x-api-key` header, `/equities/bars/daily`,
  `AdjC`). DECISION: compares daily RETURNS, not price levels — our panels are
  yfinance dividend+split adjusted, J-Quants is split-adjusted only, so levels
  always drift by the dividend factor; returns isolate the real failure mode
  (missed splits → one-day >5pp divergence). Free-plan window 2024-04-30→
  2026-04-30; validator caps its window 13 weeks back so absence ≠ mismatch.
- **India "staleness" ≠ gaps**: all 2,573 ledger-stale India tickers have
  max(trade_date) in raw bhavcopy == ledger last_update — illiquid names that
  didn't trade. Don't backfill India off the ledger's stale count.
- **EC2 gap-fill collector** (i-0fb61188e3373794f): 10,257 tickers CN/US/EU/JP/KR/HK
  (incl. first-ever HK 10y backfill, 1,504 syms), yfinance batches of 20 with
  Pyth-oracle cross-validation (>1.5% close deviation flagged), 5-min logger →
  dropbox:market-data-ec2/. India excluded (NSE blocks AWS IPs).

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

## 2026-07-23 (latest: PIT event studies; NSE results API silently migrated)

### Bundle validation vs real funds/indices (user request)

bundle_validation.py + reports/bundle_validation.md: every bundle is compared
against the closest PUBLIC benchmark — SPDR sector ETF daily holdings for US
(with weights → constituent overlap, active share, HHI/concentration) and NSE
index constituent lists for India (membership + Nifty-500 check). MSCI MCP
was tried first: connected but UNENTITLED ("data access could not be
verified") — no index data without a subscription. JP/KR/EU have no free
constituent feed; skipped explicitly, never silently.

Result: **every US/IN bundle is a differentiated satellite, not a closet
index** — 0-1 of 4-10 names overlap the sector ETF/index, active share ≈100%
across the board. IN Financials: 8/10 names are Nifty-500 members yet only
1/10 sits in Nifty Financial Services — mid-cap financials the sector index
does not carry. Weight style is deliberately more concentrated (HHI 0.11-0.22,
25% cap) than cap-weighted ETFs (0.05-0.09) — satellite sizing, not index
mimicry. Interpretation: the screens are selecting off-benchmark; the bundles
COMPLEMENT index funds rather than replicate them, and validation would flag
any future drift toward closet indexing (verdict thresholds encoded).

### value_rerating — the screen the backtests earned

screen_value_rerating.py, pipeline step [13z/14] (runs BEFORE the mailer so
today's picks are in today's email): cheap vs own sector (within-industry PE
percentile ≤ 0.20) ∩ re-rating (12M ΔlnPE > 0), ₹1cr/day liquidity-gated at
source, top-15 rank-blend promoted to watchlist.csv as `signal` rows with
entry stamps. First run: 18 passers, 11 new — a PSU-bank re-rating cluster
(CANBK, UNIONBANK, KTKBANK, BANKINDIA), industrials, healthcare. Digest grew
a 💎 Value re-rating category (chip, section, why-parser). Body re-trimmed to
100 KB (card cap 5→4).

### PE anomaly backtests (India, 2017-2026) — both user hypotheses tested

backtest_pe_anomalies.py + reports/pe_anomaly_backtest.md. 1,458 NSE names,
109 monthly formations, PIT annual EPS (fy_end+90d lag), adjusted closes.
🔴 DATA TRAP found en route: fundamentals_history/IN.parquet mixes screener_in
rows (₹ crore) with yfinance rows carrying QUARTERLY magnitudes mislabelled
annual (TCS "FY26" = one quarter) — a 4x EPS error. Used
IN_screener_only_backup (pure screener.in, validated TCS EPS 120/133/136 ✓).

Findings (survivorship-biased levels; SPREADS are the statistic):
* **Sector-relative PE anomalies DO correct**: cheap-vs-own-industry Q1 beats
  rich Q5 monotonically — +0.85%/1M, +2.60%/3M, +5.26%/6M (de-overlapped
  t ≈ 2.5-2.9). Sector-level stretch corrects ASYMMETRICALLY: sectors at
  z<−1.5 vs own 36M PE history return +9.37% fwd-3M vs +6.96% neutral;
  rich-stretched sectors (+7.34%) barely lag neutral — buying beaten-down
  sectors pays, fading hot ones does not.
* **PE trend is MOMENTUM, not reversion (3-6M)**: 12M multiple-expanders beat
  compressors (fwd-3M +5.6/+5.2% vs +3.5/+2.7%) — even "hope rallies"
  (PE↑ EPS↓) beat "cheapening on delivery". Consistent with the standing
  India-is-momentum-friendly finding.
* **High PEs are EARNED on average**: subsequent-12M EPS growth is monotone
  in PE quintile (−37% cheap → +34% rich) — the market forecasts growth
  correctly, yet the value spread survives → systematic OVERPAYMENT for
  correctly-predicted growth. Level (cheap-vs-sector) and trend (re-rating)
  are separate, compatible signals; their intersection is an obvious future
  WATCHLIST_FILTER.

### Bundles report ALPHA, not absolute return

Takeaway adopted from the user-supplied active-vs-index literature (Weiner
2022): a bundle is an active mini-fund, so its since-formation return is only
meaningful NET of what simply owning the market's pick universe returned over
the same window. value() now computes each bundle's alpha vs an equal-weight
benchmark of ALL its market's picks, anchored to the same last-bar-≤-formation
close the members use (day 0 → α = 0 by construction, never n/a); bundles are
RANKED by alpha and the card prints "α +x.x% vs market".

### Model portfolios — the watchlist as a bundling tool

portfolio_bundles.py (user, 2026-07-23): single-stock picks are now bundled
into MUTUAL-FUND-STYLE portfolios, on the rationale that stocks which cluster
together on return behaviour keep behaving similarly — the bundle is the
tradeable thesis, not the individual name.

* **Clustering**: average-linkage hierarchical on 1−corr of 90d daily returns,
  per market, universe = above-floor BUY/HOLD picks with ≥60 bars; clusters
  kept at 4-10 names with intra-corr ≥0.30. First build: 14 bundles — e.g.
  "US · Energy" intra-corr 0.76, "IN · Financial Services" 0.63.
* **Weights**: inverse-volatility (60d), 25% cap, renormalised. REJECTED
  max-Sharpe/Markowitz (the ssrn-2747802 primer approach): mean estimates
  from 90 daily bars are noise and MV optimisers amplify it into corner
  solutions; inverse-vol needs no expected-return estimate at all. A future
  upgrade path is HRP-style recursive bisection or ML-predicted returns
  (s44199-025-00140-z), both of which slot into build() without changing the
  store schema.
* **Rebalance**: monthly, first pipeline run of the month (same exactly-once
  marker pattern as the Dropbox purge archive); daily valuation reports each
  bundle's 1d, since-formation return, weight DRIFT, and how many members
  have decayed into the sell zone.
* **Rationale per constituent** (procurement trail): which screen nominated
  it, its avg correlation to the bundle, its vol → weight. In the full
  attachment; the body shows fund-style cards (weights bar, drift, top-5).
* Caveat recorded: clustering is instrument-type-blind — one bundle grouped
  US preferred shares/CEFs (they DO co-move), and OILU (a 2x levered ETP)
  landed in the Energy bundle. The instrument-type gap already lives in the
  data-gaps section.

### Mailer redesigned: portfolio-free, strategy-first, data-gaps section

Full render() rewrite (user, 2026-07-23). The digest is now a RESEARCH
product, not a portfolio tracker:

* **Portfolio excluded** — held/sold rows dropped inside render(), so every
  caller gets the analysis view; hygiene (maintain/evict/purge) still runs on
  the full watchlist. Subject counts picks, not holdings: "+ 📊 Picks (442 ·
  281 buy-zone · 28 new)".
* **Strategy-first sections** (moneycontrol/INDmoney-style card UI: white
  rounded cards, change pills, NEW badges, filter-chip index row): 🎯 Thematic
  (buy-zone names inside the top-3 sectors by median 1d) · 🚀 Breakout (129) ·
  📈 DMA crossovers (149) · 🏆 Piotroski+ROCE · 🧾 Piotroski+debt · 🎰 Triple ·
  🔁 Recurring (28) · 🚄 Momentum · 🪫 RSI · 🧪 Justified (14). pick_category()
  classifies from status+note; validated against all 531 live notes (zero
  fell to "other"). Watch ideas (manual, not analysis) live in the FULL
  attachment only. Cards sorted buy-zone first, then 1d move.
* **🔍 Data gaps section** — computed fresh each run and mailed, because a gap
  that only lives in a log stays open: names with no price data (45),
  sector-unlabelled (103), liquidity-unmeasurable, rows staler than their own
  market's latest bar (36), signals missing entry dates.
* Body 98 KB (under the clip); zone tables from the previous layout are
  superseded — zone survives as a per-card chip + the buy-zone-first sort.

### Three charts in the morning email (treemap / RRG / breadth)

New watchlist_viz.py (matplotlib+numpy only), techniques from the open-source
screener ecosystem the user asked to mine (PKScreener itself is table-only;
the good viz lives around it):

* **Market map** — Finviz-style squarified treemap (openalgo-heatmap's
  approach, layout hand-rolled — no `squarify` dep): 5 market panels, tile
  area = median USD turnover (tradeability), colour = 1d move. Two bugs
  caught by LOOKING at the rendered image, not the code: the worst-aspect
  function compared an area against a length (every row degenerated into
  full-width strips), and unclamped panel widths let the US eat 2/3 of the
  figure.
* **Sector rotation RRG** — JdK RS-Ratio × RS-Momentum per sector basket vs
  market equal-weight benchmark (RRGPy-style approximation), 5-session
  smoothed tails, fixed 94-106 frame. Bug found the same way: normalising by
  the union calendar's first row NaN'd 320/322 India columns (names start on
  different dates) — normalise by each name's own first valid bar.
* **Breadth** — % of names above EMA50 per market, 30 sessions, straight out
  of the digest's own zone engine (breadth IS the zone series aggregated —
  zero extra data work). Korea's 20%→82% V-recovery is immediately visible.

Delivery: body references cid: inline MIME images (image parts do NOT count
toward Gmail's ~102KB HTML clip — body stays 99 KB); the full attachment
inlines them as data: URIs to stay self-contained. All three fail SOFT: a
crashed chart is a missing image, never a missing mailer. build_rows() now
exposes turn_usd per row and hands loaded frames to the viz pass so nothing
re-reads ~800 parquets.

### Sell-zone audit (user query) — data verified sound; held-row clock fixed

User challenged green rows in the Sell zone (CME +5.28% showing "43d/6").
Audit findings: (1) NOT a bug — the dot is the 1-day move, the zone is trend
position; CME closed 249.90 vs EMA50 254.18, GFI 33.15 vs 36.64 — green
bounces inside 2-month downtrends, exactly what the table exists to catch.
(2) KR "grade-A breakout" names with −20% 5d: warehouse series verified clean
(no dup dates / splits / scale breaks) — KOSDAQ names genuinely crashed
together on 07-16 and 07-20, and breakout_quality graded them A on 07-21 on
patterns the crash had invalidated; the sell-streak clock is correctly
cleaning up after the scanner. (3) Real bug fixed: held rows showed the
eviction countdown ("43d/6") though held names are never auto-evicted — now a
plain grey "43d"; sell-zone subtitle states both rules.

### Monthly Dropbox snapshot of the purged-watchlist archive

daily_pipeline.sh [16b]: on the first pipeline run of each calendar month,
watchlist_purged.csv is rclone-copied to
dropbox:market-data-archive/watchlist_purged/watchlist_purged_YYYY-MM.csv.
Exactly-once via a marker file (~/.local/state/watchlist_purged_last_archive);
rides the pipeline rather than owning a monthly cron because the pmset 00:25
wake guarantees the pipeline fires while a standalone monthly schedule on a
sleeping Mac is silently skipped. First snapshot (2026-07, 7.3 KB) uploaded
and verified on Dropbox at setup.

### Full digest rides as an .html attachment

render() grew a `full=True` mode (same rows, no caps: every zone row, all
sectors, untruncated whys) and send() grew attachment support (mixed/
alternative MIME). The morning email now carries the trimmed body (~98 KB,
under the clip) PLUS `watchlist_full_YYYY-MM-DD.html` (~330 KB) — attachments
don't count toward Gmail's clip, so the trim demotes detail a click away
instead of dropping it. --draft writes watchlist_full.html beside
brief_today.html.

### Digest trimmed under Gmail's clip line (442 KB → 99 KB combined)

Gmail clips HTML above ~102 KB; the combined email ran 442 KB. The digest is
now 41 KB (brief 57 KB → combined 99 KB) via visible-never-silent caps:
top-10 rows per zone table ("… N more in this zone (M held)" trailer), sector
clusters cut to strongest 6 + weakest 2 (both ends matter for rotation; the
elided middle is counted), record strips capped at 8, the ❔ zone collapsed
to a symbol roll, per-row "As of" column dropped (a date now appears ONLY on
rows staler than the digest — its original job), why-remarks truncated at 36
chars, and inline-style diet across dashboard/zone/strip rows. The margin is
~3 KB — if a busy brief day re-clips, next lever is attaching the full
untrimmed digest as an .html attachment (attachments don't count).

### One morning email (brief + digest); 3-week sell-zone purge

* **Combined email** — send_mailer.py now appends the watchlist digest below
  the brief (navy divider between) and extends the subject: "📈 Daily Market
  Brief — … + 📊 Watchlist (42↑ 32↓ of 126 held)". One send at [14/14], still
  behind the screener.in validation gate; step [18/18] removed. The digest
  section is failure-ISOLATED: if it throws, the brief still ships with an
  error strip where the digest would be. Hygiene (entry backfill, eviction,
  purge) now runs inside that call — once per morning, draft or send.
* **Purge rule (user)** — sell-zone streak > 15 sessions (~3 trading weeks)
  DELETES the row from watchlist.csv: evicted rows get purged once they cross
  it, and a live row that far gone skips the evicted halfway house entirely.
  Rows are archived to watchlist_purged.csv (append-only, purged_date column)
  before deletion — removal from the live list, never from history. held and
  sold rows are exempt. First run: 73 rows purged (INFY, ITC, ONGC, COALINDIA,
  VEDL, WIPRO among them), watchlist 883 → 810, evicted 114 → 41. Purges are
  announced in the 🗑 churn line.

### Digest rides the pipeline; smart-investing.in template

* **Trigger moved** — daily_pipeline.sh grew step [18/18]: the digest now
  sends the moment the pipeline finishes (~05:50 IST), reading data that is
  minutes old, instead of the fixed 07:00 n8n schedule. The n8n workflow
  `watchlistdigest001` was DEACTIVATED (kept, not deleted — reactivate in the
  n8n UI to fall back) and n8n restarted so the trigger deregistered. Two
  triggers would have double-sent.
* **Template** — restyled after smart-investing.in (user-supplied reference):
  deep navy #0B2F4A banner and section strips, ice #eef4f6 canvas, white card
  tables with #ecf1f6 header rows, teal #16a085 for gains/buy, #ca3433 for
  losses/sell, coral #F07857 hold strip. Palette lifted from the site's own
  CSS (styles_custom_2.min.css), not guessed from a screenshot.

### Watchlist mailer reorganised zone-first (supersedes the country sections)

Same day, second layout iteration on user request: recommendations are now
grouped by ZONE across all countries — 🟩 Buy zone first (one table, all five
markets, green-first within), 🟨 Hold below, 🟥 Sell at the bottom (with the
per-name eviction clock as a Streak column), ❔ Unmeasured last. The
per-country sections this replaces lived for exactly one send. Exited
positions drop to a muted strip — they are records, not recommendations.
Daily churn is surfaced up top: a "🆕 joined / 🪦 left" line names what entered
(signal_tracker/recurring_movers, nightly) and what the sell-zone rule evicted
this morning, so the watchlist reads as the living list it now is.

### Watchlist: country sections, entry tracking, buy/hold/sell zones, auto-eviction

* **Schema** — watchlist.csv grew `entry_date`/`entry_price`, stamped at ADD
  time by both writers (signal_tracker, recurring_movers) and BACKFILLED for
  existing rows from the dates already embedded in notes (398/883 rows).
  signal_tracker's hand-rolled 4-column csv.writer rewrite was replaced with
  concat+to_csv — the old writer would have silently sheared the new columns
  off on the next signal day.
* **Zones** — BUY (close>EMA20>EMA50) / SELL (close<EMA50) / HOLD (between),
  computed per bar from the price series. Deliberately STATELESS: the sell
  streak is read off the tail of the series each run, so there is no counter
  column for a missed run to corrupt. <25 bars → zone "?", never evicted.
* **Eviction (user rule)** — a watch/signal/justified name in the SELL zone
  >5 consecutive sessions flips to status `evicted` (row kept, note says when
  and why; `held` is never auto-exited — exiting the portfolio is not this
  tool's call). First run purged a 116-name backlog (AARON 222d, 476040.KQ
  133d in the sell zone) — expected: the rule never existed before. Hygiene
  runs inside the digest BEFORE rendering (--no-maintain to skip), so the
  email always shows the post-eviction list.
* **Mailer layout** — per-country sections (🇮🇳🇺🇸🇯🇵🇰🇷🇪🇺, green-first within
  each) with new columns: since-entry return + days held, zone chip with the
  eviction clock visible ("🟥 sell 3d/6"), plus a capped "🪦 Evicted" strip.

### Watchlist digest → dashboard (market × sector × liquidity × returns)

The per-name digest now opens with three aggregate views over every priced row
(815 of 883 — all tiers count; a sold name is still a market observation):

* **🌍 Market pulse** — per market: n, 🟢/⚪/🔴, median 1d/5d, a stacked 1d
  return-distribution bar (7 buckets, email-safe nested-table cells — no JS,
  no images), best/worst mover.
* **🏭 Sector clusters** — cross-market, hottest median-1d first; 1-name
  "clusters" suppressed. Sector labels come from a NEW incremental cache
  (market_cache/sector_map.json): JP is free+total from the japan scan
  workbook's TSE 33-industry codes (JPX code→name map hardcoded — it is
  stable and public), everything else via yfinance .info capped at 40
  lookups per scheduled run so the 07:00 mailer can never hang on a slow
  API; `--build-sectors` backfills the whole watchlist in one sitting
  (checkpoints every 25 fetches). Unresolved names group as "Unclassified"
  and retry next run. Taxonomies deliberately NOT unified: GICS "Industrials"
  and TSE "Machinery" stay distinct rather than being force-mapped wrong.
* **💧 Liquidity × returns** — per tier T1..T4/below-floor/unmeasured: median
  1d/5d, %green, distribution bar. Answers "is today's strength in names I
  can actually buy?"

### Watchlist digest: liquidity gate, green-first ordering, "why" column

The 07:00 digest (watchlist_digest.py, n8n-sent) previously ranked by status
tier (held > watch > signal > sold) and printed the raw machine note. Three
changes, all user-requested:

* **Green movers first.** Colour is now the PRIMARY sort (🟢 → ⚪ → 🔴 → ❔),
  status tier demoted to tie-break within a colour. The old "owning something
  is the reason to look first" ordering lost to "what moved today" — with 883
  rows the held block buried every mover below the fold.
* **Liquidity gate + tier column.** Median 60d Close×Volume in USD (FX via
  liquidity.py's cached rates), tiered on the SAME absolute bands the scan
  workbooks print (T1 ≥$12M … T4 above floor) so the label means one thing
  everywhere. Names below the floor (adaptive_liquidity.scan_floor: India
  ₹1cr/day policy, $10k structural elsewhere) move to a muted bottom strip —
  visible, not deleted. First run: 76 of 883 below floor, several of them
  green (EMAMIPAP +20% — exactly the untradeable-mover trap the gate exists
  for). Unmeasurable liquidity fails OPEN ("?"), matching scan_gate's ethos.
  REJECTED: percentile tiers (adaptive_liquidity.retier) — the watchlist is a
  biased ~880-name sample, and a percentile within it would not mean
  "percentile within the market".
  REJECTED: liquidity.scan_gate() directly — it derives currency from the
  ticker suffix, and the watchlist stores IN/KR/JP bare ('RELIANCE' would be
  read as USD, inflating turnover ~83x). Currency now comes from the suffix
  when present, else the market column.
* **"Why on the list" column.** Status + note expanded to a readable reason
  ("screener signal: grade-A breakout (breakout_quality) on 2026-07-21",
  "recurring mover x3 +5.2% since …"). Pre-ledger signal rows whose note is
  just a company name are labelled "source not recorded" rather than passing
  the name off as a reason.
* **KR/JP/EU rows finally price.** market_cache/ohlc/ is US-only (7,657 bare
  tickers), so every KR row — all 125 — had shipped as "not in cache" since
  the digest existed. Prices were local all along, in the year-partitioned
  warehouse signal_tracker reads (global-market-data/warehouse/ohlcv, fresh
  through today). _load_ohlc now falls back to it, loading each market once
  per run (last TWO year partitions, so early-January still has the 10 bars
  the turnover median needs; per-symbol filtered reads at ~0.4s each were
  rejected — 190 of them is minutes). Symbol spelling bridged, not rewritten:
  the watchlist keeps broker-style bare KR codes ('5360'), the loader tries
  '005360.KS' then '.KQ' (venue unrecorded), JP gets '.T'. Missing rows
  282 → 68 (KR 125→5, JP 65→1, EU 23→1); the survivors are genuine gaps —
  ETFs (EEM, SOXL, NIFTYBEES) and renamed/delisted names, correctly surfaced
  as ❔ rather than papered over. Digest runtime 3.8s → 8.6s.

### 00:30 run: 2 steps failed on a path both scripts had already abandoned

ingest (market_ingest.py refresh_symbol_names) and ratios (financial_ratios.py)
both tracebacked reading `~/Downloads/market_cache/symbol_master.parquet` —
`Operation not permitted`, the TCC/launchd-vs-Downloads failure mode this
pipeline migrated away from on 2026-07-16. Both scripts still HARDCODED the
Downloads copy for symbol_master even though the plist exported
MARKET_CACHE=~/market-pipeline/market_cache. Fixed same morning (04:51): both
now honor $MARKET_CACHE with the live tree as default. Everything else in the
run succeeded — brief validated against screener.in (6 names agree) and sent.

### The XBRL × CA × bhavcopy join is live (pit_event_studies.py)

Three fully point-in-time India studies on adjusted prices, abnormal vs daily
market median, broadcast-timestamp anchored (after-15:30 -> next trading day):
1. PEAD on 64,263 filing-dated events, announcement-return quintiles within
   quarter: Q5−Q1 CAR63 spread only +1.09% — announcement-sorted PEAD is WEAK
   in India. 🔴 levels are biased (+13% all quintiles: filing universe vs
   microcap-median benchmark + within-window survivorship) — spreads only.
2. Surprise-sorted PEAD: n=83 (parse coverage) — noise until queue drains.
3. Post-CA (722 splits/bonuses, 10y): +14.4%/+9.9% abnormal RUN-UP in the 20d
   before ex-date, ~0% after (47% hit) — the anticipation trade exists, the
   post-event trade does not. Follow-on: anchor on caBroadcastDate
   (announcement) instead of ex-date to see how much of the run-up is
   tradeable.

### DISCOVERY: NSE moved mainstream results to the integrated-filing API

The "2025 is thin" gap in results_index was not a collection failure: under
SEBI's integrated-filing framework (Dec-2024 quarter onward), mainstream
quarterly results stopped flowing to api/corporates-financial-results — the
legacy endpoint now returns only stragglers (59 rows for Oct-Dec-2025 where
7,349 exist). New endpoint found and wired in permanently
(api/integrated-filing-results, paginated size<=5000, schema mapped onto the
legacy one, seq ids prefixed IF): index now 151,928 filings / 2,794 symbols,
2025-26 at full ~7,300/quarter volume. Any NSE-results consumer that still
reads only the legacy API is silently losing post-2024 coverage.

## 2026-07-23 (later: regime conditioning; JP/KR scoring was silently broken)

### CORRECTION: JP/KR signals never scored — join bug, not stale panels

The "~2,000 JP/KR scores blocked on panel refresh" diagnosis was wrong on the
mechanism. `score_signals.py`'s `entry_px`/horizon joins used the BARE ledger
symbol ('9202') instead of the warehouse-suffixed `wh_symbol` ('9202.T'), so
JP/KR matched **0%** even against a fresh panel — masked because IN/US/EU
symbols are identical in both forms and the stale-panel note gave the zeros an
innocent explanation. Fixed: all price joins now use wh_symbol; JP/KR anchor
100% (1,568 + 223 signals). Lesson: a 0% match rate with a plausible excuse
still deserves a direct join test.

### Regime conditioning added (CIO-review gap #7)

`build_regimes.py` → `warehouse/regimes.parquet`: daily ^VIX + ^INDIAVIX with
POINT-IN-TIME tercile labels (each day vs its trailing ~3y window — expanding
full-sample terciles were rejected as lookahead). The scorer joins the regime
at signal date (IN→IndiaVIX, others→VIX) and SIGNAL_CALIBRATION.md now has an
outcomes-by-regime section. First read: IN Darvas BUY +21d hits 63% in
HIGH-IndiaVIX regime vs 43% in MID (excess +0.47% vs −0.55%); IN SELL works in
MID (56%) but inverts in HIGH (42%) — with the standing caveat that regime is
confounded with cohort timing until multi-month cohorts accrue.

### Panels: JP/KR/EU refreshed + refresh tooling

`refresh_panels.py`: incremental yf refresh of any non-IN warehouse panel
(auto_adjust=True, same convention as collection; always re-run
price_adjuster_global.py after). JP +45,218 rows, KR +36,019, EU +13,598 —
all three now end 2026-07-23. EU remains a COVERAGE gap: 1-year/852-symbol
panel matches only 12% of EU scan signals — a full EU collection (10y, scan
universe) is the fix, not a refresh.

## 2026-07-23 (adjusted-price propagation — and a premise correction)

### CORRECTION: JP/KR/CN/US panels were never raw Close

The account-wide "raw Close — splits fake returns" flag (claims.yaml, memory)
was overbroad. Verified in-panel: NTT trades ¥147 *before* its 25:1, Samsung
₩41k *before* its 50:1, NVDA $120 through its 10:1 — fractional closes and
back-scaled volume throughout. The non-India panels are yfinance-adjusted as of
their last assembly. The raw-Close defect (and the +12.2% fake illiquidity
premium it manufactured) was **India bhavcopy only**, already fixed 2026-07-21.

### What actually needed fixing: post-assembly residual breaks

Splits occurring after a panel's last full re-download appear as raw jumps
(7946.T ¥3,673→¥733 5:1, 8227.T 3:1, KR cluster 2024-26). New
`price_adjuster_global.py`: integer-ratio (≥2:1) + calm-day-band + per-market
TURNOVER gates → 86 candidates; each must be confirmed against the yfinance
split calendar before it may adjust → 8 confirmed (JP 2, KR 3, US 3; CN/EU 0).
Sparse overlays written to gmd `warehouse/ohlcv_adj/{JP,KR,US}/
corrected_symbols.parquet` — overlay-first read rule, no 700MB duplication.

**Rejected along the way (each caught by validation):** sub-2 ratios (3:2, 5:4
matched ordinary -20/-33% days — 3,002 false positives); share-count liquidity
gate (killed thin-but-real ¥13M/day 7946.T); snapping corrections to the yf
calendar date (panel rebases days before the official ex-date — scaling at the
calendar date corrupted 3 already-rebased rows; scale at the OBSERVED break).

**New yfinance bug (memorialised):** `history(auto_adjust=True)` serves
UNADJUSTED prices across recent JP/KR splits even when `.splits` knows the
event. Validate corrections by series continuity + calendar, never by comparing
windowed returns to yf's "adjusted" history (US is fine: 3/3 exact).

**Standing rule:** every panel re-assembly resets the residual set — re-run
`price_adjuster_global.py` after any full re-download (staleness trigger in
claims.yaml).

### cleaned_ohlcv 17,571-row surplus reconciled; loads now split append vs regenerated

Closes the "known remainder" below. Root cause confirmed: `cleaned_long.parquet`
is fully REGENERATED each run (pivot + clean_ohlcv can drop or alter historical
rows) and `assembled_long.parquet` is rewritten with dedup keep="last" (old-date
rows can be replaced or backfilled), yet `bhavcopy_to_db.py --incremental` only
ever appended rows with `trade_date > max` — so cleaned-away rows accumulated as
a permanent +17,571 surplus in DuckDB and its Postgres mirror, and `--verify`
FAILed every night as a false failure in daily_pipeline step [15].
**Decision: classify each source by write semantics, not one load strategy for
all.** New `REGENERATED = {bhavcopy_ohlcv, cleaned_ohlcv}` set: incremental
DuckDB load re-creates these from source; Postgres mirror rebuilds them on
row-count divergence via DELETE+INSERT — **not DROP** (rejected: the
`market_daily.ticker_freshness` view depends on `bhavcopy.cleaned_ohlcv`, DROP
would need CASCADE and destroy it; caught live on first run). `nse_raw`/`bse_raw`
keep true append-only loads (bhavcopy_raw_archive.py only ever appends days
newer than max TradDt), `nse_deep_ohlcv` too (static archive, no live writer).
Reconciled: pg cleaned_ohlcv 1,257,133→1,239,562, `--verify` exits 0 across all
five tables, ticker_freshness view intact (21,263 tickers).

### Raw 34-col bhavcopy archives have a writer again (nse.parquet/bse.parquet)

The 2026-07-21 "known remainder" is closed. The original builder of the raw
archives was an ad-hoc script that was never committed and vanished with the
~/Downloads tree — confirmed by searching every repo's full git history: the
only file that ever referenced `nse.parquet` is `bhavcopy_to_db.py`, a
*consumer*. `bhavcopy_raw_archive.py` recreates it: appends day-CSVs newer than
each parquet's max TradDt, full `--rebuild` available. **Decision: schema is
PINNED in code** (TradDt/BizDt date32, prices double, ids int64, empty UDiFF
cols string) rather than inferred per-run — inference from a day-CSV would type
all-NaN string columns as float and silently drift the arrow schema, breaking
bhavcopy_to_db's incremental date comparison downstream. Verified before
writing: the frozen archives are a plain per-day concat (row counts match
CSV-for-CSV, 34/34 cols, no filtering beyond what bhavcopy_history applies when
writing the day-CSVs), and post-append the pre-existing rows are byte-identical.
Wired into daily_pipeline step [15] *before* bhavcopy_to_db so the raw layer
rides the same schedule as everything else; registered in data_registry
(bhavcopy.nse_raw/bse_raw, max_age 1d) so going stale is now observable.
Backfill ran: pg.bhavcopy.nse_raw 620,332→632,987, bse_raw 1,284,825→1,312,525,
both current through 2026-07-21.

Known remainder, found during the same run: `pg.bhavcopy.cleaned_ohlcv` (and
its DuckDB twin) hold 17,571 MORE rows than today's `cleaned_long.parquet` —
the incremental load only appends by date, so rows the daily-regenerated
cleaned parquet later dropped are never reconciled. Max dates match; the
`--verify` FAIL is this, not the raw-archive fix.

### US fundamentals now collected from SEC EDGAR into the store (US_current.parquet)

`us_fundamentals_edgar.py` — the US analog of the India off-hours collector, but
sourced from data.sec.gov companyfacts: official, filing-dated, and rate-limited
at a documented 10 req/s instead of an opaque throttle. **Decision: EDGAR over
yfinance for the US** — yfinance is only in the India collector because India has
no official filings API; the US does, and yfinance's alphabetical throttle-bias
is the exact disease the store exists to cure. Store shape = `IN_current.parquet`
verbatim (same columns, capex stored negative to match the yfinance convention)
so every India-store consumer reads it unchanged. Restatement rule: comparative
prior-year figures in a newer 10-K overwrite the original (latest `filed` wins);
quarterly rows inside 10-Ks are excluded by a 330–380-day span filter — both
covered by `--self-test`. Wired into `run_fundamentals_offhours.sh` (1,500
names/session ≈ full ~7k universe in 5 of the 9 weekly slots, then staleness-driven).

### Correction: future-dated debt maturities minted phantom fiscal years (EDGAR)

First bulk run (1,500 names, 0 fetch failures, A-share 10.2%) surfaced it:
PMTV's 10-K reports LongTermDebt *repayments due 2026-2029* as instant facts
with future `end` dates, and the parser treated every instant end as a fiscal
year — the ratio table's "newest US FY" read 2029-12-31. Rule now: a fiscal
year that hasn't ended cannot have been filed; ends > today are dropped
(self-tested), and the 4 phantom rows were purged from the store. One ticker
this time, but the bug class is any company tagging maturity schedules with
bare debt tags.

### New: financial_ratios.py — one India+US ratio table

PE/PB/ROE/ROA/ROCE/D-E/current ratio/margins/FCF yield/CFO-to-NI/asset turnover/
revenue growth, per ticker, latest FY vs latest close (India closes from
`cleaned_long.parquet` — NSE precedence; US from `ohlcv_US.parquet`). Currencies
never mixed: every ratio is a pure number; `mcap_local` is in the market's own
currency by design. Outputs: `market_cache/fundamentals/ratios_latest.parquet`,
Postgres `fundamentals.ratios` (full replace — derived data, stores are truth),
`reports/financial_ratios.csv`. Validated against prior screener.in checks:
RELIANCE ROE 8.9% / ROCE 11.3%, TCS ROCE 56.3%. Re-priced daily in pipeline step
[15/15]; recomputed after each off-hours collection too.

### Decision: Dropbox (rclone) replaces GitHub LFS as the off-machine data store

`~/scripts/cloud_backup.sh`, pipeline step [16/16]. The LFS account budget is
exhausted, every rewritten parquet became a new permanent blob (no delta
compression), and only repo deletion ever frees space — the delete/edit churn
this replaces. Drive side: `market-data-archive/current/<tree>` exact mirror +
`history/<YYYY-MM-DD>/` where changed/deleted files are MOVED (never destroyed),
60-day history retention, weekly Monday `pg_dump -Fc` of market_data (last 8
kept). Trees: market_cache, bhavcopy_cache, cache_seed, global-market-data
cache_seed, ~/data (duckdb). lmdb dirs excluded — live memory-mapped stores
snapshot corrupt and rebuild from parquet anyway. **Remote: `dropbox:`
(1.6 TiB free) — user's call after an initial googledrive setup; also sidesteps
rclone's shared Google client_id retiring during 2026. `gdrive1` was ruled out
either way (institutional IIT content — deactivation risk for an archive).**
Rejected: GCS (needs billing setup for no capacity we lack). Runs as step [16] rather than its
own schedule — a separate schedule off the wake window is how market_ingest
drifted 8 days. (The Google client_id retirement note only matters if the archive ever moves
back to a Drive remote: rclone.org/drive/#making-your-own-client-id.)

Orchestration layer: `n8n_dropbox_workflow.json` (import into the local n8n at
:5678). Two flows: a **09:00 daily catch-up backup** — deliberately AFTER the
00:30 pipeline, because cloud_backup.sh is idempotent so it costs seconds when
step [16] already ran, and it is the run that actually happens when the Mac
slept through the wake window (the launchd lesson, third time) — and a
**restore/list webhook** (`POST /webhook/dropbox-restore`,
action=list|history|restore, tree allowlisted, dest sanitized, optional
date=YYYY-MM-DD to pull a prior version from history/). Bulk bytes stay on
rclone; the Dropbox MCP connector (same account — verified by a marker-file
round-trip between rclone and the connector) is the browse/verify surface.

Imported + ACTIVATED as `dropboxbackup001` after two upgrades matching the
marketpipeline001 conventions: (1) the bare `rclone size` verify was replaced
with `~/scripts/cloud_backup_verify.sh` — an independent per-tree GATE
(remote-vs-local bytes with the backup's own excludes, 10% churn tolerance,
pg-dump recency <8d) because a whole-mirror byte count passes a half-synced
tree; (2) an ALERT node (send_alert.py) wired to the error outputs of both the
backup and the gate — without it a failed backup only dies quietly in the
executions list, the exact silent-staleness mode this whole day was about.
Webhook tested live: `list` returns the mirror inventory; invalid
tree/dest/date inputs throw in the Code node BEFORE any shell runs (verified:
error execution, no side effects — fail-closed). `history` errors until the
first re-sync creates history/ — expected, not a defect. 🔑 `n8n
import:workflow` DEACTIVATES on import — follow with `n8n update:workflow
--active=true` + `launchctl kickstart -k gui/501/com.umashankar.n8n`.
`DbxBkpMonitor001` (needed a Dropbox OAuth2 credential that was never attached)
is superseded by the credential-free rclone GATE and left inactive.

## 2026-07-23 (early morning: runtime ledger; two corrections it caught)

### New: morning_runtimes.py — per-run duration ledger across all three surfaces

Appends every finished run (pipeline log sections, n8n trigger executions for
the 07:00 chain and 09:00 backup) to reports/morning_runtimes.csv — append-only,
idempotent, in-flight runs picked up by the next sweep. Prints a recent trend +
per-surface median/max. Exists because drift only ever got found by hand-diffing
artifact mtimes (the Korea 3→28min case). First sweep: 8 runs back to Jul 17.

### Correction: I broke my own backup lock

The first sweep exposed the 00:30 Jul-23 run stuck in step [16] for ~4h: TWO
rclone syncs interleaving on the same tree. Cause: my queued re-run command
carried an unconditional `rmdir` of the lock — written to clear my own stale
lock, but by execution time the lock belonged to the pipeline's LIVE step-16
instance. Lesson encoded here: never clear a lock without checking the holder
is dead (`rmdir` only after `pgrep` shows no cloud_backup.sh). Competitor
killed; the pipeline's own sync left to finish alone.

### Correction: readers reintroduced the ~/Downloads TCC trap

market_ingest.py and financial_ratios.py (both written 2026-07-22) hardcoded
`~/Downloads/market_cache/symbol_master.parquet` — the launchd-TCC-denied tree,
and the exact two-trees trap symbol_master.py's own comment warns about (its
WRITER already targets MARKET_CACHE). The 00:30 run tracebacked on it in step
[15]. Both readers now resolve `$MARKET_CACHE/symbol_master.parquet` (env, then
live-tree default). The Downloads copy remains only as a stale git snapshot.

## 2026-07-23 (post-midnight: backup concurrency + restore hardening)

### Correction: the first pg dump was destroyed by a /tmp filename collision

Two concurrent cloud_backup.sh invocations shared /tmp/market_data_<date>.dump.
Instance A uploaded it, printed ok, and rm'd the file while instance B's rclone
was mid-transfer of the SAME path → hash mismatch → rclone deleted the
"corrupted" REMOTE copy too. Net: a dump that had landed was destroyed by the
retry of its twin. Three fixes in cloud_backup.sh: (1) mkdir-based
single-instance lock keyed by remote (a second invocation exits 0 with a log
line — the 00:30 pipeline hitting the lock during a manual run is normal, not
a failure); (2) $$ in the LOCAL dump path so even an aborted instance can't
collide with a later one (remote name stays dated); (3) the dump-prune used
`head -n -8`, which macOS head rejects — every prune since inception was a
silent no-op; now `sort -r | tail -n +9`.

### Restore verified against a live user restore; webhook retry flags

A full-tree restore during the triple-concurrent window (two backups + 1.6GB
dump upload) surfaced ~20 `invalid character '<'` errors — Dropbox API
throttling returning HTML where JSON belongs, NOT corruption: sampled files
byte-exact on the remote, and a re-download SHA-256-matched the local
original. The n8n restore webhook now bakes in
`--retries 5 --low-level-retries 20 --timeout 10m`; interactive restores
should carry the same flags. The instance lock also closes the worst
contention window.

## 2026-07-22 (night: justified mailer — evidence-first brief)

### New: justified_mailer.py — only screens that earned their place

Inverts the daily brief: starts from the repo's measured evidence and shows ONE
backtest-best screen per market, with the result, sample and test window printed
above the picks. India = near_high + momentum (the two screens with positive
India edge: +1.33/+1.18pp, 21d fwd, 2016→2026 PIT — run as SEPARATE lists,
matching how the backtest tested them; intersecting them left 1 name). US/KR/JP
= RSI-14 oversold (+1.85/+2.04/+0.93pp, win 0.463/0.481/0.513). Fundamental
overlay table = factor_combo CSVs verbatim (n, span, edge, t, years-positive)
with the honest caveats attached in-mail: t<1, US PIT EDGAR found high-F
INVERTED, and the Piotroski edge is an illiquidity premium (~$100k yes, $10M
no). "Excluded by evidence" box lists Golden Cross (worst everywhere), Europe
(untested), india_factor_panel (biased sampler), momentum outside India.

Three defects caught by inspecting the first drafts — each now guarded in code:
1. **India momentum list was ALL ETFs** (PHARMABEES/HEALTHIETF/MOMNC) — the
   LIQUIDSBI failure mode again; fixed with the ISIN allowlist (INE + SctySrs
   EQ from nse_raw), the documented instrument-type key.
2. **US oversold surfaced RSI≈0 zombies** (SKHYV 0.0) — thin listings falling
   14 straight days; now >=100 bars + $2 floor + RSI>2 sanity band.
3. **ohlcv_NSE holds ~126 bars — exactly too short for 126-day momentum**
   (2 non-NaN momenta in 2,069 symbols); India source switched to
   cleaned_long (273 trading days), re-gated to the workbook's ₹1cr-floor
   universe (ungated cleaned_long put VIJIFIN @ ₹9 on top).

First edition sent 2026-07-22 late night: 40 picks (10/market).

**Scheduled same night (user call):** node "Justified brief (send + sync)" in
the 07:00 weekday n8n chain — gate → recurring movers → justified brief →
digest — so the brief emails daily and its picks land in watchlist.csv
(`justified` tier, note = "<screen metric> @ <date>") BEFORE the digest builds.
The digest renders `justified` as a SEPARATE table (own heading/columns, screen
column instead of free-note), never mixed into held/watch/sold — they are
mailer output, not portfolio state. Existing watchlist rows are never touched.
First sync: +39 rows. Import gotcha hit twice tonight: `n8n export` emits a
LIST, a patched re-dump emits a DICT — a `[0]` on the re-read KeyErrors and the
stale file imports silently; the live-DB command was verified after the fix
(the node also initially lacked the `cd` prefix every other node carries —
executeCommand cwd is n8n's, not the repo's).

## 2026-07-22 (night: recurring movers — the self-updating shortlist watchlist)

### New: recurring_movers.py — mailer picks that keep recurring AND are moving

The distilled daily watchlist the signal ledger was building toward: names with
**>= 2 distinct signal dates** in the last 30d whose price is **>= +2% since the
FIRST flag** (entry = the ledger's own price_at_signal — the number the brief
actually quoted). Recurrence × movement, not either alone: one strong day is
one strong day; re-passing while the market agrees is the signal. Rules kept
few and printed in the output. Source hygiene: `india_factor_panel` rows are
EXCLUDED (documented alphabetical sampler — recurrence from a biased sampler
measures the bias); T5_MOST_ILLIQUID dropped. Current prices come from the
day's scan workbooks (KR codes zero-pad-normalised — ledger holds '400', the
workbook '000400').

Outputs: `reports/recurring_movers.csv` (full ranked list, rebuilt each run) +
top-25 promoted into `watchlist.csv` as `signal` tier — capped because a young
ledger qualifies 100+ names at 2 appearances and flooding buries the curated
tiers; existing rows are never touched (same contract as signal_tracker).

**Daily update wiring: inside the 07:00 watchlist-digest n8n workflow**
(gate → refresh movers → build digest), NOT a new schedule — the digest is the
consumer, so refreshing immediately before it means the 07:00 email always
carries today's movers, and `onError: continue` ensures a movers failure can't
block the digest. (Also deliberately not appended to daily_pipeline.sh
tonight: that script was mid-execution, and bash re-reads running scripts —
editing it live corrupts the run.) First run: 130 qualifiers, +14 promoted
(rest were already on the watchlist). watchlist_digest.py learned a `signal`
tier (own sort rank, count, and amber tag) — previously those rows rendered
untagged and uncounted, masquerading as holdings.

## 2026-07-22 (warehouse ingest repaired + per-ticker freshness ledger)

### Warehouse ingest had been silently stale for 8 days — root cause: the migration left it behind

`scripts/market_ingest.py` and `scripts/bhavcopy_to_db.py` still pointed at the
abandoned `~/Downloads/code/python_files` / `~/Downloads/data/bhavcopy_cache`
tree after the 2026-07-16 migration to `~/market-pipeline`. Both kept "running
fine" against dead directories: snapshots froze at 2026-07-16, Postgres bhavcopy
at 2026-07-14, and nothing alerted. Fixed by repointing both (with
`BHAV_CACHE`/`MARKET_PIPELINE_DIR` env overrides) and backfilling: +33,105
bhavcopy rows (Jul 15–21), and every missed workbook date per market — the
ingester now loads ALL dates absent from the table, not just the newest file, so
an ingest gap no longer loses the intervening days.

**Decision — the ingest is now step [15/15] of `daily_pipeline.sh`**, not a
separate schedule. Rejected: its own launchd/cron job (that is exactly the
arrangement that let it drift — a second schedule with no coupling to the data
it records, off the wake window). Running it in-pipeline ties it to the same
wake, the same log, and the `[ALERT]` failure email. It calls `/usr/bin/python3`
explicitly because duckdb lives there and not in the venv (the same split
documented on 2026-07-15).

### New: per-ticker freshness ledger (ticker, name, market, last update)

`market_daily.ticker_freshness` (Postgres view) + `market_ingest.py --tickers`
/ `--csv` — one row per ticker with name, market, and date of last real data:
21,279 tickers across 5 markets. India rows come from bhavcopy trade dates (the
true series, ~7.9k symbols), not the gated scan snapshot; names come from the
workbook `Name` column where it exists (EU/JP/KR) and from
`market_daily.symbol_names` (refreshed each run from `symbol_master.parquet`,
NSE preferred on symbol collisions) otherwise. India name coverage is 4,308/7,858
— the unnamed remainder are BSE-only/delisted symbols outside symbol_master,
left NULL rather than guessed. Snapshot workbooks now also persist `name`.
Exported daily to `reports/ticker_freshness.csv` for downstream extraction.

Known remainder: `nse_raw`/`bse_raw` (the 34-col raw archives) still have no
writer since 2026-07-13 — `nse.parquet`/`bse.parquet` in the new cache are not
being rebuilt by anything. The OHLCV series everything reads is current; the raw
archive is the stale layer.

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

## 2026-07-22 (adjusted prices — the data is fixed, and stays fixed)

### `price_adjuster.py` — split/bonus-adjusted India warehouse, validated 7/7

789 events parsed from the CA history (377 splits, 412 bonuses; the subject
strings are perfectly regular), factors compounded backward, 546,802 bars
re-scaled across 577 symbols → `warehouse/ohlcv_adj/IN/`.

**Validated against yfinance's INDEPENDENT adjustment, across each ex-date:
7 OK · 0 DIFF.** The same table shows what was being fixed — through recent
events the RAW series claims −93.8%, −92.1%, −88.4% "crashes" where the true
returns are −69%, −20.8%, +16.2%. This is the measured +12.2%-fake-premium
artifact, now removed at the source.

One harness lesson: the first run showed 5–9pp of fake DIFF because the two
series' return windows started/ended on different trading days. Returns over
different endpoints are different returns — both series are now cut to their
common dates spanning the ex-date. (Same family as the zero-day-holding bug:
comparisons must share their frame.)

Deliberately NOT adjusted: dividends (a total-return series is a different,
later artifact). Splits and bonuses are the return-corrupting events.

### Freshness is wired, not assumed

- Daily extras run refreshes the CURRENT quarter of CA history (idempotent), so
  new ex-dates flow to the adjuster automatically.
- `ingest.sh` step 7b rebuilds the adjusted partitions right after the daily
  warehouse fold.
- Both registered (`warehouse.ohlcv_adj_in`, `extras.corp_actions_history`) —
  staleness shows in data_index and gates like everything else.

⚠️ Consumers: use `ohlcv_adj/IN` for ANY multi-month return computation. The
raw `ohlcv/IN` remains for point-in-time price checks (what did it close at
that day) where raw is correct.

---

## 2026-07-22 (CA history + filings-based metrics, site-validated)

### Corporate-actions history: 23,480 actions back to 2015

The top correctness gap closed: the CA API serves history by exact
calendar-quarter windows (same trap as the results API — ragged windows return
almost nothing). `exchange_extras.py --ca-quarters 44` harvested every ex-date
(dividends, splits, bonuses) matching the price warehouse's depth. This is the
data needed to adjust the raw-close warehouse — the +12.2% split artifact is now
fixable rather than merely known.

### `metrics_from_filings.py` — metrics with provenance, checked against the sites

Computes net margin, OPM-proxy, EPS, YoY growth and interest cover from the
XBRL filings (every figure traces to a filing with a date), then validates
against screener.in's quarterly table — filings vs the site, per quarter, per
consolidation basis.

**Validation run: 6 OK · 0 DIFF.** Three initial mismatches, each diagnosed to
a distinct cause and each a lesson encoded in the harness:

- **SHYAMMETL 3,612cr vs 1,559cr** — consolidated filing compared against the
  standalone page. Basis is now matched PER FILING, not per symbol.
- **WEALTH 20 vs 21cr** — whole-crore rounding is 5%% of a Rs20cr quarter; the
  tolerance now has an absolute floor (1cr) alongside the 2%% relative.
- **RADICO 3,715cr vs 925cr with PAT 65 == 65 exactly** — not an error: liquor
  companies file revenue GROSS of excise, the sites net it out, and the filing
  carries no excise element to reconcile with. Classified `DEFN`
  (definitional), a category distinct from DIFF, because forcing agreement
  would hide a real convention difference.

The harness rule: DIFF against one site -> suspect our parse; DIFF against all
sites -> the filing was restated and the divergence IS the finding.

---

## 2026-07-22 (warehouse — partitioned parquet + DuckDB)

### The LFS problem was duplication and monoliths, not file format

Asked to cut LFS space "by using parquets": the panels already WERE parquet, and
measured re-compression gains nothing (68.9 vs 68MB — already compressed). The
real waste:

- **~900MB where ~450MB exists** — the same market panels tracked in BOTH data
  repos, diverging, with the canonical copy differing per market (this folklore
  is now written down once, in `warehouse_build.py`: IN from global-market-data's
  deep panel; US from global-stock-screener — the other US is the broken
  alphabetical collection).
- **Monoliths defeat LFS** — every daily update rewrote a 68-184MB file and each
  push uploaded a complete new LFS object. Append-only history, re-uploaded in
  full, forever, server-side.

### The fix: `warehouse/ohlcv/<MKT>/year=YYYY.parquet` + DuckDB views

43.5M rows, 6 markets, 2016-2026, row parity verified 6/6. Partitioning costs
+7% on disk and cuts the daily push from a 68MB monolith to the ~8MB
current-year file — **~10x less LFS growth per push**. `warehouse.duckdb` is
268KB of VIEWS (no data copied): SQL over every market with zero load step,
committable for free.

Consumers rewired and verified: `warehouse_update` writes only changed year
partitions (closed years never change under the strictly-newer rule);
`signal_tracker` / `watchlist_pnl` read the warehouse dirs (pandas reads a
partition directory natively — the swap was one path).

Monoliths untracked in both repos (local files stay as caches; README pointers
left). ⚠️ GitHub keeps already-pushed LFS objects — this stops FUTURE growth
and removes the duplication; reclaiming historical remote objects needs a
support request or repo surgery, deliberately not attempted.

---

## 2026-07-22 (NSE XBRL — the point-in-time prize)

### `nse_xbrl_results.py` — filing-dated quarterly fundamentals, 10+ years

The user pointed at NSE's corporate-filings XBRL page; behind it sits an API
that answers plain curl. This closes the last big gap: every India fundamentals
source so far failed point-in-time (yfinance has no filing dates, so backtests
guess a +90d lag; screener.in's rate limit made every panel an A-prefix sample).

**Index harvested in full: 110,942 filings · 2,495 symbols · back to 2015**,
each with `filingDate` (when the market learned the numbers), fiscal period,
audited/consolidated flags, and the XBRL file link. Backtests can now use
`visible_from = filingDate` — the real date, removing the biggest honesty
caveat on the factor work.

Files (~20KB each, full P&L in the in-bse-fin taxonomy) trickle in hash order,
~2,000 per off-hours session piggybacked on the fundamentals runner — full
history in ~8 weeks, representative at every stage.

**Three parser findings, each verified before shipping:**
- The API silently misbehaves on windows longer than a quarter (a 4.7-month
  window returned 8 filings where its quarters held thousands) — exact
  calendar-quarter windows only.
- NSE's "WEB"-format files reference `contextRef="OneD"` **without defining
  it** — invalid XBRL, but consistent; the period is synthesized from the
  index record. This alone was 172 of the first 299 "failures".
- Element names drift across taxonomy years (only
  `ProfitLossForPeriodFromContinuingOperations` in 2018 files; banks use
  `InterestEarned`) — alias lists per field.

Parse rate 42% → **95%**. Periods verified: all rows bind to true 89-91-day
quarters (zero YTD contamination — the first parse of TRIDENT took the H1 YTD
context, ₹3,291cr instead of ₹1,797cr; the period-bound parser fixed it and the
corrected figures match the company's published Q2FY24).

Registered as `xbrl.pit_quarterly`. Consumer wiring (factor panel using
filingDate as visible_from) is the follow-on once coverage accumulates.

---

## 2026-07-22 (NSE/BSE bulk extras — six new datasets)

Probed the exchanges' public endpoints directly: seven bulk files are cookie-free
(archives.nseindia.com + two JSON APIs answered plain curl; only NSE's website
APIs need the cookie dance). `exchange_extras.py` now collects daily, idempotent
per (kind, date), raw files kept verbatim + one consolidated parquet per kind.
Wired into ingest as step 3b; index_closes and delivery registered in
data_registry (3d tolerance).

What each fills:

| dataset | gap it closes |
|---|---|
| **index_closes** (162 indices/day, with P/E·P/B·yield) | the BENCHMARK gap — NIFTYBEES was ISIN-filtered out of the equity panel, so signal tracking used a panel-median stand-in; this is the real Nifty 50. Index P/E is also a regime series the pipeline never had |
| **delivery** (per-stock DELIV_PER) | conviction signal — positions taken home vs intraday churn; never collected |
| **bulk_deals / block_deals** (full history, client names) | smart-money prints; never collected |
| **corp_actions** (ex-dates: dividends, splits, bonuses) | the SPLIT-ADJUSTMENT gap — deep panels carry raw closes, and splits faked a +12.2% illiquid premium in a measured backtest; this is the data to adjust or at least flag |
| **fo_oi** (FII/DII/pro/client OI) | futures positioning; context for put_call_parity |
| **bse_results_cal** | earnings calendar without scraping |

Verified with an 8-day backfill: 966 index rows, 19,571 delivery rows, deals,
20 corp actions, 642 calendar entries — 0 failures (weekend 404s recorded as
skips, not errors; a holiday is a fact, not a failure).

**Deliberate choices:** raw files are never deleted (a parsing bug must not
destroy source data); each kind fails independently (index closes must not
depend on bulk-deals parsing); the CA endpoint raises loudly if NSE later
fences it, rather than storing a block page as data.

**Consumers not yet wired** (data first, consumers next): signal_tracker /
watchlist_pnl still benchmark against the panel median — switching them to the
real Nifty 50 series is the immediate follow-on.

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
