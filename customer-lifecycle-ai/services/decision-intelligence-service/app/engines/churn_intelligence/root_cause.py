"""Root Cause Analyzer — portfolio-level churn driver analysis.

Aggregates data from the state service across all at-risk customers
to identify the top drivers of churn. Portfolio-level, not per-customer.
"""
from __future__ import annotations

import logging
from datetime import date

from app.schemas.schemas import ChurnDriver
from app.upstream.client import upstream

logger = logging.getLogger("decision.churn_intel.root_cause")


def analyze_root_causes(as_of_date: date | None = None) -> list[ChurnDriver]:
    """Analyze top churn drivers across the portfolio.

    Uses the state service portfolio endpoint to get state breakdowns,
    then produces driver attributions based on known churn patterns.

    In production, this would aggregate SHAP values across all at-risk
    customers from the prediction service. For PoC, we use heuristic
    driver attribution based on portfolio composition.
    """
    if as_of_date is None:
        as_of_date = date.today()

    portfolio = upstream.fetch_portfolio(as_of_date)
    if not portfolio:
        logger.warning("No portfolio data for %s", as_of_date)
        return []

    by_state = portfolio.get("by_state", {})
    total = portfolio.get("total_customers", 1)

    at_risk_count = by_state.get("AT_RISK", {}).get("count", 0)
    dormant_count = by_state.get("DORMANT", {}).get("count", 0)
    churned_count = by_state.get("CHURNED", {}).get("count", 0)

    at_risk_total = at_risk_count + dormant_count

    # Heuristic driver attribution based on known banking patterns.
    # In Phase 2 (LightGBM + SHAP), these percentages come from
    # actual feature importance aggregation across the portfolio.
    drivers = [
        ChurnDriver(
            rank=1,
            driver_name="Salary cessation or redirection",
            contribution_pct=round(31.0, 1),
            affected_customer_count=round(at_risk_total * 0.31),
        ),
        ChurnDriver(
            rank=2,
            driver_name="Reduced transaction frequency",
            contribution_pct=round(24.0, 1),
            affected_customer_count=round(at_risk_total * 0.24),
        ),
        ChurnDriver(
            rank=3,
            driver_name="Extended inactivity periods",
            contribution_pct=round(18.0, 1),
            affected_customer_count=round(at_risk_total * 0.18),
        ),
        ChurnDriver(
            rank=4,
            driver_name="Low product ownership (single product)",
            contribution_pct=round(11.0, 1),
            affected_customer_count=round(at_risk_total * 0.11),
        ),
        ChurnDriver(
            rank=5,
            driver_name="Poor digital engagement",
            contribution_pct=round(9.0, 1),
            affected_customer_count=round(at_risk_total * 0.09),
        ),
        ChurnDriver(
            rank=6,
            driver_name="Age-related (young customers, short tenure)",
            contribution_pct=round(4.0, 1),
            affected_customer_count=round(at_risk_total * 0.04),
        ),
        ChurnDriver(
            rank=7,
            driver_name="Other factors",
            contribution_pct=round(3.0, 1),
            affected_customer_count=round(at_risk_total * 0.03),
        ),
    ]

    logger.info(
        "Root cause analysis: %d drivers, at_risk=%d dormant=%d churned=%d",
        len(drivers), at_risk_count, dormant_count, churned_count,
    )
    return drivers
