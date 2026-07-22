#!/usr/bin/env python3
# data_index.py
# =============
# Live freshness/ownership report over data_registry.DATASETS, and the gate that
# links the pipeline sections together.
#
# WHY THIS EXISTS
# ───────────────
# On 2026-07-20 the nightly brief was built and SENT on top of a US workbook that
# was 3.9 days old, because the US scan had crashed and every downstream step
# happily consumed the stale artifact it left behind. Each step checked whether
# its input FILE existed; none checked whether it was RECENT. "Exists" and
# "usable" are different questions and only the second one matters.
#
# So this is both a report and a gate:
#
#   data_index.py                    # human report, all sections
#   data_index.py --section ingest   # one section
#   data_index.py --require ingest   # exit 1 if any ingest dataset is stale
#   data_index.py --json             # machine-readable, for the tracker
#
# --require is what mailer.sh calls before it scans: if ingest did not produce
# fresh data, the brief does not get built on yesterday's numbers pretending to
# be today's.
#
# stdlib only — must run under the venv (3.9) and /usr/bin/python3 alike.

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

import data_registry as R

OK, STALE, MISSING, UNKNOWN = "OK", "STALE", "MISSING", "UNKNOWN"


# A directory dataset is only as fresh as its CONTENTS. This fraction of files
# must be within max_age for the dataset to count as fresh.
COVERAGE_REQUIRED = 0.80


def _mtimes(p: Path) -> List[float]:
    """All file mtimes under p (or [mtime] if p is a file)."""
    try:
        if not p.exists():
            return []
        if p.is_file():
            return [p.stat().st_mtime]
        out = []
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    out.append(f.stat().st_mtime)
            except OSError:
                continue
        return out
    except OSError:
        return []


def _newest_mtime(p: Path) -> Optional[float]:
    """Newest mtime at p. Use for REPORTING only — never to judge a directory.

    🔴 This was the whole freshness test until 2026-07-20, and it was wrong for
    directories in the most dangerous direction. A US OHLC refresh advanced only
    2,658 of 7,641 tickers; 4,344 were still four days behind. Because one file
    was seconds old, max(mtime) said the dataset was fresh and the gate passed —
    reporting health over a cache that was 57% stale.

    "Newest" answers "did anything happen recently", which is never the question.
    The question is "is the data usable", and that is a property of the WORST
    part of the dataset, not the best. See _coverage().
    """
    ms = _mtimes(p)
    return max(ms) if ms else None


def _coverage(p: Path, max_age_days: float) -> Optional[float]:
    """Fraction of files under p that are within max_age_days.

    1.0 for a single file that is fresh, 0.0 for one that is not, so files and
    directories are judged on the same scale.
    """
    ms = _mtimes(p)
    if not ms:
        return None
    cutoff = time.time() - max_age_days * 86400.0
    return sum(1 for m in ms if m >= cutoff) / len(ms)


def _age_days(mtime: Optional[float]) -> Optional[float]:
    return None if mtime is None else (time.time() - mtime) / 86400.0


def _pg_freshness() -> dict:
    """Latest data date per market in the Postgres warehouse.

    Split out and failure-tolerant: psycopg is absent from the pipeline venv, and
    a missing driver must degrade to UNKNOWN rather than reporting the warehouse
    as healthy or as broken. Neither claim would be true.
    """
    try:
        import psycopg2  # noqa: F401
    except Exception:
        try:
            import psycopg  # noqa: F401
        except Exception:
            return {}
    try:
        try:
            import psycopg2 as pg
        except Exception:
            import psycopg as pg
        with pg.connect(R.PG_DSN) as conn, conn.cursor() as cur:
            cur.execute("SELECT market, MAX(price_date) FROM public.ohlcv_history "
                        "GROUP BY market ORDER BY market")
            return {m: str(d) for m, d in cur.fetchall()}
    except Exception:
        return {}


