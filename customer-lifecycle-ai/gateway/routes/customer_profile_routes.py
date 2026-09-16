"""Gateway route — the customer profile header shown on the RM customer page.

``GET /api/v1/customers/{customer_id}/profile`` returns the identity facts the
workspace header needs — account number, national ID (NRC), tenure, assigned RM
and health score — sourced from the clean layer via
:mod:`gateway.services.customer_profile_service`.

Kept in its own router because the sibling ``/api/v1/customers/*`` routes proxy
to the Customer State Service; this one reads Postgres directly, and the extra
path segment means it never collides with that router's ``/{customer_id}``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from gateway.services.customer_profile_service import get_customer_profile

logger = logging.getLogger("gateway.routes.customer_profile")

router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])


@router.get("/{customer_id}/profile")
async def customer_profile(customer_id: str):
    """Identity + prediction summary for one customer.

    Values that no pilot source supplies yet come back as ``null`` together with
    an explicit availability flag (``national_id_available``,
    ``account_number_source``) so the UI can say *why* a field is empty rather
    than showing a bare dash.
    """
    try:
        profile = await run_in_threadpool(get_customer_profile, customer_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to build profile for %s", customer_id)
        raise HTTPException(status_code=500, detail=f"Failed to load customer profile: {exc}") from exc

    if profile is None:
        raise HTTPException(status_code=404, detail=f"Customer '{customer_id}' not found")

    return profile
