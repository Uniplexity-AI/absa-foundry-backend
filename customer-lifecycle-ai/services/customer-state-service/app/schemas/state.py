"""Customer State Service — Pydantic v2 Request/Response Schemas.

Mirrors FeatureSnapshot pattern from feature-engineering-service.
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Core state schemas
# ---------------------------------------------------------------------------

class StateResult(BaseModel):
    """Output of StateEngine.classify() — one customer's classified state.

    Health Score fields are intentionally absent — those belong to Layer 2
    (Prediction Service) per system-design.md §8.
    """
    customer_id: str
    as_of_date: date
    state: Literal["NEW", "ACTIVE", "GROWING", "AT_RISK", "DORMANT", "CHURNED"]
    classification_rules: dict = Field(default_factory=dict)
    previous_state: str | None = None
    is_transition: bool = False


class StateSnapshot(BaseModel):
    """A single customer's state snapshot for a specific as_of_date.
    Returned by GET /states/{customer_id}.

    health_score and component_scores are NULL until Layer 2 backfills.
    Frontend must render "pending" placeholder when null.
    """
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    as_of_date: date
    state: str
    previous_state: str | None = None
    is_transition: bool = False
    classification_rules: dict = Field(default_factory=dict)
    health_score: float | None = None
    component_scores: dict = Field(default_factory=dict)
    computed_at: datetime | None = None


class StateTimelineEntry(BaseModel):
    """One entry in a customer's state timeline."""
    as_of_date: date
    state: str


class StateTimeline(BaseModel):
    """Full state history for a customer."""
    customer_id: str
    timeline: list[StateTimelineEntry]
    transitions: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Portfolio / Aggregate
# ---------------------------------------------------------------------------

class StateCount(BaseModel):
    count: int
    pct: float


class PortfolioSummary(BaseModel):
    """Aggregate state counts for a branch / portfolio."""
    as_of_date: date
    branch_code: str | None = None
    total_customers: int
    by_state: dict[str, StateCount]


# ---------------------------------------------------------------------------
# Compute batch response
# ---------------------------------------------------------------------------

class ComputeStatesResponse(BaseModel):
    """Summary of a batch state computation. Mirrors ComputeBatchResponse."""
    as_of_date: date
    customers_processed: int
    states_upserted: int
    transitions_detected: int
    duration_seconds: float
    status: str = "COMPLETED"