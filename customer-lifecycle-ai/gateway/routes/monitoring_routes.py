"""Gateway route — proxies /api/v1/monitoring → Prediction Service (:8004).

Provides model monitoring endpoints: performance history, feature drift, prediction logs.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])

_MONITORING_URL = "http://localhost:8004"


@router.get("/performance-history")
async def proxy_performance_history(
    request: Request,
    horizon_days: int = Query(default=30, description="Days of history to return"),
):
    """Time-series model performance metrics."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                f"{_MONITORING_URL}/predict/monitoring/performance-history",
                params={"horizon_days": horizon_days},
            )
            return JSONResponse(
                content=resp.json() if resp.content else None,
                status_code=resp.status_code,
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Prediction Service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Prediction Service timed out")


@router.get("/feature-drift")
async def proxy_feature_drift(request: Request):
    """Feature drift (PSI) analysis."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{_MONITORING_URL}/predict/monitoring/feature-drift")
            return JSONResponse(
                content=resp.json() if resp.content else None,
                status_code=resp.status_code,
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Prediction Service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Prediction Service timed out")


@router.get("/prediction-log")
async def proxy_prediction_log(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Recent prediction log entries."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                f"{_MONITORING_URL}/predict/monitoring/prediction-log",
                params={"limit": limit, "offset": offset},
            )
            return JSONResponse(
                content=resp.json() if resp.content else None,
                status_code=resp.status_code,
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Prediction Service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Prediction Service timed out")
