"""Gateway route — proxies /api/v1/insights/* to Decision Intelligence (:8005)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/insights", tags=["insights"])

_URL = "http://127.0.0.1:8005"


@router.get("/reason-codes/{customer_id}")
async def proxy_reason_codes(request: Request, customer_id: str):
    """Forward reason code generation query."""
    return await _forward(request, f"/insights/reason-codes/{customer_id}")


@router.get("/explain-decision/{decision_id}")
async def proxy_explain(request: Request, decision_id: str):
    """Forward decision explanation query."""
    return await _forward(request, f"/insights/explain-decision/{decision_id}")


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
            raise HTTPException(status_code=502, detail="Insight Engine unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Insight Engine timed out")
