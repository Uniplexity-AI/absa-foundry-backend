"""Gateway route — proxies /api/v1/pilot/actions/* to Decision Intelligence (:8005).

Backs the frontend action buttons (Assign RM / Enrol Campaign / Launch
Campaign / Acknowledge alert / NBA Override / Save Action Plan / Record
Action) with real server-side persistence in etl_clean.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/pilot/actions", tags=["pilot-actions"])

_URL = "http://127.0.0.1:8005"


@router.post("/log")
async def proxy_log_action(request: Request):
    """Forward an action-log append to the Decision Intelligence service."""
    return await _forward(request, "/pilot/actions/log")


@router.get("")
async def proxy_list_actions(request: Request):
    """Forward recent-action list (optional ?customer_id=)."""
    return await _forward(request, "/pilot/actions")


@router.get("/state/{customer_id}")
async def proxy_get_state(request: Request, customer_id: str):
    """Forward per-customer state GET."""
    return await _forward(request, f"/pilot/actions/state/{customer_id}")


@router.post("/state/{customer_id}")
async def proxy_merge_state(request: Request, customer_id: str):
    """Forward per-customer state merge (POST body: {patch: {...}})."""
    return await _forward(request, f"/pilot/actions/state/{customer_id}")


async def _forward(request: Request, target_path: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = await request.body() if request.method in ("POST", "PUT", "PATCH") else None
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
            raise HTTPException(status_code=502, detail="Decision Intelligence unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Decision Intelligence timed out")
