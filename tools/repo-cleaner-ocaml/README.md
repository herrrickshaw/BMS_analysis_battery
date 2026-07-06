# repo-cleaner-ocaml

A structural redundancy scanner for this account's repos, written in OCaml.
Its default posture everywhere is report, not delete — the one place it
*can* delete (`--apply`) is deliberately narrow, explained below.

## What it actually checks

1. **Exact duplicate files** (`Duplicate_finder`) — byte-identical content
   across any of the directories you point it at, hashed with the stdlib's
   `Digest` (MD5). This is what caught, e.g., a 12.3MB fuel-pump data file
   sitting in both `fuel-retail-outlets` and a leftover copy inside this
   repo's `api-data-integration/`, and `full_japan_market_scan.py` existing
   byte-for-byte identically in three different repos.
2. **Data-source duplicates** (`Data_manifest`) — the same idea, scoped to
   data files (`.parquet`/`.db`/`.db.gz`/`.gz`/`.csv`/`.json`/`.xlsx`) and
   specifically aware of Git LFS: an LFS-tracked file checked out with
   smudging skipped sits on disk as a small plain-text pointer
   (`oid sha256:...` / `size N`), and comparing those pointers proves two
   files are byte-identical *without downloading the real LFS content* —
   the pointer's declared `size` is also what gets reported for a data
   file, not the ~130-byte pointer file's own on-disk size. Restricted to
   LFS pointers specifically; a non-pointer data file's duplicate (if any)
   is already found by `Duplicate_finder` over the general file set, so
   this module doesn't re-report it. `--data-manifest-out` writes a CSV
   catalog of every data file found, LFS or not — the "compile every data
   source so it's readable at a glance" ask this module exists for.
3. **Name-based doc-sprawl clusters** (`Name_clusterer`) — files that share
   a leading name token after stripping digits (`RESEARCH_PAPER.md` /
   `RESEARCH_PAPER_DETAILED.md` / `RESEARCH_PAPER_SIMPLE.md`, or
   `PHASE1_KICKOFF.txt` / `PHASE_1_KICKOFF_CHECKLIST.md`). This is a naming
   heuristic, not a content read — it flags candidates for a human to
   actually open and decide "supersede, merge, or keep both." Expect some
   over-clustering on generic first words; that's a cheap false positive
   in a report a human reads, not a correctness bug.
