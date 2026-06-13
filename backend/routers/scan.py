from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from routers.upload import data_store
from scanners import darvas, piotroski, coffee_can

router = APIRouter()

SCANNERS = {
    'darvas':      darvas.scan,
    'piotroski':   piotroski.scan,
    'coffee_can':  coffee_can.scan,
}


@router.post("/api/scan/{scan_type}")
async def run_scan(scan_type: str, market: str):
    if scan_type not in SCANNERS and scan_type != 'all':
        raise HTTPException(status_code=400, detail=f"Unknown scan type '{scan_type}'. Choose from: {list(SCANNERS)} or 'all'")

    if market not in data_store:
        raise HTTPException(status_code=404, detail=f"No data uploaded for market '{market}'. Upload a CSV first.")

    df = data_store[market]

    if scan_type == 'all':
        results: dict[str, list] = {}
        for name, fn in SCANNERS.items():
            results[name] = await run_in_threadpool(fn, df)
        return {"market": market, "results": results}

    rows = await run_in_threadpool(SCANNERS[scan_type], df)
    return {"market": market, "scan": scan_type, "results": {scan_type: rows}}


@router.get("/api/results")
async def get_results(
    market: str,
    scan_type: str = 'all',
    signal: Optional[str] = None,
    min_score: Optional[int] = None,
    min_completeness: float = 0,
):
    if market not in data_store:
        raise HTTPException(status_code=404, detail=f"No data for '{market}'")

    df = data_store[market]
    scans_to_run = SCANNERS if scan_type == 'all' else {scan_type: SCANNERS[scan_type]}

    all_results: dict[str, list] = {}
    for name, fn in scans_to_run.items():
        rows = await run_in_threadpool(fn, df)
        if signal:
            rows = [r for r in rows if r.get('signal') == signal]
        if min_score is not None:
            rows = [r for r in rows if (r.get('score') or 0) >= min_score]
        if min_completeness > 0:
            rows = [r for r in rows if (r.get('completeness') or 0) >= min_completeness]
        all_results[name] = rows

    return {"market": market, "results": all_results}
