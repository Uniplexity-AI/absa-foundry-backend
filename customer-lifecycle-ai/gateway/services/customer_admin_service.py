"""Customer administration — soft delete and restore.

Deleting a customer is a **soft** delete. The clean layer is the historical
record that the feature store, state engine and model metrics are derived from,
so removing rows would break six foreign keys, orphan ten more tables, and
destroy ROI/label history (see ``database/migrations/016_customer_soft_delete.sql``
for the full reasoning). Instead a customer is flagged and every customer-facing
read filters it out.

Two properties this module guarantees:

* **Auditable.** Each affected customer gets a row in ``public.pilot_action_log``
  with the actor, timestamp and reason, and the flag on ``customers_clean``
  records ``deleted_at``/``deleted_by``. Nothing is silent.
* **Reversible.** :func:`restore_customers` clears the flag, so a mistaken
  bulk delete is one call to undo.

The caller's identity comes from the authenticated request (see
``gateway/routes/customer_admin_routes.py``); this module never invents one.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine

from shared.database.postgres import get_sync_target_engine

logger = logging.getLogger("gateway.services.customer_admin")

#: Guard rail: a single bulk call cannot touch more than this many customers.
#: Keeps a malformed client payload from flagging the whole portfolio.
MAX_BULK_DELETE = 500

#: Reason recorded when the operator does not supply one.
DEFAULT_REASON = "Removed by operator"

ACTION_DELETED = "CUSTOMER_DELETED"
ACTION_RESTORED = "CUSTOMER_RESTORED"


class CustomerAdminError(ValueError):
    """Raised for an unusable delete/restore request."""


def _normalise_ids(customer_ids: Iterable[Any]) -> list[str]:
    """De-duplicate, trim and length-check a caller-supplied id list."""
    seen: dict[str, None] = {}
    for raw in customer_ids or []:
        value = str(raw or "").strip()
        if value:
            seen.setdefault(value, None)

    ids = list(seen)
    if not ids:
        raise CustomerAdminError("No customer IDs were supplied.")
    if len(ids) > MAX_BULK_DELETE:
        raise CustomerAdminError(
            f"{len(ids)} customers were selected — the limit for one operation is {MAX_BULK_DELETE}."
        )
    return ids


def _audit(
    conn,
    *,
    customer_ids: Sequence[str],
    action: str,
    actor: str,
    reason: str | None,
    detail: str | None = None,
) -> None:
    """Append one audit row per affected customer.

    Best-effort: a missing/renamed ``pilot_action_log`` must not roll back a
    delete the operator already confirmed.
    """
    if not customer_ids:
        return
    try:
        conn.execute(
            text(
                """
                INSERT INTO public.pilot_action_log
                    (customer_id, action_type, detail, meta, actor, created_at)
                VALUES
                    (:customer_id, :action_type, :detail, CAST(:meta AS JSONB), :actor, :created_at)
                """
            ),
            [
                {
                    "customer_id": customer_id,
                    "action_type": action,
                    "detail": detail or reason,
                    "meta": _json(
                        {"reason": reason, "source": "customer_admin", "count": len(customer_ids)}
                    ),
                    "actor": actor,
                    "created_at": datetime.now(timezone.utc),
                }
                for customer_id in customer_ids
            ],
        )
    except Exception as exc:  # noqa: BLE001 - audit is advisory, the flag is the record
        logger.warning("Could not write %s to pilot_action_log: %s", action, exc)


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)


def delete_customers(
    customer_ids: Iterable[Any],
    *,
    actor: str = "api",
    reason: str | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Soft-delete customers. Returns a summary including which ids were affected."""
    engine = engine or get_sync_target_engine()
    ids = _normalise_ids(customer_ids)
    reason_text = (reason or DEFAULT_REASON).strip()[:255]

    with engine.begin() as conn:
        # Only flag rows that exist and are currently live, so re-deleting an
        # already-deleted id is a no-op rather than a false success.
        rows = conn.execute(
            text(
                """
                UPDATE public.customers_clean
                   SET is_deleted = true,
                       deleted_at = :deleted_at,
                       deleted_by = :deleted_by,
                       deleted_reason = :reason
                 WHERE customer_id = ANY(:ids)
                   AND NOT is_deleted
                RETURNING customer_id
                """
            ),
            {
                "ids": ids,
                "deleted_at": datetime.now(timezone.utc),
                "deleted_by": actor,
                "reason": reason_text,
            },
        ).scalars().all()

        deleted = list(rows)
        _audit(
            conn,
            customer_ids=deleted,
            action=ACTION_DELETED,
            actor=actor,
            reason=reason_text,
            detail=f"Soft-deleted {len(deleted)} customer(s)",
        )

    missing = [customer_id for customer_id in ids if customer_id not in set(deleted)]
    already = _already_deleted(engine, missing)
    not_found = [customer_id for customer_id in missing if customer_id not in set(already)]

    logger.info(
        "Soft-deleted %d customer(s) [%s]; %d already deleted, %d not found",
        len(deleted), actor, len(already), len(not_found),
    )

    return {
        "action": "delete",
        "requested": len(ids),
        "deleted": len(deleted),
        "deleted_ids": deleted,
        "already_deleted": already,
        "not_found": not_found,
        "reason": reason_text,
        "actor": actor,
        "soft_delete": True,
    }


