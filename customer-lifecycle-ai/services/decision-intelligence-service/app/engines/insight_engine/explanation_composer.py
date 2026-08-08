"""Explanation Composer — assembles deterministic explanation output.

Combines reason codes + decision package into a structured ExplanationResponse.
Phase 2: deterministic only. Phase 3: LLM-generated natural language.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.schemas.schemas import DecisionPackage, ExplanationResponse, ReasonCode

logger = logging.getLogger("decision.insight.composer")


class ExplanationComposer:
    """Assembles explanation output from decision data."""

    def __init__(self) -> None:
        logger.info("ExplanationComposer initialized (deterministic mode)")

    def compose(
        self,
        decision: DecisionPackage,
        reason_codes: list[ReasonCode],
    ) -> ExplanationResponse:
        """Compose a full explanation for a decision package.

        Args:
            decision: The DecisionPackage from the Decision Engine.
            reason_codes: Generated reason codes from ReasonCodeGenerator.

        Returns:
            ExplanationResponse with structured explanation.
        """
        # Derive confidence from decision data
        confidence = self._compute_confidence(decision)

        return ExplanationResponse(
            decision_id=decision.decision_id,
            customer_id=decision.customer_id,
            top_reasons=reason_codes[:5],  # Top 5 most severe
            decision_summary=self._build_summary(decision, reason_codes),
            confidence_factors=confidence,
        )

    def explain(self, decision_id: str) -> ExplanationResponse | None:
        """Explain a previously computed decision by ID (stub).

        Phase 2: Returns None — no decision persistence yet.
        Phase 3: Query Decision Memory for historical decision.
        """
        logger.warning(
            "Decision persistence not available — no decision for %s", decision_id
        )
        return None

    def _build_summary(
        self, decision: DecisionPackage, codes: list[ReasonCode]
    ) -> str:
        """Build a deterministic summary string from reason codes."""
        high_codes = [c for c in codes if c.severity == "HIGH"]
        medium_codes = [c for c in codes if c.severity == "MEDIUM"]

        parts = []
        if high_codes:
            parts.append(f"{len(high_codes)} high-severity factors detected")
        if medium_codes:
            parts.append(f"{len(medium_codes)} medium-severity factors")
        if decision.top_actions:
            top = decision.top_actions[0]
            parts.append(
                f"Top action: {top.action} (score: {top.score:.0f})"
            )
        if decision.routing:
            parts.append(f"Channel: {decision.routing.channel}")

        return " | ".join(parts) if parts else "No significant factors detected"

    def _compute_confidence(self, decision: DecisionPackage) -> dict:
        """Compute confidence factors for the decision (deterministic)."""
        factors = {
            "ranked_actions_count": len(decision.top_actions),
            "strategy": decision.strategy,
            "status": decision.status,
        }

        if decision.top_actions:
            # Score spread between top and second action
            top_score = decision.top_actions[0].score
            if len(decision.top_actions) > 1:
                second_score = decision.top_actions[1].score
                factors["score_margin"] = round(top_score - second_score, 1)
            else:
                factors["score_margin"] = top_score

        if decision.routing:
            factors["routing_channel"] = decision.routing.channel
            factors["routing_reason"] = decision.routing.reason

        if decision.approval:
            factors["approval_required"] = decision.approval.required

        return factors
