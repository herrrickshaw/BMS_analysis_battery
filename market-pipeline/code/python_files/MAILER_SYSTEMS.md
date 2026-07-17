# Mailer Systems — Summary (from day 1)

Two genuinely separate mailer systems have been built across this work: the
**market-pipeline daily briefs** (this repo) and the **herrrickshaw
real-time digest mailer** (a different repo, `~/Library/CloudStorage/
GoogleDrive-.../herrrickshaw`). They share no code and serve different
purposes — covered here as two sections, not blended into one timeline.

---

## 1. market-pipeline — Daily Market Brief system

### Timeline

| Date | What happened |
|---|---|
| 2026-07-13 | `build_mailer.py` created by merging a previously-separate, unused `build_email.py` into the live assembler — one builder instead of two overlapping ones. |
| 2026-07-15 | `validate_brief.py` (India, cross-checked against screener.in) added — the first pre-send QA layer, after a real bug: a scan-vs-live price mismatch that would have shipped uncaught. `send_alert.py` (pipeline-failure email) and `com.umashankar.dailybrief.plist` (launchd schedule) added same day. |
| 2026-07-16 | External validation expanded market-by-market: `validate_brief_us.py` (EODHD), `validate_brief_eu.py` (Alpha Vantage), `validate_brief_india_mc.py` (moneycontrol, fallback to yfinance), `validate_brief_jpkr.py` (yfinance — the one previously-identified gap). Four `brief_today_draft*.html` iterations during same-day template tuning. |
| 2026-07-17 (this session) | `build_action_brief.py` built — a companion brief restructured around actions instead of analysis. Wired into `send_mailer.py` so both briefs send as two independent emails. This document written. |

### Components

| File | Role |
|---|---|
| `build_mailer.py` | Assembles the full **Daily Market Brief** (`brief_today.html`) — one block per market: screener picks, upcoming earnings + PEAD/dividend context, India CCC, convergence (fundamentals+news agreement), news picks, Darvas breakouts, then global context (momentum, 5y scoreboard, correlation clusters, carry-trade FX). Answers "what does the data say." |
| `build_action_brief.py` | **NEW.** Assembles the **Daily Action Brief** (`action_brief_today.html`) — reuses `build_mailer.py`'s data loaders directly (no duplicated logic), restructured around explicit triggers: 🟢 BUY WATCHLIST (Triple-Hit + liquid, ranked up by same-day Tier-1 breakout or bullish convergence), 🚀 BREAKOUT ENTRIES (momentum-only Tier-1 Darvas), 📅 EARNINGS WATCH (next 4 days, cut down to only PEAD-confirmed or dividend-history names), ⚠️ CAUTION (convergence-negative). A 🌍 Regime section turns the India/US/Europe 200-DMA + Golden/Death Cross snapshot into an explicit sizing rule (RISK-ON/RISK-OFF/MIXED), not just a number. Drops CCC, correlation clusters, 5y scoreboard, momentum table, carry-FX, and generic news/sentiment tables entirely — nothing here is included unless it maps to an action. ~14KB vs. the full brief's ~70KB. Subject line carries live counts (`4 BUY · 2 breakout · 5 earnings · 0 caution`) so it's actionable from an inbox list without opening. Answers "what, if anything, should I do today." |
| `send_mailer.py` | SMTP sender (Gmail, zero LLM tokens). Builds **and sends both briefs independently** — a failure building/sending one never blocks the other (two separate try/except blocks). `--draft` writes both `.html` files without sending. Credentials via `.env` (`GMAIL_USER`, `GMAIL_APP_PASSWORD`, `MAIL_TO`), never hard-coded. |
| `send_alert.py` | Short failure-alert email, separate from both briefs — fires when one or more `daily_pipeline.sh` steps fail, so a broken step is known before (or instead of) a brief with silently-degraded sections arrives. |
| `validate_brief.py` / `validate_brief_us.py` / `validate_brief_eu.py` / `validate_brief_india_mc.py` / `validate_brief_jpkr.py` | Pre-send QA layer — cross-check each market's scan against an **independent** external price source (screener.in / EODHD / Alpha Vantage / moneycontrol+yfinance / yfinance respectively) before anything ships. Not mailers themselves; they exist because checking the brief against our own scan artifact only proves internal consistency, not correctness against the real market. |
| `com.umashankar.dailybrief.plist` | launchd schedule — `daily_pipeline.sh` (which calls `send_mailer.py` then `send_alert.py` on failure) fires at **00:30, weekdays**. |

### What each brief is for

- **brief_today.html** — read when you want the full picture: every screener pass, every market's fundamentals, sentiment, correlation structure. A research/reference document.
- **action_brief_today.html** — read first, fast: only what clears a double-confirmation bar today. A triage document, not a replacement for the full brief.

### Open items

- `build_action_brief.py` is not yet covered by the `validate_brief_*.py` external-source QA layer — it reuses `build_mailer.py`'s already-validated data (picks, Darvas breakouts), so it inherits that validation indirectly, but there's no independent check on the *action brief's own* filtering logic (e.g., that the BUY WATCHLIST intersection math is correct) the way the price data itself is checked.
- No archival/diffing between days yet — "which names are NEW to the buy watchlist since yesterday" would be a natural next action-oriented addition once a dated archive of past action briefs exists.

---

## 2. herrrickshaw — Real-time digest mailer

A completely different system, built earlier in this session, in the
unrelated `herrrickshaw` trading-platform repo (FastAPI + React +
Cassandra). Full detail in that repo's `ARCHITECTURE_SAFE.md`; summarized
here only to distinguish it from the market-pipeline briefs above.

| | market-pipeline briefs | herrrickshaw digest |
|---|---|---|
| Trigger | launchd, once daily (00:30) | APScheduler, in-process, once daily (default 08:30) |
| Content source | Screener scans, news sentiment, Darvas breakouts, PEAD/sector-spillover research | Cassandra `stock_quotes` — Darvas/Buffett + Piotroski BUY/WATCH signals only |
| Delivery gate | Credentials present or falls back to a saved `.html` draft | Two independent flags — `MAILER_ENABLED` (deployed vs. released) and `MAILER_DRY_RUN` — deliberately separate from whether the job is even running |
| Pre-send QA | 5 external-source `validate_brief_*.py` scripts, run separately | CI-style dry-render + validation inside the pipeline itself (`mailer.pipeline.build_and_validate()`), no external price cross-check yet |
| Manual trigger | `python3 send_mailer.py [--draft]` | `python -m mailer.cli --dry-run` / REST `POST /api/mailer/trigger` |
| Known open item | see above | digest is currently unbounded (21,632 rows across 8 markets combined) — needs a scope decision before `MAILER_ENABLED=true` |

Do not conflate the two: a change to one has no effect on the other, and
"the mailer" in future instructions should specify which repo/system is
meant once both exist.
