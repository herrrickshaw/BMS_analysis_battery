"""
PostgreSQL Database Handler for file tracking with versioning, compression, and deduplication.
Ported from herrrickshaw/global-stock-screener (feature/repository-systems-complete).
"""
from __future__ import annotations

import gzip
import hashlib
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False
    log.warning('psycopg2 not installed — VCRUD will run in no-op mode')


@dataclass
class FileRecord:
    path: str
    size_bytes: int
    checksum: str
    branch: str
    last_modified: datetime
    git_commit: Optional[str] = None
    compressed_size: Optional[int] = None
    compression_ratio: Optional[float] = None
    retrieval_count: int = 0


class CompressionManager:
    @staticmethod
    def compress_file(file_path: str) -> Tuple[bytes, float]:
        data = Path(file_path).read_bytes()
        compressed = gzip.compress(data, compresslevel=6)
        ratio = len(compressed) / len(data) if data else 1.0
        return compressed, ratio

    @staticmethod
    def decompress_file(compressed_data: bytes) -> bytes:
        return gzip.decompress(compressed_data)

    @staticmethod
    def compute_checksum(file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()


class GitBranchScanner:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def _git(self, *args) -> str:
        result = subprocess.run(
            ['git', '-C', self.repo_path, *args],
            capture_output=True, text=True,
        )
        return result.stdout.strip()

    def get_all_branches(self) -> List[str]:
        out = self._git('branch', '-a', '--format=%(refname:short)')
        return [b.strip() for b in out.splitlines() if b.strip()]

    def get_branch_files(self, branch: str) -> Dict[str, Dict]:
        out = self._git('ls-tree', '-r', '--name-only', branch)
        files = {}
        for path in out.splitlines():
            path = path.strip()
            if not path:
                continue
            abs_path = os.path.join(self.repo_path, path)
            try:
                stat = os.stat(abs_path)
                files[path] = {
                    'size_bytes': stat.st_size,
                    'last_modified': datetime.fromtimestamp(stat.st_mtime),
                }
            except OSError:
                files[path] = {'size_bytes': 0, 'last_modified': datetime.now()}
        return files

    def get_commit_history(self, branch: str, file_path: str) -> List[str]:
        out = self._git('log', '--pretty=format:%H', branch, '--', file_path)
        return [c.strip() for c in out.splitlines() if c.strip()]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS branches (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    total_files INTEGER DEFAULT 0,
    total_size_bytes BIGINT DEFAULT 0,
    compressed_size_bytes BIGINT DEFAULT 0,
    last_scanned TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS files (
    id               SERIAL PRIMARY KEY,
    branch_id        INTEGER REFERENCES branches(id) ON DELETE CASCADE,
    path             TEXT NOT NULL,
    size_bytes       BIGINT NOT NULL,
    checksum         TEXT NOT NULL,
    compressed_size  BIGINT,
    compression_ratio FLOAT,
    git_commit       TEXT,
    last_modified    TIMESTAMP NOT NULL,
    retrieval_count  INTEGER DEFAULT 0,
    deleted          BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE(branch_id, path)
);

CREATE TABLE IF NOT EXISTS file_versions (
    id          SERIAL PRIMARY KEY,
    file_id     INTEGER REFERENCES files(id) ON DELETE CASCADE,
    git_commit  TEXT,
    checksum    TEXT,
    size_bytes  BIGINT,
    recorded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS file_dedup (
    id           SERIAL PRIMARY KEY,
    checksum     TEXT NOT NULL,
    file_paths   TEXT[] NOT NULL,
    branch_names TEXT[] NOT NULL,
    wasted_bytes BIGINT DEFAULT 0,
    detected_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS retrieval_cache (
    id          SERIAL PRIMARY KEY,
    file_id     INTEGER REFERENCES files(id) ON DELETE CASCADE,
    accessed_at TIMESTAMP DEFAULT NOW(),
    branch      TEXT,
    path        TEXT
);

CREATE TABLE IF NOT EXISTS compression_stats (
    id              SERIAL PRIMARY KEY,
    branch_id       INTEGER REFERENCES branches(id) ON DELETE CASCADE,
    avg_ratio       FLOAT,
    best_ratio      FLOAT,
    worst_ratio     FLOAT,
    files_analyzed  INTEGER,
    computed_at     TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_files_branch_path ON files(branch_id, path);
CREATE INDEX IF NOT EXISTS idx_files_checksum    ON files(checksum);
CREATE INDEX IF NOT EXISTS idx_fv_commit         ON file_versions(git_commit);
"""


class DatabaseHandler:
    def __init__(self, db_url: str):
        self._db_url = db_url
        self._conn = None
        if not _PSYCOPG2_AVAILABLE or not db_url:
            return
        try:
            self._conn = psycopg2.connect(db_url)
            self._conn.autocommit = True
            self._init_schema()
            log.info('VCRUD: PostgreSQL connected')
        except Exception as exc:
            log.warning('VCRUD: PostgreSQL unavailable (%s) — running in no-op mode', exc)
            self._conn = None

    def _init_schema(self):
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def available(self) -> bool:
        return self._conn is not None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_or_create_branch(self, branch: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                'INSERT INTO branches(name) VALUES (%s) '
                'ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name RETURNING id',
                (branch,)
            )
            return cur.fetchone()[0]

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create_file(self, record: FileRecord) -> int:
        if not self._conn:
            return -1
        branch_id = self._get_or_create_branch(record.branch)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO files(branch_id, path, size_bytes, checksum,
                    compressed_size, compression_ratio, git_commit, last_modified)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (branch_id, path) DO UPDATE SET
                    size_bytes=EXCLUDED.size_bytes,
                    checksum=EXCLUDED.checksum,
                    compressed_size=EXCLUDED.compressed_size,
                    compression_ratio=EXCLUDED.compression_ratio,
                    git_commit=EXCLUDED.git_commit,
                    last_modified=EXCLUDED.last_modified,
                    deleted=FALSE
                RETURNING id
                """,
                (branch_id, record.path, record.size_bytes, record.checksum,
                 record.compressed_size, record.compression_ratio,
                 record.git_commit, record.last_modified),
            )
            file_id = cur.fetchone()[0]
            cur.execute(
                'INSERT INTO file_versions(file_id, git_commit, checksum, size_bytes) '
                'VALUES (%s,%s,%s,%s)',
                (file_id, record.git_commit, record.checksum, record.size_bytes),
            )
            return file_id

    def read_file(self, file_path: str, branch: str) -> Optional[FileRecord]:
        if not self._conn:
            return None
        with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT f.path, f.size_bytes, f.checksum, b.name AS branch,
                       f.last_modified, f.git_commit, f.compressed_size,
                       f.compression_ratio, f.retrieval_count
                FROM files f JOIN branches b ON f.branch_id=b.id
                WHERE b.name=%s AND f.path=%s AND f.deleted=FALSE
                """,
                (branch, file_path),
            )
            row = cur.fetchone()
            if not row:
                return None
            cur.execute(
                'UPDATE files SET retrieval_count=retrieval_count+1 '
                'WHERE path=%s AND branch_id=(SELECT id FROM branches WHERE name=%s)',
                (file_path, branch),
            )
            return FileRecord(**dict(row))

    def update_file(self, record: FileRecord) -> bool:
        if not self._conn:
            return False
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE files SET
                    size_bytes=%s, checksum=%s, compressed_size=%s,
                    compression_ratio=%s, git_commit=%s, last_modified=%s
                WHERE path=%s
                  AND branch_id=(SELECT id FROM branches WHERE name=%s)
                  AND deleted=FALSE
                RETURNING id
                """,
                (record.size_bytes, record.checksum, record.compressed_size,
                 record.compression_ratio, record.git_commit, record.last_modified,
                 record.path, record.branch),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    'INSERT INTO file_versions(file_id, git_commit, checksum, size_bytes) '
                    'VALUES (%s,%s,%s,%s)',
                    (row[0], record.git_commit, record.checksum, record.size_bytes),
                )
            return row is not None

    def delete_file(self, file_path: str, branch: str,
                    git_commit: Optional[str] = None) -> bool:
        if not self._conn:
            return False
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE files SET deleted=TRUE
                WHERE path=%s
                  AND branch_id=(SELECT id FROM branches WHERE name=%s)
                RETURNING id
                """,
                (file_path, branch),
            )
            row = cur.fetchone()
            if row and git_commit:
                cur.execute(
                    'INSERT INTO file_versions(file_id, git_commit, checksum, size_bytes) '
                    'VALUES (%s,%s,NULL,0)',
                    (row[0], git_commit),
                )
            return row is not None

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_files_by_branch(self, branch: str) -> List[FileRecord]:
        if not self._conn:
            return []
        with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT f.path, f.size_bytes, f.checksum, b.name AS branch,
                       f.last_modified, f.git_commit, f.compressed_size,
                       f.compression_ratio, f.retrieval_count
                FROM files f JOIN branches b ON f.branch_id=b.id
                WHERE b.name=%s AND f.deleted=FALSE
                ORDER BY f.path
                """,
                (branch,),
            )
            return [FileRecord(**dict(r)) for r in cur.fetchall()]

    def get_branch_stats(self, branch: str) -> Dict:
        if not self._conn:
            return {}
        with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS file_count,
                       COALESCE(SUM(f.size_bytes), 0)       AS total_bytes,
                       COALESCE(SUM(f.compressed_size), 0)  AS compressed_bytes,
                       COALESCE(AVG(f.compression_ratio), 0) AS avg_ratio
                FROM files f JOIN branches b ON f.branch_id=b.id
                WHERE b.name=%s AND f.deleted=FALSE
                """,
                (branch,),
            )
            return dict(cur.fetchone())

    def find_duplicates(self) -> List[Dict]:
        if not self._conn:
            return []
        with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT f.checksum,
                       ARRAY_AGG(f.path  ORDER BY f.path) AS file_paths,
                       ARRAY_AGG(b.name  ORDER BY f.path) AS branch_names,
                       COUNT(*)                            AS count,
                       MIN(f.size_bytes)                  AS size_bytes
                FROM files f JOIN branches b ON f.branch_id=b.id
                WHERE f.deleted=FALSE
                GROUP BY f.checksum HAVING COUNT(*) > 1
                ORDER BY size_bytes DESC
                """
            )
            return [dict(r) for r in cur.fetchall()]

    def get_file_history(self, file_path: str, branch: str) -> List[Dict]:
        if not self._conn:
            return []
        with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT fv.git_commit, fv.checksum, fv.size_bytes, fv.recorded_at
                FROM file_versions fv
                JOIN files f    ON fv.file_id = f.id
                JOIN branches b ON f.branch_id = b.id
                WHERE f.path=%s AND b.name=%s
                ORDER BY fv.recorded_at DESC
                """,
                (file_path, branch),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_top_retrieval_files(self, branch: str, limit: int = 10) -> List[Dict]:
        if not self._conn:
            return []
        with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT f.path, f.retrieval_count, f.size_bytes, f.compression_ratio
                FROM files f JOIN branches b ON f.branch_id=b.id
                WHERE b.name=%s AND f.deleted=FALSE
                ORDER BY f.retrieval_count DESC LIMIT %s
                """,
                (branch, limit),
            )
            return [dict(r) for r in cur.fetchall()]

    def compare_branches(self, branch1: str, branch2: str) -> Dict:
        if not self._conn:
            return {}
        with self._conn.cursor() as cur:
            cur.execute(
                'SELECT f.path FROM files f JOIN branches b ON f.branch_id=b.id '
                'WHERE b.name=%s AND f.deleted=FALSE',
                (branch1,),
            )
            set1 = {r[0] for r in cur.fetchall()}
            cur.execute(
                'SELECT f.path FROM files f JOIN branches b ON f.branch_id=b.id '
                'WHERE b.name=%s AND f.deleted=FALSE',
                (branch2,),
            )
            set2 = {r[0] for r in cur.fetchall()}
        return {
            'branch1_only': sorted(set1 - set2),
            'branch2_only': sorted(set2 - set1),
            'common':       sorted(set1 & set2),
            'branch1_count': len(set1),
            'branch2_count': len(set2),
        }
