import io

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from column_map import normalize_columns

router = APIRouter()

# Shared in-memory store: market_id -> normalized DataFrame
data_store: dict[str, pd.DataFrame] = {}


@router.post("/api/upload")
async def upload_csv(market: str, file: UploadFile = File(...)):
    content = await file.read()
    try:
        if file.filename and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
            df = await run_in_threadpool(pd.read_excel, io.BytesIO(content))
        else:
            try:
                df = pd.read_csv(io.BytesIO(content))
            except Exception:
                df = pd.read_csv(io.BytesIO(content), encoding='latin-1')
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}")

    df = await run_in_threadpool(normalize_columns, df)
    data_store[market] = df

    return {
        "market": market,
        "rows": len(df),
        "columns_detected": [c for c in df.columns],
        "message": f"Loaded {len(df)} stocks for '{market}'",
    }


@router.get("/api/markets")
def list_markets():
    return {
        "markets": list(data_store.keys()),
        "counts": {m: len(df) for m, df in data_store.items()},
    }
