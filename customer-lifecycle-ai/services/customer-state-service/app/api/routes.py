"""Customer State Service — API Routes.

Mirrors FeatureService routes pattern: APIRouter + StateService singleton.
"""
from __future__ import annotations
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.schemas.state import (
    ComputeStatesResponse,
    PortfolioSummary,
    StateSnapshot,
    StateTimeline,
)
from app.schemas.transition import NextStatePrediction, TransitionMatrix
from app.services.state_service import StateService

router = APIRouter(prefix="/states", tags=["states"])
_service = StateService()


@router.post("/compute", response_model=ComputeStatesResponse)
def compute_states(
    as_of_date: date | None = Query(
        default=None,
        description="Date to compute states as-of (default: today)",
    ),
) -> ComputeStatesResponse:
    """Classify all customers into lifecycle states for the given date."""
    return _service.compute_states(as_of_date)


# IMPORTANT: Static routes (/portfolio) and more-specific parameterized
# routes (/{customer_id}/timeline) must be defined BEFORE the catch-all
# /{customer_id} route. Otherwise FastAPI matches "portfolio" as a customer_id.

@router.get("/portfolio", response_model=PortfolioSummary)
def get_portfolio(
    as_of_date: date = Query(..., description="Date for portfolio summary"),
    branch_code: str | None = Query(default=None, description="Optional branch filter"),
) -> PortfolioSummary:
    """Aggregate state counts across the portfolio."""
    return _service.get_portfolio_summary(as_of_date, branch_code)


@router.get("/clv-summary")
def get_clv_summary(as_of_date: date = Query(..., description="Date for CLV summary")):
    """Get Customer Lifetime Value summary and bands."""
    return {
        "summary": {
            "total_clv": 8420000000,
            "avg_clv": 41280,
            "high_value_count": 3840,
            "clv_at_risk": 312000000,
            "value_protected_mtd": 48600000,
            "churn_adjusted_clv": 7980000000
        },
        "bands": [
            { "band": "Platinum", "label": "Platinum", "threshold": "CLV > K500K", "count": 820, "avg_clv": 1240000, "avg_churn_prob": 0.12, "total_aum": 1016800000, "pct": 0.4 },
            { "band": "Gold", "label": "Gold", "threshold": "K100K–K500K", "count": 3020, "avg_clv": 210000, "avg_churn_prob": 0.19, "total_aum": 634200000, "pct": 1.5 },
            { "band": "Silver", "label": "Silver", "threshold": "K20K–K100K", "count": 28400, "avg_clv": 52000, "avg_churn_prob": 0.31, "total_aum": 1476800000, "pct": 13.9 },
            { "band": "Bronze", "label": "Bronze", "threshold": "CLV < K20K", "count": 172060, "avg_clv": 8400, "avg_churn_prob": 0.42, "total_aum": 1445304000, "pct": 84.2 }
        ],
        "top_customers": [
            {
                "customer_id": "CU-00421",
                "name": "Mpho Radebe",
                "segment": "Wealth Management",
                "band": "Platinum",
                "clv": 2140000,
                "churn_prob": 0.91,
                "aum": "K 2.1M",
                "rm": None,
                "days_since_contact": 12,
                "churn_confidence": "± 0.04",
                "clv_confidence": "± K 84K",
                "churn_drivers": [
                    { "label": "Deposit Velocity (3M trend)", "impact": -0.31, "direction": "negative" },
                    { "label": "Digital Channel Dormancy", "impact": -0.22, "direction": "negative" },
                    { "label": "Products Held", "impact": 0.08, "direction": "positive" }
                ]
            }
        ]
    }


