"""Cross-Sell Logic — applies YAML cross-sell rules to boost product scores.

"Customer has Savings + Salary → offer Credit Card"
Loads rules from config/products/cross_sell_rules.yaml.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from app.schemas.schemas import DecisionContext

logger = logging.getLogger("decision.recommendation.cross_sell")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config" / "products"


class CrossSellLogic:
    """Applies cross-sell rules to boost product propensity scores."""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "cross_sell_rules.yaml")
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        self._rules = cfg["rules"]
        logger.info("CrossSellLogic: %d rules loaded", len(self._rules))

    def apply(self, scored: list[dict], ctx: DecisionContext) -> list[dict]:
        """Apply cross-sell rules and return boosted scores + applied rules.

        Returns: (boosted_scored_list, applied_rules_list)
        """
        held = set(ctx.products.keys()) if ctx.products else set()
        applied: list[dict] = []

        for rule in self._rules:
            if self._match_trigger(rule, ctx, held):
                target = rule["target"]
                for item in scored:
                    if item["product_id"] == target and item["is_eligible"]:
                        boost = rule["boost"]
                        item["propensity_score"] = round(
                            min(item["propensity_score"] + boost, 1.0), 4
                        )
                        applied.append({
                            "rule_id": rule["id"],
                            "description": rule["description"],
                            "target": target,
                            "boost": boost,
                            "reason": rule.get("reason", ""),
                        })
                        break

        # Re-sort after boosting
        scored.sort(key=lambda r: r["propensity_score"], reverse=True)
        return scored, applied

    def _match_trigger(self, rule: dict, ctx: DecisionContext, held: set[str]) -> bool:
        """Evaluate rule trigger conditions against the DecisionContext."""
        trigger = rule.get("trigger", {})

        # Required products held
        required = trigger.get("products_held", [])
        if required and not all(p in held for p in required):
            return False

        # Salary credit requirement
        if trigger.get("has_salary_credit") and not ctx.has_salary_credit:
            return False

        # High balance
        if trigger.get("high_balance") and (ctx.total_amount_90d or 0) < 100000:
            return False

        # Income band
        min_income = trigger.get("min_income_band")
        if min_income:
            seg = ctx.segment or "MASS_MARKET"
            band_order = ["MASS_MARKET", "MASS_AFFLUENT", "AFFLUENT", "SME", "CORPORATE"]
            min_idx = band_order.index(min_income) if min_income in band_order else 0
            seg_idx = band_order.index(seg) if seg in band_order else 0
            if seg_idx < min_idx:
                return False

        # Segment minimum
        min_seg = trigger.get("min_segment")
        if min_seg:
            seg = ctx.segment or "MASS_MARKET"
            band_order = ["MASS_MARKET", "MASS_AFFLUENT", "AFFLUENT", "SME", "CORPORATE"]
            min_idx = band_order.index(min_seg) if min_seg in band_order else 0
            seg_idx = band_order.index(seg) if seg in band_order else 0
            if seg_idx < min_idx:
                return False

        return True

    def reload(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "cross_sell_rules.yaml")
        with open(config_path) as f:
            self._rules = yaml.safe_load(f)["rules"]
        logger.info("CrossSellLogic reloaded")
