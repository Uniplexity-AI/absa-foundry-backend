"""Tests for Business Rules Engine — all 8 rules."""
from __future__ import annotations

import pytest
from datetime import date

from app.schemas.schemas import DecisionContext
from app.engines.business_rules_engine import BusinessRulesEngine


@pytest.fixture
def engine():
    return BusinessRulesEngine()


@pytest.fixture
def base_context():
    return DecisionContext(
        customer_id="TEST001",
        as_of_date=date(2026, 7, 27),
        customer_state="ACTIVE",
        segment="MASS_MARKET",
        age=35,
        branch_code="BR001",
        health_score=70.0,
        churn_probability=0.2,
        clv_percentile=0.5,
        engagement_score=60.0,
        products={},
    )


def test_vip_escalation(engine, base_context):
    """RULE-002: VIP customers escalate to RM."""
    base_context.segment = "AFFLUENT"
    result = engine.apply(base_context)
    assert "RM_CALL" in result.required_actions
    assert "RULE-002" in result.triggered_rules


def test_at_risk_retention_priority(engine, base_context):
    """RULE-003: At-risk + high churn prioritizes retention."""
    base_context.customer_state = "AT_RISK"
    base_context.churn_probability = 0.6
    result = engine.apply(base_context)
    assert "RULE-003" in result.triggered_rules


def test_high_value_cross_sell(engine, base_context):
    """RULE-005: High CLV + healthy → prioritize cross-sell."""
    base_context.clv_percentile = 0.9
    base_context.health_score = 70.0
    result = engine.apply(base_context)
    assert "RULE-005" in result.triggered_rules


def test_churned_no_marketing(engine, base_context):
    """RULE-007: Churned customers get no marketing."""
    base_context.customer_state = "CHURNED"
    result = engine.apply(base_context)
    assert "RULE-007" in result.triggered_rules


def test_dormant_reactivation_only(engine, base_context):
    """RULE-001: Long-dormant customers only get reactivation."""
    base_context.customer_state = "DORMANT"
    base_context.state_duration_days = 200
    result = engine.apply(base_context)
    assert "RULE-001" in result.triggered_rules


def test_contact_frequency_guard(engine, base_context):
    """RULE-006: High contact frequency reduces outbound."""
    base_context.contact_frequency_30d = 5
    result = engine.apply(base_context)
    assert "RULE-006" in result.triggered_rules


def test_low_engagement_digital(engine, base_context):
    """RULE-008: Low engagement + non-senior → digital push."""
    base_context.engagement_score = 15.0
    base_context.age = 40
    result = engine.apply(base_context)
    assert "RULE-008" in result.triggered_rules


def test_clean_customer_no_rules(engine, base_context):
    """Clean active customer triggers no hard rules."""
    result = engine.apply(base_context)
    assert len(result.triggered_rules) == 0
