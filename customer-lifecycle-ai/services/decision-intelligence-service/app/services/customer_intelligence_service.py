"""Customer Intelligence Service — orchestrates trajectory, lifecycle, and alerts.

Returns a complete CustomerIntelligence package for a single customer.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from app.context.builder import build_decision_context
from app.engines.customer_intelligence.health_trajectory import compute_health_trajectory
from app.engines.customer_intelligence.lifecycle_stage import classify_lifecycle_stage
from app.engines.customer_intelligence.behavioural_alerts import detect_alerts
from app.schemas.schemas import CustomerIntelligence

logger = logging.getLogger("decision.customer_intel")


class CustomerIntelligenceService:
    """Orchestrates customer intelligence analysis."""

    def analyze(
        self, customer_id: str, as_of_date: date | None = None
    ) -> CustomerIntelligence | None:
        """Build a full 360° customer intelligence report."""
        if as_of_date is None:
            as_of_date = date.today()

        try:
            context = build_decision_context(customer_id, as_of_date)
        except Exception:
            logger.exception("Failed to build context for %s", customer_id)
            return None

        trajectory = compute_health_trajectory(context)
        lifecycle = classify_lifecycle_stage(context)
        alerts = detect_alerts(context)

        # Projected states from Markov (simplified — uses heuristics)
        projected_30d = self._project_state(context, 30)
        projected_90d = self._project_state(context, 90)

        return CustomerIntelligence(
            customer_id=customer_id,
            as_of_date=as_of_date,
            health_trajectory=trajectory,
            lifecycle_stage=lifecycle["stage"],
            alerts=alerts,
            projected_state_30d=projected_30d,
            projected_state_90d=projected_90d,
            computed_at=datetime.utcnow(),
        )

    def get_alerts(self, customer_id: str, as_of_date: date | None = None) -> list:
        """Return only active behavioural alerts."""
        if as_of_date is None:
            as_of_date = date.today()
        context = build_decision_context(customer_id, as_of_date)
        return detect_alerts(context)

    def get_trajectory(self, customer_id: str, as_of_date: date | None = None):
        """Return only health trajectory."""
        if as_of_date is None:
            as_of_date = date.today()
        context = build_decision_context(customer_id, as_of_date)
        return compute_health_trajectory(context)

    @staticmethod
    def _project_state(context, days: int) -> str:
        """Simplify Markov projection into a state label."""
        if context.customer_state == "CHURNED":
            return "CHURNED"
        if context.customer_state == "DORMANT" and context.state_duration_days > 180:
            return "CHURNED" if days >= 90 else "DORMANT"
        if context.health_score < 30:
            return "CHURNED" if days >= 90 else "AT_RISK"
        if context.health_score < 50:
            return "DORMANT" if days >= 90 else "AT_RISK"
        if context.churn_probability > 0.7:
            return "DORMANT" if days >= 90 else "AT_RISK"
        return "ACTIVE" if context.customer_state == "ACTIVE" else "AT_RISK"


# Singleton
customer_intel_service = CustomerIntelligenceService()
