#!/usr/bin/env python3
# decision_log.py
# ===============
# Daily provenance log: what changed, which data it was based on, and what was
# DECIDED. Deliberately independent of the pipeline — it observes, never runs
# anything, and its failure cannot affect a scan or a brief.
#
# WHY THIS EXISTS
# ───────────────
# The pipeline records what it DID (section logs, [ALERT] trailers). Nothing
# records WHY, or on what evidence. That gap has already cost real work:
#
#   * A liquidity "regression" was chased for an hour before turning out to be
#     the audit's own floor constant — the reasoning behind the original floor
#     was nowhere on record.
#   * A Korea data-corruption hunt went through four wrong hypotheses. Each was
#     plausible and none was written down, so there was nothing to compare a new
#     theory against.
#   * "Piotroski dominates all 7 markets" survived in notes for weeks as a
#     variance artefact on 272 stocks, because the sample size travelled
#     separately from the claim.
#
# A conclusion is only as good as the data it was drawn from, and that
# provenance evaporates fastest. This captures it daily while it is still true.
#
# WHAT IT READS (all local, all read-only)
#   git log              — fixes actually shipped
#   *_pipeline_*.log     — which sections ran, what failed
#   data_index --json    — which datasets were fresh/stale AT THE TIME
#   ~/.claude transcripts— prompts, decisions taken, tools/data sources touched
#
# 🔴 SECRET REDACTION IS MANDATORY, NOT COSMETIC.
# Claude Code transcripts log echoed values in cleartext, and this repo has
# already shipped a live app password into a public git history. A provenance
# log that copies secrets into a NEW tracked file would repeat that mistake with
# better formatting. Everything extracted here passes through _redact() and the
# output path is gitignored by default.
#
#   decision_log.py                 # today
#   decision_log.py --date 2026-07-20
#   decision_log.py --days 7        # roll up a week
#   decision_log.py --install       # write the launchd plist (does not load it)

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "decision_log"
TRANSCRIPTS = Path.home() / ".claude" / "projects"

# Patterns whose VALUE must never reach the log. Matching is deliberately broad:
# a false positive costs one redacted line, a false negative publishes a secret.
_SECRET_PAT = re.compile(
    r"(?i)\b("
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"        # email
    r"|[A-Z]{5}\d{4}[A-Z]"                                    # PAN
    r"|(?:[a-z]{4}\s){3}[a-z]{4}"                             # gmail app password
    r"|(?:sk|ghp|gho|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{10,}"
    r"|[A-Fa-f0-9]{32,}"                                      # long hex key
    r")\b")
# NOTE the optional \w*[_-] prefix. A leading \b does NOT match inside
# SCREENER_PASSWORD, because underscore is a word character — so the first
# version of this pattern let `SCREENER_PASSWORD=...` through untouched while
# redacting a bare `password=...`. Env-var style names are the common case here,
# so that miss covered nearly everything it was meant to catch.
# Consumes to END OF LINE, not \S+. A Gmail app password is four space-separated
# groups, so `\S+` redacted "abcd" and left "efgh ijkl mnop" in place — three
# quarters of the secret, published under a line that looked sanitised. Partial
# redaction is worse than none: it invites trust it has not earned.
_SECRET_KEYS = re.compile(
    r"(?i)(?:\w*[_-])?"
    r"(password|passwd|secret|token|api[_-]?key|crtfc_key|app_key|key)"
    r"\s*[=:]\s*.+")


def _redact(s: str) -> str:
    if not s:
        return ""
    s = _SECRET_KEYS.sub(lambda m: m.group(0).split("=")[0].split(":")[0] + "=<redacted>", s)
    return _SECRET_PAT.sub("<redacted>", s)


def _run(cmd: list, cwd: Optional[Path] = None) -> str:
    try:
        return subprocess.run(cmd, cwd=cwd or HERE, capture_output=True,
                              text=True, timeout=60).stdout
    except Exception:
        return ""


# ── sources ───────────────────────────────────────────────────────────────────
def git_changes(day: str) -> list:
    """Commits authored on `day`, with the files they touched."""
    out = _run(["git", "log", f"--since={day} 00:00", f"--until={day} 23:59",
                "--pretty=format:%h|%an|%s", "--name-only"], cwd=HERE)
    commits, cur = [], None
    for line in out.splitlines():
        if "|" in line and len(line.split("|")) >= 3:
            h, an, subj = line.split("|", 2)
            cur = {"hash": h, "author": an, "subject": _redact(subj), "files": []}
            commits.append(cur)
        elif line.strip() and cur is not None:
            cur["files"].append(line.strip())
    return commits


