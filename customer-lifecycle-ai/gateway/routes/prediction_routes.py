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


# NOTE: must be declared BEFORE the /{customer_id} catch-all below, otherwise
# "portfolio-scores" is captured as a customer id.
@router.get("/portfolio-scores")
async def proxy_portfolio_scores(request: Request):
    """Forward the whole portfolio's scores for one date, in a single call.

    Returns ``{customer_id, churn_probability, clv, clv_percentile}`` per
    customer — this is the only place the **absolute** 12-month CLV is exposed,
    as opposed to ``clv_percentile``, which is only the customer's rank within
    the cohort. Unlike the per-customer route it does not raise when the churn
    model is missing: churn comes back null and CLV is still returned.
    """
    return await _forward(request, _PREDICTION_SERVICE_URL, "/predict/portfolio-scores")


# NOTE: also before the /{customer_id} catch-all, for the same reason.
@router.get("/lifecycle-forecast")
async def proxy_lifecycle_forecast(request: Request):
    """Forward the forward-looking lifecycle-stage forecast (14/30/90 days).

    One call returns every customer's predicted stage **per horizon**, with the
    class probabilities behind it. The current stage is not part of this — it is
    the state service's rule engine that owns "now".
    """
    return await _forward(request, _PREDICTION_SERVICE_URL, "/predict/lifecycle-forecast")


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


@router.post("/clv-run")
async def proxy_clv_run(request: Request):
    """Run the CLV LightGBM model for the selected snapshot date.

    Forwarded to the Prediction Service (``POST /predict/clv-batch``). Scoring a
    full portfolio takes longer than the default budget, so this call gets its
    own timeout.
    """
    return await _forward(
        request, _PREDICTION_SERVICE_URL, "/predict/clv-batch",
        timeout=_VALUE_BATCH_TIMEOUT,
    )


@router.post("/balance-growth-run")
async def proxy_balance_growth_run(request: Request):
    """Run the Balance Growth LightGBM model for the selected snapshot date.

    Forwards to the Prediction Service (``POST /predict/balance-growth-batch``).
    The model scores every customer's predicted balance_growth_pct which is then
    consumed by the AUM Forecast endpoint. Scoring a full portfolio can take up
    to 2 minutes, so this call gets a generous timeout.
    """
    return await _forward(
        request, _PREDICTION_SERVICE_URL, "/predict/balance-growth-batch",
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