def restore_customers(
    customer_ids: Iterable[Any],
    *,
    actor: str = "api",
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Undo a soft delete."""
    engine = engine or get_sync_target_engine()
    ids = _normalise_ids(customer_ids)

    with engine.begin() as conn:
        restored = list(
            conn.execute(
                text(
                    """
                    UPDATE public.customers_clean
                       SET is_deleted = false,
                           deleted_at = NULL,
                           deleted_by = NULL,
                           deleted_reason = NULL
                     WHERE customer_id = ANY(:ids)
                       AND is_deleted
                    RETURNING customer_id
                    """
                ),
                {"ids": ids},
            ).scalars().all()
        )

        _audit(
            conn,
            customer_ids=restored,
            action=ACTION_RESTORED,
            actor=actor,
            reason=None,
            detail=f"Restored {len(restored)} customer(s)",
        )

    not_restored = [customer_id for customer_id in ids if customer_id not in set(restored)]
    logger.info("Restored %d customer(s) [%s]", len(restored), actor)

    return {
        "action": "restore",
        "requested": len(ids),
        "restored": len(restored),
        "restored_ids": restored,
        "not_deleted": not_restored,
        "actor": actor,
    }


def _already_deleted(engine: Engine, candidate_ids: Sequence[str]) -> list[str]:
    """Which of these ids exist but are already flagged deleted."""
    if not candidate_ids:
        return []
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    """
                    SELECT customer_id FROM public.customers_clean
                     WHERE customer_id = ANY(:ids) AND is_deleted
                    """
                ),
                {"ids": list(candidate_ids)},
            ).scalars().all()
        )


def deleted_customer_count(engine: Engine | None = None) -> int:
    """How many customers are currently soft-deleted (for the UI restore affordance)."""
    engine = engine or get_sync_target_engine()
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM public.customers_clean WHERE is_deleted")
            ).scalar_one()
        )


def list_deleted_customers(limit: int = 100, engine: Engine | None = None) -> list[dict[str, Any]]:
    """Recently deleted customers, newest first — lets the UI offer a restore."""
    engine = engine or get_sync_target_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT customer_id, full_name, branch_code, deleted_at, deleted_by, deleted_reason
                  FROM public.customers_clean
                 WHERE is_deleted
                 ORDER BY deleted_at DESC NULLS LAST, customer_id
                 LIMIT :limit
                """
            ),
            {"limit": max(1, min(int(limit), MAX_BULK_DELETE))},
        ).mappings().all()
    return [dict(row) for row in rows]
