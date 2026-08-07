"""Tests for Ranking Engine — heuristic scoring logic."""
from __future__ import annotations

from datetime import date

from app.schemas.schemas import CandidateAction, DecisionContext
from app.engines.ranking_engine import RankingEngine


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
    }
    defaults.update(kwargs)
    return DecisionContext(**defaults)


def test_retention_scored_higher_for_at_risk():
    engine = RankingEngine()
    ctx = make_context(customer_state="AT_RISK", churn_probability=0.6, health_score=35)
    candidates = [
        CandidateAction(action="RETENTION_CALL", category="retention"),
        CandidateAction(action="OFFER_PERSONAL_LOAN", category="cross_sell"),
    ]
    result = engine.rank(candidates, ctx, top_n=2)
    assert result[0].action == "RETENTION_CALL"
    assert result[0].score > result[1].score


def test_cross_sell_higher_for_healthy():
    engine = RankingEngine()
    ctx = make_context(health_score=75, clv_percentile=0.8, has_salary_credit=True)
    candidates = [
        CandidateAction(action="RETENTION_CALL", category="retention"),
        CandidateAction(action="OFFER_PERSONAL_LOAN", category="cross_sell"),
    ]
    result = engine.rank(candidates, ctx, top_n=2)
    assert result[0].action == "OFFER_PERSONAL_LOAN"


def test_engagement_higher_for_low_engagement():
    engine = RankingEngine()
    ctx = make_context(engagement_score=15, age=35)
    candidates = [
        CandidateAction(action="MOBILE_BANKING_ONBOARDING", category="engagement"),
        CandidateAction(action="MONITOR_ONLY", category="passive"),
    ]
    result = engine.rank(candidates, ctx, top_n=2)
    assert result[0].category == "engagement"
    assert result[0].score > result[1].score


def test_top_n_limit():
    engine = RankingEngine()
    ctx = make_context()
    candidates = [
        CandidateAction(action=f"ACTION_{i}", category="retention") for i in range(10)
    ]
    result = engine.rank(candidates, ctx, top_n=3)
    assert len(result) == 3


def test_score_range():
    engine = RankingEngine()
    ctx = make_context()
    candidates = [CandidateAction(action="RETENTION_CALL", category="retention")]
    result = engine.rank(candidates, ctx)
    assert 0 <= result[0].score <= 100
