"""Gateway route — proxies /api/states/* to customer-state-service:8003.

Uses httpx to forward requests to the Customer State Service.
All /api/states/* paths are forwarded directly to the corresponding
/states/* endpoint on port 8003.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/states", tags=["states"])

_CUSTOMER_STATE_URL = "http://127.0.0.1:8003"


# Static routes — must come before catch-all
@router.get("/portfolio")
async def proxy_portfolio(request: Request):
    """Forward portfolio query to customer-state-service."""
    return await _forward(request, "/states/portfolio")


# Catch-all for all other /api/states/* paths
@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_to_state_service(request: Request, path: str):
    """Forward all requests to the Customer State Service."""
    target = f"/states/{path}" if path else "/states"
    return await _forward(request, target)


async def _forward(request: Request, target_path: str) -> JSONResponse:
    """Forward an incoming request to the Customer State Service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = await request.body() if request.method in ("POST", "PUT") else None
            params = dict(request.query_params)

            resp = await client.request(
                method=request.method,
                url=f"{_CUSTOMER_STATE_URL}{target_path}",
                params=params if params else None,
                content=body,
                headers={
                    k: v for k, v in request.headers.items()
                    if k.lower() not in ("host", "content-length")
                },
            )
            return JSONResponse(
                content=resp.json() if resp.content else None,
                status_code=resp.status_code,
            )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=502,
                detail="Customer State Service is not available",
            )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="Customer State Service timed out",
            )