4. **Recency annotations** (`Recency`) — every file listed in a duplicate
   group or name cluster is tagged with its size and the last-commit date
   *from its own repo's git history* (not the CLI's combined view — each
   repo's history is independent). The file with the latest date in each
   group is marked `**<- most recently touched**`. This is what turns "these
   are duplicates across repos" into an actual answer for which copy is
   current: every cross-repo duplicate of the shared engine scripts
   (`full_us_market_scan.py`, `full_korea_market_scan.py`,
   `full_japan_market_scan.py`, `full_indian_market_scan.py`,
   `nse_data_fetcher.py`, and others) resolves to **`global-market-scanners`**
   as the most recently touched copy — consistently dated 2026-07-03,
   against `quant-stock-analysis`'s 2026-06-29 and `claude-stock-tools`'s
   2026-06-13. That's real evidence for which of the three overlapping
   stock-analysis codebases is being actively maintained, not a guess.
   Note what this does and doesn't establish: recency says which copy was
   *touched most recently*, not which is *most complete* — for
   byte-identical exact duplicates there's no completeness difference to
   measure (they're the same bytes), so recency is the only signal that
   applies. For name clusters, where files genuinely differ, size is shown
   alongside recency so both signals are visible; this tool doesn't try to
   collapse them into one "winner" for a name cluster, since unlike an
   exact duplicate, a name cluster's files aren't proven to be the same
   thing at different points in time — that's still a human's call.
5. **Branch staleness** (`Branch_analyzer`) — ahead/behind commit counts and
   last-commit date for each branch vs a base ref, with a triage label
   (`Merged` / `Likely_stale` / `Recent`).

## `--apply`: what it will and won't touch

`--apply` (via `Cleanup`) removes redundant copies, but only within a
narrow, deliberately conservative scope:

- **Only within a single repo.** A cross-repo duplicate means "which repo
  is the canonical owner of this file" — a judgment this tool has no basis
  to make silently. It's reported, never auto-resolved.
- **Never a protected-alias filename.** Any file whose basename contains
  `latest`, `current`, or `stable` (case-insensitive) is excluded from
  every group it appears in, even within one repo. A real run of this
  tool proposed deleting `backtest_1yr_full_NSE_latest.xlsx` and keeping
  only its timestamped twin, purely because of alphabetical sort order —
  byte-identical *today* doesn't mean a fixed path nothing else reads from
  is safe to remove.
- **Never name clusters or branches.** Those stay report-only regardless
  of `--apply` — a shared leading name token or a stale-looking branch is
  a candidate for a human to read, not a deletion rule.
- Default is always dry-run: without `--apply`, the plan prints and
  nothing is touched.

The Scanner itself also skips `_build/`, `node_modules/`, `.venv`,
`__pycache__`, `dist`, and `target` by default (alongside `.git`) — not
real `.gitignore` parsing, just a denylist for the most common
build/dependency directories. This exists because an early run of this
tool against its own checked-out `_build/` output proposed keeping a
compiled copy of a source file and deleting the real one (`_build/...`
sorts alphabetically before `lib/...`) — caught in a dry run before
anything was actually removed, then fixed at the source rather than
worked around per-run.

## What it deliberately does NOT do

- **No semantic/logic analysis of the code being scanned.** This tool is
  written in OCaml; the repos it scans are Python. OCaml-LSP, Merlin, and
  Dune make *developing this tool itself* safe — type errors and syntax
  mistakes in `repo-cleaner-ocaml`'s own source show up in your editor as
  you type. They give this tool zero ability to understand whether two
  Python files are logically equivalent, only whether they're
  byte-identical or similarly named. "Defect-free" means *this tool* is
  defect-free (25 tests, all passing, including regression tests for the
  two real bugs found while running it against real repo data) — not a
  claim that the tool can certify the Python codebases it scans as
  defect-free.
- **No Menhir.** Menhir is a parser generator for actual grammars — a
  custom language or config DSL. Nothing here needs one: CSV/JSON-shaped
  data and Git LFS pointer text are all handled with plain string
  operations. Adding Menhir would be reaching for a tool because it was
  named, not because the problem calls for it.

## Build and run

```bash
cd tools/repo-cleaner-ocaml
dune build
dune exec test/test_repo_cleaner.exe   # 25 tests, synthetic fixtures

# report only (default -- nothing is ever deleted without --apply)
dune exec bin/main.exe -- \
  --root /path/to/repo-a \
  --root /path/to/repo-b \
  --repo-dir /path/to/repo-a \
  --base-ref origin/main \
  --branch origin/some-branch \
  --out REPORT.md \
  --data-manifest-out DATA_MANIFEST.csv

# actually remove redundant copies -- only within-repo, non-aliased ones
dune exec bin/main.exe -- --root /path/to/repo-a --apply --out REPORT.md
```

Editor support (Merlin / OCaml-LSP) works automatically once this is
opened as a Dune project — no extra config needed beyond having
`ocaml-lsp-server` and `dune` on your machine.

## REPORT.md and DATA_MANIFEST.csv in this directory

Generated by running the tool above against local clones of every repo
referenced from this account: this repo (`quant-stock-analysis`),
`global-market-scanners`, `fuel-retail-outlets`, `toll-plaza-highways`,
`india-trade-export-analysis`, `claude-stock-tools`, `colab-experiments`,
and `subscription-model-revenue`, plus every branch of this repo, *after*
`--apply` had already removed this repo's own 6 confirmed within-repo
duplicates (a stray browser-download-style PDF/HTML copy, a cache file
duplicated between a code-bundled seed and a runtime cache, and similar —
see the commit history for the exact list). The duplicates still listed
for `fuel-retail-outlets` were left alone: this repo has no branch/commit
mechanism set up for that repo in this pass, so they're reported, not
applied. Re-run the commands above against fresh clones to regenerate
both files as the repos change.
