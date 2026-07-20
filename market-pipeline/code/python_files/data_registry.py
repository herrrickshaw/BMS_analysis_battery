# data_registry.py
# ================
# THE one place that knows where data lives, who writes it, and how stale it may get.
#
# WHY THIS EXISTS
# ───────────────
# Two failures on 2026-07-20 came from the same root cause — path and ownership
# knowledge scattered across ~40 scripts as private constants:
#
#   1. market_data_cache.py hardcoded ~/Downloads/market_cache while every sibling
#      honoured $MARKET_CACHE. macOS TCC denies launchd all access to ~/Downloads,
#      so the nightly US scan died with PermissionError mid-download. Nothing
#      declared that this path had to agree with the others, so nothing caught it.
#   2. The Postgres warehouse sat 6-7 days stale in every market. No script
#      declared itself the writer, so "nobody has written this since 13 Jul" was
#      not a state anything could observe — it needed a human to run --status and
#      read the dates.
#
# A registry fixes both classes: paths resolve HERE (one env-var idiom, one
# default), and every dataset names its writer and its tolerated age, so
# data_index.py can report "stale, and here is who was supposed to write it".
#
# CONTRACT
# ────────
#   * Import paths from here. Do not re-derive them.
#   * Adding a dataset means adding a Dataset() row — that is what makes it
#     visible to the index, the freshness check, and the repo tracker.
#   * stdlib only, and must import under BOTH interpreters: the pipeline venv
#     (3.9, has pandas/yfinance, no duckdb) and /usr/bin/python3 (has duckdb).
#     Anything heavier belongs in the consumer, not here.

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ── roots ─────────────────────────────────────────────────────────────────────
# Defaults stay on the historical ~/Downloads locations so interactive use is
# unchanged; launchd overrides both via the plist, which is what moves the whole
# tree out of TCC's way. Every consumer must read these rather than rebuilding
# the expression, or we reintroduce the US-scan bug in a new file.
HOME = Path.home()
CODE = Path(__file__).resolve().parent

MARKET_CACHE = Path(os.environ.get("MARKET_CACHE", HOME / "Downloads" / "market_cache"))
BHAV_CACHE = Path(os.environ.get("BHAV_CACHE", HOME / "Downloads" / "data" / "bhavcopy_cache"))

OHLC_DIR = MARKET_CACHE / "ohlc"
FUND_DIR = MARKET_CACHE / "fundamentals"
INDEX_DIR = MARKET_CACHE / "index"
META_DIR = MARKET_CACHE / "meta"

# Postgres warehouse. Peer auth over the unix socket, no password — see
# project_market_data_warehouse. Overridable for a remote/CI target.
PG_DSN = os.environ.get("PGDSN", "dbname=market_data host=/tmp user=umashankar")

# Section run logs. One per section per day; scan_timings/run_monitor parse the
# [STEP] markers out of these.
LOG_GLOB = "*_pipeline_*.log"

# ── cadences ──────────────────────────────────────────────────────────────────
DAILY = "weekday 00:15-02:30"
WEEKLY = "Saturday 02:00"
ONDEMAND = "on demand"


@dataclass
class Dataset:
    """One tracked artifact.

    max_age_days is the point at which the data is WRONG to use, not merely old.
    India EOD is 1 because bhavcopy is same-day-EOD; the research panels are 8
    because a week-old factor panel is still a valid research input. None means
    staleness is not meaningful (append-only logs, derived reports).
    """
    key: str
    path: Path
    writer: str                      # the script that produces it
    section: str                     # which pipeline section owns the writer
    cadence: str
    max_age_days: Optional[float]
    note: str = ""
    consumers: List[str] = field(default_factory=list)

    def exists(self) -> bool:
        return self.path.exists()


