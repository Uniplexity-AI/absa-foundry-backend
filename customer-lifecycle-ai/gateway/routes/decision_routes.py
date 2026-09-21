"""Gateway route - proxies /api/v1/decisions/* to Decision Intelligence (:8005)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])

_URL = "http://127.0.0.1:8005"


@router.get("/{customer_id}/nba")
async def proxy_nba(request: Request, customer_id: str):
    """Forward NBA generation query."""
    return await _forward(request, f"/decisions/{customer_id}/nba")

@router.post("/cohort-campaigns")
async def proxy_cohort_campaigns(request: Request):
    """Forward Cohort Campaign generation query."""
    return await _forward(request, "/decisions/cohort-campaigns")

@router.api_route("/catalog/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_catalog(request: Request, path: str):
    """Forward Catalog queries."""
    return await _forward(request, f"/catalog/{path}")


async def _forward(request: Request, target_path: str) -> JSONResponse:
    # Set a high timeout because the LLM can take a while to respond
    async with httpx.AsyncClient(timeout=300.0) as client:
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
            raise HTTPException(status_code=502, detail="Decision Engine unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Decision Engine timed out")
