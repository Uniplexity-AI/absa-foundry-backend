"""Pilot Action Service — business logic for frontend action buttons.

Delegates persistence to PilotActionRepository and maps repository rows to
API schemas. No business rules here beyond light validation — this is an
append-only audit log plus a per-customer JSONB state blob.

TODO:
Wire into gateway write endpoints when the pilot promotes to real ops.
"""
from __future__ import annotations

import logging

from app.repository.pilot_action_repository import PilotActionRepository
from app.schemas.schemas import (
    PilotActionLogEntry,
    PilotActionLogRequest,
    PilotActionLogResponse,
    PilotStateResponse,
)

logger = logging.getLogger("decision.pilot_action")


class PilotActionService:
    """Orchestrates logging + per-customer state for frontend actions."""

    def __init__(self) -> None:
        self._repo = PilotActionRepository()
        logger.info("PilotActionService initialized")

    # ------------------------------------------------------------------
    # Action log
    # ------------------------------------------------------------------

    def log_action(self, req: PilotActionLogRequest) -> PilotActionLogResponse:
        """Persist one action to the pilot_action_log table."""
        action_id = self._repo.insert_action(
            customer_id=req.customer_id,
            action_type=req.action_type,
            detail=req.detail,
            meta=req.meta,
            actor=req.actor,
        )
        logger.info(
            "Logged %s for %s (id=%s)", req.action_type, req.customer_id, action_id
        )
        entry = PilotActionLogEntry(
            id=action_id,
            customer_id=req.customer_id,
            action_type=req.action_type,
            detail=req.detail,
            meta=req.meta,
            actor=req.actor,
        )
        return PilotActionLogResponse(ok=True, id=action_id, action=entry)

    def list_actions(self, customer_id: str | None = None, limit: int = 100) -> list[PilotActionLogEntry]:
        """Return recent actions, newest first."""
        rows = self._repo.list_actions(customer_id=customer_id, limit=limit)
        return [
            PilotActionLogEntry(
                id=r["id"],
                customer_id=r["customer_id"],
                action_type=r["action_type"],
                detail=r.get("detail"),
                meta=r.get("meta") or {},
                actor=r.get("actor"),
                created_at=r.get("created_at"),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Per-customer state
    # ------------------------------------------------------------------

    def get_state(self, customer_id: str) -> PilotStateResponse:
        """Return the current JSONB state blob for a customer."""
        return PilotStateResponse(customer_id=customer_id, state=self._repo.get_state(customer_id))

    def merge_state(self, customer_id: str, patch: dict) -> PilotStateResponse:
        """Merge `patch` into the customer's state and return the merged blob."""
        merged = self._repo.upsert_state(customer_id, patch or {})
        return PilotStateResponse(customer_id=customer_id, state=merged)


# Module-level singleton (mirrors customer_intel_service pattern)
pilot_action_service = PilotActionService()
