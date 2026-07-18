# Backlog

The Kanban backlog for this repo (see `CONTRIBUTING.md` for the process this
supports). Items here were deliberately triaged as "needs its own pass," not
half-fixed to make some other PR look more complete — see each item's source
PR for why it wasn't done inline.

Pick an item, open a branch, do it properly (with the verification bar from
`CONTRIBUTING.md`), remove it from this file in the same PR that closes it.

## Code quality (from the repo-wide tooling pass, PR #19 / #20)

- [ ] **`full_*_market_scan.py` fundamentals duplication, part 2**: PR #20 only unified the Darvas Box detection loop and the `first_df`/`row`/`series` helpers. Each file's `fundamental_scan()` (the biggest single function in each — 200-300+ lines) still has real per-market duplication in the Piotroski/Coffee Can/Magic Formula/Bull Cartel scoring logic. Not attempted: needs the same rigorous behavioral-diff treatment as the Darvas Box work, at larger scope, and the financial-statement column-name handling differs more than the Darvas Box wrapper did.
- [ ] **Second legacy report-script duplication cluster**: `us_stock_daily_report.py` / `us_stocks_colab.py` / `stock_daily_report_improved.py` / `sg_stock_daily_report.py` / `us_market_screener.py` — 30-68 line duplicate blocks between pairs (jscpd). Not attempted: unclear which of these are still actively used vs. superseded snapshots; needs that answered before any consolidation, otherwise risk silently changing a script someone still runs.
- [ ] **~110 files `make format` would reformat**: pure Ruff-format whitespace changes, never applied repo-wide (only applied to files touched by other work). Low risk but large diff — do as its own PR so it doesn't obscure logic changes elsewhere, and someone should skim the diff once for anything `ruff format` gets stylistically wrong on this codebase's less-common patterns (e.g. wide dict literals) before landing it.
- [ ] **~570 pre-existing `ruff check` findings** (370 auto-fixable) across files nobody has reviewed under the newer `UP`/`B`/`C4`/`SIM` rule categories added in PR #19. Auto-fixable ≠ safe-to-blind-apply — `--fix` output should be diffed, not trusted, since Bugbear (`B`) findings in particular can flag real behavior (e.g. mutable default args) where the "fix" changes semantics.
- [ ] **39 bandit Medium-severity findings** (32 `hardcoded_sql_expressions`, 4 `hardcoded_tmp_directory`, 3 `blacklist`). The SQL ones are probably f-string column-name interpolation with no user input (same pattern as this session's own `warehouse_common.py`/`load_*_to_warehouse.py`), but "probably" isn't good enough for a security finding — needs someone to actually open each one and confirm, not batch-dismiss.
- [ ] **Complexity hotspots** (radon rank D-F): `ipo_tracker.py::screen_ipo` (F), `consistency_audit.py::main` (E), `ipo_tracker.py::download_ohlc` (E), `carry_fx.py::carry_status` (D), `strategies/darvas.py::_compute_box` (D). Real financial logic — decomposing these needs domain review of what each branch is actually deciding, not a mechanical extract-method pass.
- [ ] **`nse_data_fetcher.py`'s 5 unused imports** (`expiry_list`, `holiday_master`, `nse_circular`, `nse_get_top_gainers`, `nse_get_top_losers`). Left alone on the theory that this matches `global-stock-screener`'s documented "legacy data-fetchers keep optional/availability imports" convention — but that's a guess about *this* file's intent, not confirmed. Either confirm and add the same per-file ruff ignore `global-stock-screener` uses, or remove them if they're genuinely dead.
- [ ] **No CI for this repo.** `global-stock-screener` has a real GitHub Actions pipeline (ruff/black/pytest/bandit/integrity-checksums on every push). This repo has the same tooling available locally (`make check-all`) but nothing runs it automatically. Until this exists, every PR's "verified" claims rely entirely on the author actually having run the commands — worth fixing before this repo gets a second regular contributor.

## Research / data pipeline

- [ ] **Phase F: geography expansion** — Japan/Korea are technical-only, India is partial, Europe is blocked. (Long-standing item, predates this session's tooling work.)
- [ ] **India NSE `results-comparison` full-universe collection** — the nsepython-based collector hit a domain-wide NSE WAF block partway through (403/1,679 tickers collected). Needs either a retry strategy or acceptance that yfinance (already collected, shallower history) is the primary India PIT fundamentals source going forward.