def pipeline_runs(day: str) -> list:
    """Which sections ran, how long, and what failed."""
    stamp = day.replace("-", "")
    runs = []
    for p in sorted(glob.glob(str(HERE / f"*_pipeline_{stamp}.log"))):
        text = Path(p).read_text(errors="replace")
        steps = re.findall(r"^\[STEP\] (\d+) \S+ (?:\w+ )?(.+)$", text, re.M)
        fails = re.findall(r"^\[ALERT\] (.+)$", text, re.M)
        done = re.search(r"=== done (\S+).*?— (.+?) ===", text)
        runs.append({"section": Path(p).name.split("_pipeline_")[0],
                     "steps": len(steps),
                     "duration": done.group(2) if done else "did not finish",
                     "failures": [_redact(f) for f in fails]})
    return runs


def data_state() -> list:
    """Freshness of every registered dataset — the evidence a run was built on.

    Captured DAILY because it is the part that cannot be reconstructed later: a
    conclusion drawn on a stale cache looks identical afterwards to one drawn on
    fresh data.
    """
    out = _run([str(HERE / ".venv/bin/python3"), str(HERE / "data_index.py"), "--json"])
    try:
        rows = json.loads(out)
    except Exception:
        return []
    return [{"key": r["key"], "status": r["status"], "writer": r["writer"],
             "age_days": r.get("age_days")} for r in rows]


def transcript_activity(day: str) -> dict:
    """Prompts, decisions, and which data sources were touched.

    Decisions are the valuable part: an AskUserQuestion answer is a fork that a
    human chose, and it explains later behaviour that the code alone cannot.
    """
    prompts, decisions, tools, files = [], [], {}, set()
    day_start = dt.datetime.fromisoformat(day).timestamp()
    day_end = day_start + 86400

    for f in TRANSCRIPTS.glob("*/*.jsonl"):
        try:
            if f.stat().st_mtime < day_start - 86400:
                continue
        except OSError:
            continue
        for ln in f.open(errors="replace"):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            ts = r.get("timestamp")
            if ts:
                try:
                    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    if not (day_start <= t < day_end):
                        continue
                except Exception:
                    pass
            typ = r.get("type")
            if typ == "user":
                c = r.get("message", {}).get("content")
                if isinstance(c, str) and c.strip() and not c.lstrip().startswith("<"):
                    prompts.append(_redact(c.strip())[:300])
            elif typ == "assistant":
                for blk in (r.get("message", {}).get("content") or []):
                    if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                        continue
                    name = blk.get("name", "?")
                    tools[name] = tools.get(name, 0) + 1
                    inp = blk.get("input", {}) or {}
                    for k in ("file_path", "notebook_path"):
                        if inp.get(k):
                            files.add(str(inp[k]))
                    if name == "AskUserQuestion":
                        for q in (inp.get("questions") or []):
                            decisions.append({"question": _redact(str(q.get("question", "")))[:180],
                                              "options": [_redact(str(o.get("label", "")))[:60]
                                                          for o in (q.get("options") or [])]})
                    if name == "Bash":
                        cmd = str(inp.get("command", ""))
                        for host in re.findall(r"https?://([A-Za-z0-9.-]+)", cmd):
                            files.add(f"net:{host}")
    return {"prompts": prompts, "decisions": decisions, "tools": tools,
            "touched": sorted(files)[:60]}


