#!/usr/bin/env python3
"""
obs.py — production observability for the trading/backtest stack (before AWS).

Three primitives, shared by every module:
  * LOGGER  — structured, UTC-timestamped, to stdout + logs/<name>_<UTCdate>.log
  * CLOCK   — `with timed(log, "label"):` times a phase; `Stopwatch` accumulates splits
  * DECISION LOG — append-only JSONL audit trail of what the algo decided and WHY
    (regime, factor chosen, metric, FX asof, capacity …). This is the record the
    HFT literature (Gomber et al.) says algorithmic traders must keep for back-
    testing and supervisory review.

All timestamps are UTC ISO-8601. Regular-Python time/clock use (not a Workflow
sandbox), so time.time()/datetime.now() are fine here.

    from obs import get_logger, timed, DecisionLog
    log = get_logger("regime_survival")
    dl  = DecisionLog(run="regime-2026-07-24")
    with timed(log, "load IN panel"):
        ...
    dl.record(kind="regime_rule", market="IN", active_rule="trend", ir=2.34)
"""
from __future__ import annotations
import json, logging, os, sys, time, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LOGDIR = Path(os.environ.get("MARKET_LOGDIR", Path(__file__).resolve().parent / "logs"))
LOGDIR.mkdir(parents=True, exist_ok=True)


def _utcstamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def get_logger(name: str, level=logging.INFO) -> logging.Logger:
    """Configured logger: UTC timestamps, stdout + a per-day file. Idempotent."""
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(level)
    fmt = logging.Formatter("%(asctime)s.%(msecs)03dZ %(levelname)-5s [%(name)s] %(message)s",
                            datefmt="%Y-%m-%dT%H:%M:%S")
    fmt.converter = time.gmtime                     # UTC, not local
    for h in (logging.StreamHandler(sys.stdout),
              logging.FileHandler(LOGDIR / f"{name}_{_utcstamp()}.log")):
        h.setFormatter(fmt); lg.addHandler(h)
    lg.propagate = False
    return lg


# ── CLOCKS ──────────────────────────────────────────────────────────────────
@contextmanager
def timed(logger: logging.Logger, label: str, level=logging.INFO):
    """Time a phase; logs START then DONE with elapsed seconds (even on error)."""
    t0 = time.perf_counter()
    logger.log(level, f"START {label}")
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        dt = time.perf_counter() - t0
        logger.log(level, f"{'DONE ' if ok else 'FAIL '}{label} ({dt:,.2f}s)")


class Stopwatch:
    """Accumulates named splits; `.summary()` returns a sorted breakdown."""
    def __init__(self):
        self.splits: dict[str, float] = {}
        self._t = time.perf_counter()

    def split(self, label: str) -> float:
        now = time.perf_counter()
        self.splits[label] = self.splits.get(label, 0.0) + (now - self._t)
        self._t = now
        return self.splits[label]

    def summary(self) -> dict:
        total = sum(self.splits.values())
        return {"total_s": round(total, 2),
                "splits": {k: round(v, 2) for k, v in
                           sorted(self.splits.items(), key=lambda kv: -kv[1])}}


# ── DECISION LOG ────────────────────────────────────────────────────────────
class DecisionLog:
    """Append-only JSONL audit trail. Each record is timestamped and tagged with a
    run id so a single backtest/live run is reconstructable end-to-end."""
    def __init__(self, run: str | None = None, path: Path | None = None):
        self.run = run or f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.path = Path(path) if path else (LOGDIR / f"decisions_{_utcstamp()}.jsonl")

    def record(self, kind: str, **fields) -> dict:
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
               "run": self.run, "kind": kind, **fields}
        with self.path.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        return rec

    def read(self, run: str | None = None) -> list:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if run is None or r.get("run") == run:
                out.append(r)
        return out


if __name__ == "__main__":
    log = get_logger("obs_selftest")
    dl = DecisionLog(run="selftest")
    with timed(log, "demo phase"):
        time.sleep(0.05)
    dl.record("demo", market="IN", active_rule="trend", ir=2.34, note="self-test")
    log.info(f"decision log -> {dl.path}")
    print("records:", dl.read("selftest"))
