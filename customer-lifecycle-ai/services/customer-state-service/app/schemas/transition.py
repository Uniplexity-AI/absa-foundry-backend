"""Transition & Markov Schemas — Pydantic v2 models."""
from __future__ import annotations
from datetime import date

from pydantic import BaseModel, Field


class TransitionRecord(BaseModel):
    """A single state transition for a customer."""
    customer_id: str
    from_state: str
    to_state: str
    transition_date: date
    days_in_previous_state: int | None = None
    trigger_reason: str | None = None
    feature_snapshot: dict = Field(default_factory=dict)


class TransitionMatrix(BaseModel):
    """4×4 Markov transition probability matrix with cold-start handling."""
    as_of_date: date
    window_days: int
    states: list[str] = Field(default_factory=lambda: ["ACTIVE", "AT_RISK", "DORMANT", "CHURNED"])
    matrix: list[list[float | None]]  # null rows = insufficient data
    steady_state: dict[str, float] | None = None  # null if matrix degenerate
    warnings: list[dict] = Field(default_factory=list)
    total_transitions_observed: int = 0


class NextStatePrediction(BaseModel):
    """Predicted next-state probabilities for a customer."""
    customer_id: str
    current_state: str
    predictions: dict[str, float] | None = None  # null = insufficient data
    warning: str | None = None


class Milestone(BaseModel):
    """A lifecycle milestone for a customer."""
    customer_id: str
    milestone_type: str
    milestone_date: date
    description: str | None = None