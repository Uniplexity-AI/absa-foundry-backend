"""Product Propensity Scorer — heuristic scoring engine.

Scores every product for a customer based on:
- Segment affinity (which products are relevant for their segment)
- Product eligibility (age, income, existing holdings)
- Base propensity + modifier boost from YAML product_catalog.yaml

Phase 1: heuristic — no ML. Phase 2+: LightGBM multi-label classifier.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from app.schemas.schemas import DecisionContext

logger = logging.getLogger("decision.recommendation.propensity")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config" / "products"


class ProductPropensityScorer:
    """Scores all products for a given customer using YAML rules."""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "product_catalog.yaml")
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        self._products = cfg["products"]
        self._income_bands = cfg["income_bands"]
        self._segment_affinity = cfg["segment_affinity"]
        logger.info("ProductPropensityScorer: %d products loaded", len(self._products))

    def score(self, ctx: DecisionContext) -> list[dict]:
        """Score every product for this customer.

        Returns list of {product_id, product_name, propensity_score (0-1),
                         is_eligible, reason_codes[]}
        """
        results = []
        held = set(ctx.products.keys()) if ctx.products else set()

        for product in self._products:
            pid = product["id"]
            eligibility = self._check_eligibility(product, ctx, held)
            if not eligibility["eligible"]:
                results.append({
                    "product_id": pid,
                    "product_name": product["name"],
                    "propensity_score": 0.0,
                    "is_eligible": False,
                    "reason_codes": eligibility["reasons"],
                })
                continue

            score = self._compute_propensity(product, ctx)
            results.append({
                "product_id": pid,
                "product_name": product["name"],
                "propensity_score": round(min(max(score, 0.0), 1.0), 4),
                "is_eligible": True,
                "reason_codes": eligibility["reasons"],
            })

        results.sort(key=lambda r: r["propensity_score"], reverse=True)
        return results

    def _check_eligibility(
        self, product: dict, ctx: DecisionContext, held: set[str]
    ) -> dict:
        """Check if a customer is eligible for a product. Uses YAML eligibility rules."""
        reasons = []
        el = product.get("eligibility", {})

        # Already held?
        if product["id"] in held:
            return {"eligible": False, "reasons": ["already_holds"]}

        # Age check
        if ctx.age:
            min_age = el.get("min_age", 0)
            max_age = el.get("max_age", 120)
            if ctx.age < min_age:
                return {"eligible": False, "reasons": [f"age_below_{min_age}"]}
            if ctx.age > max_age:
                return {"eligible": False, "reasons": [f"age_above_{max_age}"]}

        # Segment exclusion
        excluded = el.get("excluded_segments", [])
        if ctx.segment and ctx.segment in excluded:
            return {"eligible": False, "reasons": [f"segment_excluded_{ctx.segment}"]}

        # Required products
        required = el.get("required_products", [])
        for rp in required:
            if rp not in held:
                return {"eligible": False, "reasons": [f"missing_{rp}"]}

        # Income band check (simplified — uses segment affinity as proxy)
        segment_products = self._segment_affinity.get(ctx.segment, [])
        if product["id"] not in segment_products:
            reasons.append("segment_affinity_low")

        return {"eligible": True, "reasons": reasons}

    def _compute_propensity(self, product: dict, ctx: DecisionContext) -> float:
        """Compute heuristic propensity score from base + modifiers."""
        score = product.get("propensity_base", 0.5)
        modifiers = product.get("propensity_modifiers", {})

        if modifiers.get("has_salary_credit") and ctx.has_salary_credit:
            score += modifiers["has_salary_credit"]
        if modifiers.get("digital_active") and (ctx.engagement_score or 0) > 60:
            score += modifiers["digital_active"]
        if modifiers.get("high_engagement") and (ctx.engagement_score or 0) > 70:
            score += modifiers["high_engagement"]
        if modifiers.get("high_clv") and ctx.clv_percentile > 0.7:
            score += modifiers["high_clv"]
        if modifiers.get("high_balance") and (ctx.total_amount_90d or 0) > 100000:
            score += modifiers["high_balance"]
        if modifiers.get("long_tenure") and ctx.tenure_months > 36:
            score += modifiers["long_tenure"]
        if modifiers.get("health_score_high") and ctx.health_score > 70:
            score += modifiers["health_score_high"]
        if modifiers.get("credit_risk_low") and ctx.credit_risk_rating in ("LOW", "A", "AA"):
            score += modifiers["credit_risk_low"]
        if modifiers.get("has_family_products"):
            score += modifiers["has_family_products"]  # simplified — stubbed
        if modifiers.get("international_txn"):
            pass  # stubbed — needs feature data

        # Segment-based modifiers
        seg = ctx.segment or "MASS_MARKET"
        if modifiers.get("segment_mass_affluent") and seg == "MASS_AFFLUENT":
            score += modifiers["segment_mass_affluent"]
        if modifiers.get("segment_affluent") and seg == "AFFLUENT":
            score += modifiers["segment_affluent"]
        if modifiers.get("segment_corporate") and seg in ("CORPORATE", "SME"):
            score += modifiers["segment_corporate"]

        return score

    def reload(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "product_catalog.yaml")
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        self._products = cfg["products"]
        self._segment_affinity = cfg["segment_affinity"]
        logger.info("ProductPropensityScorer reloaded")
