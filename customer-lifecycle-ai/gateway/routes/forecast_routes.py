"""Gateway route — proxies /api/v1/forecasts/* to Decision Intelligence (:8005)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/forecasts", tags=["forecasts"])

_URL = "http://127.0.0.1:8005"

@router.get("/churn")
async def proxy_churn_forecast(request: Request):
    return await _forward(request, "/forecasts/churn")

@router.get("/revenue-at-risk")
async def proxy_revenue(request: Request):
    return await _forward(request, "/forecasts/revenue-at-risk")


@router.get("/balance")
async def proxy_balance(request: Request):
    return await _forward(request, "/forecasts/balance")

async def _forward(request: Request, target_path: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            params = dict(request.query_params)
            resp = await client.get(f"{_URL}{target_path}", params=params)
            return JSONResponse(content=resp.json() if resp.content else None, status_code=resp.status_code)
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Forecast Engine unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Forecast Engine timed out")
