"""Gateway route — proxies /api/v1/churn-intel/* to Decision Intelligence (:8005).
Branch-manager specific routes proxy to Customer State Service (:8003).
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/churn-intel", tags=["churn-intel"])

_URL       = "http://127.0.0.1:8005"   # Decision Intelligence
_STATE_URL = "http://127.0.0.1:8003"   # Customer State Service

@router.get("/drivers")
async def proxy_drivers(request: Request):
    return await _forward(request, "/churn-intel/drivers", _URL)

@router.get("/segments")
async def proxy_segments(request: Request):
    return await _forward(request, "/churn-intel/segments", _URL)

@router.get("/branches")
async def proxy_branches(request: Request):
    return await _forward(request, "/churn-intel/branches", _URL)

# ── Branch Manager live data (from Customer State Service) ──────────────────

@router.get("/at-risk-cases")
async def proxy_at_risk_cases(request: Request):
    """Top at-risk customers for the Branch Manager case list."""
    return await _forward(request, "/states/at-risk-cases", _STATE_URL)

@router.get("/unenrolled-high-risk")
async def proxy_unenrolled(request: Request):
    """AT_RISK customers not yet enrolled in any action."""
    return await _forward(request, "/states/unenrolled-high-risk", _STATE_URL)

@router.get("/priority-actions")
async def proxy_priority_actions(request: Request):
    """Real AI priority actions derived from aggregate at-risk data."""
    return await _forward(request, "/states/priority-actions", _STATE_URL)

async def _forward(request: Request, target_path: str, base_url: str = _URL) -> JSONResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            params = dict(request.query_params)
            resp = await client.get(f"{base_url}{target_path}", params=params)
            return JSONResponse(content=resp.json() if resp.content else None, status_code=resp.status_code)
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Churn Intelligence unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Churn Intelligence timed out")
