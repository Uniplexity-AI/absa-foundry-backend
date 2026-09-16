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


@router.post("/value-batch")
def run_value_batch(
    as_of_date: date | None = Query(
        default=None,
        description="Date to score value erosion + future value for (default: latest feature date)",
    ),
):
    """Run XGBoost Value Erosion + Future Value models for all customers.

    Writes erosion_probability, erosion_risk_level, predicted_future_value,
    future_value_percentile, model_version, prediction_date into customer_states.
    Idempotent — re-running overwrites previous value scores for the date.
    """
    return _service.run_value_batch(as_of_date)


@router.post("/clv-batch")
def run_clv_batch(
    as_of_date: date | None = Query(
        default=None,
        description="Date to score CLV for (default: latest feature date)",
    ),
):
    """Run the CLV LightGBM model for all customers on a date.

    Returns the distribution of predicted 12-month net revenue (ZMW). There is
    no proxy fallback: if the model is not loaded the status is
    ``CLV_MODEL_NOT_LOADED``.
    """
    return _service.clv_batch(as_of_date)


@router.post("/balance-growth-batch")
def run_balance_growth_batch(
    as_of_date: date | None = Query(
        default=None,
        description="Date to score balance growth for (default: latest feature date)",
    ),
):
    """Run the Balance Growth LightGBM model for all customers on a date.

    Scores ``predicted_balance_growth_pct`` per customer. The result is used by
    the AUM Forecast endpoint (GET /forecasts/balance) on the next call — the
    Decision Intelligence service reads ``balance_growth_pct`` from
    ``GET /predict/portfolio-scores``, which calls the same predictor.

    Returns a summary of the run (customers scored, mean/min/max growth pct).
    If the model artifact is missing the status is ``MODEL_NOT_LOADED``.
    """
    return _service.balance_growth_batch(as_of_date)


# IMPORTANT: Static routes (/models) and more-specific parameterized
# routes (/{customer_id}/churn, /{customer_id}/health) must be defined
# BEFORE the catch-all /{customer_id} route. Otherwise FastAPI matches
# "models" as a customer_id.


@router.get("/models", response_model=ModelsResponse)
def get_models() -> ModelsResponse:
    """List all registered models (champion + challenger)."""
    return _service.get_models()


@router.get("/portfolio-scores")
def get_portfolio_scores(
    as_of_date: date | None = Query(default=None, description="Score as-of date (default: latest feature date)"),
):
    """Churn + CLV percentile for every customer on a date. No persistence.

    Consumed by the Decision Intelligence Service (8005) for portfolio
    aggregations (CLV bands, AUM forecast, lifecycle summaries).
    """
    return _service.portfolio_scores(as_of_date)


@router.get("/lifecycle-forecast")
def get_lifecycle_forecast(
    as_of_date: date | None = Query(
        default=None,
        description="Forecast as-of date (default: latest feature date)",
    ),
):
    """Forward lifecycle-stage forecast for every customer, all horizons.

    Predicts the stage at 14/30/90 days per customer. The *current* stage is not
    in this payload — that comes from the state service's rule engine.
    """
    return _service.lifecycle_forecast(as_of_date)


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


@router.post("/simulate")
def simulate_prediction(payload: dict):
    """Real-time 'What-If' simulation using deterministic feature evaluation."""
    features = payload.get("features", {})
    baseline_prob = payload.get("baseline_probability", 0.5)
    
    # Deterministic simulation based on feature values
    delta = 0.0
    shap_vals = {}
    
    # Simple deterministic weight mapping for simulation
    weights = {
        "balance_decline_6m": 0.005,
        "complaints_count": 0.02,
        "days_since_active": 0.001,
        "interest_rate_delta": 0.05
    }
    
    for k, v in features.items():
        weight = weights.get(k, 0.01)
        # Calculate contribution deterministically
        contrib = float(v) * weight
        # Bound the contribution
        contrib = max(-0.15, min(0.15, contrib))
        shap_vals[k] = contrib
        delta += contrib

    simulated_prob = max(0.01, min(0.99, baseline_prob + delta))
    threshold = payload.get("threshold", 0.5)
    
    return {
        "simulation": True,
        "model_id": "simulated-churn-xgb",
        "model_version": "1.4.x",
        "baseline_probability": round(baseline_prob, 4),
        "simulated_probability": round(simulated_prob, 4),
        "delta": round(simulated_prob - baseline_prob, 4),
        "threshold": threshold,
        "classification": "HIGH_RISK" if simulated_prob > threshold else "LOW_RISK",
        "shap_values": {k: round(v, 4) for k, v in shap_vals.items()}
    }

