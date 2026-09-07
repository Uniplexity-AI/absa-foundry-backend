"""Gateway route — proxies /api/v1/predictions/* to Prediction Service (:8004).

Frontend stores call /api/v1/predictions/{id}/churn, /api/v1/predictions/{id}/health,
/api/v1/predictions/markov-matrix — all forwarded to the Prediction Service.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])

_PREDICTION_SERVICE_URL = "http://127.0.0.1:8004"


@router.get("/markov-matrix")
async def proxy_markov_matrix(request: Request):
    """Forward Markov transition matrix query to State Service."""
    # Markov matrix lives on the state service, not prediction service
    return await _forward(request, "http://127.0.0.1:8003", "/states/markov/matrix")


@router.get("/{customer_id}/churn")
async def proxy_churn(request: Request, customer_id: str):
    """Forward churn probability query."""
    return await _forward(request, _PREDICTION_SERVICE_URL, f"/predict/{customer_id}/churn")


@router.get("/{customer_id}/health")
async def proxy_health(request: Request, customer_id: str):
    """Forward health score query."""
    return await _forward(request, _PREDICTION_SERVICE_URL, f"/predict/{customer_id}/health")


@router.get("/{customer_id}")
async def proxy_customer_prediction(request: Request, customer_id: str):
    """Forward full customer prediction."""
    return await _forward(request, _PREDICTION_SERVICE_URL, f"/predict/{customer_id}")


async def _forward(request: Request, base_url: str, target_path: str) -> JSONResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body = await request.body() if request.method in ("POST", "PUT") else None
            params = dict(request.query_params)

            resp = await client.request(
                method=request.method,
                url=f"{base_url}{target_path}",
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
            raise HTTPException(status_code=502, detail="Backend service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Backend service timed out")
