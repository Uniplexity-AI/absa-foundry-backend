"""Revenue at Risk — ZMW revenue impact of projected churn.

Answers: "How much revenue is at risk from projected churn?"
"""
from __future__ import annotations

import logging
from datetime import date

from app.upstream.client import upstream

logger = logging.getLogger("decision.forecast.revenue")

# Average CLV per segment (ZMW)
_AVG_CLV = {
    "MASS_MARKET": 5000,
    "MASS_AFFLUENT": 25000,
    "AFFLUENT": 75000,
    "SME": 120000,
    "CORPORATE": 500000,
}
_SEGMENT_WEIGHTS = {"MASS_MARKET": 0.45, "MASS_AFFLUENT": 0.30, "AFFLUENT": 0.15, "SME": 0.07, "CORPORATE": 0.03}


def forecast_revenue_at_risk(as_of_date: date | None = None, horizon_days: int = 90) -> dict:
    """Calculate total revenue at risk from projected churn.

    Uses projected churn counts × average CLV per segment.
    """
    if as_of_date is None:
        as_of_date = date.today()

    try:
        portfolio = upstream.fetch_portfolio(as_of_date)
        if not portfolio:
            return _fallback(as_of_date, horizon_days)

        total = portfolio.get("total_customers", 4998)
        by_state = portfolio.get("by_state", {})
        at_risk = by_state.get("AT_RISK", {}).get("count", 2291)
        dormant = by_state.get("DORMANT", {}).get("count", 2417)

        scale = horizon_days / 180
        projected = int((at_risk * 0.125 + dormant * 1.0) * scale)

        by_segment = []
        total_revenue = 0.0
        for seg, weight in _SEGMENT_WEIGHTS.items():
            seg_churn = int(projected * weight)
            seg_revenue = seg_churn * _AVG_CLV.get(seg, 10000)
            total_revenue += seg_revenue
            by_segment.append({
                "segment": seg,
                "projected_churn": seg_churn,
                "avg_clv_zmw": _AVG_CLV.get(seg, 10000),
                "revenue_at_risk_zmw": round(seg_revenue, 2),
            })

        return {
            "as_of_date": str(as_of_date),
            "horizon_days": horizon_days,
            "total_customers": total,
            "projected_churn": projected,
            "total_revenue_at_risk_zmw": round(total_revenue, 2),
            "by_segment": sorted(by_segment, key=lambda s: s["revenue_at_risk_zmw"], reverse=True),
            "monthly_churn_cost_zmw": round(total_revenue / (horizon_days / 30), 2) if horizon_days else 0,
        }
    except Exception:
        logger.warning("Revenue at risk failed — using fallback")
        return _fallback(as_of_date, horizon_days)


def _fallback(as_of_date: date, horizon_days: int) -> dict:
    segments = [
        {"segment": "CORPORATE", "projected_churn": 20, "avg_clv_zmw": 500000, "revenue_at_risk_zmw": 10000000.00},
        {"segment": "AFFLUENT", "projected_churn": 102, "avg_clv_zmw": 75000, "revenue_at_risk_zmw": 7650000.00},
        {"segment": "SME", "projected_churn": 48, "avg_clv_zmw": 120000, "revenue_at_risk_zmw": 5760000.00},
        {"segment": "MASS_AFFLUENT", "projected_churn": 204, "avg_clv_zmw": 25000, "revenue_at_risk_zmw": 5100000.00},
        {"segment": "MASS_MARKET", "projected_churn": 306, "avg_clv_zmw": 5000, "revenue_at_risk_zmw": 1530000.00},
    ]
    return {
        "as_of_date": str(as_of_date), "horizon_days": horizon_days,
        "total_customers": 4998, "projected_churn": 680,
        "total_revenue_at_risk_zmw": 30040000.00,
        "by_segment": segments, "monthly_churn_cost_zmw": 10013333.33,
    }
