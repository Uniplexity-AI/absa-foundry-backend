"""Behavioural Alerts — detects key signals in customer behaviour.

Alerts: SALARY_MISSING, VOLUME_DROPPING, ENGAGEMENT_DECLINING, DORMANCY_RISK.
"""
from __future__ import annotations

import logging

from app.schemas.schemas import BehaviouralAlert, DecisionContext

logger = logging.getLogger("decision.customer_intel.alerts")


def detect_alerts(context: DecisionContext) -> list[BehaviouralAlert]:
    """Scan the DecisionContext for actionable behavioural signals."""
    alerts: list[BehaviouralAlert] = []

    # ⚠ SALARY_MISSING: had salary credit but stopped
    if not context.has_salary_credit and context.days_since_last_txn and context.days_since_last_txn > 14:
        alerts.append(BehaviouralAlert(
            alert_type="SALARY_MISSING",
            severity="CRITICAL",
            description=f"No salary credit detected. Last transaction {context.days_since_last_txn} days ago. Salary may have been redirected to a competitor.",
        ))

    # ⚠ VOLUME_DROPPING: transaction count fell significantly
    if context.txn_count_30d is not None and context.txn_count_90d is not None:
        expected_30d = context.txn_count_90d / 3
        if expected_30d > 0 and context.txn_count_30d < expected_30d * 0.5:
            drop_pct = round((1 - context.txn_count_30d / expected_30d) * 100)
            alerts.append(BehaviouralAlert(
                alert_type="VOLUME_DROPPING",
                severity="WARNING",
                description=f"Transaction volume dropped {drop_pct}% vs 90-day average. Recent: {context.txn_count_30d}, Expected: {round(expected_30d)}.",
            ))

    # ⚠ ENGAGEMENT_DECLINING: engagement score critically low
    if context.engagement_score is not None and context.engagement_score < 20:
        alerts.append(BehaviouralAlert(
            alert_type="ENGAGEMENT_DECLINING",
            severity="WARNING",
            description=f"Digital engagement critically low (score: {context.engagement_score}/100). Customer may need re-onboarding to digital channels.",
        ))

    # ⚠ DORMANCY_RISK: approaching dormancy threshold
    if context.days_since_last_txn is not None and context.days_since_last_txn > 60:
        alerts.append(BehaviouralAlert(
            alert_type="DORMANCY_RISK",
            severity="WARNING",
            description=f"Customer inactive for {context.days_since_last_txn} days. Approaching 90-day dormancy threshold.",
        ))

    # ⚠ HIGH CHURN: immediate attention needed
    if context.churn_probability > 0.7:
        alerts.append(BehaviouralAlert(
            alert_type="HIGH_CHURN_RISK",
            severity="CRITICAL",
            description=f"Churn probability is {round(context.churn_probability * 100)}%. Immediate intervention recommended.",
        ))

    # ⚠ CHURNED: already lost
    if context.customer_state == "CHURNED":
        alerts.append(BehaviouralAlert(
            alert_type="CUSTOMER_CHURNED",
            severity="CRITICAL",
            description="Customer has already churned. Review for win-back campaign eligibility.",
        ))

    return alerts
