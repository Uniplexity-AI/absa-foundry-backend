"""Strategy Layer — re-weights ranked actions based on business strategy.

The ranking model never changes. Only the Strategy Layer's weights change.
This makes strategy experimentation fast, safe, and auditable.
"""
from __future__ import annotations

import logging

from app.schemas.schemas import RankedAction

logger = logging.getLogger("decision.strategy")

# Strategy definitions
STRATEGIES: dict[str, dict] = {
    "BALANCED": {
        "description": "Equal weights — no adjustment",
        "retention_boost": 1.0,
        "cross_sell_boost": 1.0,
        "engagement_boost": 1.0,
    },
    "RETENTION_FIRST": {
        "description": "Prioritize churn prevention",
        "retention_boost": 1.5,
        "cross_sell_boost": 0.8,
        "engagement_boost": 1.0,
    },
    "REVENUE_FIRST": {
        "description": "Maximize product sales and revenue",
        "retention_boost": 0.9,
        "cross_sell_boost": 1.5,
        "engagement_boost": 0.8,
    },
}


class StrategyLayer:
    """Applies business strategy weights to ranked actions."""

    def __init__(self) -> None:
        self._active_strategy = "BALANCED"
        logger.info("StrategyLayer loaded: active=%s", self._active_strategy)

    def apply(
        self, ranked_actions: list[RankedAction], strategy: str | None = None
    ) -> list[RankedAction]:
        """Re-weight scores based on active strategy."""
        strat_name = strategy or self._active_strategy
        strat = STRATEGIES.get(strat_name, STRATEGIES["BALANCED"])

        for action in ranked_actions:
            original = action.score
            if action.category == "retention":
                action.score = min(original * strat["retention_boost"], 100.0)
            elif action.category == "cross_sell":
                action.score = min(original * strat["cross_sell_boost"], 100.0)
            elif action.category == "engagement":
                action.score = min(original * strat["engagement_boost"], 100.0)

        # Re-sort after re-weighting
        ranked_actions.sort(key=lambda x: x.score, reverse=True)
        for i, action in enumerate(ranked_actions, 1):
            action.rank = i

        return ranked_actions

    @property
    def active_strategy(self) -> str:
        return self._active_strategy

    def set_strategy(self, strategy: str) -> bool:
        if strategy in STRATEGIES:
            self._active_strategy = strategy
            logger.info("Strategy switched to: %s", strategy)
            return True
        return False

    @staticmethod
    def list_strategies() -> list[dict]:
        return [
            {"name": k, "description": v["description"], "is_active": False}
            for k, v in STRATEGIES.items()
        ]
