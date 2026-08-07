"""Revenue at Risk — estimates revenue impact of projected churn.

Uses CLV estimates and churn forecast to calculate ZMW at risk.
"""
from __future__ import annotations

import logging
from datetime import date

from app.upstream.client import upstream

logger = logging.getLogger("decision.forecast.revenue")

# Estimated average CLV per segment (ZMW) — PoC placeholder
AVG_CLV_BY_SEGMENT = {
    "MASS_MARKET": 10000,
    "MASS_AFFLUENT": 35000,
    "AFFLUENT": 85000,
    "SME": 50000,
}


def forecast_revenue_at_risk(as_of_date: date | None = None, horizon_days: int = 90) -> dict:
    """Estimate total revenue at risk from projected churn.

    Combines churn forecast with segment-level CLV estimates.
    """
    if as_of_date is None:
        as_of_date = date.today()

    from app.engines.forecast_engine.churn_forecast import forecast_churn
    churn_data = forecast_churn(as_of_date, horizon_days)

    total_at_risk = 0.0
    segment_detail = []

    for seg in churn_data["by_segment"]:
        seg_name = seg["segment"]
        projected = seg["projected"]
        avg_clv = AVG_CLV_BY_SEGMENT.get(seg_name, 15000)
        revenue = projected * avg_clv
        total_at_risk += revenue
        segment_detail.append({
            "segment": seg_name,
            "projected_churn": projected,
            "avg_clv_zmw": avg_clv,
            "revenue_at_risk_zmw": round(revenue),
        })

    logger.info("Revenue at risk: ZMW %.2f over %d days", total_at_risk, horizon_days)

    return {
        "as_of_date": as_of_date.isoformat(),
        "horizon_days": horizon_days,
        "total_revenue_at_risk_zmw": round(total_at_risk, 2),
        "avg_clv_per_customer_zmw": round(total_at_risk / max(churn_data["projected_churn"], 1), 2),
        "by_segment": segment_detail,
    }
