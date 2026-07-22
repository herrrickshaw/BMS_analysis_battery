#!/bin/bash
# ingest.sh — SECTION 1 of 4: get today's data on disk.
# ====================================================
# Everything the other three sections read. Fast (~20-30 min) and deliberately
# free of anything that produces a recommendation: this section is only about
# whether the numbers are present and current.
#
# Runs BEFORE the mailer (00:15 vs 00:30) so the brief has fresh inputs rather
# than yesterday's. mailer.sh gates on this section via `require_fresh ingest`.
#
#   ./ingest.sh
#
# Feeds: bhavcopy.{assembled,cleaned,lmdb}, cache.{ohlc,meta,symbol_master},
#        fx.usd, india.ccc_screen   (see data_registry.py)

source "$(cd "$(dirname "$0")" && pwd)/pipeline_lib.sh"
section_start "ingest"

{
  # Dependency check is CRITICAL here and nowhere else. A missing lmdb or pykrx
  # degrades a scan; a missing one during ingest means the artifact never lands
  # and all three downstream sections build on stale data without knowing it.
  # Four deps were silently absent on 2026-07-15 and each failure looked exactly
  # like a bad network day.
  run_critical "[1/7] dependency check" $PY check_deps.py

  # India EOD. Official bhavcopy, incremental — 1-2 new trading days per run.
  run "[2/7] India EOD refresh (bhavcopy, incremental)" \
      $PY bhavcopy_history.py 400

  # FX for the liquidity gate. Refreshed here rather than inside each scan so all
  # five markets are gated against ONE rate set — on 2026-07-15 Europe and Japan
  # ran with no gate at all because the per-scan FX fetch failed independently.
  run "[3/7] FX rates for liquidity gate" \
      $PY -c "import liquidity, json; r = liquidity.scan_fx(); liquidity._fx_write_cache(r); print(f'  fx: {len(r)} currencies cached')"

  # NSE/BSE bulk extras: index closes (real benchmarks + index P/E), delivery %,
  # bulk/block deals, corporate actions (the split-adjustment data), F&O OI,
  # BSE results calendar. All cookie-free archive files; idempotent per day.
  run "[3b/7] NSE/BSE extras (indices, delivery, deals, corp actions)" \
      $PY exchange_extras.py

  # Cross-market symbol normalisation.
  run "[4/7] symbol master refresh" $PY symbol_master.py

  # screener.in cash-conversion-cycle screen, plus its scrape test. The test is
  # here rather than in the mailer because a broken scrape must be known before
  # the brief is built, not while it is being sent.
  run "[5/7] India CCC screen (screener.in)" \
      $PY -c "import screener_in as s; s.ccc_screen().to_parquet('cache_seed/india_ccc_screen.parquet', index=False)"

  run "[6/7] test: validate screener.in CCC scrape" $PY test_screener_in.py

  # ── fold today's bars into the deep panels ──────────────────────────────────
  # Without this the LFS panels drift stale (IN was 8d behind, US 19d) while the
  # daily stores stay current — and every analysis then had to guess which store
  # to read. Guessing wrong never errored, it just returned a plausible wrong
  # number: a 3-year return from the 36-bar LMDB, or entry==ltp printing "+0.0%".
  # Append-only and refuses to write if rows fall or symbols vanish.
  run "[7/7] fold fresh bars into the deep price panels" \
      $PY warehouse_update.py

  # Rebuild split/bonus-adjusted partitions from the freshly-folded warehouse +
  # the CA history refreshed above. Validated 7/7 against yfinance's independent
  # adjustment; raw closes fake -90% "crashes" through every split without this.
  run "[7b/7] split/bonus-adjust the India warehouse" \
      $PY price_adjuster.py

  # Close the section by reporting what actually landed. This is the artifact the
  # mailer's gate reads, so printing it here makes a blocked mailer explainable
  # from the ingest log alone.
  step "[index] ingest freshness"
  $PY data_index.py --section ingest || true

  section_end
} >> "$LOG" 2>&1

echo "ingest complete — see $LOG"
