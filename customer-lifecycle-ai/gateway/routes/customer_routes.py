"""Gateway route — proxies /api/v1/customers/* to Customer State Service (:8003).

Frontend stores call /api/v1/customers/portfolio, /api/v1/customers/{id},
/api/v1/customers/{id}/timeline — all forwarded to the State Service.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

_STATE_SERVICE_URL = "http://localhost:8003"


@router.get("/portfolio")
async def proxy_portfolio(request: Request):
    """Forward portfolio summary query."""
    return await _forward(request, "/states/portfolio")


@router.get("")
async def proxy_list_all(request: Request):
    """Forward list-all customer states query."""
    return await _forward(request, "/states")


@router.get("/{customer_id}")
async def proxy_customer_detail(request: Request, customer_id: str):
    """Forward single customer state snapshot."""
    return await _forward(request, f"/states/{customer_id}")


@router.get("/{customer_id}/timeline")
async def proxy_customer_timeline(request: Request, customer_id: str):
    """Forward customer state transition timeline."""
    return await _forward(request, f"/states/{customer_id}/timeline")


async def _forward(request: Request, target_path: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = await request.body() if request.method in ("POST", "PUT") else None
            params = dict(request.query_params)

            resp = await client.request(
                method=request.method,
                url=f"{_STATE_SERVICE_URL}{target_path}",
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
            raise HTTPException(status_code=502, detail="Customer State Service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Customer State Service timed out")
