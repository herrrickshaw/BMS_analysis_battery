"""
Persistent file workspace.

Files are saved to disk in UPLOADS_DIR and survive server restarts.
Each file gets a uuid-based ID. Supported analysis types:
  - screener   → normalize columns + run darvas/piotroski/coffee_can
  - portfolio  → parse as portfolio (Excel/PDF), enrich with P&L
  - preview    → return first 20 rows as JSON (any tabular file)
"""
from __future__ import annotations

import io
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

router = APIRouter(prefix='/api/files', tags=['files'])

UPLOADS_DIR = Path(__file__).resolve().parents[2] / 'uploads'
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

META_FILE = UPLOADS_DIR / '_meta.json'

ALLOWED = {
    'csv':  'text/csv',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'xls':  'application/vnd.ms-excel',
    'pdf':  'application/pdf',
}
MAX_MB = 30


# ── metadata store ─────────────────────────────────────────────────────────────

def _load_meta() -> dict:
    try:
        return json.loads(META_FILE.read_text()) if META_FILE.exists() else {}
    except Exception:
        return {}


def _save_meta(meta: dict) -> None:
    META_FILE.write_text(json.dumps(meta, indent=2, default=str))


# ── helpers ────────────────────────────────────────────────────────────────────

def _read_tabular(path: Path, ext: str) -> pd.DataFrame:
    if ext in ('xlsx', 'xls'):
        return pd.read_excel(path)
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.read_csv(path, encoding='latin-1')


# ── endpoints ──────────────────────────────────────────────────────────────────

@router.get('')
def list_files():
    """List all uploaded files with metadata."""
    meta = _load_meta()
    files = []
    for fid, info in meta.items():
        disk_path = UPLOADS_DIR / info['stored_name']
        if disk_path.exists():
            info['size_bytes'] = disk_path.stat().st_size
            files.append({'id': fid, **info})
        else:
            # stale entry — remove
            pass
    files.sort(key=lambda f: f.get('uploaded_at', ''), reverse=True)
    return {'files': files, 'count': len(files)}


@router.post('/upload')
async def upload_file(
    file: UploadFile = File(...),
    label: Optional[str] = Query(None, description='Optional display label'),
):
    """Save a file to the uploads workspace."""
    ext = (file.filename or '').rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED:
        raise HTTPException(415, f'Unsupported type ".{ext}". Allowed: {", ".join(ALLOWED)}.')

    raw = await file.read()
    if len(raw) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f'File exceeds {MAX_MB} MB.')

    fid         = str(uuid.uuid4())[:8]
    stored_name = f'{fid}_{file.filename}'
    disk_path   = UPLOADS_DIR / stored_name
    disk_path.write_bytes(raw)

    meta = _load_meta()
    meta[fid] = {
        'original_name': file.filename,
        'stored_name':   stored_name,
        'label':         label or file.filename,
        'ext':           ext,
        'size_bytes':    len(raw),
        'uploaded_at':   datetime.now(timezone.utc).isoformat(),
    }
    _save_meta(meta)

    return {'id': fid, **meta[fid]}


@router.delete('/{file_id}')
def delete_file(file_id: str):
    """Remove a file from the workspace."""
    meta = _load_meta()
    if file_id not in meta:
        raise HTTPException(404, 'File not found.')
    info = meta.pop(file_id)
    disk_path = UPLOADS_DIR / info['stored_name']
    if disk_path.exists():
        disk_path.unlink()
    _save_meta(meta)
    return {'deleted': file_id}


@router.get('/{file_id}/preview')
def preview_file(file_id: str, rows: int = Query(20, le=100)):
    """Return the first N rows of a tabular file as JSON."""
    meta = _load_meta()
    if file_id not in meta:
        raise HTTPException(404, 'File not found.')
    info = meta[file_id]
    ext  = info['ext']
    if ext == 'pdf':
        raise HTTPException(400, 'Preview not available for PDF files.')

    path = UPLOADS_DIR / info['stored_name']
    try:
        df = _read_tabular(path, ext)
        return {
            'file_id':  file_id,
            'filename': info['original_name'],
            'total_rows': len(df),
            'columns':  list(df.columns),
            'preview':  df.head(rows).fillna('').to_dict(orient='records'),
        }
    except Exception as exc:
        raise HTTPException(400, f'Could not read file: {exc}')