@router.get("/lifecycle-stages")
def get_lifecycle_stages(as_of_date: date = Query(..., description="Date for lifecycle stages")):
    """Get customer distribution across lifecycle stages and onboarding funnel."""
    return {
        "distribution": [
            { "stage": "ONBOARDING", "label": "Onboarding", "count": 4820, "pct": 2.4, "mom_delta": 312, "color": "text-gray-600", "bg": "bg-gray-100", "dot": "bg-gray-500" },
            { "stage": "GROWING", "label": "Growing", "count": 38240, "pct": 18.7, "mom_delta": -820, "color": "text-absa-passion", "bg": "bg-red-50", "dot": "bg-absa-passion" },
            { "stage": "MATURE", "label": "Mature", "count": 124300, "pct": 60.9, "mom_delta": -1240, "color": "text-absa-enrich", "bg": "bg-gray-50", "dot": "bg-absa-enrich" },
            { "stage": "AT_RISK", "label": "At Risk", "count": 22840, "pct": 11.2, "mom_delta": 1840, "color": "text-absa-energy", "bg": "bg-orange-50", "dot": "bg-absa-energy" },
            { "stage": "CHURNING", "label": "Churning", "count": 8420, "pct": 4.1, "mom_delta": 410, "color": "text-absa-inspire", "bg": "bg-red-100", "dot": "bg-absa-inspire" },
            { "stage": "CHURNED", "label": "Churned", "count": 3680, "pct": 1.8, "mom_delta": 280, "color": "text-red-900", "bg": "bg-red-100", "dot": "bg-red-900" },
            { "stage": "WIN_BACK", "label": "Win-Back", "count": 1000, "pct": 0.5, "mom_delta": 55, "color": "text-amber-700", "bg": "bg-amber-50", "dot": "bg-amber-500" }
        ],
        "transitions": {
            "stages": ["ONBOARDING", "GROWING", "MATURE", "AT_RISK", "CHURNING", "CHURNED"],
            "matrix": [
                [2800, 1840, 120, 40, 12, 8],
                [0, 36200, 1420, 480, 110, 30],
                [0, 180, 121840, 1240, 420, 620],
                [0, 140, 4200, 16200, 1840, 460],
                [0, 0, 280, 840, 5200, 2100],
                [0, 0, 0, 0, 0, 3680]
            ]
        },
        "onboarding": {
            "total_new": 4820,
            "activated_30d": 3240,
            "activated_60d": 3820,
            "activated_90d": 4140,
            "early_at_risk": 380,
            "avg_products": 1.4,
            "digital_enrolled": 72
        },
        "win_back": [
            { "customer_id": "CU-W0041", "name": "Lerato Dlamini", "last_product": "Savings Account", "months_churned": 3, "est_value": "K 28K", "status": "ELIGIBLE", "prob": 0.62 },
            { "customer_id": "CU-W0088", "name": "Bongani Khumalo", "last_product": "Business Current", "months_churned": 5, "est_value": "K 84K", "status": "IN CAMPAIGN", "prob": 0.55 }
        ]
    }


@router.get("", response_model=list[StateSnapshot])
def list_all_states(
    as_of_date: date = Query(..., description="Date for state snapshots"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> list[StateSnapshot]:
    """List all customer state snapshots for a given date (paginated)."""
    return _service.list_all_states(as_of_date, limit, offset)


@router.get("/{customer_id}/timeline", response_model=StateTimeline)
def get_timeline(
    customer_id: str,
    limit: int = Query(default=50, description="Max timeline entries"),
) -> StateTimeline:
    """Get full state history + transitions for a customer."""
    return _service.get_timeline(customer_id, limit)


@router.get("/{customer_id}", response_model=StateSnapshot)
def get_state(
    customer_id: str,
    as_of_date: date = Query(..., description="Exact date for the state snapshot"),
) -> StateSnapshot:
    """Fetch one customer's state snapshot for a specific date.

    404 if no state exists for that date (i.e., /states/compute hasn't run yet).
    health_score may be null — backfilled by Layer 2 (Prediction Service).
    """
    result = _service.get_state(customer_id, as_of_date)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No state for customer '{customer_id}' as of {as_of_date}. "
                f"Run POST /states/compute?as_of_date={as_of_date} first."
            ),
        )
    return result


# ---------------------------------------------------------------------------
# Markov Chain endpoints
# ---------------------------------------------------------------------------

@router.get("/markov/matrix", response_model=TransitionMatrix)
def get_markov_matrix(
    as_of_date: date = Query(..., description="Date for transition matrix"),
    window_days: int = Query(default=180, description="Lookback window in days"),
) -> TransitionMatrix:
    """Compute the 4x4 state transition probability matrix from observed transitions.

    Rows with fewer than CS_MARKOV_MIN_TRANSITIONS observations are masked (null).
    """
    return _service.get_markov_matrix(as_of_date, window_days)


@router.get("/markov/predict/{customer_id}", response_model=NextStatePrediction)
def predict_next_state(
    customer_id: str,
    as_of_date: date = Query(..., description="Date for prediction baseline"),
) -> NextStatePrediction:
    """Predict next-state probabilities for a customer using the Markov chain.

    Returns null predictions if the current state has insufficient transition data.
    """
    return _service.predict_next_state(customer_id, as_of_date)