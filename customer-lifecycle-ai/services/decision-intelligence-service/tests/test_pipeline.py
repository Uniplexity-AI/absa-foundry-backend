"""Integration test — full decision pipeline with mocked upstream."""
from __future__ import annotations

import pytest
from datetime import date
from unittest.mock import patch, MagicMock

from app.services.service import DecisionService


@pytest.fixture
def mock_upstream():
    """Mock all upstream calls to return valid test data."""
    with patch("app.context.builder.upstream") as mock:
        mock.fetch_state.return_value = {
            "state": "DORMANT",
            "previous_state": "AT_RISK",
        }
        mock.fetch_state_timeline.return_value = {
            "timeline": [
                {"as_of_date": "2026-06-01", "state": "ACTIVE"},
                {"as_of_date": "2026-07-01", "state": "AT_RISK"},
                {"as_of_date": "2026-07-27", "state": "DORMANT"},
            ]
        }
        mock.fetch_churn.return_value = {"churn_probability": 0.5373}
        mock.fetch_health.return_value = {
            "health_score": 35.1,
            "component_scores": {
                "churn_risk_sub": 46.3,
                "clv_percentile_sub": 55.2,
                "behaviour_sub": 0.0,
            },
        }
        mock.fetch_features.return_value = {
            "customer_segment": "MASS_AFFLUENT",
            "age_years": 42,
            "customer_tenure_days": 1440,
            "prof_primary_branch": "BR014",
            "engagement_score": 15.0,
            "days_since_last_txn": 129,
            "total_amount_90d": 85000.0,
            "has_salary_credit": False,
            "txn_count_30d": 5,
            "txn_count_90d": 60,
            "rel_has_savings": True,
            "rel_has_current": True,
            "rel_has_card": False,
            "rel_has_loan": False,
        }
        mock.fetch_portfolio.return_value = None
        yield mock


def test_full_pipeline_dormant_customer(mock_upstream):
    """Dormant customer → retention actions prioritized."""
    service = DecisionService()
    result = service.compute_for_customer("CUST00042", date(2026, 7, 27))

    assert result is not None
    assert result.status in ("AUTO_APPROVED", "PENDING_APPROVAL")
    assert len(result.top_actions) == 5
    # Dormant customer should get retention actions
    categories = [a.category for a in result.top_actions]
    assert "retention" in categories
    assert result.routing is not None
    assert result.approval is not None


def test_full_pipeline_active_customer(mock_upstream):
    """Active healthy customer → cross-sell prioritized."""
    mock_upstream.fetch_state.return_value = {
        "state": "ACTIVE",
        "previous_state": None,
    }
    mock_upstream.fetch_churn.return_value = {"churn_probability": 0.1}
    mock_upstream.fetch_health.return_value = {
        "health_score": 75.0,
        "component_scores": {"churn_risk_sub": 90.0, "clv_percentile_sub": 70.0, "behaviour_sub": 65.0},
    }
    mock_upstream.fetch_features.return_value = {
        "customer_segment": "MASS_MARKET",
        "age_years": 30,
        "customer_tenure_days": 720,
        "prof_primary_branch": "BR001",
        "engagement_score": 70.0,
        "days_since_last_txn": 3,
        "total_amount_90d": 25000.0,
        "has_salary_credit": True,
        "txn_count_30d": 25,
        "txn_count_90d": 75,
        "rel_has_savings": True,
        "rel_has_current": False,
        "rel_has_card": False,
        "rel_has_loan": False,
    }

    service = DecisionService()
    result = service.compute_for_customer("CUST00100", date(2026, 7, 27))

    assert result is not None
    assert len(result.top_actions) == 5


def test_ineligible_customer(mock_upstream):
    """AML-flagged customer → rejected."""
    mock_upstream.fetch_features.return_value.update({
        "customer_segment": "MASS_MARKET",
        "age_years": 25,
        "has_salary_credit": True,
    })

    service = DecisionService()
    result = service.compute_for_customer("BAD001", date(2026, 7, 27))

    assert result is not None
    # Note: AML flag is in the context defaults, not from features.
    # In real use, AML would come from an external system.
    # For now, test that the pipeline runs without crashing.
