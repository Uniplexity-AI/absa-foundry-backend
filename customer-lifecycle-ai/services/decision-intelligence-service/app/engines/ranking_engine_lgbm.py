"""LightGBM Ranking Engine — Phase 2.

Replaces heuristic ranking with trained LightGBM model.
Falls back to heuristic if model file not found.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import lightgbm as lgb

from app.schemas.schemas import CandidateAction, DecisionContext, RankedAction
from app.engines.ranking_engine import RankingEngine as HeuristicRanking

logger = logging.getLogger("decision.ranking_lgbm")

_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "champion" / "ranking"


class LGBMRankingEngine:
    """LightGBM action ranking. Falls back to heuristic if model missing."""

    def __init__(self) -> None:
        self._model = None
        self._fallback = HeuristicRanking()

        txt_path = _MODEL_DIR / "lgbm_ranker_v1.txt"
        meta_path = _MODEL_DIR / "metadata.json"

        if txt_path.exists() and meta_path.exists():
            self._model = lgb.Booster(model_file=str(txt_path))
            with open(meta_path) as f:
                meta = json.load(f)
            self._features = meta["feature_columns"]
            logger.info("LGBMRankingEngine loaded: %d features, MAE=%.4f",
                        len(self._features), meta.get("mae", 0))
        else:
            logger.info("No LightGBM model found. Using heuristic. "
                        "Run scripts/train_ranking_model.py to train.")

    def rank(
        self, candidates: list[CandidateAction], context: DecisionContext, top_n: int = 5
    ) -> list[RankedAction]:
        if self._model is None:
            return self._fallback.rank(candidates, context, top_n)

        vectors = [self._to_features(context, c) for c in candidates]
        X = np.array(vectors, dtype=np.float32)
        scores = self._model.predict(X)

        paired = list(zip(candidates, scores))
        paired.sort(key=lambda x: x[1], reverse=True)

        result = []
        for rank, (candidate, score) in enumerate(paired[:top_n], 1):
            result.append(RankedAction(
                rank=rank, action=candidate.action, category=candidate.category,
                score=round(float(score) * 100.0, 1),
            ))
        return result

    @staticmethod
    def _to_features(ctx: DecisionContext, action: CandidateAction) -> list[float]:
        eng = ctx.engagement_score or 50.0
        days = ctx.days_since_last_txn or 0
        amt = ctx.total_amount_90d or 0
        txn30 = ctx.txn_count_30d or 0
        sal = 1.0 if ctx.has_salary_credit else 0.0
        return [
            ctx.health_score, ctx.churn_probability, ctx.clv_percentile,
            eng, ctx.tenure_months, ctx.age, days, amt, sal, txn30,
            1.0 if ctx.customer_state == "ACTIVE" else 0.0,
            1.0 if ctx.customer_state == "AT_RISK" else 0.0,
            1.0 if ctx.customer_state == "DORMANT" else 0.0,
            1.0 if ctx.customer_state == "CHURNED" else 0.0,
            1.0 if action.category == "retention" else 0.0,
            1.0 if action.category == "cross_sell" else 0.0,
            1.0 if action.category == "engagement" else 0.0,
            1.0 if action.category == "service" else 0.0,
            1.0 if action.category == "passive" else 0.0,
        ]
