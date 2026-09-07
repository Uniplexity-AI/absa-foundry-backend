"""Gateway route — proxies /api/v1/outcomes/* to Decision Intelligence (:8005)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/outcomes", tags=["outcomes"])

_URL = "http://127.0.0.1:8005"

@router.get("/retention-roi")
async def proxy_retention_roi(request: Request):
    return await _forward(request, "/outcomes/retention-roi")

async def _forward(request: Request, target_path: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            params = dict(request.query_params)
            resp = await client.get(f"{_URL}{target_path}", params=params)
            return JSONResponse(content=resp.json() if resp.content else None, status_code=resp.status_code)
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Decision Engine outcomes service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Decision Engine outcomes service timed out")
