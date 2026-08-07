"""Approval Workflow — determines whether a decision needs human approval.

Auto-approves low-risk actions. Requires RM/BM approval for
high-value, fee waivers, and corporate customers.
"""
from __future__ import annotations

import logging

from app.schemas.schemas import ApprovalResult, DecisionContext, RankedAction

logger = logging.getLogger("decision.approval")


class ApprovalWorkflow:
    """Determines if a decision requires human approval before execution."""

    def check(
        self, context: DecisionContext, top_action: RankedAction
    ) -> ApprovalResult:
        """Check whether this decision needs approval."""
        action = top_action.action
        clv = context.clv_percentile
        segment = context.segment
        health = context.health_score

        # Fee waivers always need RM approval
        if action == "FEE_WAIVER":
            return ApprovalResult(
                required=True,
                reason="Fee waivers require Relationship Manager approval",
                approver_role="RM",
            )

        # Corporate customers need BM approval
        if segment == "CORPORATE":
            return ApprovalResult(
                required=True,
                reason="Corporate customers require Branch Manager approval",
                approver_role="BRANCH_MANAGER",
            )

        # Very high CLV customers need RM approval
        if clv > 0.9:
            return ApprovalResult(
                required=True,
                reason="Top-decile CLV customer requires RM approval",
                approver_role="RM",
            )

        # Critical health score → escalate
        if health < 20:
            return ApprovalResult(
                required=True,
                reason="Critical health score — escalate to Regional Manager",
                approver_role="REGIONAL_MANAGER",
            )

        # Auto-approve everything else
        return ApprovalResult(
            required=False,
            reason=None,
        )
