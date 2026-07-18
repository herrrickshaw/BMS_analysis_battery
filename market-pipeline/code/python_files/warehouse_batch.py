#!/usr/bin/env python3
"""
warehouse_batch.py -- shared load_batches bookkeeping for
load_signals_to_warehouse.py and load_ohlcv_to_warehouse.py.

Every loader run now opens a batch row before writing, tags every fact row
it writes with that batch_id, and closes the batch (success/failed, final
row_count) when done. See warehouse_versioning.sql for the schema and the
"accumulate, don't overwrite" rationale.
"""

from __future__ import annotations

import subprocess


def git_commit_or_none() -> str | None:
    """Best-effort short commit hash for the currently checked-out repo
    state, so a batch row records what code produced it. None (not a
    fabricated value) if git is unavailable or the tree isn't a repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd="/Users/umashankar",
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def start_batch(conn, table_name: str, job_name: str, source_file: str | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO load_batches (table_name, job_name, source_file, git_commit, status)
            VALUES (%s, %s, %s, %s, 'running')
            RETURNING batch_id
            """,
            (table_name, job_name, source_file, git_commit_or_none()),
        )
        batch_id = cur.fetchone()[0]
    conn.commit()
    return batch_id


def finish_batch(
    conn, batch_id: int, row_count: int, status: str = "success", notes: str | None = None
) -> None:
    assert status in ("success", "failed")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE load_batches
            SET row_count = %s, finished_at = CURRENT_TIMESTAMP, status = %s, notes = %s
            WHERE batch_id = %s
            """,
            (row_count, status, notes, batch_id),
        )
    conn.commit()
