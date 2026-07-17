"""VCRUD dataset-tracking endpoints."""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/vcrud', tags=['vcrud'])


def _tracker():
    from vcrud.kaggle_tracker import get_tracker
    t = get_tracker()
    if t is None:
        raise HTTPException(503, 'VCRUD tracker not initialised')
    return t


@router.get('/status')
def vcrud_status():
    """Return indexing stats and per-category file list for Kaggle datasets."""
    try:
        from vcrud.kaggle_tracker import get_tracker
        t = get_tracker()
        if t is None:
            return {'available': False, 'message': 'Tracker not initialised yet'}
        return t.status()
    except Exception as exc:
        log.error('vcrud_status: %s', exc)
        return {'available': False, 'error': str(exc)}


@router.post('/index')
def vcrud_index_all():
    """Walk data/kaggle/ and index every downloaded file."""
    return _tracker().index_all()


@router.get('/export')
def vcrud_export():
    """Full summary of all indexed Kaggle dataset files with metadata."""
    return _tracker().export()


@router.get('/duplicates')
def vcrud_duplicates():
    """Find duplicate files (same checksum) across all tracked datasets."""
    return {'duplicates': _tracker().duplicates()}


@router.get('/hints')
def vcrud_hints():
    """Retrieval-frequency hints — which files to consider caching locally."""
    return _tracker().hints()


@router.get('/optimize')
def vcrud_optimize(min_ratio: float = 0.85):
    """Report files with poor compression ratio (already small / binary)."""
    return _tracker().optimize(min_ratio)


@router.get('/lfs/status')
def vcrud_lfs_status():
    """Show which data/kaggle files are LFS pointers vs real content."""
    return _tracker().lfs_status()


@router.post('/lfs/pull')
def vcrud_lfs_pull():
    """Run git lfs pull to materialise LFS pointer files."""
    return _tracker().lfs_pull()
