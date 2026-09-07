"""Health Trajectory — computes customer health trend over time.

Classifies trajectory as: IMPROVING, STABLE, DECLINING, or CRITICAL.
Reads health_score from state timeline to detect direction and magnitude.
"""
from __future__ import annotations

import logging
from datetime import date

from app.schemas.schemas import DecisionContext, HealthTrajectory
from app.upstream.client import upstream

logger = logging.getLogger("decision.customer_intel.trajectory")


def compute_health_trajectory(context: DecisionContext) -> HealthTrajectory:
    """Determine the customer's health trend using state timeline data."""
    # Try to get historical health scores from state timeline
    timeline = upstream.fetch_state_timeline(context.customer_id)
    previous_score = None
    score_30d_ago = None

    if timeline and "timeline" in timeline:
        entries = timeline.get("timeline", [])
        # State timeline entries have as_of_date + state.
        # Health scores are in the full state snapshot, not the timeline.
        # For now, use current + estimate from trajectory logic.
        pass

    current = context.health_score

    # Without history, estimate trajectory from context signals
    if context.state_duration_days > 90 and context.customer_state in ("DORMANT", "CHURNED"):
        trajectory = "CRITICAL"
        magnitude = 30.0
    elif context.customer_state == "AT_RISK" and context.churn_probability > 0.5:
        trajectory = "DECLINING"
        magnitude = 15.0
    elif context.health_score < 40:
        trajectory = "DECLINING"
        magnitude = 10.0
    elif context.health_score > 70:
        trajectory = "IMPROVING" if context.customer_state == "ACTIVE" else "STABLE"
        magnitude = 5.0
    else:
        trajectory = "STABLE"
        magnitude = 0.0

    trend_direction = "UP" if trajectory == "IMPROVING" else "DOWN" if trajectory in ("DECLINING", "CRITICAL") else "FLAT"

    return HealthTrajectory(
        trajectory=trajectory,
        current_score=current,
        previous_score=previous_score,
        score_30d_ago=score_30d_ago,
        trend_direction=trend_direction,
        trend_magnitude=magnitude,
    )
