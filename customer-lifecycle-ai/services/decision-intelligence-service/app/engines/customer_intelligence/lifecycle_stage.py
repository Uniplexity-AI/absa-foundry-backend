"""Lifecycle Stage — classifies customer into lifecycle stage.

Stages: ONBOARDING → ENGAGED → MATURE → DECLINING → AT_RISK
Based on tenure, health score, engagement, and state.
"""
from __future__ import annotations

import logging

from app.schemas.schemas import DecisionContext

logger = logging.getLogger("decision.customer_intel.lifecycle")


def classify_lifecycle_stage(context: DecisionContext) -> dict:
    """Classify customer into a lifecycle stage with confidence."""
    tenure = context.tenure_months
    health = context.health_score
    state = context.customer_state
    engagement = context.engagement_score or 50.0
    churn = context.churn_probability

    # ONBOARDING: new customer, short tenure
    if tenure < 6:
        return {"stage": "ONBOARDING", "confidence": 0.9, "criteria": ["tenure < 6 months"]}

    # AT_RISK: elevated churn or DORMANT state
    if state in ("CHURNED", "DORMANT") or churn > 0.6:
        criteria = []
        if state in ("CHURNED",):
            criteria.append("state=CHURNED")
        elif state == "DORMANT":
            criteria.append("state=DORMANT")
        if churn > 0.6:
            criteria.append("churn>60%")
        return {"stage": "AT_RISK", "confidence": 0.85, "criteria": criteria}

    # DECLINING: health dropping, moderate risk
    if health < 50 or state == "AT_RISK":
        return {"stage": "DECLINING", "confidence": 0.75, "criteria": ["health<50" if health < 50 else "state=AT_RISK"]}

    # ENGAGED: healthy, active, good engagement
    if health > 60 and engagement > 50 and state == "ACTIVE":
        return {"stage": "ENGAGED", "confidence": 0.8, "criteria": ["health>60", "high engagement", "active"]}

    # MATURE: long tenure, stable, moderate-to-good health
    if tenure >= 24 and health >= 50:
        return {"stage": "MATURE", "confidence": 0.7, "criteria": ["tenure>=24m", "health>=50"]}

    # DEFAULT
    return {"stage": "ENGAGED", "confidence": 0.5, "criteria": ["default"]}
