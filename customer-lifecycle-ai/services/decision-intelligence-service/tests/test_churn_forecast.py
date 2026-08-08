"""Tests for Churn Intelligence + Forecast engines."""
from __future__ import annotations

from datetime import date
from app.engines.churn_intelligence.root_cause import analyze_root_causes, _fallback as root_fallback
from app.engines.churn_intelligence.segment_analyzer import analyze_segments, _fallback as seg_fallback
from app.engines.forecast_engine.churn_forecast import forecast_churn, _fallback as fc_fallback
from app.engines.forecast_engine.revenue_at_risk import forecast_revenue_at_risk, _fallback as rar_fallback


class TestChurnIntelligence:
    def test_root_cause_fallback_returns_drivers(self):
        drivers = root_fallback()
        assert len(drivers) == 7
        assert drivers[0].driver_name == "Salary Credit Disruption"
        assert all(d.rank == i + 1 for i, d in enumerate(drivers))

    def test_root_cause_analyze_returns_list(self):
        drivers = analyze_root_causes(date(2026, 7, 27))
        assert len(drivers) >= 5
        assert drivers[0].contribution_pct >= drivers[-1].contribution_pct

    def test_segment_fallback_returns_5_segments(self):
        segments = seg_fallback()
        assert len(segments) == 5
        assert segments[0]["segment"] == "MASS_MARKET"
        assert segments[-1]["deterioration_status"] == "HEALTHY"

    def test_segment_analyze_returns_list(self):
        segments = analyze_segments(date(2026, 7, 27))
        assert len(segments) == 5
        assert all("segment" in s for s in segments)
        assert all("combined_risk_pct" in s for s in segments)

    def test_segments_sorted_by_risk(self):
        segments = analyze_segments(date(2026, 7, 27))
        risks = [s["combined_risk_pct"] for s in segments]
        assert risks == sorted(risks, reverse=True)


class TestForecastEngine:
    def test_churn_fallback_returns_dict(self):
        fc = fc_fallback(date(2026, 7, 27), 90)
        assert fc["total_customers"] == 4998
        assert fc["projected_churn"] == 680
        assert "intervention_scenario" in fc

    def test_churn_forecast_has_segments(self):
        fc = forecast_churn(date(2026, 7, 27), 90)
        assert fc["total_customers"] > 0
        assert fc["projected_churn"] > 0
        assert len(fc["by_segment"]) == 5
        assert "intervention_scenario" in fc

    def test_horizon_scales_projection(self):
        fc30 = forecast_churn(date(2026, 7, 27), 30)
        fc90 = forecast_churn(date(2026, 7, 27), 90)
        assert fc30["projected_churn"] <= fc90["projected_churn"]

    def test_revenue_fallback_returns_dict(self):
        rar = rar_fallback(date(2026, 7, 27), 90)
        assert rar["total_revenue_at_risk_zmw"] > 0
        assert len(rar["by_segment"]) == 5
        assert "monthly_churn_cost_zmw" in rar

    def test_revenue_has_segments_sorted(self):
        rar = forecast_revenue_at_risk(date(2026, 7, 27), 90)
        assert rar["total_revenue_at_risk_zmw"] > 0
        revenues = [s["revenue_at_risk_zmw"] for s in rar["by_segment"]]
        assert revenues == sorted(revenues, reverse=True)
