"""Optimization Engine — multi-objective scoring.

Combines ranking score, estimated revenue, retention impact,
and acceptance probability into a final optimized score.
"""
from __future__ import annotations

import logging

from app.schemas.schemas import DecisionContext, RankedAction

logger = logging.getLogger("decision.optimization")

# Default weights (configurable via env vars)
DEFAULT_RANK_WEIGHT = 0.30
DEFAULT_REVENUE_WEIGHT = 0.25
DEFAULT_RETENTION_WEIGHT = 0.20
DEFAULT_ACCEPTANCE_WEIGHT = 0.15
DEFAULT_STRATEGIC_WEIGHT = 0.10

# Estimated revenue per action type (ZMW) — PoC estimates
ESTIMATED_REVENUE: dict[str, float] = {
    "OFFER_PERSONAL_LOAN": 2800,
    "OFFER_CREDIT_CARD": 1200,
    "OFFER_MORTGAGE": 8000,
    "OFFER_INSURANCE": 1500,
    "OFFER_INVESTMENT": 5000,
    "OFFER_OVERDRAFT": 800,
    "OFFER_FX_ACCOUNT": 2000,
    "RETENTION_CALL": 0,  # value is in retained customer, not direct revenue
    "FEE_WAIVER": -500,    # cost to the bank
    "LOYALTY_REWARD": -200,
    "MOBILE_BANKING_ONBOARDING": 300,
    "SALARY_ACCOUNT_MIGRATION": 1500,
}

# Estimated retention impact per action type
RETENTION_IMPACT: dict[str, float] = {
    "RETENTION_CALL": 0.18,
    "FEE_WAIVER": 0.22,
    "LOYALTY_REWARD": 0.15,
    "INTEREST_RATE_REVIEW": 0.12,
    "PRIORITY_SUPPORT": 0.10,
    "BRANCH_VISIT": 0.14,
    "RM_CALL": 0.16,
}


class OptimizationEngine:
    """Applies multi-objective optimization to ranked actions."""

    def __init__(
        self,
        w_rank: float = DEFAULT_RANK_WEIGHT,
        w_revenue: float = DEFAULT_REVENUE_WEIGHT,
        w_retention: float = DEFAULT_RETENTION_WEIGHT,
        w_acceptance: float = DEFAULT_ACCEPTANCE_WEIGHT,
        w_strategic: float = DEFAULT_STRATEGIC_WEIGHT,
    ) -> None:
        self._w = {
            "rank": w_rank,
            "revenue": w_revenue,
            "retention": w_retention,
            "acceptance": w_acceptance,
            "strategic": w_strategic,
        }
        logger.info("OptimizationEngine loaded: weights=%s", self._w)

    def optimize(
        self, ranked_actions: list[RankedAction], context: DecisionContext
    ) -> list[RankedAction]:
        """Re-score actions using multi-objective optimization."""
        max_revenue = max(
            (abs(ESTIMATED_REVENUE.get(a.action, 0)) for a in ranked_actions),
            default=1,
        )

        for action in ranked_actions:
            rank_score = action.score / 100.0  # normalize to [0, 1]
            revenue_score = abs(ESTIMATED_REVENUE.get(action.action, 0)) / max(max_revenue, 1)
            retention_score = RETENTION_IMPACT.get(action.action, 0.0)
            acceptance_score = 0.5  # default — would come from NBO model

            final = (
                self._w["rank"] * rank_score
                + self._w["revenue"] * revenue_score
                + self._w["retention"] * retention_score
                + self._w["acceptance"] * acceptance_score
                + self._w["strategic"] * 0.5  # strategic alignment
            )
            action.score = round(final * 100.0, 1)

        ranked_actions.sort(key=lambda x: x.score, reverse=True)
        for i, action in enumerate(ranked_actions, 1):
            action.rank = i

        return ranked_actions
