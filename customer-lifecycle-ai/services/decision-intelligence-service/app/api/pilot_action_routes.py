"""Pilot Action Routes — /pilot/actions/* (frontend write buttons).

Endpoints:
  POST /pilot/actions/log                      — append one action-log row
  GET  /pilot/actions?customer_id=             — recent actions (optional filter)
  GET  /pilot/actions/state/{customer_id}      — per-customer state blob
  POST /pilot/actions/state/{customer_id}      — merge patch into state

These are the server-side home for the frontend buttons that previously
only wrote to localStorage. The gateway proxies them at /api/v1/pilot/actions/*.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.schemas import (
    PilotActionLogEntry,
    PilotActionLogRequest,
    PilotActionLogResponse,
    PilotStateMergeRequest,
    PilotStateResponse,
)
from app.services.pilot_action_service import pilot_action_service

router = APIRouter(prefix="/pilot/actions", tags=["pilot-actions"])


@router.post("/log", response_model=PilotActionLogResponse)
def log_action(req: PilotActionLogRequest) -> PilotActionLogResponse:
    """Append one action-log row (RM assign, enrol, ack, override ...)."""
    if not req.customer_id.strip() or not req.action_type.strip():
        raise HTTPException(status_code=422, detail="customer_id and action_type are required")
    return pilot_action_service.log_action(req)


@router.get("", response_model=list[PilotActionLogEntry])
def list_actions(
    customer_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return recent action-log rows, newest first. Optional customer filter."""
    return pilot_action_service.list_actions(customer_id=customer_id, limit=limit)


@router.get("/state/{customer_id}", response_model=PilotStateResponse)
def get_state(customer_id: str) -> PilotStateResponse:
    """Return the per-customer mutable state blob."""
    return pilot_action_service.get_state(customer_id)


@router.post("/state/{customer_id}", response_model=PilotStateResponse)
def merge_state(customer_id: str, body: PilotStateMergeRequest) -> PilotStateResponse:
    """Merge `patch` into the customer's JSONB state and return the merged blob."""
    return pilot_action_service.merge_state(customer_id, body.patch or {})
