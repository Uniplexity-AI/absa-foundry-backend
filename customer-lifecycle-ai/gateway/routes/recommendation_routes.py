"""Gateway route — proxies /api/v1/recommendations/* to Decision Intelligence (:8005)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])

_URL = "http://localhost:8005"


@router.get("/{customer_id}")
async def proxy_recommendations(request: Request, customer_id: str):
    """Forward product recommendation query."""
    return await _forward(request, f"/recommendations/{customer_id}")


@router.get("/campaigns/list")
async def proxy_campaigns(request: Request):
    """Forward campaign target list."""
    return await _forward(request, "/recommendations/campaigns/list")


async def _forward(request: Request, target_path: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = await request.body() if request.method in ("POST", "PUT") else None
            params = dict(request.query_params)
            resp = await client.request(
                method=request.method,
                url=f"{_URL}{target_path}",
                params=params if params else None,
                content=body,
                headers={k: v for k, v in request.headers.items()
                         if k.lower() not in ("host", "content-length")},
            )
            return JSONResponse(
                content=resp.json() if resp.content else None,
                status_code=resp.status_code,
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Recommendation Engine unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Recommendation Engine timed out")
