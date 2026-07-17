"""
Versioned CRUD Manager — high-level interface over DatabaseHandler.
Ported from herrrickshaw/global-stock-screener (feature/repository-systems-complete).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from vcrud.db_handler import CompressionManager, DatabaseHandler, FileRecord, GitBranchScanner

log = logging.getLogger(__name__)


class LocalFileIndexer:
    def __init__(self, root: str):
        self.root = Path(root)

    def scan_directory(self, branch: str,
                       patterns: Optional[List[str]] = None) -> List[FileRecord]:
        patterns = patterns or ['**/*']
        records: List[FileRecord] = []
        for pattern in patterns:
            for path in self.root.glob(pattern):
                if '.git' in path.parts or not path.is_file():
                    continue
                try:
                    stat = path.stat()
                    _, ratio = CompressionManager.compress_file(str(path))
                    checksum = CompressionManager.compute_checksum(str(path))
                    records.append(FileRecord(
                        path=str(path.relative_to(self.root)),
                        size_bytes=stat.st_size,
                        checksum=checksum,
                        branch=branch,
                        last_modified=datetime.fromtimestamp(stat.st_mtime),
                        compressed_size=int(stat.st_size * ratio),
                        compression_ratio=ratio,
                    ))
                except Exception as exc:
                    log.warning('Skipping %s: %s', path, exc)
        return records


class GitHubRemoteSync:
    """Placeholder for remote GitHub synchronization."""

    def fetch_branches(self, owner: str, repo: str) -> List[str]:
        return []

    def fetch_file_metadata(self, owner: str, repo: str, branch: str) -> Dict:
        return {}


class VersionedCRUDManager:
    def __init__(self, db_handler: DatabaseHandler, repo_path: str):
        self._db = db_handler
        self._repo = repo_path
        self._git = GitBranchScanner(repo_path)

    # ── Create ────────────────────────────────────────────────────────────────

    def create_file(self, file_path: str, branch: str,
                    git_commit: Optional[str] = None) -> int:
        abs_path = os.path.join(self._repo, file_path)
        if not os.path.exists(abs_path):
            log.warning('create_file: %s does not exist', file_path)
            return -1
        try:
            stat = os.stat(abs_path)
            checksum = CompressionManager.compute_checksum(abs_path)
            _, ratio = CompressionManager.compress_file(abs_path)
            record = FileRecord(
                path=file_path,
                size_bytes=stat.st_size,
                checksum=checksum,
                branch=branch,
                last_modified=datetime.fromtimestamp(stat.st_mtime),
                git_commit=git_commit,
                compressed_size=int(stat.st_size * ratio),
                compression_ratio=ratio,
            )
            file_id = self._db.create_file(record)
            log.info('Indexed %s (branch=%s, id=%s)', file_path, branch, file_id)
            return file_id
        except Exception as exc:
            log.error('create_file %s: %s', file_path, exc)
            return -1

    def create_many(self, branch: str, file_paths: List[str],
                    git_commit: Optional[str] = None) -> Dict:
        results = {'indexed': 0, 'failed': 0}
        for fp in file_paths:
            fid = self.create_file(fp, branch, git_commit)
            if fid >= 0:
                results['indexed'] += 1
            else:
                results['failed'] += 1
        log.info('create_many: %d indexed, %d failed', results['indexed'], results['failed'])
        return results

    # ── Read ─────────────────────────────────────────────────────────────────

    def read_file(self, file_path: str, branch: str) -> Optional[FileRecord]:
        return self._db.read_file(file_path, branch)

    def read_with_retrieval_hints(self, branch: str) -> Dict:
        return {
            'branch': branch,
            'stats':  self._db.get_branch_stats(branch),
            'top_files_to_cache': self._db.get_top_retrieval_files(branch),
        }

    # ── Update ────────────────────────────────────────────────────────────────

    def update_file(self, file_path: str, branch: str,
                    git_commit: Optional[str] = None) -> bool:
        abs_path = os.path.join(self._repo, file_path)
        if not os.path.exists(abs_path):
            return False
        try:
            stat = os.stat(abs_path)
            checksum = CompressionManager.compute_checksum(abs_path)
            _, ratio = CompressionManager.compress_file(abs_path)
            record = FileRecord(
                path=file_path,
                size_bytes=stat.st_size,
                checksum=checksum,
                branch=branch,
                last_modified=datetime.fromtimestamp(stat.st_mtime),
                git_commit=git_commit,
                compressed_size=int(stat.st_size * ratio),
                compression_ratio=ratio,
            )
            return self._db.update_file(record)
        except Exception as exc:
            log.error('update_file %s: %s', file_path, exc)
            return False

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_file(self, file_path: str, branch: str,
                    git_commit: Optional[str] = None) -> bool:
        return self._db.delete_file(file_path, branch, git_commit)

    # ── Analysis ─────────────────────────────────────────────────────────────

    def scan_branch_and_index(self, branch: str) -> Dict:
        indexer = LocalFileIndexer(self._repo)
        records = indexer.scan_directory(branch)
        results = {'indexed': 0, 'failed': 0, 'total': len(records)}
        for rec in records:
            try:
                self._db.create_file(rec)
                results['indexed'] += 1
            except Exception as exc:
                log.warning('scan_branch_and_index: %s failed: %s', rec.path, exc)
                results['failed'] += 1
        return results

    def find_duplicates_across_branches(self) -> List[Dict]:
        return self._db.find_duplicates()

    def compare_branches(self, branch1: str, branch2: str) -> Dict:
        return self._db.compare_branches(branch1, branch2)

    def get_file_history(self, file_path: str, branch: str) -> List[Dict]:
        return self._db.get_file_history(file_path, branch)

    def export_summary(self, branch: str) -> Dict:
        files = self._db.list_files_by_branch(branch)
        stats = self._db.get_branch_stats(branch)
        return {
            'branch': branch,
            'stats':  stats,
            'files':  [
                {
                    'path':             f.path,
                    'size_bytes':       f.size_bytes,
                    'compressed_size':  f.compressed_size,
                    'compression_ratio': f.compression_ratio,
                    'checksum':         f.checksum,
                    'retrieval_count':  f.retrieval_count,
                }
                for f in files
            ],
        }

    def optimize_storage(self, branch: str,
                         min_compression_ratio: float = 0.85) -> Dict:
        files = self._db.list_files_by_branch(branch)
        poor = [
            f for f in files
            if f.compression_ratio is not None and f.compression_ratio > min_compression_ratio
        ]
        return {
            'branch': branch,
            'files_with_poor_compression': [
                {'path': f.path, 'ratio': f.compression_ratio, 'size_bytes': f.size_bytes}
                for f in poor
            ],
            'recommendation': (
                f'{len(poor)} file(s) have compression ratio > {min_compression_ratio} '
                '(already small / incompressible)'
            ),
        }
