"""Feature Engineering — Pydantic v2 Request/Response Schemas."""
from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class FeatureSnapshot(BaseModel):
    """A single customer's feature snapshot for a specific as_of_date."""
    model_config = ConfigDict(from_attributes=True)
    customer_id: str
    as_of_date: date
    days_since_last_txn: int | None = None
    days_since_first_txn: int | None = None
    txn_count_30d: int | None = None
    txn_count_90d: int | None = None
    txn_count_180d: int | None = None
    avg_days_between_txn: float | None = None
    total_amount_90d: float | None = None
    avg_amount_90d: float | None = None
    total_amount_180d: float | None = None
    amount_growth_ratio: float | None = None
    distinct_channels_90d: int | None = None
    distinct_txn_types_90d: int | None = None
    dominant_channel: str | None = None
    amount_stddev_90d: float | None = None
    computed_at: datetime | None = None


class ComputeBatchRequest(BaseModel):
    """Request to compute features for all customers as of a date."""
    as_of_date: date | None = Field(default=None, description="Date to compute features as-of (default: today)")


class ComputeBatchResponse(BaseModel):
    """Summary of a batch feature computation."""
    as_of_date: date
    customers_processed: int
    rows_upserted: int
    duration_seconds: float
    status: str = "COMPLETED"
