"""Tests for Insight Engine — reason codes, explanation composer."""
from __future__ import annotations

from datetime import date, datetime

from app.schemas.schemas import DecisionContext, DecisionPackage, RankedAction, RoutingDecision
from app.engines.insight_engine.reason_code_generator import ReasonCodeGenerator
from app.engines.insight_engine.explanation_composer import ExplanationComposer


def make_context(**kwargs) -> DecisionContext:
    defaults = {
        "customer_id": "TEST001",
        "as_of_date": date(2026, 7, 27),
        "customer_state": "ACTIVE",
        "segment": "MASS_MARKET",
        "age": 35,
        "branch_code": "BR001",
        "health_score": 70.0,
        "churn_probability": 0.2,
        "clv_percentile": 0.5,
        "engagement_score": 60.0,
        "days_since_last_txn": 10,
        "has_salary_credit": False,
    }
    defaults.update(kwargs)
    return DecisionContext(**defaults)


def make_decision_package(customer_id: str = "TEST001") -> DecisionPackage:
    return DecisionPackage(
        customer_id=customer_id,
        as_of_date=date(2026, 7, 27),
        decision_id=f"DEC-{customer_id}",
        status="GENERATED",
        top_actions=[
            RankedAction(rank=1, action="RETENTION_CALL", category="retention", score=85.0),
            RankedAction(rank=2, action="FEE_WAIVER", category="retention", score=68.8),
        ],
        routing=RoutingDecision(channel="RM_CALL", stakeholder="RELATIONSHIP_MANAGER", reason="High churn + high CLV"),
        strategy="BALANCED",
        computed_at=datetime(2026, 7, 27, 10, 0, 0),
    )


class TestReasonCodeGenerator:
    """Tests for ReasonCodeGenerator."""

    def test_high_churn_triggers_risk_code(self):
        gen = ReasonCodeGenerator()
        ctx = make_context(churn_probability=0.55, health_score=30, days_since_last_txn=90)
        codes = gen.generate(ctx)
        high_codes = [c for c in codes if c.severity == "HIGH"]
        assert len(high_codes) >= 2
        code_names = {c.code for c in codes}
        assert "CHURN_RISK_HIGH" in code_names

    def test_dormant_triggers_state_code(self):
        gen = ReasonCodeGenerator()
        ctx = make_context(customer_state="DORMANT", churn_probability=0.4)
        codes = gen.generate(ctx)
        code_names = {c.code for c in codes}
        assert "STATE_DORMANT" in code_names

    def test_healthy_customer_minimal_codes(self):
        gen = ReasonCodeGenerator()
        ctx = make_context(
            customer_state="ACTIVE",
            health_score=75,
            churn_probability=0.1,
            clv_percentile=0.5,
        )
        codes = gen.generate(ctx)
        high_codes = [c for c in codes if c.severity == "HIGH"]
        assert len(high_codes) == 0
        # Should have HEALTHY_STATE
        code_names = {c.code for c in codes}
        assert "HEALTHY_STATE" in code_names

    def test_salary_creates_opportunity_code(self):
        gen = ReasonCodeGenerator()
        ctx = make_context(has_salary_credit=True, health_score=65)
        codes = gen.generate(ctx)
        code_names = {c.code for c in codes}
        assert "SALARY_ACTIVE" in code_names

    def test_codes_sorted_by_severity(self):
        gen = ReasonCodeGenerator()
        ctx = make_context(
            churn_probability=0.55,
            health_score=35,
            customer_state="AT_RISK",
            clv_percentile=0.8,
        )
        codes = gen.generate(ctx)
        severities = [c.severity for c in codes]
        assert severities == sorted(severities, key=lambda s: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[s])


class TestExplanationComposer:
    """Tests for ExplanationComposer."""

    def test_composes_from_package_and_codes(self):
        composer = ExplanationComposer()
        gen = ReasonCodeGenerator()
        decision = make_decision_package("TEST001")
        ctx = make_context(churn_probability=0.55, health_score=35, customer_state="DORMANT")
        codes = gen.generate(ctx)
        result = composer.compose(decision, codes)

        assert result.decision_id == "DEC-TEST001"
        assert result.customer_id == "TEST001"
        assert len(result.top_reasons) <= 5
        assert len(result.decision_summary) > 0
        assert "ranked_actions_count" in result.confidence_factors
        assert result.confidence_factors["strategy"] == "BALANCED"

    def test_summary_includes_top_action(self):
        composer = ExplanationComposer()
        gen = ReasonCodeGenerator()
        decision = make_decision_package("TEST002")
        ctx = make_context(churn_probability=0.6, health_score=30)
        codes = gen.generate(ctx)
        result = composer.compose(decision, codes)
        assert "RETENTION_CALL" in result.decision_summary
        assert "RM_CALL" in result.decision_summary
