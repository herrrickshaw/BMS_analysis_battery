"""
KaggleDatasetTracker — wraps VersionedCRUDManager to track Kaggle dataset files
under data/kaggle/ after each download, providing checksum integrity, compression
analytics, version history, and duplicate detection.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from vcrud.db_handler import DatabaseHandler
from vcrud.vcrud_manager import VersionedCRUDManager

log = logging.getLogger(__name__)

_BRANCH = 'kaggle-datasets'


class KaggleDatasetTracker:
    def __init__(self, db_url: Optional[str], repo_root: str):
        resolved_url = db_url or os.environ.get('DATABASE_URL', '')
        self._db = DatabaseHandler(resolved_url)
        self._manager = VersionedCRUDManager(self._db, repo_root)
        self._root = Path(repo_root)
        self._kaggle_dir = self._root / 'data' / 'kaggle'

    @property
    def available(self) -> bool:
        return self._db.available

    # ── Indexing ─────────────────────────────────────────────────────────────

    def index_dataset(self, dest: Path, category: str, slug: str) -> Dict:
        """Index every file under a just-downloaded dataset directory."""
        if not dest.exists():
            return {'indexed': 0, 'failed': 0, 'skipped': 'directory not found'}
        files = [f for f in dest.rglob('*') if f.is_file()]
        paths = [str(f.relative_to(self._root)) for f in files]
        result = self._manager.create_many(_BRANCH, paths,
                                           git_commit=f'kaggle:{slug}')
        return {**result, 'category': category, 'slug': slug, 'total_files': len(files)}

    def index_all(self) -> Dict:
        """Walk data/kaggle/** and index every file present on disk."""
        if not self._kaggle_dir.exists():
            return {'error': 'data/kaggle/ directory not found'}
        all_files = [
            str(f.relative_to(self._root))
            for f in self._kaggle_dir.rglob('*')
            if f.is_file()
        ]
        return self._manager.create_many(_BRANCH, all_files,
                                         git_commit='kaggle:bulk-index')

    # ── Status & reporting ───────────────────────────────────────────────────

    def status(self) -> Dict:
        if not self._db.available:
            return {
                'available': False,
                'message': 'PostgreSQL not connected — set DATABASE_URL to enable VCRUD tracking',
            }
        stats = self._db.get_branch_stats(_BRANCH)
        files = self._db.list_files_by_branch(_BRANCH)

        by_category: Dict[str, List[Dict]] = {}
        for f in files:
            parts = Path(f.path).parts
            # Expected layout: data / kaggle / <category> / <dataset-dir> / file
            cat = parts[2] if len(parts) > 2 else 'unknown'
            by_category.setdefault(cat, []).append({
                'path':             f.path,
                'size_bytes':       f.size_bytes,
                'compression_ratio': round(f.compression_ratio, 3) if f.compression_ratio else None,
                'checksum':         (f.checksum[:12] + '…') if f.checksum else None,
                'retrieval_count':  f.retrieval_count,
            })

        return {
            'available':   True,
            'branch':      _BRANCH,
            'stats':       stats,
            'by_category': {k: v for k, v in sorted(by_category.items())},
        }

    def export(self) -> Dict:
        return self._manager.export_summary(_BRANCH)

    def duplicates(self) -> List[Dict]:
        return self._manager.find_duplicates_across_branches()

    def optimize(self, min_ratio: float = 0.85) -> Dict:
        return self._manager.optimize_storage(_BRANCH, min_ratio)

    def hints(self) -> Dict:
        return self._manager.read_with_retrieval_hints(_BRANCH)

    # ── LFS helpers ──────────────────────────────────────────────────────────

    def lfs_pull(self) -> Dict:
        """Run git lfs pull to materialise LFS pointer files under data/kaggle/."""
        try:
            result = subprocess.run(
                ['git', 'lfs', 'pull', '--include', 'data/kaggle/**'],
                cwd=str(self._root), capture_output=True, text=True,
            )
            return {
                'success': result.returncode == 0,
                'stdout':  result.stdout.strip(),
                'stderr':  result.stderr.strip(),
            }
        except FileNotFoundError:
            return {'success': False, 'error': 'git-lfs not installed'}

    def lfs_status(self) -> Dict:
        """Report which data/kaggle files are LFS pointers vs real content."""
        pointers, real = [], []
        if not self._kaggle_dir.exists():
            return {'lfs_available': False, 'error': 'data/kaggle/ not found'}
        for f in self._kaggle_dir.rglob('*'):
            if not f.is_file():
                continue
            try:
                # LFS pointer files start with "version https://git-lfs..."
                header = f.read_bytes(40)
                if header.startswith(b'version https://git-lfs'):
                    pointers.append(str(f.relative_to(self._root)))
                else:
                    real.append(str(f.relative_to(self._root)))
            except OSError:
                pass
        return {
            'lfs_pointers': pointers,
            'real_files': real,
            'pointer_count': len(pointers),
            'real_count': len(real),
            'tip': 'Run git lfs pull (or POST /api/vcrud/lfs-pull) to fetch real content' if pointers else '',
        }

    def close(self):
        self._db.close()


# Module-level singleton — set by main.py lifespan
_tracker: Optional[KaggleDatasetTracker] = None


def init_tracker(db_url: Optional[str], repo_root: str) -> KaggleDatasetTracker:
    global _tracker
    _tracker = KaggleDatasetTracker(db_url, repo_root)
    return _tracker


def get_tracker() -> Optional[KaggleDatasetTracker]:
    return _tracker
