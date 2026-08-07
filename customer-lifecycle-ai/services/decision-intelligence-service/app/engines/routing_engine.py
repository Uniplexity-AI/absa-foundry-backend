"""Routing Engine — determines which stakeholder/channel handles each action.

Routes decisions to RM, Marketing, Retail, or System based on
customer value, risk level, and channel preference.
"""
from __future__ import annotations

import logging

from app.schemas.schemas import DecisionContext, RankedAction, RoutingDecision

logger = logging.getLogger("decision.routing")


class RoutingEngine:
    """Routes decisions to the right stakeholder and channel."""

    def route(
        self, top_action: RankedAction, context: DecisionContext
    ) -> RoutingDecision:
        """Determine routing for the top-ranked action."""
        action = top_action.action
        segment = context.segment
        health = context.health_score
        churn = context.churn_probability
        clv = context.clv_percentile

        # === Premier / High-Value customers → RM ===
        if segment in ("AFFLUENT", "CORPORATE"):
            return RoutingDecision(
                channel="RM_DIRECT",
                stakeholder="RELATIONSHIP_MANAGER",
                reason=f"VIP customer ({segment}) requires personal attention",
            )

        # === High churn + high CLV → urgent RM call ===
        if churn > 0.7 and clv > 0.8:
            return RoutingDecision(
                channel="RM_CALL",
                stakeholder="RELATIONSHIP_MANAGER",
                reason="High-value customer with critical churn risk",
            )

        # === FEE_WAIVER or LOYALTY_REWARD → RM review ===
        if action in ("FEE_WAIVER", "LOYALTY_REWARD"):
            return RoutingDecision(
                channel="RM_CALL",
                stakeholder="RELATIONSHIP_MANAGER",
                reason="Financial concession requires RM approval",
            )

        # === Retention calls for moderate risk → RM ===
        if action in ("RETENTION_CALL", "BRANCH_VISIT", "RM_CALL", "PRIORITY_SUPPORT"):
            return RoutingDecision(
                channel="RM_CALL",
                stakeholder="RELATIONSHIP_MANAGER",
                reason="Retention action requires human contact",
            )

        # === Digital/engagement actions → Marketing automation ===
        if action in (
            "MOBILE_BANKING_ONBOARDING", "DIGITAL_CAMPAIGN",
            "SMS_CAMPAIGN", "EMAIL_CAMPAIGN",
        ):
            return RoutingDecision(
                channel="DIGITAL",
                stakeholder="MARKETING",
                reason="Digital engagement action can be automated",
            )

        # === Cross-sell for healthy mass market → Marketing ===
        if top_action.category == "cross_sell" and health > 50 and segment == "MASS_MARKET":
            return RoutingDecision(
                channel="DIGITAL",
                stakeholder="MARKETING",
                reason="Cross-sell for healthy mass market — digital campaign",
            )

        # === Cross-sell for higher segments → RM ===
        if top_action.category == "cross_sell":
            return RoutingDecision(
                channel="RM_CALL",
                stakeholder="RELATIONSHIP_MANAGER",
                reason="Cross-sell for this segment benefits from RM contact",
            )

        # === Passive → System ===
        if top_action.category == "passive":
            return RoutingDecision(
                channel="PASSIVE",
                stakeholder="SYSTEM",
                reason="No action required — monitoring only",
            )

        # === Default → RM ===
        return RoutingDecision(
            channel="RM_CALL",
            stakeholder="RELATIONSHIP_MANAGER",
            reason="Default routing to Relationship Manager",
        )
