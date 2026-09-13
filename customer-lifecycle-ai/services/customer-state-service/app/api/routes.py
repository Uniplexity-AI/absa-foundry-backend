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
    """Live CLV summary: bands + at-risk top customers (frontend contract shape)."""
    from app.services.portfolio_views import portfolio_views
    return portfolio_views.clv_summary(as_of_date)


@router.get("/lifecycle-stages")
def get_lifecycle_stages(as_of_date: date = Query(..., description="Date for lifecycle stages")):
    """Live lifecycle distribution, 30d transitions, onboarding funnel, win-back."""
    from app.services.portfolio_views import portfolio_views
    return portfolio_views.lifecycle_stages(as_of_date)


@router.get("/at-risk-cases")
def get_at_risk_cases(
    as_of_date: date = Query(..., description="Date for at-risk case list"),
    limit: int = Query(default=50, ge=1, le=200, description="Max cases to return"),
):
    """Top at-risk customers ranked by erosion probability for the Branch Manager case list."""
    from app.services.portfolio_views import portfolio_views
    return portfolio_views.at_risk_cases(as_of_date, limit)


@router.get("/unenrolled-high-risk")
def get_unenrolled_high_risk(
    as_of_date: date = Query(..., description="Date for unenrolled customers"),
    limit: int = Query(default=20, ge=1, le=100, description="Max rows to return"),
):
    """AT_RISK customers with no pilot action logged — for the unenrolled campaign panel."""
    from app.services.portfolio_views import portfolio_views
    return portfolio_views.unenrolled_high_risk(as_of_date, limit)


@router.get("/priority-actions")
def get_priority_actions(
    as_of_date: date = Query(..., description="Date for priority action aggregates"),
):
    """Computed AI priority actions based on real at-risk aggregates."""
    from app.services.portfolio_views import portfolio_views
    return portfolio_views.priority_actions(as_of_date)


@router.get("", response_model=list[StateSnapshot])
def list_all_states(
    as_of_date: date = Query(..., description="Date for state snapshots"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> list[StateSnapshot]:
    """List all customer state snapshots for a given date (paginated)."""
    return _service.list_all_states(as_of_date, limit, offset)


# NOTE: declared before /{customer_id} so "count" is not read as a customer id.
@router.get("/count")
def count_states(
    as_of_date: date = Query(..., description="Date for state snapshots"),
) -> dict:
    """Total state snapshots for the date.

    ``limit`` on the list route is capped at 500 and the response is a bare
    array, so a caller cannot tell "500 of 500" from "500 of 5,000". This is the
    authoritative denominator for pagination and portfolio totals.
    """
    return {"as_of_date": as_of_date, "total": _service.count_states(as_of_date)}


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