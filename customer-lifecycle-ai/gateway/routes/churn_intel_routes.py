"""Gateway route — proxies /api/v1/churn-intel/* to Decision Intelligence (:8005)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/churn-intel", tags=["churn-intel"])

_URL = "http://127.0.0.1:8005"

@router.get("/drivers")
async def proxy_drivers(request: Request):
    return await _forward(request, "/churn-intel/drivers")

@router.get("/segments")
async def proxy_segments(request: Request):
    return await _forward(request, "/churn-intel/segments")

@router.get("/branches")
async def proxy_branches(request: Request):
    return await _forward(request, "/churn-intel/branches")

async def _forward(request: Request, target_path: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            params = dict(request.query_params)
            resp = await client.get(f"{_URL}{target_path}", params=params)
            return JSONResponse(content=resp.json() if resp.content else None, status_code=resp.status_code)
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Churn Intelligence unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Churn Intelligence timed out")
