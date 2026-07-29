"""Feature Engineering — Pydantic v2 Request/Response Schemas."""
from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class FeatureSnapshot(BaseModel):
    """A single customer's feature snapshot for a specific as_of_date."""
    model_config = ConfigDict(from_attributes=True)

    # -- Identity --
    customer_id: str
    as_of_date: date

    # -- Phase 1: Transaction aggregates (legacy) --
    days_since_last_txn: int | None = None
    days_since_first_txn: int | None = None
    txn_count_30d: int | None = None
    txn_count_90d: int | None = None
    txn_count_180d: int | None = None
    txn_count_365d: int | None = None
    avg_days_between_txn: float | None = None
    total_amount_90d: float | None = None
    avg_amount_90d: float | None = None
    total_amount_180d: float | None = None
    amount_growth_ratio: float | None = None
    credit_sum_30d: float | None = None
    debit_sum_30d: float | None = None
    credit_to_debit_ratio_90d: float | None = None
    balance_trend_90d: str | None = None
    has_salary_credit: bool | None = None
    monthly_income_estimate: float | None = None
    distinct_channels_90d: int | None = None
    distinct_txn_types_90d: int | None = None
    dominant_channel: str | None = None
    amount_stddev_90d: float | None = None
    computed_at: datetime | None = None

    # -- Phase 2: Customer Profile (Domain 1) --
    customer_tenure_days: int | None = None
    customer_segment: str | None = None
    age_years: int | None = None
    onboarding_channel: str | None = None
    prof_primary_branch: str | None = None
    prof_age_band: str | None = None

    # -- Phase 2: Behaviour (Domain 2) --
    behav_txn_count_7d: int | None = None
    behav_active_days_90d: int | None = None
    behav_inactive_days_90d: int | None = None
    behav_recency_score: float | None = None
    behav_frequency_score: float | None = None
    behav_diversity_score: float | None = None
    behav_activity_consistency: float | None = None
    engagement_score: float | None = None
    txn_frequency_trend: float | None = None
    inactivity_streak_days: int | None = None

    # -- Phase 2: Financial (Domain 3) --
    fin_total_credit_90d: float | None = None
    fin_total_debit_90d: float | None = None
    fin_median_txn_amount_90d: float | None = None
    fin_salary_consistency: float | None = None
    fin_income_growth: float | None = None

    # -- Phase 2: Channel (Domain 4) --
    chan_mobile_ratio_90d: float | None = None
    chan_atm_ratio_90d: float | None = None
    chan_branch_ratio_90d: float | None = None
    chan_digital_adoption_score: float | None = None
    chan_channel_entropy: float | None = None

    # -- Phase 2: Temporal (Domain 7) --
    temp_weekend_txn_ratio_90d: float | None = None
    temp_weekday_txn_ratio_90d: float | None = None
    temp_morning_activity_ratio_90d: float | None = None
    temp_afternoon_activity_ratio_90d: float | None = None
    temp_evening_activity_ratio_90d: float | None = None
    temp_payday_activity_ratio_90d: float | None = None

    # -- Phase 2: Risk (Domain 6) --
    risk_high_value_txn_ratio_90d: float | None = None
    risk_txn_volatility_90d: float | None = None
    risk_reversal_ratio_90d: float | None = None
    risk_cash_heavy_ratio_90d: float | None = None
    risk_unusual_channel_flag: bool | None = None
    risk_dormant_indicator: bool | None = None

    # -- Phase 2: Relationship (Domain 5) --
    rel_customer_status: str | None = None
    rel_accounts_active: int | None = None
    rel_has_loan: bool | None = None
    rel_has_savings: bool | None = None
    rel_products_owned: int | None = None

    # -- Phase 3: Cards (Domain 5 extended) --
    rel_has_card: bool | None = None
    rel_card_count: int | None = None
    rel_has_unactivated_card: bool | None = None
    rel_card_expiring_30d: int | None = None
    rel_card_types: int | None = None

    # -- Phase 3: Digital Engagement (Domain 5 extended) --
    eng_login_count_7d: int | None = None
    eng_login_count_30d: int | None = None
    eng_digital_platform_preference: str | None = None
    eng_avg_session_duration_30d: float | None = None


class ComputeBatchRequest(BaseModel):
    """Request to compute features for all customers as of a date."""
    as_of_date: date | None = Field(default=None, description="Date to compute features as-of (default: today)")


class ComputeBatchResponse(BaseModel):
    """Summary of a batch feature computation."""
    as_of_date: date
    customers_processed: int
    rows_upserted: int
    phase2_updated: int = 0
    duration_seconds: float
    status: str = "COMPLETED"
