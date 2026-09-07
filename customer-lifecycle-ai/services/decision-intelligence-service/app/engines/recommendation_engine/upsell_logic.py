"""Upsell Logic — applies YAML upsell rules for product upgrades.

"Customer has Basic Savings → offer Premium Savings"
Loads rules from config/products/upsell_rules.yaml.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from app.schemas.schemas import DecisionContext

logger = logging.getLogger("decision.recommendation.upsell")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config" / "products"


class UpsellLogic:
    """Applies upsell rules to offer premium product upgrades."""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "upsell_rules.yaml")
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        self._rules = cfg["rules"]
        logger.info("UpsellLogic: %d rules loaded", len(self._rules))

    def apply(self, scored: list[dict], ctx: DecisionContext) -> list[dict]:
        """Generate upsell recommendations as additional entries.

        Returns list of upsell recommendations appended to scored list.
        """
        held = set(ctx.products.keys()) if ctx.products else set()
        upsells = []

        for rule in self._rules:
            trigger = rule.get("trigger", {})
            product_held = trigger.get("product_held", "")

            if product_held not in held:
                continue
            if not self._match_conditions(trigger, ctx):
                continue

            upgrade = rule.get("upgrade", "UNKNOWN")
            # Skip if customer already holds the upgrade
            if upgrade in held:
                continue

            upsells.append({
                "product_id": upgrade,
                "product_name": upgrade.replace("_", " ").title(),
                "propensity_score": round(min(rule.get("boost", 0.0), 1.0), 4),
                "is_eligible": True,
                "is_upsell": True,
                "upgrade_from": product_held,
                "reason_codes": [f"upsell_{rule['id']}"],
                "reason_text": rule.get("reason", ""),
            })

        # Add upsells to scored list and re-sort
        all_recs = scored + upsells
        all_recs.sort(key=lambda r: r["propensity_score"], reverse=True)
        return all_recs

    def _match_conditions(self, trigger: dict, ctx: DecisionContext) -> bool:
        if trigger.get("has_salary_credit") and not ctx.has_salary_credit:
            return False
        if trigger.get("credit_risk_low") and ctx.credit_risk_rating not in ("LOW", "A", "AA"):
            return False
        if trigger.get("has_family_products"):
            return False  # stubbed — no family product data yet
        min_balance = trigger.get("min_balance_zmw")
        if min_balance and (ctx.total_amount_90d or 0) < min_balance:
            return False
        min_tenure = trigger.get("min_tenure_months")
        if min_tenure and ctx.tenure_months < min_tenure:
            return False
        min_age = trigger.get("min_age")
        if min_age and (ctx.age or 0) < min_age:
            return False
        min_clv = trigger.get("min_clv_percentile")
        if min_clv and ctx.clv_percentile < min_clv:
            return False
        return True

    def reload(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "upsell_rules.yaml")
        with open(config_path) as f:
            self._rules = yaml.safe_load(f)["rules"]
        logger.info("UpsellLogic reloaded")