# ── the datasets ──────────────────────────────────────────────────────────────
# Ordered by section so the index reads as a dependency chain: ingest feeds
# mailer, mailer feeds research.
DATASETS: List[Dataset] = [
    # ---- ingest ----------------------------------------------------------
    Dataset("bhavcopy.assembled", BHAV_CACHE / "assembled_long.parquet",
            "bhavcopy_history.py", "ingest", DAILY, 1.0,
            "raw NSE+BSE EOD, append-only",
            ["scan_bhavcopy.py"]),
    Dataset("bhavcopy.cleaned", BHAV_CACHE / "cleaned_long.parquet",
            "bhavcopy_history.py", "ingest", DAILY, 1.0,
            "🔴 load India from HERE, not assembled — NSE/BSE share bare symbols "
            "and 2534 collide; the cleaned pivot resolves the exchange",
            ["scan_bhavcopy.py", "factor_zscore_panel.py"]),
    Dataset("bhavcopy.lmdb", BHAV_CACHE / "ohlcv.lmdb",
            "bhavcopy_history.py", "ingest", DAILY, 1.0,
            "per-symbol OHLCV store, ~7.8k symbols; needs lmdb",
            ["scan_bhavcopy.py"]),
    Dataset("cache.ohlc", OHLC_DIR,
            "market_data_cache.py", "ingest", DAILY, 1.5,
            "5y OHLC parquet per ticker, incremental; US scan's backing store",
            ["full_us_market_scan.py", "portfolio_builder.py", "dl_strategy_eval.py"]),
    Dataset("cache.meta", META_DIR / "cache_index.json",
            "market_data_cache.py", "ingest", DAILY, 1.5,
            "🔴 the file whose hardcoded ~/Downloads path killed the US scan "
            "on 2026-07-20 — must resolve under $MARKET_CACHE",
            ["market_data_cache.py"]),
    Dataset("cache.symbol_master", MARKET_CACHE / "symbol_master.parquet",
            "symbol_master.py", "ingest", DAILY, 2.0,
            "cross-market symbol normalisation"),
    Dataset("fx.usd", BHAV_CACHE / "fx_usd.json",
            "liquidity.py", "ingest", DAILY, 7.0,
            "USD rates for the liquidity gate; refuses to serve >7d old, which is "
            "why a stale FX file shows as UNKNOWN tiers rather than a silent gate",
            ["liquidity.py", "adaptive_liquidity.py"]),
    Dataset("india.ccc_screen", CODE / "cache_seed" / "india_ccc_screen.parquet",
            "screener_in.py", "ingest", DAILY, 3.0,
            "cash-conversion-cycle screen scraped from screener.in",
            ["send_mailer.py"]),

    # ---- mailer ----------------------------------------------------------
    Dataset("scan.india", CODE / "indian_full_scan",
            "scan_bhavcopy.py", "mailer", DAILY, 1.5,
            "🔴 Median_Turnover is in RUPEES; floor is Rs 1cr, not the USD floor",
            ["consistency_audit.py", "send_mailer.py"]),
    Dataset("scan.us", CODE / "us_full_scan",
            "full_us_market_scan.py", "mailer", DAILY, 1.5,
            "Turnover_USD; structural $10k floor",
            ["consistency_audit.py", "send_mailer.py"]),
    Dataset("scan.europe", CODE / "european_scan",
            "full_european_market_scan.py", "mailer", DAILY, 1.5,
            "mixed-currency universe; lacks Data_Points so 200-DMA is unverifiable",
            ["consistency_audit.py", "send_mailer.py"]),
    Dataset("scan.japan", CODE / "japan_scan",
            "full_japan_market_scan.py", "mailer", DAILY, 1.5, "",
            ["consistency_audit.py", "send_mailer.py"]),
    Dataset("scan.korea", CODE / "korea_scan",
            "full_korea_market_scan.py", "mailer", DAILY, 1.5, "",
            ["consistency_audit.py", "send_mailer.py"]),
    Dataset("report.combined", CODE / "combined_report_results",
            "daily_combined_report.py", "mailer", DAILY, 1.5,
            "fundamentals + street talk, per market"),
    Dataset("brief.html", CODE / "brief_today.html",
            "send_mailer.py", "mailer", DAILY, 1.0,
            "the sent brief; also written on the --draft suppression path"),

    # ---- modelling -------------------------------------------------------
    Dataset("correlation", CODE / "correlation_scan",
            "market_correlation_scan.py", "modelling", WEEKLY, 8.0,
            "5-market clusters; needs networkx. Moved off the nightly path "
            "2026-07-20 — ~25 min and nothing in the brief consumes it",
            []),
    Dataset("factor.zscore_panel", CODE / "cache_seed" / "factor_zscore_panel.parquet",
            "factor_zscore_panel.py", "modelling", WEEKLY, 8.0,
            "🔴 cross-sectional factor z-scores. The writer hardcodes this as an "
            "ABSOLUTE /Users/umashankar/... path (factor_zscore_panel.py:215) — the "
            "same class of bug that killed the US scan; it should resolve via "
            "data_registry instead"),
    Dataset("ppo.weights", CODE / "strategies",
            "train_ppo_walk_forward.py", "modelling", WEEKLY, 30.0,
            "PPO factor weights; walk-forward + entropy + shrinkage per the "
            "overfitting fix in eb0c48f9"),
    Dataset("backtest.walk_forward", CODE / "wf_backtest",
            "walk_forward_backtest.py", "modelling", WEEKLY, 30.0,
            "walk-forward equity curves"),

    # ---- factor_tests ----------------------------------------------------
    Dataset("test.factorial", CODE / "reports",
            "factorial_screener_test.py", "factor_tests", WEEKLY, 30.0,
            "factorial screener grids, per market (IN/JP/KR/CN)"),
    Dataset("test.screeners", CODE / "backtest_results",
            "backtest_screeners.py", "factor_tests", WEEKLY, 30.0,
            "screener-level forward-return backtest. Dir does not exist yet — this "
            "has never been run to completion, which is itself worth seeing"),

    # ---- warehouse (no declared writer — see note) ------------------------
    Dataset("warehouse.postgres", Path("/dev/null"),
            "market_ingest.py (NOT SCHEDULED)", "unowned", ONDEMAND, 2.0,
            "🔴 public.ohlcv_history + bhavcopy.* + market_daily.ingest_log. On "
            "2026-07-20 every market was 6-7d stale because NOTHING schedules "
            "market_ingest.py — it is run by hand. Listed here so the gap is "
            "visible rather than rediscovered. Query freshness via PG_DSN, not mtime."),
]

BY_KEY = {d.key: d for d in DATASETS}
SECTIONS = ("ingest", "mailer", "modelling", "factor_tests", "unowned")


def get(key: str) -> Dataset:
    return BY_KEY[key]


def for_section(section: str) -> List[Dataset]:
    return [d for d in DATASETS if d.section == section]


def resolve(key: str) -> Path:
    """Path for a dataset key — the accessor consumers should use."""
    return BY_KEY[key].path
