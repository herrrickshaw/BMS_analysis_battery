import io

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from routers.upload import data_store
from scanners import coffee_can, darvas, piotroski

router = APIRouter()

ALL_SCANNERS = {
    'darvas':     darvas.scan,
    'piotroski':  piotroski.scan,
    'coffee_can': coffee_can.scan,
}


@router.get("/api/export")
async def export_results(market: str, scan_type: str = 'all'):
    if market not in data_store:
        raise HTTPException(status_code=404, detail=f"No data for '{market}'")

    df = data_store[market]
    scans = ALL_SCANNERS if scan_type == 'all' else {scan_type: ALL_SCANNERS[scan_type]}

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for name, fn in scans.items():
            rows = await run_in_threadpool(fn, df)
            if not rows:
                continue
            flat = _flatten(rows)
            flat.to_excel(writer, sheet_name=name[:31], index=False)

            # Auto-width columns
            ws = writer.sheets[name[:31]]
            for col_cells in ws.columns:
                width = max(len(str(c.value or '')) for c in col_cells) + 2
                ws.column_dimensions[col_cells[0].column_letter].width = min(width, 40)

    output.seek(0)
    filename = f"{market}_{scan_type}_results.xlsx"
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


def _flatten(results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        row = {k: v for k, v in r.items() if k not in ('criteria', 'passed')}
        for key, val in (r.get('criteria') or {}).items():
            row[key] = 'Pass' if val is True else 'Fail' if val is False else 'N/A'
        rows.append(row)
    return pd.DataFrame(rows)