@router.post('/{file_id}/analyse')
async def analyse_file(
    file_id: str,
    analysis: str = Query(..., description='screener | portfolio | darvas | piotroski | coffee_can'),
    market:   str = Query('india'),
    scan_type: Optional[str] = Query(None, description='For screener: darvas|piotroski|coffee_can|all'),
):
    """
    Run an analysis on an uploaded file.

    analysis=screener   → normalize columns, run scan engines
    analysis=portfolio  → parse as portfolio, enrich with P&L + RSI
    analysis=darvas / piotroski / coffee_can  → shorthand for screener + specific scan
    """
    meta = _load_meta()
    if file_id not in meta:
        raise HTTPException(404, 'File not found.')
    info = meta[file_id]
    ext  = info['ext']
    path = UPLOADS_DIR / info['stored_name']

    # ── portfolio analysis ────────────────────────────────────────────────────
    if analysis == 'portfolio':
        raw = path.read_bytes()
        if ext == 'pdf':
            from parsers.pdf_parser import parse_pdf
            holdings = await run_in_threadpool(parse_pdf, io.BytesIO(raw), market)
        elif ext in ('xlsx', 'xls'):
            from parsers.excel_parser import parse_excel
            holdings = await run_in_threadpool(parse_excel, io.BytesIO(raw), market)
        else:
            raise HTTPException(400, 'Portfolio analysis requires Excel or PDF.')

        if not holdings:
            raise HTTPException(422, 'No holdings found in file.')

        from fetchers.history import fetch_holdings_history
        result = await run_in_threadpool(fetch_holdings_history, holdings)
        return {'analysis': 'portfolio', 'file_id': file_id, 'market': market, **result}

    # ── screener / scan analysis ──────────────────────────────────────────────
    if ext == 'pdf':
        raise HTTPException(400, 'Screener analysis requires CSV or Excel, not PDF.')

    try:
        df = await run_in_threadpool(_read_tabular, path, ext)
    except Exception as exc:
        raise HTTPException(400, f'Could not read file: {exc}')

    from column_map import normalize_columns
    df = await run_in_threadpool(normalize_columns, df)

    if 'ticker' not in df.columns and 'name' not in df.columns:
        raise HTTPException(422, 'File does not appear to be a screener export (no ticker/name column).')

    # Resolve which scan(s) to run
    shorthand = {'darvas': 'darvas', 'piotroski': 'piotroski', 'coffee_can': 'coffee_can'}
    if analysis in shorthand:
        run_scans = [shorthand[analysis]]
    else:
        # analysis == 'screener'
        target = scan_type or 'all'
        from scanners import darvas, piotroski, coffee_can
        all_scanners = {'darvas': darvas.scan, 'piotroski': piotroski.scan, 'coffee_can': coffee_can.scan}
        run_scans = list(all_scanners) if target == 'all' else [target]

    from scanners import darvas as _d, piotroski as _p, coffee_can as _cc
    SCANNER_FN = {'darvas': _d.scan, 'piotroski': _p.scan, 'coffee_can': _cc.scan}

    results: dict[str, list] = {}
    for st in run_scans:
        if st not in SCANNER_FN:
            raise HTTPException(400, f'Unknown scan type "{st}".')
        results[st] = await run_in_threadpool(SCANNER_FN[st], df)

    total = sum(len(v) for v in results.values())
    return {
        'analysis':  analysis,
        'file_id':   file_id,
        'market':    market,
        'rows_read': len(df),
        'total_results': total,
        'results':   results,
    }