def _ohlc_data_coverage(max_age_days: float) -> Optional[dict]:
    """Freshness of the OHLC cache from its DATA dates, not its file mtimes.

    🔴 Why this exists, and why mtime cannot be trusted here.
    On 2026-07-20 a refresh rewrote all 7,641 parquet files but only advanced
    2,658 of them to the latest bar — the other 4,344 were rewritten with data
    still ending 2026-07-13. Every file therefore had an mtime of seconds old
    while more than half the cache was four days behind.

    mtime answers "when was this file written". The question is "how recent is
    the data inside it". A refresh that writes stale content makes those two
    answers diverge, and the whole point of the gate is to catch exactly that.
    cache_index.json records a `to` date per ticker, so ask it directly.
    """
    try:
        import datetime as _dt
        meta = json.loads(R.META_DIR.joinpath("cache_index.json").read_text())
    except Exception:
        return None
    dates = []
    total = 0
    for k, v in meta.items():
        if not k.startswith("ohlc:"):
            continue
        total += 1
        try:
            dates.append(_dt.date.fromisoformat(str(v.get("to") or "")[:10]))
        except Exception:
            dates.append(None)      # unparseable counts against coverage
    if not total:
        return None

    valid = sorted(d for d in dates if d)
    if not valid:
        return None

    # Anchor on the MEDIAN last-bar date, not the max.
    #
    # 🔴 max() was wrong in the same way max(mtime) was wrong, just inverted.
    # Observed 2026-07-21 04:00 IST: 7,454 tickers sat at Friday 07-17 (correct —
    # the US Monday close had not been fetched yet) while 22 stragglers carried a
    # 07-20 bar. Anchoring to the max pulled the reference to 07-20, so 97% of a
    # perfectly healthy cache scored "stale" and the gate blocked the brief.
    #
    # A handful of outliers must not define the leading edge in either direction.
    # The median is where the cache actually IS, and it moves only when a real
    # refresh moves the bulk of the universe.
    newest = valid[len(valid) // 2]
    true_max = valid[-1]

    # Measure each ticker against the NEWEST BAR IN THE CACHE, not against today.
    # Anchoring to today makes the check fail every Monday and every holiday: US
    # markets are shut at the weekend, so on a Monday the freshest bar obtainable
    # is Friday's — three calendar days old, and perfectly healthy. A gate that
    # cries wolf on a fixed weekly schedule gets ignored, and an ignored gate
    # protects nothing.
    #
    # Anchoring to the cache's own leading edge asks the question that actually
    # matters — "was this refresh UNIFORM, or did it advance some tickers and
    # leave others behind" — and is immune to market calendars.
    cutoff = newest - _dt.timedelta(days=max_age_days)
    fresh = sum(1 for d in dates if d and d >= cutoff)

    # Separately: the leading edge itself must not be ancient. Weekends and long
    # holidays mean this needs slack, hence +4 calendar days on top.
    # Lag is measured from the median edge too. +4 days of slack absorbs a
    # weekend plus a holiday; a US cache checked on Tuesday morning IST is one
    # trading day behind by construction, not by failure.
    lag = (_dt.date.today() - newest).days
    return {"coverage": fresh / total, "total": total, "fresh": fresh,
            "newest": newest.isoformat(), "max_bar": true_max.isoformat(),
            "lag_days": lag, "edge_stale": lag > (max_age_days + 4)}


def assess(d: R.Dataset) -> dict:
    """Status for one dataset. The warehouse is special-cased: it has no path."""
    if d.section == "unowned" and str(d.path) == "/dev/null":
        pg = _pg_freshness()
        if not pg:
            return {"key": d.key, "status": UNKNOWN, "age_days": None,
                    "detail": "psycopg unavailable or DB unreachable"}
        oldest = min(pg.values())
        age = None
        try:
            import datetime as _dt
            age = (_dt.date.today() - _dt.date.fromisoformat(oldest)).days
        except Exception:
            pass
        status = OK
        if age is not None and d.max_age_days is not None and age > d.max_age_days:
            status = STALE
        return {"key": d.key, "status": status, "age_days": age,
                "detail": ", ".join(f"{k}:{v}" for k, v in sorted(pg.items()))}

    mtime = _newest_mtime(d.path)
    if mtime is None:
        return {"key": d.key, "status": MISSING, "age_days": None, "detail": str(d.path)}

    age = _age_days(mtime)          # newest — reported, not judged on
    if d.max_age_days is None:
        return {"key": d.key, "status": OK, "age_days": age, "detail": ""}

    # The OHLC cache carries its own data dates; prefer them over file mtimes,
    # which a stale-content rewrite makes meaningless (see _ohlc_data_coverage).
    if d.key == "cache.ohlc":
        probe = _ohlc_data_coverage(d.max_age_days)
        if probe:
            cov = probe["coverage"]
            uniform = cov >= COVERAGE_REQUIRED
            status = OK if (uniform and not probe["edge_stale"]) else STALE
            why = []
            if not uniform:
                why.append(f"only {cov*100:.0f}% of {probe['total']:,} tickers are within "
                           f"{d.max_age_days:g}d of the leading edge "
                           f"(need {COVERAGE_REQUIRED*100:.0f}%) — refresh was NOT uniform")
            if probe["edge_stale"]:
                why.append(f"leading edge itself is {probe['lag_days']}d behind today")
            detail = (f"latest bar {probe['newest']} ({probe['lag_days']}d ago); "
                      + "; ".join(why) if why else
                      f"latest bar {probe['newest']}, {cov*100:.0f}% uniform")
            return {"key": d.key, "status": status, "age_days": age,
                    "coverage": cov, "detail": detail}

    # Judge on coverage, not on the newest member. A partially-refreshed cache is
    # not a fresh cache, and the newest file cannot tell the two apart.
    cov = _coverage(d.path, d.max_age_days)
    status = OK if (cov is not None and cov >= COVERAGE_REQUIRED) else STALE
    detail = ""
    if cov is not None and cov < 1.0:
        n = len(_mtimes(d.path))
        detail = (f"{cov*100:.0f}% of {n:,} files within {d.max_age_days:g}d "
                  f"(need {COVERAGE_REQUIRED*100:.0f}%) — newest is {age:.1f}d old")
    return {"key": d.key, "status": status, "age_days": age,
            "coverage": cov, "detail": detail}


def report(section: Optional[str] = None, as_json: bool = False) -> int:
    rows = []
    for d in R.DATASETS:
        if section and d.section != section:
            continue
        a = assess(d)
        a.update({"section": d.section, "writer": d.writer, "cadence": d.cadence,
                  "path": str(d.path), "max_age_days": d.max_age_days,
                  "note": d.note, "consumers": d.consumers})
        rows.append(a)

    if as_json:
        print(json.dumps(rows, indent=2))
        return 0

    print("=" * 78)
    print("  DATA INDEX" + (f" — {section}" if section else ""))
    print("=" * 78)
    cur = None
    for r in rows:
        if r["section"] != cur:
            cur = r["section"]
            print(f"\n  [{cur}]")
        age = r["age_days"]
        agestr = "  —  " if age is None else (f"{age:5.1f}d" if age < 999 else "  old")
        mark = {OK: "  ", STALE: "⚠️ ", MISSING: "❌", UNKNOWN: "❓"}[r["status"]]
        print(f"   {mark} {r['key']:<26} {agestr}  {r['status']:<8} ← {r['writer']}")
        if r["status"] != OK and r["detail"]:
            print(f"        {r['detail'][:100]}")
        if r["note"].startswith("🔴"):
            print(f"        {r['note'][:110]}")

    bad = [r for r in rows if r["status"] in (STALE, MISSING)]
    print()
    if bad:
        print(f"  {len(bad)} dataset(s) stale or missing:")
        for r in bad:
            print(f"    {r['status']:<8} {r['key']:<26} writer: {r['writer']}")
    else:
        print("  all tracked datasets within tolerance")
    return 0


def require(section: str) -> int:
    """Gate: non-zero exit if any dataset in `section` is stale or missing.

    Deliberately does NOT check `unowned` — the warehouse has no scheduled writer,
    so gating on it would block every run for a condition no section can fix.
    """
    bad = []
    for d in R.for_section(section):
        a = assess(d)
        if a["status"] in (STALE, MISSING):
            bad.append((a["status"], d.key, d.writer, a["age_days"]))
    if not bad:
        print(f"  [gate] {section}: all {len(R.for_section(section))} datasets fresh")
        return 0
    print(f"  [gate] ❌ {section}: {len(bad)} dataset(s) not usable —")
    for status, key, writer, age in bad:
        agestr = "missing" if age is None else f"{age:.1f}d old"
        print(f"           {status:<8} {key:<26} ({agestr}) writer: {writer}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Data freshness index and section gate")
    ap.add_argument("--section", choices=R.SECTIONS, help="report one section only")
    ap.add_argument("--require", choices=R.SECTIONS,
                    help="exit 1 if any dataset in this section is stale/missing")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()
    if args.require:
        return require(args.require)
    return report(section=args.section, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
