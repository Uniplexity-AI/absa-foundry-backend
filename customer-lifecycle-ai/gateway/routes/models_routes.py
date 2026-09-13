"""Gateway route - proxies /api/v1/models/* to Model Management Service (:8006).

Exception: the ROOT `GET /api/v1/models` serves the model registry document
(models/registry.json) because the UI store consumes that shape
(`{models: [{model_id, type, status, metrics, ...}]}`) and the registry file is
the source of truth written by scripts/train_models.py and read by predictors.
All sub-paths (/champion, /challengers, /features, /calibration, /audit, ...)
are still proxied to the Model Management Service.
"""
from __future__ import annotations
import json
from pathlib import Path

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/models", tags=["models"])

_MANAGEMENT_URL = "http://127.0.0.1:8006"

# <repo>/gateway/routes/models_routes.py -> parents[2] == <repo>
_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "models" / "registry.json"

async def _forward(request: Request, target_path: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = await request.body() if request.method in ("POST", "PUT") else None
            params = dict(request.query_params)
            resp = await client.request(
                method=request.method,
                url=f"{_MANAGEMENT_URL}{target_path}",
                params=params if params else None,
                content=body,
                headers={k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")},
            )
            return JSONResponse(content=resp.json() if resp.content else None, status_code=resp.status_code)
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Model Management Service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Model Management Service timed out")

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all_models(request: Request, path: str):
    """Proxy all /api/v1/models/* traffic to the Model Management Service."""
    return await _forward(request, f"/api/v1/models/{path}")

@router.get("")
async def root_models(request: Request):
    """Serve the model registry document (models/registry.json).

    Falls back to proxying the Model Management Service if the file is missing.
    """
    try:
        document = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        return JSONResponse(content=document)
    except (OSError, json.JSONDecodeError):
        return await _forward(request, "/api/v1/models")
