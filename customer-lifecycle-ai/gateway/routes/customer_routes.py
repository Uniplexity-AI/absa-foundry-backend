"""Gateway route — proxies /api/v1/customers/* to Customer State Service (:8003).

Frontend stores call /api/v1/customers/portfolio, /api/v1/customers/{id},
/api/v1/customers/{id}/timeline — all forwarded to the State Service.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from gateway.services.customer_profile_service import get_customer_names

logger = logging.getLogger("gateway.routes.customers")

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

_STATE_SERVICE_URL = "http://127.0.0.1:8003"

#: The list endpoint caps at 500 ids, so a names lookup never needs more.
_MAX_NAME_IDS = 500


@router.get("/portfolio")
async def proxy_portfolio(request: Request):
    """Forward portfolio summary query."""
    return await _forward(request, "/states/portfolio")


@router.get("/clv-summary")
async def proxy_clv_summary(request: Request):
    """Forward CLV summary query."""
    return await _forward(request, "/states/clv-summary")


@router.post("/compute-states")
async def proxy_compute_states(request: Request):
    """Recompute the lifecycle state snapshot for one as_of_date.

    The portfolio list, counts and KPIs all read ``customer_states`` — a derived
    per-snapshot table — so a customer that was just added (master record and/or
    feature snapshot) stays invisible until the state engine has run for that
    date. Exposed here, beside the other ``/customers`` reads, because that is
    exactly what the Add Customer form has to call after writing a snapshot.

    Idempotent: ``/states/compute`` upserts, so re-running is safe.
    """
    return await _forward(request, "/states/compute")


@router.get("/lifecycle-stages")
async def proxy_lifecycle_stages(request: Request):
    """Forward lifecycle stages query."""
    return await _forward(request, "/states/lifecycle-stages")


@router.get("")
async def proxy_list_all(request: Request):
    """Forward list-all customer states query."""
    return await _forward(request, "/states")


# NOTE: must be declared BEFORE the /{customer_id} catch-all below, otherwise
# "count" is captured as a customer id.
@router.get("/count")
async def proxy_count(request: Request):
    """Forward the total state-snapshot count for a date.

    The list endpoint caps ``limit`` at 500 and returns a bare array, so the UI
    has no way to know the true portfolio size from it; this is that denominator.
    """
    return await _forward(request, "/states/count")


@router.get("/snapshots")
async def proxy_snapshots(request: Request):
    """Forward the distinct snapshot dates to the state service."""
    return await _forward(request, "/states/snapshots")


# NOTE: like /count and /snapshots, this must be declared BEFORE the
# /{customer_id} catch-all below, otherwise "names" is read as a customer id.
@router.get("/names")
async def customer_names(
    request: Request,
    ids: str = Query(default="", description="Comma-separated customer ids"),
):
    """Customer id → ``full_name``, in one query, for the portfolio list.

    The list is served by the Customer State Service, and ``customer_states``
    carries no name column — which is why every row used to render a synthetic
    ``Customer <id>``. Names exist only on ``customers_clean``, so they are
    joined in here instead of with one request per row.

    Unknown, nameless and soft-deleted ids are simply absent from the map; the
    UI keeps its placeholder for those. A failure here is non-fatal for the list.
    """
    wanted = [part.strip() for part in ids.split(",") if part.strip()]
    if not wanted:
        return {"names": {}}
    if len(wanted) > _MAX_NAME_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"At most {_MAX_NAME_IDS} ids per request (got {len(wanted)}).",
        )

    try:
        names = await run_in_threadpool(get_customer_names, wanted)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Customer names lookup failed")
        raise HTTPException(status_code=500, detail=f"Names lookup failed: {exc}") from exc

    return {"names": names}


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
