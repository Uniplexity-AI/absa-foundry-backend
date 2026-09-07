"""Ranking Engine — scores eligible actions and returns Top-N.

Phase 1: heuristic scoring driven by YAML config (config/ranking/ranking_rules.yaml).
Phase 2: LightGBM via LGBMRankingEngine.
All scoring weights are in YAML — no hardcoded numbers.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from app.schemas.schemas import CandidateAction, DecisionContext, RankedAction

logger = logging.getLogger("decision.ranking")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "ranking"


class RankingEngine:
    """Scores and ranks candidate actions using YAML-configurable heuristic rules."""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "ranking_rules.yaml")
        cfg = self._load_config(config_path)
        self._scoring = cfg["scoring"]
        self._thresholds = cfg["thresholds"]
        self._categories = cfg["categories"]
        logger.info("RankingEngine loaded: %d categories from YAML",
                     len(self._categories))

    def rank(
        self, candidates: list[CandidateAction], context: DecisionContext, top_n: int = 5
    ) -> list[RankedAction]:
        scored = [(c, self._score(c, context)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            RankedAction(rank=i, action=c.action, category=c.category, score=round(s, 1))
            for i, (c, s) in enumerate(scored[:top_n], 1)
        ]

    def _score(self, c: CandidateAction, ctx: DecisionContext) -> float:
        cat = c.category
        s = self._scoring
        t = self._thresholds
        score = s["baseline"]

        if cat == "retention":
            if ctx.customer_state in ("AT_RISK", "DORMANT"):
                score += s["retention"]["state_at_risk_dormant_bonus"]
            if ctx.churn_probability > t["churn_probability_high"]:
                score += s["retention"]["high_churn_bonus"]
            if ctx.health_score < t["health_score_low"]:
                score += s["retention"]["low_health_bonus"]
            if ctx.clv_percentile > t["clv_percentile_high"]:
                score += s["retention"]["high_clv_bonus"]

        elif cat == "cross_sell":
            if ctx.health_score > t["health_score_healthy"]:
                score += s["cross_sell"]["healthy_bonus"]
            if ctx.clv_percentile > t["clv_percentile_high"]:
                score += s["cross_sell"]["high_clv_bonus"]
            if ctx.has_salary_credit:
                score += s["cross_sell"]["salary_credit_bonus"]
            if ctx.customer_state in ("DORMANT", "CHURNED"):
                score += s["cross_sell"]["dormant_churned_penalty"]

        elif cat == "engagement":
            eng = ctx.engagement_score or 50.0
            if eng < t["engagement_score_low"]:
                score += s["engagement"]["low_engagement_bonus"]
            if (ctx.age or 99) < t["customer_age_young"]:
                score += s["engagement"]["young_customer_bonus"]
            if ctx.customer_state == "CHURNED":
                score += s["engagement"]["churned_penalty"]

        elif cat == "service":
            if ctx.kyc_expired:
                score += s["service"]["kyc_expired_bonus"]
            if ctx.active_complaint or ctx.aml_flag:
                score += s["service"]["compliance_issue_bonus"]

        elif cat == "passive":
            score = s["passive"]["score"]

        return min(max(score, 0.0), 100.0)

    def _load_config(self, path: str) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)

    def reload(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "ranking_rules.yaml")
        cfg = self._load_config(config_path)
        self._scoring = cfg["scoring"]
        self._thresholds = cfg["thresholds"]
        logger.info("RankingEngine reloaded from YAML config")
