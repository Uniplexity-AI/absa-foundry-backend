"""Decision Intelligence Platform — Pydantic v2 Schemas.

Defines the DecisionContext (shared across all 6 engines) and
all request/response models for every API endpoint.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


# ===========================================================================
# Decision Context — the single object flowing through every engine
# ===========================================================================

class DecisionContext(BaseModel):
    """Assembled once by the Context Builder, shared across all 6 engines."""

    customer_id: str
    as_of_date: date

    # From State Service (L1, 8003)
    customer_state: Literal["ACTIVE", "AT_RISK", "DORMANT", "CHURNED"]
    state_duration_days: int = 0
    state_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    previous_state: str | None = None

    # From Prediction Service (L2, 8004)
    health_score: float = Field(default=50.0, ge=0.0, le=100.0)
    churn_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    clv_percentile: float = Field(default=0.5, ge=0.0, le=1.0)
    component_scores: dict = Field(default_factory=dict)

    # From Feature Store (8002)
    segment: str = "MASS_MARKET"
    age: int = 35
    income_band: str | None = None
    tenure_months: int = 0
    branch_code: str = ""
    preferred_channel: str | None = None
    engagement_score: float | None = None
    days_since_last_txn: int | None = None
    total_amount_90d: float | None = None
    has_salary_credit: bool = False
    products: dict = Field(default_factory=dict)
    txn_count_30d: int | None = None
    txn_count_90d: int | None = None

    # Eligibility flags
    aml_flag: bool = False
    kyc_expired: bool = False
    marketing_opt_out: bool = False
    active_complaint: bool = False
    credit_risk_rating: str | None = None
    loan_in_arrears: bool = False

    # History
    last_action_date: date | None = None
    contact_frequency_30d: int = 0
    previous_offers: list[dict] = Field(default_factory=list)


# ===========================================================================
# Pipeline stage outputs
# ===========================================================================

class EligibilityResult(BaseModel):
    is_eligible: bool
    blocked_actions: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class PolicyResult(BaseModel):
    blocked_actions: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    priority_modifiers: dict = Field(default_factory=dict)
    triggered_rules: list[str] = Field(default_factory=list)


class CandidateAction(BaseModel):
    action: str
    category: str  # retention | cross_sell | engagement | service | passive


class RankedAction(BaseModel):
    rank: int
    action: str
    category: str
    score: float = Field(ge=0.0, le=100.0)


class RoutingDecision(BaseModel):
    channel: Literal["RM_DIRECT", "RM_CALL", "DIGITAL", "MARKETING", "BRANCH", "PASSIVE"]
    stakeholder: Literal["RELATIONSHIP_MANAGER", "MARKETING", "RETAIL", "SYSTEM"]
    reason: str


class ApprovalResult(BaseModel):
    required: bool
    reason: str | None = None
    approver_role: str | None = None


# ===========================================================================
# Decision Engine output
# ===========================================================================

class DecisionPackage(BaseModel):
    customer_id: str
    as_of_date: date
    decision_id: str
    status: str = "GENERATED"
    top_actions: list[RankedAction] = Field(default_factory=list)
    routing: RoutingDecision | None = None
    approval: ApprovalResult | None = None
    priority_score: float = Field(default=0.0, ge=0.0, le=100.0)
    estimated_revenue_zmw: float | None = None
    estimated_churn_reduction: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    decision_confidence: dict = Field(default_factory=dict)
    strategy: str = "BALANCED"
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class BatchDecisionResponse(BaseModel):
    as_of_date: date
    customers_processed: int
    decisions_generated: int
    duration_seconds: float
    strategy: str
    status: str = "COMPLETED"


# ===========================================================================
# Customer Intelligence
# ===========================================================================

class BehaviouralAlert(BaseModel):
    alert_type: str
    severity: Literal["CRITICAL", "WARNING", "INFO"]
    description: str


class HealthTrajectory(BaseModel):
    trajectory: Literal["IMPROVING", "STABLE", "DECLINING", "CRITICAL"]
    current_score: float
    previous_score: float | None = None
    score_30d_ago: float | None = None
    trend_direction: str = "FLAT"
    trend_magnitude: float = 0.0


class CustomerIntelligence(BaseModel):
    customer_id: str
    as_of_date: date
    health_trajectory: HealthTrajectory | None = None
    lifecycle_stage: str | None = None
    alerts: list[BehaviouralAlert] = Field(default_factory=list)
    projected_state_30d: str | None = None
    projected_state_90d: str | None = None
    computed_at: datetime = Field(default_factory=datetime.utcnow)


# ===========================================================================
# Churn Intelligence
# ===========================================================================

class ChurnDriver(BaseModel):
    rank: int
    driver_name: str
    contribution_pct: float
    affected_customer_count: int


class ChurnIntelligenceResult(BaseModel):
    as_of_date: date
    top_drivers: list[ChurnDriver] = Field(default_factory=list)
    segment_analysis: list[dict] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=datetime.utcnow)


# ===========================================================================
# Forecast
# ===========================================================================

class ForecastResult(BaseModel):
    forecast_date: date
    horizon_days: int
    metric: str
    segment: str | None = None
    predicted_value: float


# ===========================================================================
# Execution & Feedback
# ===========================================================================

class ExecutionRequest(BaseModel):
    rm_id: str
    action_taken: str
    channel_used: str
    notes: str | None = None


class OutcomeRequest(BaseModel):
    outcome: Literal["ACCEPTED", "DECLINED", "NOT_REACHABLE", "EXPIRED"]
    actual_revenue_zmw: float | None = None
    product_adopted: str | None = None


# ===========================================================================
# Platform
# ===========================================================================

class PlatformHealth(BaseModel):
    status: str = "healthy"
    service: str = "decision-intelligence-platform"
    version: str = "3.0.0"
    upstream: dict = Field(default_factory=dict)
