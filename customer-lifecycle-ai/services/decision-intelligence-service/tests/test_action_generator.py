"""Tests for Action Generator — validates catalog produces all actions."""
from __future__ import annotations

from app.engines.action_generator import ActionGenerator


def test_generates_all_categories():
    gen = ActionGenerator()
    candidates = gen.generate()
    categories = set(c.category for c in candidates)
    assert "retention" in categories
    assert "cross_sell" in categories
    assert "engagement" in categories
    assert "service" in categories
    assert "passive" in categories


def test_total_action_count():
    gen = ActionGenerator()
    candidates = gen.generate()
    assert len(candidates) == 27  # 6 + 7 + 6 + 6 + 2


def test_passive_always_included():
    gen = ActionGenerator()
    candidates = gen.generate()
    passive = [c for c in candidates if c.category == "passive"]
    assert len(passive) == 2
    assert any(c.action == "NO_ACTION" for c in passive)
    assert any(c.action == "MONITOR_ONLY" for c in passive)


def test_categories_list():
    gen = ActionGenerator()
    cats = gen.categories
    assert "retention" in cats
    assert "cross_sell" in cats
