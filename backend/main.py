from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import upload, scan, export, live, sectors

app = FastAPI(title="Stock Screener API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(scan.router)
app.include_router(export.router)
app.include_router(live.router)
app.include_router(sectors.router)


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}
