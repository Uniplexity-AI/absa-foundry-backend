"""Business Rules Engine — deterministic banking logic.

Evaluates YAML-configured banking rules AFTER eligibility checks.
Controls HOW actions are prioritized — action categories loaded from YAML config.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from app.schemas.schemas import DecisionContext, PolicyResult

logger = logging.getLogger("decision.business_rules")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "policies"
_CATALOG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "candidates"


def _load_action_categories() -> dict[str, set[str]]:
    """Load action category membership from YAML action catalog."""
    path = _CATALOG_DIR / "action_catalog.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return {k: set(v) for k, v in data.get("actions", {}).items()}


# Load once at module level
_action_categories = _load_action_categories()
RETENTION_ACTIONS = _action_categories.get("retention", set())
CROSS_SELL_ACTIONS = _action_categories.get("cross_sell", set())
ENGAGEMENT_ACTIONS = _action_categories.get("engagement", set())


class BusinessRulesEngine:
    """Applies deterministic banking logic to the decision pipeline."""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "banking_rules.yaml")
        self._rules = self._load_rules(config_path)
        logger.info("BusinessRulesEngine loaded: %d rules", len(self._rules))

    def apply(self, context: DecisionContext) -> PolicyResult:
        """Evaluate all business rules against the context."""
        blocked: list[str] = []
        required: list[str] = []
        modifiers: dict = {}
        triggered: list[str] = []

        for rule in self._rules:
            if self._evaluate_condition(rule["condition"], context):
                triggered.append(rule["id"])
                action = rule["action"]
                severity = rule.get("severity", "HARD")

                if action == "ONLY_REACTIVATION":
                    # Block all non-retention actions
                    blocked.extend(CROSS_SELL_ACTIONS)
                    blocked.extend(ENGAGEMENT_ACTIONS)
                elif action == "NO_MARKETING":
                    blocked.extend(CROSS_SELL_ACTIONS)
                    blocked.extend(ENGAGEMENT_ACTIONS)
                elif action == "PRIORITIZE_RETENTION":
                    for a in RETENTION_ACTIONS:
                        modifiers[a] = modifiers.get(a, 1.0) * 1.5
                elif action == "PRIORITIZE_CROSS_SELL":
                    for a in CROSS_SELL_ACTIONS:
                        modifiers[a] = modifiers.get(a, 1.0) * 1.5
                elif action == "PRIORITIZE_DIGITAL":
                    for a in ENGAGEMENT_ACTIONS:
                        modifiers[a] = modifiers.get(a, 1.0) * 1.5
                elif action == "REDUCE_OUTBOUND":
                    modifiers["_global"] = 0.5
                elif action == "ESCALATE_TO_RM":
                    required.append("RM_CALL")
                elif action == "REMOVE_CANDIDATE":
                    blocked.append("_duplicate_product")

        return PolicyResult(
            blocked_actions=list(set(blocked)),
            required_actions=list(set(required)),
            priority_modifiers=modifiers,
            triggered_rules=triggered,
        )

    def _evaluate_condition(self, condition: str, context: DecisionContext) -> bool:
        """Evaluate a simple condition string against the context.

        Supports: 'AND', 'OR', '==', '!=', 'in', 'not in', '>', '<', '>=', '<='
        with attribute access via 'context.field'.
        """
        try:
            import re
            ns = {"context": context, "True": True, "False": False, "None": None}
            expr = re.sub(r'\bAND\b', 'and', condition)
            expr = re.sub(r'\bOR\b', 'or', expr)
            return bool(eval(expr, {"__builtins__": {}}, ns))
        except Exception as e:
            logger.warning("Failed to evaluate condition '%s': %s: %s", condition, type(e).__name__, e)
            return False

    def _load_rules(self, config_path: str) -> list[dict]:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return data.get("rules", [])

    def reload(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "banking_rules.yaml")
        self._rules = self._load_rules(config_path)
        logger.info("BusinessRulesEngine reloaded: %d rules", len(self._rules))
