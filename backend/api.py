from __future__ import annotations

from fastapi import FastAPI, Query

from .service import SERVICE

app = FastAPI(title="Stablecoin Yield Dashboard API", version="1.0.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/yields")
def yields(force_refresh: bool = Query(default=False)) -> dict:
    return SERVICE.get_payload(force_refresh=force_refresh)


@app.get("/api/web3daoge")
def web3daoge(force_refresh: bool = Query(default=False)) -> dict:
    return SERVICE.get_daoge_payload(force_refresh=force_refresh)
