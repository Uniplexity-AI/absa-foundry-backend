"""Tests for Eligibility Engine — all 7 rules."""
from __future__ import annotations

import pytest
from datetime import date

from app.schemas.schemas import DecisionContext
from app.engines.eligibility_engine import EligibilityEngine


@pytest.fixture
def engine():
    return EligibilityEngine()


@pytest.fixture
def base_context():
    return DecisionContext(
        customer_id="TEST001",
        as_of_date=date(2026, 7, 27),
        customer_state="ACTIVE",
        segment="MASS_MARKET",
        age=35,
        branch_code="BR001",
    )


def test_minor_credit_blocked(engine, base_context):
    """ELIG-001: Customers under 18 cannot get credit."""
    base_context.age = 16
    result = engine.evaluate(base_context)
    assert not result.is_eligible
    assert "BLOCK_ALL_CREDIT" in result.blocked_actions
    assert "Customer under 18" in result.reasons[0]


def test_adult_is_eligible(engine, base_context):
    """Customers 18+ should pass age check."""
    base_context.age = 25
    result = engine.evaluate(base_context)
    assert result.is_eligible


def test_aml_block(engine, base_context):
    """ELIG-002: AML flag blocks all actions."""
    base_context.aml_flag = True
    result = engine.evaluate(base_context)
    assert not result.is_eligible


def test_kyc_expired_blocks_sales(engine, base_context):
    """ELIG-003: Expired KYC blocks sales campaigns."""
    base_context.kyc_expired = True
    result = engine.evaluate(base_context)
    assert "BLOCK_SALES" in result.blocked_actions


def test_marketing_opt_out(engine, base_context):
    """ELIG-004: Marketing opt-out blocks marketing."""
    base_context.marketing_opt_out = True
    result = engine.evaluate(base_context)
    assert "BLOCK_MARKETING" in result.blocked_actions


def test_credit_risk_high(engine, base_context):
    """ELIG-005: High credit risk blocks credit."""
    base_context.credit_risk_rating = "HIGH"
    result = engine.evaluate(base_context)
    assert "BLOCK_CREDIT" in result.blocked_actions


def test_loan_arrears(engine, base_context):
    """ELIG-006: Loan in arrears blocks cross-sell."""
    base_context.loan_in_arrears = True
    result = engine.evaluate(base_context)
    assert "BLOCK_CROSS_SELL" in result.blocked_actions


def test_active_complaint(engine, base_context):
    """ELIG-007: Active complaint suppresses marketing."""
    base_context.active_complaint = True
    result = engine.evaluate(base_context)
    assert "SUPPRESS_MARKETING" in result.blocked_actions


def test_clean_customer_passes_all(engine, base_context):
    """Clean customer passes all eligibility checks."""
    result = engine.evaluate(base_context)
    assert result.is_eligible
    assert len(result.blocked_actions) == 0
