"""Eligibility Engine — "Does this customer qualify?"

Runs BEFORE business rules or AI ranking. Evaluates regulatory,
compliance, and credit policy constraints from YAML config.
If ineligible, the pipeline stops and returns the reason.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from app.schemas.schemas import DecisionContext, EligibilityResult

logger = logging.getLogger("decision.eligibility")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "eligibility"


class EligibilityEngine:
    """Evaluates YAML-configured eligibility rules against a DecisionContext."""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "eligibility_rules.yaml")
        self._rules = self._load_rules(config_path)
        logger.info("EligibilityEngine loaded: %d rules", len(self._rules))

    def evaluate(self, context: DecisionContext) -> EligibilityResult:
        """Check all eligibility rules. Returns blocked actions + reasons."""
        blocked: list[str] = []
        reasons: list[str] = []

        for rule in self._rules:
            if self._rule_matches(rule, context):
                blocked.append(rule["action"])
                reasons.append(rule["reason"])
                logger.debug(
                    "Eligibility rule %s triggered: %s", rule["id"], rule["reason"]
                )

        is_eligible = len(blocked) == 0

        return EligibilityResult(
            is_eligible=is_eligible,
            blocked_actions=blocked,
            reasons=reasons,
        )

    def _rule_matches(self, rule: dict, context: DecisionContext) -> bool:
        """Evaluate a single YAML rule against the context."""
        field_path = rule["field"].replace("context.", "")
        operator = rule["operator"]
        value = rule["value"]

        # Get the field value from context
        actual = getattr(context, field_path, None)

        if operator == "eq":
            return actual == value
        elif operator == "lt":
            return actual is not None and actual < value
        elif operator == "gt":
            return actual is not None and actual > value
        elif operator == "lte":
            return actual is not None and actual <= value
        elif operator == "gte":
            return actual is not None and actual >= value

        return False

    def _load_rules(self, config_path: str) -> list[dict]:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return data.get("rules", [])

    def reload(self, config_path: str | None = None) -> None:
        """Hot-reload rules from YAML without restart."""
        if config_path is None:
            config_path = str(_CONFIG_DIR / "eligibility_rules.yaml")
        self._rules = self._load_rules(config_path)
        logger.info("EligibilityEngine reloaded: %d rules", len(self._rules))
