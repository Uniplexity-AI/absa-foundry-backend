"""Prediction Service — API Routes.

Mirrors FeatureService + StateService routes pattern:
APIRouter + PredictionService singleton.
Static routes (/models) defined BEFORE parameterized routes.
"""
from __future__ import annotations
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.schemas.schemas import (
    BatchPredictResponse,
    CustomerChurn,
    CustomerHealth,
    CustomerPrediction,
    ModelsResponse,
    PerformanceHistoryResponse,
    FeatureDriftResponse,
    PredictionLogResponse,
)
from app.services.service import PredictionService
from app.services.monitoring import MonitoringService

router = APIRouter(prefix="/predict", tags=["prediction"])
_service = PredictionService()


@router.post("/batch", response_model=BatchPredictResponse)
def compute_batch(
    as_of_date: date | None = Query(
        default=None,
        description="Date to score all customers as-of (default: today)",
    ),
) -> BatchPredictResponse:
    """Score all customers for the given date and backfill health scores.

    Chunks customers (1,000/batch) to bound memory. Idempotent —
    running twice on the same date produces identical health_scores.
    """
    return _service.compute_batch(as_of_date)


# IMPORTANT: Static routes (/models) and more-specific parameterized
# routes (/{customer_id}/churn, /{customer_id}/health) must be defined
# BEFORE the catch-all /{customer_id} route. Otherwise FastAPI matches
# "models" as a customer_id.


@router.get("/models", response_model=ModelsResponse)
def get_models() -> ModelsResponse:
    """List all registered models (champion + challenger)."""
    return _service.get_models()


@router.get("/{customer_id}/churn", response_model=CustomerChurn)
def get_churn(
    customer_id: str,
    as_of_date: date = Query(..., description="Exact date for the prediction"),
) -> CustomerChurn:
    """Churn probability only for one customer."""
    result = _service.get_churn(customer_id, as_of_date)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No features for customer '{customer_id}' as of {as_of_date}. "
                f"Run POST /features/compute-batch?as_of_date={as_of_date} first."
            ),
        )
    return result


@router.get("/{customer_id}/health", response_model=CustomerHealth)
def get_health(
    customer_id: str,
    as_of_date: date = Query(..., description="Exact date for the health score"),
) -> CustomerHealth:
    """Health score breakdown for one customer."""
    result = _service.get_health(customer_id, as_of_date)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No features for customer '{customer_id}' as of {as_of_date}. "
                f"Run POST /features/compute-batch?as_of_date={as_of_date} first."
            ),
        )
    return result


_monitoring = MonitoringService()


@router.get("/monitoring/performance-history", response_model=PerformanceHistoryResponse)
def get_performance_history(
    horizon_days: int = 30,
) -> PerformanceHistoryResponse:
    """Time-series model performance metrics over N days."""
    return _monitoring.get_performance_history(horizon_days)


@router.get("/monitoring/feature-drift", response_model=FeatureDriftResponse)
def get_feature_drift() -> FeatureDriftResponse:
    """Feature drift (PSI) monitor comparing training vs current distribution."""
    return _monitoring.get_feature_drift()


@router.get("/monitoring/prediction-log", response_model=PredictionLogResponse)
def get_prediction_log(
    limit: int = 50,
    offset: int = 0,
) -> PredictionLogResponse:
    """Recent prediction log entries from the inference pipeline."""
    return _monitoring.get_prediction_log(limit, offset)


@router.get("/{customer_id}", response_model=CustomerPrediction)
def get_prediction(
    customer_id: str,
    as_of_date: date = Query(..., description="Exact date for the prediction"),
) -> CustomerPrediction:
    """Full prediction for one customer: churn + CLV + health.

    404 if no features exist for that date (i.e.,
    /features/compute-batch hasn't run yet).
    """
    result = _service.get_prediction(customer_id, as_of_date)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No features for customer '{customer_id}' as of {as_of_date}. "
                f"Run POST /features/compute-batch?as_of_date={as_of_date} first."
            ),
        )
    return result
