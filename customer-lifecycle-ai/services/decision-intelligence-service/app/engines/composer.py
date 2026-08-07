"""Decision Composer — assembles the final DecisionPackage.

Combines outputs from all engines into the API response.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from app.schemas.schemas import (
    ApprovalResult,
    DecisionContext,
    DecisionPackage,
    RankedAction,
    RoutingDecision,
)

logger = logging.getLogger("decision.composer")


class DecisionComposer:
    """Assembles the final decision package from engine outputs."""

    _counter: int = 0

    def compose(
        self,
        context: DecisionContext,
        top_actions: list[RankedAction],
        routing: RoutingDecision | None,
        approval: ApprovalResult | None,
        strategy: str = "BALANCED",
    ) -> DecisionPackage:
        """Assemble all outputs into a single DecisionPackage."""
        # Generate unique decision ID
        DecisionComposer._counter += 1
        decision_id = (
            f"DEC-{context.as_of_date.isoformat().replace('-', '')}"
            f"-{context.customer_id}-{DecisionComposer._counter:04d}"
        )

        # Determine status
        if approval and approval.required:
            status = "PENDING_APPROVAL"
        else:
            status = "AUTO_APPROVED"

        # Priority score from top action
        priority = top_actions[0].score if top_actions else 0.0

        # Confidence breakdown
        confidence = {
            "overall": 0.85,
            "model_confidence": 0.85,  # heuristic — will improve with LightGBM
            "rule_confidence": 1.0,
            "data_completeness": self._estimate_completeness(context),
        }

        # Reason codes
        reason_codes = self._generate_reason_codes(context, top_actions[0] if top_actions else None)

        return DecisionPackage(
            customer_id=context.customer_id,
            as_of_date=context.as_of_date,
            decision_id=decision_id,
            status=status,
            top_actions=top_actions,
            routing=routing,
            approval=approval,
            priority_score=round(priority, 1),
            estimated_revenue_zmw=2000.0,  # PoC placeholder
            estimated_churn_reduction=0.15 if context.churn_probability > 0.5 else 0.05,
            reason_codes=reason_codes,
            decision_confidence=confidence,
            strategy=strategy,
            computed_at=datetime.now(timezone.utc),
        )

    def _estimate_completeness(self, context: DecisionContext) -> float:
        """Estimate how complete the DecisionContext data is."""
        score = 1.0
        if context.health_score == 50.0:  # default
            score -= 0.1
        if context.churn_probability == 0.0:  # default
            score -= 0.1
        if context.engagement_score is None:
            score -= 0.05
        if not context.products:
            score -= 0.1
        return max(score, 0.0)

    def _generate_reason_codes(
        self, context: DecisionContext, top_action: RankedAction | None
    ) -> list[str]:
        """Generate structured reason codes for this decision."""
        codes = []

        if context.churn_probability > 0.5:
            codes.append("RC001")  # High Churn Risk
        else:
            codes.append("RC002")  # Low Churn Risk

        if context.clv_percentile > 0.7:
            codes.append("RC003")  # High CLV

        if context.has_salary_credit:
            codes.append("RC007")  # Stable Salary Inflows

        if context.total_amount_90d and context.total_amount_90d > 50000:
            codes.append("RC008")  # High Savings Balance

        if top_action and top_action.category == "cross_sell":
            codes.append("RC009")  # No Active Lending

        if context.engagement_score and context.engagement_score < 30:
            codes.append("RC004")  # Declining Engagement

        return codes