# ── render ────────────────────────────────────────────────────────────────────
def render(day: str) -> str:
    g, runs, data, act = (git_changes(day), pipeline_runs(day),
                          data_state(), transcript_activity(day))
    L = [f"# Decision log — {day}", ""]

    L += ["## Data state at capture", ""]
    if data:
        bad = [d for d in data if d["status"] != "OK"]
        L += [f"- {len(data) - len(bad)}/{len(data)} datasets OK"]
        for d in bad:
            age = f"{d['age_days']:.1f}d" if d.get("age_days") is not None else "—"
            L.append(f"  - ⚠️ `{d['key']}` **{d['status']}** ({age}) ← {d['writer']}")
    else:
        L.append("- data_index unavailable")
    L.append("")

    L += ["## Pipeline runs", ""]
    if runs:
        for r in runs:
            f = f" · **{len(r['failures'])} failure(s)**" if r["failures"] else ""
            L.append(f"- `{r['section']}` — {r['steps']} steps, {r['duration']}{f}")
            for x in r["failures"]:
                L.append(f"  - {x}")
    else:
        L.append("- no section logs for this date")
    L.append("")

    L += ["## Fixes shipped", ""]
    if g:
        for c in g:
            L.append(f"- `{c['hash']}` {c['subject']}  ({len(c['files'])} files)")
    else:
        L.append("- no commits")
    L.append("")

    L += ["## Decisions taken", ""]
    if act["decisions"]:
        for d in act["decisions"]:
            L.append(f"- **{d['question']}**")
            L.append(f"  - options: {', '.join(d['options'])}")
    else:
        L.append("- none recorded")
    L.append("")

    L += ["## Requests", ""]
    for p in act["prompts"][:25]:
        L.append(f"- {p.splitlines()[0][:200]}")
    if not act["prompts"]:
        L.append("- none recorded")
    L.append("")

    L += ["## Sources touched", ""]
    nets = [t for t in act["touched"] if t.startswith("net:")]
    fs = [t for t in act["touched"] if not t.startswith("net:")]
    if nets:
        L.append(f"- network: {', '.join(sorted({n[4:] for n in nets}))}")
    if fs:
        L.append(f"- files: {len(fs)} touched")
    if act["tools"]:
        top = sorted(act["tools"].items(), key=lambda x: -x[1])[:8]
        L.append(f"- tools: {', '.join(f'{k}×{v}' for k, v in top)}")
    L.append("")
    L.append("_Secrets are redacted at extraction. Do not commit this file._")
    return "\n".join(L)


# MARKET_CACHE / BHAV_CACHE are NOT optional here. data_index.py resolves them
# through data_registry, which defaults to ~/Downloads when unset. Under launchd
# that default is both wrong (the tree moved) and unreadable (macOS TCC denies
# launchd all access to ~/Downloads) — so the "Data state at capture" section
# would report MISSING for everything, and a provenance log that misreports the
# evidence is worse than no log. No credentials here: this job never sends mail.
PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.umashankar.decisionlog</string>
  <key>EnvironmentVariables</key><dict>
    <key>MARKET_CACHE</key><string>{market_cache}</string>
    <key>BHAV_CACHE</key><string>{bhav_cache}</string>
    <key>PATH</key><string>{here}/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>ProgramArguments</key><array>
    <string>{py}</string><string>{script}</string>
  </array>
  <key>WorkingDirectory</key><string>{here}</string>
  <key>StandardOutPath</key><string>{here}/decision_log_out.log</string>
  <key>StandardErrorPath</key><string>{here}/decision_log_err.log</string>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>23</integer><key>Minute</key><integer>45</integer>
  </dict>
</dict></plist>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily provenance / decision log")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--days", type=int, default=1, help="roll up N days ending --date")
    ap.add_argument("--install", action="store_true",
                    help="write the launchd plist to ./launchd (does NOT load it)")
    a = ap.parse_args()

    if a.install:
        d = HERE / "launchd"
        d.mkdir(exist_ok=True)
        p = d / "com.umashankar.decisionlog.plist"
        # Bake in whatever the current shell resolves, falling back to the
        # migrated tree — never to the ~/Downloads default.
        mc = os.environ.get("MARKET_CACHE", "/Users/umashankar/market-pipeline/market_cache")
        bc = os.environ.get("BHAV_CACHE",
                            "/Users/umashankar/market-pipeline/data/bhavcopy_cache")
        p.write_text(PLIST.format(py=HERE / ".venv/bin/python3",
                                  script=HERE / "decision_log.py", here=HERE,
                                  market_cache=mc, bhav_cache=bc))
        print(f"  wrote {p}\n  load with: launchctl bootstrap gui/$(id -u) {p}")
        return 0

    OUT_DIR.mkdir(exist_ok=True)
    end = dt.date.fromisoformat(a.date)
    for i in range(a.days):
        day = (end - dt.timedelta(days=i)).isoformat()
        md = render(day)
        out = OUT_DIR / f"{day}.md"
        out.write_text(md)
        print(f"  → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
