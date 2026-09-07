"""Tests for Strategy Layer — validates re-weighting logic."""
from __future__ import annotations

from app.schemas.schemas import RankedAction
from app.engines.strategy_layer import StrategyLayer, STRATEGIES


def test_balanced_no_change():
    layer = StrategyLayer()
    actions = [
        RankedAction(rank=1, action="RETENTION_CALL", category="retention", score=80.0),
        RankedAction(rank=2, action="OFFER_LOAN", category="cross_sell", score=75.0),
    ]
    result = layer.apply(actions, "BALANCED")
    assert result[0].score == 80.0  # unchanged
    assert result[1].score == 75.0  # unchanged


def test_retention_first_boosts_retention():
    layer = StrategyLayer()
    actions = [
        RankedAction(rank=1, action="RETENTION_CALL", category="retention", score=80.0),
        RankedAction(rank=2, action="OFFER_LOAN", category="cross_sell", score=90.0),
    ]
    result = layer.apply(actions, "RETENTION_FIRST")
    assert result[0].action == "RETENTION_CALL"  # boosted above cross_sell
    assert result[0].score > 90.0  # 80 * 1.5 = 120 → capped at 100


def test_revenue_first_boosts_cross_sell():
    layer = StrategyLayer()
    actions = [
        RankedAction(rank=1, action="RETENTION_CALL", category="retention", score=90.0),
        RankedAction(rank=2, action="OFFER_LOAN", category="cross_sell", score=65.0),
    ]
    result = layer.apply(actions, "REVENUE_FIRST")
    # 65 * 1.5 = 97.5 > 90 * 0.9 = 81
    assert result[0].action == "OFFER_LOAN"


def test_invalid_strategy_defaults_to_balanced():
    layer = StrategyLayer()
    actions = [RankedAction(rank=1, action="RETENTION_CALL", category="retention", score=80.0)]
    result = layer.apply(actions, "NONEXISTENT")
    assert result[0].score == 80.0


def test_list_strategies():
    strategies = StrategyLayer.list_strategies()
    assert len(strategies) == 3
    names = [s["name"] for s in strategies]
    assert "BALANCED" in names
    assert "RETENTION_FIRST" in names
    assert "REVENUE_FIRST" in names
