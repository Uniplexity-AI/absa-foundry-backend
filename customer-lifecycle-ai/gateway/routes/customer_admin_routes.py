"""Gateway routes — customer administration (soft delete + restore).

Mounted at ``/api/v1/customer-admin`` rather than under ``/api/v1/customers``
**deliberately**. The RBAC matrix is a union with no deny rules
(``shared/auth/permissions.py``: ``has_permission`` returns True if *any*
matching entry grants the role), so ``RoutePermission("*", "/api/v1/customers/**",
["RELATIONSHIP_MANAGER"])`` would authorise an RM to delete customers no matter
what narrower rule was added alongside it. A separate prefix means only the
entry for this prefix applies. This mirrors the existing precedent where ingest
was mounted at ``/api/v1/ingest`` to avoid inheriting ``/api/etl``'s rules.

Deletion is a **soft** delete and is reversible — see
``gateway/services/customer_admin_service.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from gateway.services import customer_admin_service as admin

logger = logging.getLogger("gateway.routes.customer_admin")

router = APIRouter(prefix="/api/v1/customer-admin", tags=["Customer Admin"])


# ═══════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════

class BulkDeleteRequest(BaseModel):
    """Delete many customers in one confirmed action."""

    customer_ids: list[str] = Field(
        ..., min_length=1, description="Customer IDs to soft-delete"
    )
    reason: str | None = Field(
        default=None, max_length=255,
        description="Why these customers are being removed (recorded in the audit trail)",
    )


class RestoreRequest(BaseModel):
    """Undo a soft delete."""

    customer_ids: list[str] = Field(..., min_length=1, description="Customer IDs to restore")


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _actor(request: Request) -> str:
    """Authenticated caller identity for the audit trail."""
    user = getattr(request.state, "user", None)
    username = getattr(user, "username", None)
    if username:
        return str(username)
    service = getattr(request.state, "service", None)
    if service is not None:
        return f"service:{getattr(service, 'name', 'unknown')}"
    return "api"


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════
# Deleted-customer views
# ═══════════════════════════════════════════════════════════════════

@router.get("/deleted")
async def list_deleted(limit: int = Query(default=100, ge=1, le=500)):
    """Recently deleted customers, newest first — powers the restore list."""
    try:
        rows = await run_in_threadpool(admin.list_deleted_customers, limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list deleted customers")
        raise HTTPException(status_code=500, detail=f"Failed to list deleted customers: {exc}") from exc
    return {"total": len(rows), "customers": rows}


@router.get("/deleted/count")
async def deleted_count():
    """How many customers are currently soft-deleted."""
    try:
        return {"total": await run_in_threadpool(admin.deleted_customer_count)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to count deleted customers")
        raise HTTPException(status_code=500, detail=f"Failed to count deleted customers: {exc}") from exc


# ═══════════════════════════════════════════════════════════════════
# Delete
# ═══════════════════════════════════════════════════════════════════

@router.post("/customers/bulk-delete")
async def bulk_delete_customers(request: Request, body: BulkDeleteRequest):
    """Soft-delete up to ``MAX_BULK_DELETE`` customers in one action."""
    try:
        result = await run_in_threadpool(
            admin.delete_customers,
            body.customer_ids,
            actor=_actor(request),
            reason=body.reason,
        )
    except admin.CustomerAdminError as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Bulk delete failed for %d id(s)", len(body.customer_ids))
        raise HTTPException(status_code=500, detail=f"Bulk delete failed: {exc}") from exc

    logger.info(
        "Bulk delete by %s: requested=%d deleted=%d already=%d not_found=%d",
        result["actor"], result["requested"], result["deleted"],
        len(result["already_deleted"]), len(result["not_found"]),
    )
    return result


@router.delete("/customers/{customer_id}")
async def delete_customer(
    request: Request,
    customer_id: str,
    reason: str | None = Query(default=None, max_length=255),
):
    """Soft-delete one customer."""
    try:
        result = await run_in_threadpool(
            admin.delete_customers,
            [customer_id],
            actor=_actor(request),
            reason=reason,
        )
    except admin.CustomerAdminError as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Delete failed for customer %s", customer_id)
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}") from exc

    if result["deleted"] == 0 and result["not_found"]:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} was not found.")

    logger.info("Delete %s by %s: deleted=%d", customer_id, result["actor"], result["deleted"])
    return result


# ═══════════════════════════════════════════════════════════════════
# Restore
# ═══════════════════════════════════════════════════════════════════

@router.post("/restore")
async def restore_customers(request: Request, body: RestoreRequest):
    """Undo a soft delete (single or bulk)."""
    try:
        result = await run_in_threadpool(
            admin.restore_customers, body.customer_ids, actor=_actor(request)
        )
    except admin.CustomerAdminError as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Restore failed for %d id(s)", len(body.customer_ids))
        raise HTTPException(status_code=500, detail=f"Restore failed: {exc}") from exc

    logger.info("Restore by %s: restored=%d", result["actor"], result["restored"])
    return result
