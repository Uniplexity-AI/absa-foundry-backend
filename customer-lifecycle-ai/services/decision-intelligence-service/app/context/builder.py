"""Decision Context Builder — assembles the DecisionContext from upstream services.

This is the ONLY module that calls upstream services.
All 6 engines receive the already-assembled DecisionContext.
"""
from __future__ import annotations

import logging
from datetime import date

from app.schemas.schemas import DecisionContext
from app.upstream.client import upstream

logger = logging.getLogger("decision.context_builder")


def build_decision_context(
    customer_id: str, as_of_date: date | None = None
) -> DecisionContext:
    """Assemble the complete DecisionContext for one customer.

    Calls State Service (8003), Prediction Service (8004), and
    Feature Service (8002). All downstream engines consume this object
    without making their own upstream calls.

    Returns a DecisionContext with defaults for any unavailable data.
    """
    if as_of_date is None:
        as_of_date = date.today()

    ctx_data: dict = {
        "customer_id": customer_id,
        "as_of_date": as_of_date,
    }

    # === State Service (8003) ===
    state = upstream.fetch_state(customer_id, as_of_date)
    if state:
        ctx_data["customer_state"] = state.get("state") or "ACTIVE"
        ctx_data["previous_state"] = state.get("previous_state")
        ctx_data["state_duration_days"] = _extract_state_duration(
            customer_id, as_of_date
        )

    # === Prediction Service (8004) ===
    churn = upstream.fetch_churn(customer_id, as_of_date)
    if churn:
        ctx_data["churn_probability"] = churn.get("churn_probability") or 0.0

    health = upstream.fetch_health(customer_id, as_of_date)
    if health:
        ctx_data["health_score"] = health.get("health_score") or 50.0
        ctx_data["component_scores"] = health.get("component_scores") or {}

    # === Feature Service (8002) ===
    features = upstream.fetch_features(customer_id)
    if features:
        ctx_data["segment"] = features.get("customer_segment") or "MASS_MARKET"
        ctx_data["age"] = features.get("age_years") or 35
        ctx_data["tenure_months"] = (features.get("customer_tenure_days") or 0) // 30
        ctx_data["branch_code"] = features.get("prof_primary_branch") or ""
        ctx_data["engagement_score"] = features.get("engagement_score")
        ctx_data["days_since_last_txn"] = features.get("days_since_last_txn")
        ctx_data["total_amount_90d"] = features.get("total_amount_90d")
        ctx_data["has_salary_credit"] = features.get("has_salary_credit", False) or False
        ctx_data["txn_count_30d"] = features.get("txn_count_30d")
        ctx_data["txn_count_90d"] = features.get("txn_count_90d")
        ctx_data["products"] = _extract_products(features)

    # CLV percentile from full prediction
    full_pred = _fetch_clv_percentile(customer_id, as_of_date)
    if full_pred is not None:
        ctx_data["clv_percentile"] = full_pred

    return DecisionContext(**ctx_data)


def _extract_state_duration(customer_id: str, as_of_date: date) -> int:
    """Estimate how long the customer has been in the current state."""
    timeline = upstream.fetch_state_timeline(customer_id)
    if not timeline:
        return 0

    entries = timeline.get("timeline", [])
    if len(entries) < 2:
        return 0

    # Find the most recent transition date
    current = entries[-1]
    for entry in reversed(entries[:-1]):
        if entry.get("state") != current.get("state"):
            delta = as_of_date - date.fromisoformat(entry["as_of_date"])
            return max(0, delta.days)

    # No transition found — customer has always been in this state
    first_date = date.fromisoformat(entries[0]["as_of_date"])
    return max(0, (as_of_date - first_date).days)


def _extract_products(features: dict) -> dict:
    """Extract product holdings from feature snapshot."""
    return {
        "savings": bool(features.get("rel_has_savings", False)),
        "current": bool(features.get("rel_has_current", False)),
        "credit_card": bool(features.get("rel_has_card", False)),
        "loan": bool(features.get("rel_has_loan", False)),
        "insurance": False,
        "investment": False,
        "mortgage": False,
        "overdraft": False,
    }


def _fetch_clv_percentile(customer_id: str, as_of_date: date) -> float | None:
    """Try to get CLV percentile from prediction service."""
    # The prediction service GET /predict/{id} returns CustomerPrediction with clv_percentile
    # For now, use health endpoint which includes component scores
    health = upstream.fetch_health(customer_id, as_of_date)
    if health and "component_scores" in health:
        cs = health["component_scores"]
        if "clv_percentile_sub" in cs:
            return cs["clv_percentile_sub"] / 100.0
    return None
