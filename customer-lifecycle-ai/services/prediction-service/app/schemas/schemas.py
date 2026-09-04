"""Prediction Service — Pydantic v2 Request/Response Schemas.

Matches the response contracts in prediction-service.md §8.2.
"""
from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel, Field


# ── Component Scores ──────────────────────────────────────────────

class ComponentScores(BaseModel):
    """Breakdown of the three sub-scores that compose health_score."""
    churn_risk_sub: float = Field(..., description="(1 - churn_prob) × 100, range [0,100]")
    clv_percentile_sub: float = Field(..., description="clv_percentile × 100, range [0,100]")
    behaviour_sub: float = Field(..., description="engagement_score or 50 if NULL, range [0,100]")


class ModelVersions(BaseModel):
    """Which model versions produced this prediction."""
    churn: str = Field(default="churn_v1")
    clv: str = Field(default="percentile_v1")


# ── Single Customer ───────────────────────────────────────────────

class CustomerPrediction(BaseModel):
    """Full prediction for a single customer.  §8.2 GET /predict/{id}"""
    customer_id: str
    as_of_date: date
    state: str | None = Field(default=None, description="From customer_states (Layer 1)")
    churn_probability: float = Field(..., ge=0.0, le=1.0)
    clv_percentile: float = Field(..., ge=0.0, le=1.0)
    health_score: float = Field(..., ge=0.0, le=100.0)
    component_scores: ComponentScores
    model_versions: ModelVersions
    computed_at: datetime


class CustomerChurn(BaseModel):
    """Churn probability only.  §8.2 GET /predict/{id}/churn"""
    customer_id: str
    as_of_date: date
    churn_probability: float = Field(..., ge=0.0, le=1.0)
    model_version: str = "churn_v1"
    computed_at: datetime


class CustomerHealth(BaseModel):
    """Health score breakdown.  §8.2 GET /predict/{id}/health"""
    customer_id: str
    as_of_date: date
    health_score: float = Field(..., ge=0.0, le=100.0)
    component_scores: ComponentScores
    model_versions: ModelVersions
    computed_at: datetime


# ── Batch ─────────────────────────────────────────────────────────

class BatchPredictResponse(BaseModel):
    """Result of scoring all customers.  §8.2 POST /predict/batch"""
    as_of_date: date
    customers_scored: int
    chunks_processed: int
    chunk_size: int
    churn_model: str
    health_scores_backfilled: int
    duration_seconds: float
    status: str = "COMPLETED"


# ── Models ────────────────────────────────────────────────────────

class ModelSummary(BaseModel):
    """One entry in the registered-models list.  §8.2 GET /models"""
    model_id: str
    type: str
    status: str
    metrics: dict | None = None
    method: str | None = None  # "percentile_rank" for CLV PoC
    # Governance / training metadata (from models/registry.json)
    version: str | None = None
    framework: str | None = None
    trained_at: str | None = None
    holdout_date: str | None = None
    training_dates: list[str] | None = None
    classification: dict | None = None  # holdout precision/recall/f1/confusion_matrix
    classification_threshold: float | None = None
    n_training_features: int | None = None
    data: dict | None = None            # train/holdout sizes, class balance
    hyperparameters: dict | None = None
    top_features: list | None = None
    governance: dict | None = None      # owners, approval stages (pilot: registry block)


class ModelsResponse(BaseModel):
    """List of registered models."""
    models: list[ModelSummary]


# ── Model Monitoring ──────────────────────────────────────────────

class PerformancePoint(BaseModel):
    """One data point in the performance-over-time series."""
    date: str
    auc: float
    precision: float
    recall: float
    log_loss: float


class PerformanceHistoryResponse(BaseModel):
    """Time-series model performance metrics."""
    model_id: str
    horizon_days: int
    history: list[PerformancePoint]
    status: str = "OK"  # OK | AWAITING_OUTCOME_LABELS (sparse until labels accrue)


class FeatureDriftItem(BaseModel):
    """PSI and distribution stats for one feature."""
    name: str
    training_mean: float
    current_mean: float
    drift_score: float  # PSI value
    invert_shift: bool
    status: str  # "STABLE", "WARNING", "CRITICAL"


class FeatureDriftResponse(BaseModel):
    """Feature drift monitoring results."""
    model_id: str
    threshold: float = 0.20
    baseline_date: str | None = None   # training-window snapshot used as baseline
    current_date: str | None = None    # latest snapshot compared against baseline
    features: list[FeatureDriftItem]


class PredictionLogEntry(BaseModel):
    """One row in the live prediction log."""
    timestamp: str
    correlation_id: str
    customer_id: str
    churn_probability: float
    predicted_class: str
    latency_ms: float


class PredictionLogResponse(BaseModel):
    """Paginated prediction log."""
    model_id: str
    total_predictions: int
    predictions: list[PredictionLogEntry]
