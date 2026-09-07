"""Reason Code Generator — deterministic, structured explanation codes.

Converts DecisionContext into structured reason codes using YAML thresholds.
Independent of LLM — works offline, always produces the same output for
the same input. The LLM gateway (Phase 3) will consume these codes
to generate natural language explanations.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from app.schemas.schemas import DecisionContext, ReasonCode

logger = logging.getLogger("decision.insight.reason_codes")

_CONFIG_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "config" / "explainability"
)


class ReasonCodeGenerator:
    """Generates structured reason codes from DecisionContext + YAML rules."""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "reason_codes.yaml")
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        self._thresholds = cfg["thresholds"]
        self._codes = cfg["reason_codes"]
        logger.info("ReasonCodeGenerator: %d codes loaded", len(self._codes))

    def generate(self, ctx: DecisionContext) -> list[ReasonCode]:
        """Generate all applicable reason codes for a DecisionContext."""
        t = self._thresholds
        codes: list[ReasonCode] = []

        # --- Churn Risk ---
        if ctx.churn_probability > t["churn_probability"]["high"]:
            codes.append(ReasonCode(
                code="CHURN_RISK_HIGH", severity="HIGH", category="RISK",
                detail={"churn_probability": ctx.churn_probability},
            ))
        elif ctx.churn_probability > t["churn_probability"]["medium"]:
            codes.append(ReasonCode(
                code="CHURN_RISK_MODERATE", severity="MEDIUM", category="RISK",
                detail={"churn_probability": ctx.churn_probability},
            ))

        # --- Health Score ---
        if ctx.health_score < t["health_score"]["low"]:
            codes.append(ReasonCode(
                code="HEALTH_DECLINING", severity="HIGH", category="RISK",
                detail={"health_score": ctx.health_score},
            ))
        elif ctx.health_score < t["health_score"]["medium"]:
            codes.append(ReasonCode(
                code="HEALTH_BELOW_AVERAGE", severity="MEDIUM", category="RISK",
                detail={"health_score": ctx.health_score},
            ))

        # --- State ---
        state = ctx.customer_state
        if state == "AT_RISK":
            codes.append(ReasonCode(
                code="STATE_AT_RISK", severity="HIGH", category="RISK",
                detail={"state": state, "duration_days": ctx.state_duration_days},
            ))
        elif state == "DORMANT":
            codes.append(ReasonCode(
                code="STATE_DORMANT", severity="HIGH", category="RISK",
                detail={"state": state, "duration_days": ctx.state_duration_days},
            ))
        elif state == "CHURNED":
            codes.append(ReasonCode(
                code="STATE_CHURNED", severity="HIGH", category="RISK",
                detail={"state": state},
            ))
        elif state == "ACTIVE" and ctx.health_score > t["health_score"]["medium"]:
            codes.append(ReasonCode(
                code="HEALTHY_STATE", severity="LOW", category="NEUTRAL",
                detail={"state": state, "health_score": ctx.health_score},
            ))

        # --- CLV ---
        if ctx.clv_percentile > t["clv_percentile"]["high"]:
            codes.append(ReasonCode(
                code="HIGH_CLV", severity="MEDIUM", category="OPPORTUNITY",
                detail={"clv_percentile": ctx.clv_percentile},
            ))
        elif ctx.clv_percentile < t["clv_percentile"]["low"]:
            codes.append(ReasonCode(
                code="LOW_CLV", severity="LOW", category="NEUTRAL",
                detail={"clv_percentile": ctx.clv_percentile},
            ))

        # --- Engagement ---
        eng = ctx.engagement_score or 50.0
        if eng < t["engagement_score"]["low"]:
            codes.append(ReasonCode(
                code="LOW_ENGAGEMENT", severity="MEDIUM", category="RISK",
                detail={"engagement_score": eng},
            ))

        # --- Inactivity ---
        days = ctx.days_since_last_txn or 0
        if days > t["days_since_last_txn"]["high"]:
            codes.append(ReasonCode(
                code="INACTIVE_EXTENDED", severity="HIGH", category="RISK",
                detail={"days_since_last_txn": days},
            ))

        # --- Salary ---
        if ctx.has_salary_credit:
            codes.append(ReasonCode(
                code="SALARY_ACTIVE", severity="LOW", category="OPPORTUNITY",
                detail={"has_salary_credit": True},
            ))

        codes.sort(key=lambda c: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[c.severity])
        return codes

    def reload(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "reason_codes.yaml")
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        self._thresholds = cfg["thresholds"]
        self._codes = cfg["reason_codes"]
        logger.info("ReasonCodeGenerator reloaded")
