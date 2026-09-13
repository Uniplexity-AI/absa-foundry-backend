"""Customer profile header — identity facts read straight from the clean layer.

The RM workspace header needs five facts that are spread across the pilot
schema and are not all served by the Customer State Service proxy:

===============  ==========================================================
Field            Source
===============  ==========================================================
Account number   ``customers_clean.account_number`` (set by ingest), else the
                 earliest row in ``accounts_clean`` for that customer
ID number (NRC)  ``customers_clean.national_id`` (set by ingest)
Tenure           derived from ``customers_clean.customer_since_date`` measured
                 to the customer's latest snapshot date
Assigned RM      ``pilot_customer_state.state->>'rm'`` (written by the pilot
                 action log when an RM is assigned)
Health score     ``customer_states.health_score`` (Layer 2 backfill)
===============  ==========================================================

Reads run against the **target** (clean) database, unlike the other
``/api/v1/customers/*`` routes which proxy to the Customer State Service — the
identity columns only exist here.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from shared.database.postgres import get_sync_target_engine

logger = logging.getLogger("gateway.services.customer_profile")

_PROFILE_SQL = text(
    """
    SELECT
        c.customer_id,
        c.full_name,
        c.status,
        c.branch_code,
        c.kyc_tier,
        c.nationality,
        c.date_of_birth,
        c.customer_since_date,
        c.market_segment_code,
        c.market_segment,
        c.account_number          AS stored_account_number,
        c.national_id,
        c.loaded_at,
        pa.account_id             AS derived_account_number,
        pa.account_type,
        pa.account_status,
        pa.opened_date,
        acc.account_count,
        s.as_of_date              AS snapshot_date,
        s.state                   AS lifecycle_state,
        s.health_score,
        s.erosion_probability,
        s.erosion_risk_level,
        s.predicted_future_value,
        s.future_value_percentile,
        rm.rm_value
    FROM public.customers_clean c
    LEFT JOIN LATERAL (
        SELECT a.account_id, a.account_type, a.status AS account_status, a.opened_date
        FROM public.accounts_clean a
        WHERE a.customer_id = c.customer_id
        ORDER BY a.opened_date NULLS LAST, a.account_id
        LIMIT 1
    ) pa ON TRUE
    LEFT JOIN LATERAL (
        SELECT count(*)::int AS account_count
        FROM public.accounts_clean a
        WHERE a.customer_id = c.customer_id
    ) acc ON TRUE
    LEFT JOIN LATERAL (
        SELECT cs.as_of_date, cs.state, cs.health_score, cs.erosion_probability,
               cs.erosion_risk_level, cs.predicted_future_value, cs.future_value_percentile
        FROM public.customer_states cs
        WHERE cs.customer_id = c.customer_id
        ORDER BY cs.as_of_date DESC
        LIMIT 1
    ) s ON TRUE
    LEFT JOIN LATERAL (
        SELECT p.state -> 'rm' AS rm_value
        FROM public.pilot_customer_state p
        WHERE p.customer_id = c.customer_id
        LIMIT 1
    ) rm ON TRUE
    WHERE c.customer_id = :customer_id
      -- A soft-deleted customer is not readable: the profile 404s, so the UI
      -- cannot open a page for a record the operator has removed.
      AND NOT c.is_deleted
    """
)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_json_scalar(value: Any) -> str | None:
    """``pilot_customer_state.state->'rm'`` is JSONB — unwrap to plain text."""
    if value is None:
        return None
    text_value = str(value).strip()
    if text_value.startswith('"') and text_value.endswith('"') and len(text_value) > 1:
        text_value = text_value[1:-1]
    return text_value or None


def _tenure(customer_since: date | None, as_of: date | None) -> tuple[int | None, str | None]:
    if customer_since is None:
        return None, None
    reference = as_of or datetime.now(timezone.utc).date()
    days = (reference - customer_since).days
    if days < 0:
        return None, None
    years = days / 365.25
    if years >= 1:
        label = f"{int(years)} Year{'s' if int(years) != 1 else ''}"
    else:
        months = max(1, round(days / 30.44))
        label = f"{months} Month{'s' if months != 1 else ''}"
    return days, label


def _age_years(date_of_birth: date | None, as_of: date | None) -> int | None:
    if date_of_birth is None:
        return None
    reference = as_of or datetime.now(timezone.utc).date()
    years = reference.year - date_of_birth.year - (
        (reference.month, reference.day) < (date_of_birth.month, date_of_birth.day)
    )
    return years if 0 <= years <= 130 else None


def get_customer_profile(
    customer_id: str, engine: Engine | None = None
) -> dict[str, Any] | None:
    """Compose the profile header for one customer, or ``None`` if unknown."""
    engine = engine or get_sync_target_engine()
    with engine.connect() as conn:
        row = conn.execute(_PROFILE_SQL, {"customer_id": customer_id}).mappings().first()

    if row is None:
        return None

    snapshot_date = row["snapshot_date"]
    customer_since = row["customer_since_date"]
    tenure_days, tenure_label = _tenure(customer_since, snapshot_date)

    account_number = row["stored_account_number"] or row["derived_account_number"]
    account_number_source = (
        "customers_clean" if row["stored_account_number"] else
        "accounts_clean" if row["derived_account_number"] else
        "not_on_file"
    )

    return {
        "customer_id": row["customer_id"],
        "full_name": row["full_name"],
        "account_number": account_number,
        "account_number_source": account_number_source,
        "account_count": row["account_count"] or 0,
        "account_type": row["account_type"],
        "account_status": row["account_status"],
        "account_opened_date": row["opened_date"],
        "national_id": row["national_id"],
        "national_id_available": row["national_id"] is not None,
        "tenure_days": tenure_days,
        "tenure_label": tenure_label,
        "customer_since_date": customer_since,
        "assigned_rm": _clean_json_scalar(row["rm_value"]),
        "health_score": _as_float(row["health_score"]),
        "lifecycle_state": row["lifecycle_state"],
        "erosion_probability": _as_float(row["erosion_probability"]),
        "erosion_risk_level": row["erosion_risk_level"],
        "predicted_future_value": _as_float(row["predicted_future_value"]),
        "future_value_percentile": _as_float(row["future_value_percentile"]),
        "status": row["status"],
        "branch_code": row["branch_code"],
        "kyc_tier": row["kyc_tier"],
        "nationality": row["nationality"],
        "date_of_birth": row["date_of_birth"],
        "age_years": _age_years(row["date_of_birth"], snapshot_date),
        "market_segment_code": row["market_segment_code"],
        "market_segment": row["market_segment"],
        "snapshot_date": snapshot_date,
        "loaded_at": row["loaded_at"],
    }
