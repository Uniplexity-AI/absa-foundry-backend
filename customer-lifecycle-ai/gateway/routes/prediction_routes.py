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

# Portfolio-wide value scoring can exceed the default 30s budget
_VALUE_BATCH_TIMEOUT = 300.0


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

@router.post("/simulate")
async def proxy_simulate(request: Request):
    """Forward What-If simulation to Prediction Service."""
    return await _forward(request, _PREDICTION_SERVICE_URL, "/predict/simulate")


@router.post("/value-batch")
async def proxy_value_batch(request: Request):
    """Forward Value Erosion + Future Value batch scoring to the Prediction Service.

    Writes erosion_probability / predicted_future_value into customer_states for the
    requested as_of_date. Scoring a full portfolio takes longer than the default
    timeout, so this call gets its own budget.
    """
    return await _forward(
        request, _PREDICTION_SERVICE_URL, "/predict/value-batch",
        timeout=_VALUE_BATCH_TIMEOUT,
    )


async def _forward(
    request: Request, base_url: str, target_path: str, timeout: float = 30.0
) -> JSONResponse:
    async with httpx.AsyncClient(timeout=timeout) as client:
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
