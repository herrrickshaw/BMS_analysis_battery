# Development process

This repo runs **Kanban + Lean**, backed by a DevOps-style automation layer
(`Makefile`/`pyproject.toml`, see `make help`). This is a deliberate choice,
not a default — see the rationale below.

## Why Kanban + Lean, not Scrum/SAFe/Waterfall

| Framework | Assumes | This repo has |
|---|---|---|
| Scrum | A team, fixed-length sprints, a Product Owner/Scrum Master | One maintainer + Claude Code sessions running whenever work shows up — no sprint cadence to timebox |
| SAFe | Multiple coordinated Agile teams, an enterprise release train | A single codebase, no cross-team alignment problem to solve |
| Waterfall / V-Model | Fixed upfront requirements, regulatory sign-off gates | Requirements emerge from research findings (a backtest result, a lint scan, a data-quality bug) — nothing here is spec'd months in advance |
| **Kanban** | Continuous, unpredictable inflow of work items, WIP limits to prevent thrash | **Matches directly**: work arrives as "run this scan," "fix this bug," "build this collector" — one item at a time, done to completion before the next starts |
| **Lean** | Eliminate waste, decide late, deliver fast | **Matches directly**: this repo's own convention is *detect, then triage* — fix what's clearly safe now, defer what needs its own dedicated pass rather than half-fixing it under time pressure |

DevOps (the `Makefile` stack: ruff/mypy/bandit/pylint) is the automation
backbone underneath this — not a competing framework, an implementation
detail of it. If this repo ever gains a second regular contributor or a
release cadence with external users, Scrumban (Kanban's flow + Scrum's
light structure) would be the natural next step, not Scrum itself.

## The actual flow (already in use, now written down)

```
BACKLOG.md item  →  branch  →  work + verify  →  PR  →  human merges
   (or ad-hoc          |
    request)      WIP limit: 1 branch/PR open per logical unit of work.
                   Don't start item 2 while item 1 is mid-review — finish
                   or explicitly park it in BACKLOG.md first.
```

**Triage rule (Lean: eliminate waste, don't gold-plate):** when a scan/audit
surfaces N findings, split them immediately:
- **Clear win** — mechanical, low-risk, independently verifiable → fix now, in the same PR as the scan that found it.
- **Needs its own pass** — touches live/production-facing behavior, requires domain judgment, or the fix itself is bigger than the finding → write it to `BACKLOG.md` with enough context to pick up cold, do NOT half-fix it to make the PR look more complete.

**Verification bar before a PR is opened:**
1. `python3 -m py_compile` on every touched file (non-negotiable, catches nothing expensive)
2. `make lint-check` / relevant `ruff check` on touched files
3. **If the change touches logic with existing behavior to preserve** (not just new code): write a standalone before/after comparison and run it against randomized or real inputs, not just eyeball the diff. See `full_*_market_scan.py`'s `compute_darvas_box` refactor for the shape of this — an MD5-based "these look identical" check was wrong and would have silently changed live mailer output; a randomized behavioral harness (14,000 trials, 0 mismatches) caught it before merge.
4. State what you verified in the PR description, not just what you changed.

**Merge gate:** a human merges. Nothing in this repo auto-merges — there is
no CI required-check gate yet (see `BACKLOG.md`), so the PR description's
test plan is the only record of what was actually verified. Write it like
someone else has to trust it without re-running anything.

## Where Claude Code fits (the "Agentic AI SDLC" pattern, made explicit)

This repo is mostly developed through Claude Code sessions. The 2026
"Agentic AI SDLC" framing — an agent orchestrating its own transitions
between stages, executing autonomously within policy boundaries, escalating
at the boundary — describes how this has actually been working, not a new
process to adopt:

- **Autonomous**: detect (scan/audit) → fix clear wins → verify → PR. No
  need to check in at each of these steps individually.
- **Escalates**: when a finding is ambiguous, high-blast-radius (e.g. would
  touch 100+ files, or the live mailer's output), or requires a judgment
  call only the maintainer can make (which SDLC framework, which repo,
  how deep a pass) — ask, don't guess. Several points in this repo's history
  are literal examples of this boundary: a proposed full-repo `make format`
  run was caught mid-execution and reverted rather than pushed through: see
  git log for `refactor: consolidate on the modern Ruff-only stack`.
- **Governed, not unlimited**: the policy boundary is this file plus
  whatever the maintainer states in the request. When those two are silent
  on scope, the default is *ask*, not *assume the most thorough interpretation*.

## Standing quality gates

Run via `make help` in `code/python_files/`:
- `make lint-check` / `make format` / `make lint` — Ruff (replaces Black/isort/Flake8/pyupgrade)
- `make typecheck` — mypy (permissive; this is an untyped research codebase, tightened incrementally)
- `make security` — bandit
- `make duplicates` / `make duplicates-jscpd` — two independent duplicate-code detectors (AST-based and token-based)
- `make check-all` — all of the above, report-only, safe to run anytime

None of these are wired into CI yet for this repo (unlike `global-stock-screener`,
which has a real GitHub Actions pipeline) — see `BACKLOG.md`.
