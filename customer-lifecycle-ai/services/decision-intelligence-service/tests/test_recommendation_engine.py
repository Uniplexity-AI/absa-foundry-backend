"""Tests for Recommendation Engine — product propensity, cross-sell, upsell, campaigns."""
from __future__ import annotations

from datetime import date

from app.schemas.schemas import DecisionContext
from app.engines.recommendation_engine.product_propensity import ProductPropensityScorer
from app.engines.recommendation_engine.cross_sell_logic import CrossSellLogic
from app.engines.recommendation_engine.upsell_logic import UpsellLogic
from app.engines.recommendation_engine.campaign_mapper import CampaignMapper


def make_context(**kwargs) -> DecisionContext:
    defaults = {
        "customer_id": "TEST001",
        "as_of_date": date(2026, 7, 27),
        "customer_state": "ACTIVE",
        "segment": "MASS_AFFLUENT",
        "age": 35,
        "branch_code": "BR001",
        "health_score": 70.0,
        "churn_probability": 0.2,
        "clv_percentile": 0.6,
        "tenure_months": 24,
        "has_salary_credit": True,
        "engagement_score": 65.0,
        "total_amount_90d": 75000,
        "products": {"SAVINGS": {}, "CURRENT_ACCOUNT": {}},
    }
    defaults.update(kwargs)
    return DecisionContext(**defaults)


class TestProductPropensity:
    """Tests for ProductPropensityScorer."""

    def test_all_products_scored(self):
        scorer = ProductPropensityScorer()
        ctx = make_context()
        results = scorer.score(ctx)
        assert len(results) == 6
        # All 6 products should be present
        pids = {r["product_id"] for r in results}
        assert "PERSONAL_LOAN" in pids
        assert "CREDIT_CARD" in pids

    def test_already_held_excluded(self):
        scorer = ProductPropensityScorer()
        ctx = make_context(products={"PERSONAL_LOAN": {}, "SAVINGS": {}})
        results = scorer.score(ctx)
        loan = next(r for r in results if r["product_id"] == "PERSONAL_LOAN")
        assert loan["is_eligible"] is False
        assert "already_holds" in loan["reason_codes"]

    def test_affluent_gets_mortgage(self):
        scorer = ProductPropensityScorer()
        ctx = make_context(segment="AFFLUENT", age=35, clv_percentile=0.8)
        results = scorer.score(ctx)
        mortgage = next(r for r in results if r["product_id"] == "MORTGAGE")
        assert mortgage["is_eligible"] is True
        assert mortgage["propensity_score"] > 0.4

    def test_mass_market_no_mortgage(self):
        scorer = ProductPropensityScorer()
        ctx = make_context(segment="MASS_MARKET")
        results = scorer.score(ctx)
        mortgage = next(r for r in results if r["product_id"] == "MORTGAGE")
        assert mortgage["is_eligible"] is False
        assert "segment_excluded_MASS_MARKET" in mortgage["reason_codes"]

    def test_scores_sorted_descending(self):
        scorer = ProductPropensityScorer()
        ctx = make_context()
        results = scorer.score(ctx)
        scores = [r["propensity_score"] for r in results if r["is_eligible"]]
        assert scores == sorted(scores, reverse=True)


class TestCrossSellLogic:
    """Tests for CrossSellLogic."""

    def test_salary_triggers_credit_card(self):
        logic = CrossSellLogic()
        ctx = make_context(products={"SAVINGS": {}}, has_salary_credit=True)
        scored = [
            {"product_id": "CREDIT_CARD", "propensity_score": 0.55, "is_eligible": True, "product_name": "Credit Card", "reason_codes": []},
        ]
        boosted, applied = logic.apply(scored, ctx)
        assert boosted[0]["propensity_score"] > 0.55
        assert len(applied) == 1
        assert applied[0]["rule_id"] == "SAVINGS_TO_CREDIT_CARD"

    def test_no_salary_no_boost(self):
        logic = CrossSellLogic()
        ctx = make_context(products={"SAVINGS": {}}, has_salary_credit=False)
        scored = [
            {"product_id": "CREDIT_CARD", "propensity_score": 0.55, "is_eligible": True, "product_name": "Credit Card", "reason_codes": []},
        ]
        boosted, applied = logic.apply(scored, ctx)
        assert boosted[0]["propensity_score"] == 0.55
        assert len(applied) == 0


class TestUpsellLogic:
    """Tests for UpsellLogic."""

    def test_basic_savings_triggers_premium(self):
        logic = UpsellLogic()
        ctx = make_context(
            products={"SAVINGS": {}},
            total_amount_90d=60000,
            tenure_months=18,
        )
        scored = [
            {"product_id": "CREDIT_CARD", "propensity_score": 0.55, "is_eligible": True, "product_name": "Credit Card", "reason_codes": []},
        ]
        result = logic.apply(scored, ctx)
        # Should have the original + PREMIUM_SAVINGS upsell
        assert len(result) >= 2
        upsells = [r for r in result if r.get("is_upsell")]
        assert len(upsells) == 1
        assert upsells[0]["product_id"] == "PREMIUM_SAVINGS"

    def test_low_balance_no_upsell(self):
        logic = UpsellLogic()
        ctx = make_context(
            products={"SAVINGS": {}},
            total_amount_90d=10000,
            tenure_months=6,
        )
        scored = [
            {"product_id": "CREDIT_CARD", "propensity_score": 0.55, "is_eligible": True, "product_name": "Credit Card", "reason_codes": []},
        ]
        result = logic.apply(scored, ctx)
        upsells = [r for r in result if r.get("is_upsell")]
        assert len(upsells) == 0


class TestCampaignMapper:
    """Tests for CampaignMapper."""

    def test_personal_loan_mapped_to_campaign(self):
        mapper = CampaignMapper()
        ctx = make_context(segment="MASS_MARKET")
        recs = [
            {"product_id": "PERSONAL_LOAN", "propensity_score": 0.65, "is_eligible": True, "product_name": "Personal Loan"},
        ]
        result = mapper.map_recommendations(recs, ctx)
        assert result[0]["campaign_id"] == "PL_AUG_2026"
        assert result[0]["channel"] == "DIGITAL"

    def test_campaign_list_filtered_by_segment(self):
        mapper = CampaignMapper()
        result = mapper.get_campaign_target_list(segment="MASS_MARKET")
        assert len(result) > 0
        for c in result:
            assert "MASS_MARKET" in c["target_segments"]
