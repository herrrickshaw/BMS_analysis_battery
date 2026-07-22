---
name: verify-morning-runs-0915
description: One-time 09:15 IST check that the 07:00 mailers and 09:00 Dropbox backup all fired cleanly on 2026-07-23
---

Audit this morning's (2026-07-23) three scheduled market-pipeline surfaces and report pass/fail for each. READ-ONLY: inspect logs and databases only — do NOT re-run anything, do NOT send any email.

## Context (self-contained)
All infrastructure lives at /Users/umashankar/market-pipeline/code/python_files/. A local n8n server (launchd com.umashankar.n8n, http://localhost:5678) runs two active workflows:
- `watchlistdigest001` "Watchlist Digest — daily 07:00" — chain: Gate (cache fresh?) → Refresh recurring movers → Justified brief (send + sync) → Build + send digest. It should have SENT TWO emails around 07:00-07:10 IST: the "🧪 Justified Brief" and the "📊 Watchlist Digest".
- `dropboxbackup001` "Dropbox Market Data — Backup & Restore" — daily 09:00 IST: cloud_backup.sh → GATE (cloud_backup_verify.sh) → usage report; on any error an ALERT email goes via send_alert.py. A healthy run is SILENT (no alert email).
The 00:30 pipeline already ran and sent its brief (verified at 04:16) — no need to recheck it unless something else looks off.

## Checks
1. n8n executions: `sqlite3 ~/.n8n/database.sqlite "SELECT e.id, w.name, e.status, e.mode, e.startedAt, e.stoppedAt FROM execution_entity e JOIN workflow_entity w ON w.id=e.workflowId WHERE e.startedAt > '2026-07-22 19:00' ORDER BY e.startedAt;"` — NOTE startedAt is stored in UTC (07:00 IST = 01:30 UTC, 09:00 IST = 03:30 UTC). Expect one `trigger`-mode execution per workflow this morning, status success. `status=error` on watchlistdigest001 may mean the gate correctly blocked on stale cache — check which node failed via `SELECT data FROM execution_data WHERE executionId=<id>` (search for node names + "error").
2. Mailer evidence: for the justified brief, check mtime of reports/justified_brief.html (should be ~07:0x IST today) and that watchlist.csv gained/refreshed `justified` rows dated 2026-07-23 (notes end "@ 2026-07-23"). For the digest, the execution data for node "Build + send digest" should contain a "sent" or digest summary line.
3. Backup: cloud_backup.log should have a run stamped ~09:00 IST today ending "=== done" WITHOUT "FAILURE(S)". Note: if it ended with "another instance holds ... lock — exiting (not an error)" that is benign lock behavior, but then verify the mirror is still fresh. Run `/Users/umashankar/scripts/cloud_backup_verify.sh` (read-only checks against Dropbox) — expect "VERIFY OK" exit 0, including "ok pg: newest dump market_data_20260722.dump" (a dump dated 20260722 or later is fine; Monday is the weekly dump day).
4. Alert check: no "⚠️" alert email should have been triggered — grep the n8n execution data for "[alert] sent" occurrences this morning; any hit means a failure fired the ALERT path — report what it said.

## Output
A short pass/fail table for: 07:00 gate, movers refresh, justified brief sent, digest sent, 09:00 backup, GATE verify. Lead with the single most important fact. If everything passed, say so in two lines — don't pad. If something failed, quote the exact error from the execution data or log and name the file/node it came from.