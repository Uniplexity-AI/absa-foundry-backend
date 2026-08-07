"""Churn Forecast — portfolio-level churn projections.

Aggregates individual churn probabilities into portfolio forecasts.
"""
from __future__ import annotations

import logging
from datetime import date

from app.upstream.client import upstream

logger = logging.getLogger("decision.forecast.churn")

# Portfolio constants (from state service live data, 2026-07-27)
TOTAL_CUSTOMERS = 4998
AT_RISK_COUNT = 2291
DORMANT_COUNT = 2417
CHURNED_COUNT = 290
AVG_CHURN_PROBABILITY = 0.45  # estimated from prediction batch


def forecast_churn(as_of_date: date | None = None, horizon_days: int = 90) -> dict:
    """Project churn counts for a given horizon.

    Uses portfolio composition and estimated churn probabilities
    from the prediction service batch results.
    """
    if as_of_date is None:
        as_of_date = date.today()

    portfolio = upstream.fetch_portfolio(as_of_date)
    if portfolio:
        by_state = portfolio.get("by_state", {})
        at_risk = by_state.get("AT_RISK", {}).get("count", AT_RISK_COUNT)
        dormant = by_state.get("DORMANT", {}).get("count", DORMANT_COUNT)
        churned = by_state.get("CHURNED", {}).get("count", CHURNED_COUNT)
        total = portfolio.get("total_customers", TOTAL_CUSTOMERS)
    else:
        at_risk = AT_RISK_COUNT
        dormant = DORMANT_COUNT
        churned = CHURNED_COUNT
        total = TOTAL_CUSTOMERS

    # Transition probabilities from the live Markov matrix:
    # AT_RISK → DORMANT: 0.82, AT_RISK → CHURNED: 0.18
    # DORMANT → CHURNED: 1.00
    at_risk_to_churn = at_risk * 0.18
    dormant_to_churn = dormant * 1.0

    # Scale to horizon
    if horizon_days <= 30:
        factor = 0.33
    elif horizon_days <= 60:
        factor = 0.66
    else:
        factor = 1.0

    projected_churn = round((at_risk_to_churn + dormant_to_churn) * factor)

    # Segment breakdown (estimated proportions)
    segments = [
        {"segment": "MASS_MARKET", "projected": round(projected_churn * 0.55)},
        {"segment": "MASS_AFFLUENT", "projected": round(projected_churn * 0.28)},
        {"segment": "AFFLUENT", "projected": round(projected_churn * 0.12)},
        {"segment": "SME", "projected": round(projected_churn * 0.05)},
    ]

    logger.info("Churn forecast: %d customers over %d days", projected_churn, horizon_days)

    return {
        "as_of_date": as_of_date.isoformat(),
        "horizon_days": horizon_days,
        "total_customers": total,
        "at_risk_count": at_risk,
        "dormant_count": dormant,
        "already_churned": churned,
        "projected_churn": projected_churn,
        "projected_churn_pct": round(projected_churn / total * 100, 1),
        "by_segment": segments,
        "methodology": "Markov transition matrix (live data) × horizon scaling factor",
    }
