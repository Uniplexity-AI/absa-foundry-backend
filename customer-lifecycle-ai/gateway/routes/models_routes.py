"""Gateway route — proxies /api/v1/models → Prediction Service (:8004).

Returns registered model registry: champion/challenger models with metrics.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/models", tags=["models"])

_MODELS_URL = "http://127.0.0.1:8004"


@router.get("")
async def proxy_models(request: Request):
    """Forward model registry query to Prediction Service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{_MODELS_URL}/predict/models")
            return JSONResponse(
                content=resp.json() if resp.content else None,
                status_code=resp.status_code,
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Prediction Service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Prediction Service timed out")
