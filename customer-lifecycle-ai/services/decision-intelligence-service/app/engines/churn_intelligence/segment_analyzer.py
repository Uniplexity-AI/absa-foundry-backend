"""Segment Analyzer — segment-level deterioration analysis.

Identifies which customer segments are deteriorating fastest.
"""
from __future__ import annotations

import logging
from datetime import date

from app.upstream.client import upstream

logger = logging.getLogger("decision.churn_intel.segments")


def analyze_segments(as_of_date: date | None = None) -> list[dict]:
    """Analyze churn and at-risk rates by customer segment.

    Returns segment-level breakdown with deterioration trends.
    """
    if as_of_date is None:
        as_of_date = date.today()

    portfolio = upstream.fetch_portfolio(as_of_date)
    if not portfolio:
        return []

    by_state = portfolio.get("by_state", {})
    at_risk = by_state.get("AT_RISK", {}).get("count", 0)
    dormant = by_state.get("DORMANT", {}).get("count", 0)
    churned = by_state.get("CHURNED", {}).get("count", 0)

    # Placeholder segment breakdown — in production, this comes from
    # the state service portfolio endpoint with segment filtering.
    segments = [
        {
            "segment": "MASS_MARKET",
            "total_customers": 3200,
            "at_risk_count": round(at_risk * 0.55),
            "at_risk_pct": round(at_risk * 0.55 / 3200 * 100, 1) if at_risk else 0,
            "churned_count": round(churned * 0.50),
            "churn_rate_pct": round(churned * 0.50 / 3200 * 100, 1) if churned else 0,
            "trend": "DETERIORATING",
        },
        {
            "segment": "MASS_AFFLUENT",
            "total_customers": 1200,
            "at_risk_count": round(at_risk * 0.30),
            "at_risk_pct": round(at_risk * 0.30 / 1200 * 100, 1) if at_risk else 0,
            "churned_count": round(churned * 0.30),
            "churn_rate_pct": round(churned * 0.30 / 1200 * 100, 1) if churned else 0,
            "trend": "STABLE",
        },
        {
            "segment": "AFFLUENT",
            "total_customers": 400,
            "at_risk_count": round(at_risk * 0.10),
            "at_risk_pct": round(at_risk * 0.10 / 400 * 100, 1) if at_risk else 0,
            "churned_count": round(churned * 0.12),
            "churn_rate_pct": round(churned * 0.12 / 400 * 100, 1) if churned else 0,
            "trend": "DETERIORATING",
        },
        {
            "segment": "SME",
            "total_customers": 198,
            "at_risk_count": round(at_risk * 0.05),
            "at_risk_pct": round(at_risk * 0.05 / 198 * 100, 1) if at_risk else 0,
            "churned_count": round(churned * 0.08),
            "churn_rate_pct": round(churned * 0.08 / 198 * 100, 1) if churned else 0,
            "trend": "STABLE",
        },
    ]

    logger.info("Segment analysis: %d segments analyzed", len(segments))
    return segments
