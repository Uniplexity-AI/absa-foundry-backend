"""HealthScorer — Composite health score from churn, CLV, behaviour.

Follows prediction-service.md §6.3 exactly.

health_score = (W_churn × churn_sub) + (W_clv × clv_sub) + (W_behaviour × behaviour_sub)
"""
from __future__ import annotations

import logging

from app.config.settings import PredictionConfig

logger = logging.getLogger("prediction.health_scorer")


class HealthScorer:
    """Computes 0-100 health score from churn prob, CLV percentile, behaviour.

    PoC caveat (D12): churn_probability is uncalibrated. Health scores
    are relative rankings within a date, not absolute values.
    """

    def __init__(self, config: PredictionConfig) -> None:
        self._w_churn = config.health_churn_weight      # 0.40
        self._w_clv = config.health_clv_weight          # 0.30
        self._w_behav = config.health_behaviour_weight  # 0.30
        logger.info(
            "HealthScorer loaded: w_churn=%.2f, w_clv=%.2f, w_behav=%.2f",
            self._w_churn, self._w_clv, self._w_behav,
        )

    def compute(
        self,
        churn_prob: float,
        clv_percentile: float,
        engagement_score: float | None,
    ) -> dict:
        """Return {health_score, component_scores}.

        Args:
            churn_prob: Raw XGBoost churn score [0, 1] — uncalibrated in PoC.
            clv_percentile: PERCENT_RANK of total_amount_90d [0, 1].
            engagement_score: From Feature Engine, or None → default 50.

        Returns:
            dict with keys: health_score (0-100, rounded to 1 decimal),
            component_scores: {churn_risk_sub, clv_percentile_sub, behaviour_sub}.
        """
        churn_sub = (1.0 - churn_prob) * 100.0
        clv_sub = clv_percentile * 100.0
        behav_sub = engagement_score if engagement_score is not None else 50.0

        score = (
            self._w_churn * churn_sub
            + self._w_clv * clv_sub
            + self._w_behav * behav_sub
        )
        return {
            "health_score": round(max(0.0, min(100.0, score)), 1),
            "component_scores": {
                "churn_risk_sub": round(churn_sub, 1),
                "clv_percentile_sub": round(clv_sub, 1),
                "behaviour_sub": round(behav_sub, 1),
            },
        }
