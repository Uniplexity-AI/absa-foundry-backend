"""
ETL Orchestration Schemas - Pydantic v2 models for pipeline orchestration.

Defines pipeline definitions, step configurations, retry policies,
scheduling, and execution results.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PipelineStatus(str, Enum):
    """Overall pipeline execution status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class StepStatus(str, Enum):
    """Individual step execution status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    RETRYING = "RETRYING"


class TriggerType(str, Enum):
    """What triggered the pipeline run."""
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    EVENT = "event"
    API = "api"
    DEPENDENCY = "dependency"


# ---------------------------------------------------------------------------
# Retry Policy
# ---------------------------------------------------------------------------

class RetryPolicy(BaseModel):
    """Retry configuration for pipeline steps."""
    max_retries: int = Field(default=3, ge=0, le=10)
    backoff_seconds: float = Field(default=5.0, ge=0.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    max_backoff_seconds: float = Field(default=300.0, ge=1.0)
    retry_on_exceptions: list[str] = Field(
        default_factory=lambda: ["ConnectionError", "TimeoutError", "RuntimeError"],
    )

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt using exponential backoff.

        Args:
            attempt: 1-based retry attempt number.

        Returns:
            Delay in seconds.
        """
        delay = self.backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_backoff_seconds)


# ---------------------------------------------------------------------------
# Pipeline Step
# ---------------------------------------------------------------------------

class PipelineStep(BaseModel):
    """Definition of a single step in the ETL pipeline."""
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(description="Unique step identifier")
    step_name: str = Field(description="Human-readable step name")
    service: str = Field(description="Service/module that executes this step")
    action: str = Field(description="Action/method to call")
    depends_on: list[str] = Field(
        default_factory=list,
        description="Step IDs that must complete before this one",
    )
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_seconds: float = Field(default=600.0, ge=1.0)
    is_enabled: bool = Field(default=True)
    params: dict[str, Any] = Field(default_factory=dict)
    description: str = Field(default="")


class StepResult(BaseModel):
    """Result of a single pipeline step execution."""
    step_id: str
    step_name: str
    status: StepStatus
    attempt: int = 1
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline Definition & Result
# ---------------------------------------------------------------------------

class PipelineDefinition(BaseModel):
    """Complete pipeline definition — the DAG of steps."""
    model_config = ConfigDict(extra="forbid")

    pipeline_name: str = Field(description="Unique pipeline name")
    description: str = Field(default="")
    steps: list[PipelineStep] = Field(description="Steps in the pipeline")
    default_retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    on_failure: str = Field(
        default="stop",
        description="Failure behavior: stop, continue, rollback",
    )
    notify_on_completion: list[str] = Field(
        default_factory=list,
        description="Channels to notify on completion: email, slack, webhook",
    )
    max_concurrent_steps: int = Field(default=4, ge=1)
    schedule: str | None = Field(
        default=None,
        description="Cron expression for scheduled execution",
    )


class PipelineRun(BaseModel):
    """A single execution run of a pipeline."""
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Unique run identifier (UUID v4)")
    pipeline_name: str
    trigger_type: TriggerType = Field(default=TriggerType.MANUAL)
    triggered_by: str = Field(default="system")
    batch_id: str | None = Field(default=None)
    status: PipelineStatus = Field(default=PipelineStatus.PENDING)
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    step_results: list[StepResult] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    correlation_id: str | None = None

    @property
    def is_successful(self) -> bool:
        return self.status == PipelineStatus.COMPLETED


# ---------------------------------------------------------------------------
# Default ETL Pipeline
# ---------------------------------------------------------------------------

def default_etl_pipeline() -> PipelineDefinition:
    """Build the default end-to-end ETL pipeline.

    Extract → Validate → Transform → Stage → Load
    → Feature Engineering → Markov → Prediction → Decision → Dashboard
    """
    return PipelineDefinition(
        pipeline_name="etl_full_pipeline",
        description="Complete ETL pipeline: Extract → Validate → Transform → Stage → Load → ML",
        steps=[
            PipelineStep(
                step_id="extract",
                step_name="Extract Data",
                service="etl.connectors",
                action="extract",
                timeout_seconds=1800,
                description="Extract data from source systems via connectors",
            ),
            PipelineStep(
                step_id="ingest",
                step_name="Ingest Data",
                service="etl.ingestion",
                action="ingest",
                depends_on=["extract"],
                description="Receive data, generate batch ID, compute checksums",
            ),
            PipelineStep(
                step_id="validate",
                step_name="Validate Data",
                service="etl.validation",
                action="validate",
                depends_on=["ingest"],
                description="Schema, mandatory fields, business rules, duplicates, RI",
            ),
            PipelineStep(
                step_id="transform",
                step_name="Transform Data",
                service="etl.transformation",
                action="transform",
                depends_on=["validate"],
                description="Map fields, standardize values, enrich, normalize dates",
            ),
            PipelineStep(
                step_id="stage",
                step_name="Stage Data",
                service="etl.staging",
                action="load",
                depends_on=["transform"],
                description="Load transformed data into staging tables",
            ),
            PipelineStep(
                step_id="load",
                step_name="Load to Production",
                service="etl.loading",
                action="execute",
                depends_on=["stage"],
                retry_policy=RetryPolicy(max_retries=2, backoff_seconds=30),
                description="Upsert staging data into production tables",
            ),
            PipelineStep(
                step_id="feature_engineering",
                step_name="Feature Engineering",
                service="feature-engineering-service",
                action="recompute_features",
                depends_on=["load"],
                timeout_seconds=3600,
                description="Recompute features in the feature store",
            ),
            PipelineStep(
                step_id="markov_state",
                step_name="Markov State Classification",
                service="customer-state-service",
                action="classify_states",
                depends_on=["feature_engineering"],
                description="Classify customers into lifecycle states",
            ),
            PipelineStep(
                step_id="prediction",
                step_name="Run Predictions",
                service="prediction-service",
                action="batch_predict",
                depends_on=["feature_engineering", "markov_state"],
                timeout_seconds=3600,
                description="Run XGBoost/LightGBM batch predictions",
            ),
            PipelineStep(
                step_id="decision",
                step_name="Decision Intelligence",
                service="decision-intelligence-service",
                action="generate_nba",
                depends_on=["prediction"],
                description="Generate Next Best Action recommendations",
            ),
            PipelineStep(
                step_id="dashboard",
                step_name="Dashboard Refresh",
                service="dashboard-service",
                action="refresh_views",
                depends_on=["decision"],
                description="Refresh materialized views for dashboards",
            ),
        ],
    )
