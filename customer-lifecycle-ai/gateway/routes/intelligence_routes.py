"""Gateway route — proxies /api/v1/intelligence/* to Decision Intelligence (:8005)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])

_URL = "http://127.0.0.1:8005"


@router.get("/clv-summary")
async def proxy_clv_summary(request: Request):
    return await _forward(request, "/intelligence/clv-summary")


@router.get("/aum-forecast")
async def proxy_aum_forecast(request: Request):
    return await _forward(request, "/intelligence/aum-forecast")


@router.get("/business-outcomes")
async def proxy_business_outcomes(request: Request):
    return await _forward(request, "/intelligence/business-outcomes")


@router.get("/lifecycle-summary")
async def proxy_lifecycle_summary(request: Request):
    return await _forward(request, "/intelligence/lifecycle-summary")


async def _forward(request: Request, target_path: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            params = dict(request.query_params)
            resp = await client.get(f"{_URL}{target_path}", params=params)
            return JSONResponse(content=resp.json() if resp.content else None, status_code=resp.status_code)
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Decision Intelligence Service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Decision Intelligence Service timed out")
