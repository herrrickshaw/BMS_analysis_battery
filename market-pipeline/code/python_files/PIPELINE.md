# Pipeline sections

`daily_pipeline.sh` was one 14-step, 3–5h, all-or-nothing nightly run. It is now
four sections on three schedules, linked by a data freshness gate.

`daily_pipeline.sh` is **unchanged and still works** — nothing was deleted. The
sections are additive until you install the staged plists.

```
  ingest.sh          mailer.sh              modelling.sh        factor_tests.sh
  weekdays 00:15  →  weekdays 00:30         Sat 02:00        →  Sat (after)
  ~20-30m            ~60-90m                hours               hours
       │                  │                      │                    │
       │  require_fresh   │   warn_stale         │   warn_stale       │
       └──── (HARD) ──────┘   └──── (advisory) ──┴──── (advisory) ────┘
       │
       └─ bhavcopy, OHLC cache, FX, symbol master, CCC screen
                          │
                          └─ 5 scans → cross-market audit → screener.in validation → SEND
                                                 │
                                                 └─ correlation, factor panel, PPO, walk-forward
                                                                      │
                                                                      └─ factorial grids, backtests
```

## The linkage

Sections communicate through `data_registry.py` — one declaration of where every
dataset lives, who writes it, and how stale it may get — read by
`data_index.py --require <section>`.

- **mailer gates HARD on ingest.** Stale inputs mean no brief. This is the
  2026-07-20 failure: the US scan crashed, left a 3.9-day-old workbook behind,
  and the brief was built and *sent* from it because every check asked whether
  the file existed, not whether it was current.
- **modelling and factor_tests gate ADVISORY.** A day-old panel is still a valid
  research input; blocking the weekly run over a few hours' lag would trade a
  real output for a theoretical risk. The asymmetry is deliberate.

## Commands

```bash
./ingest.sh && ./mailer.sh      # the weekday chain
./mailer.sh --draft             # build the brief without sending
./modelling.sh --skip-ppo       # weekly research, minus the long pole
./factor_tests.sh --market IN   # one market's grid

data_index.py                   # what is stale, and who was supposed to write it
data_index.py --require ingest  # the gate itself; exit 1 = not usable
run_monitor.py                  # per-step durations, per-section trend
run_monitor.py --slowest 15     # where the time actually goes
repo_tracker.py --paths         # path-drift guard (the US-scan bug class)
repo_tracker.py --orphans       # scripts no section invokes
```

## Scheduling

Plists are **staged in `launchd/`, not installed**. Each carries its own install
instructions and ships credential **placeholders** — copy the real values from
the currently-installed `com.umashankar.dailybrief.plist`.

⚠️ **Install ingest first.** `mailer.sh` hard-gates on it; swapping the mailer
plist without a running ingest job stops the brief.

Two blockers that have each stopped this job before:

1. **TCC.** macOS denies launchd all access to `~/Downloads`. Every path must
   resolve through `$MARKET_CACHE`/`$BHAV_CACHE`. `repo_tracker.py --paths` guards it.
2. **The Mac must be awake.** `StartCalendarInterval` cannot fire on a
   powered-off Mac and does not replay missed slots — `pmset -g sched` must be
   non-empty.

`launchctl list` showing a job is **not** evidence it ran. Check `runs =` in
`launchctl print gui/$(id -u)/<label>`.

## Known state (2026-07-20)

| Thing | Status |
|---|---|
| `cache.ohlc` / `cache.meta` | **5.3d stale** — not written since the US scan crash. The mailer gate blocks on this today. |
| `warehouse.postgres` | 6–7d stale in all 5 markets. **Nothing schedules `market_ingest.py`** — it is run by hand. Registered as `unowned` so the gap is visible. |
| `backtest.walk_forward`, `test.screeners` | Never produced output. |
| India combined report | **66m of the 92m nightly run** — the real long pole. Totals trend 26m → 64m → 92m. |
| Path drift | 8 TCC-fatal files (all unwired/dead), 34 non-relocatable absolutes. |

See [GLOSSARY.md](GLOSSARY.md) for terms, thresholds, and the traps behind them.
