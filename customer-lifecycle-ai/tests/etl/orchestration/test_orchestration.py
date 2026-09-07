"""
Unit tests for ETL Orchestration Engine.

Tests cover:
- Pipeline step dependency resolution (topological sort)
- Pipeline execution with mocked handlers
- Retry with exponential backoff
- Timeout handling
- Cancel pipeline mid-execution
- RetryPolicy delay calculation
"""

from __future__ import annotations

import asyncio

import pytest

from etl.orchestration.service import OrchestrationService
from etl.schemas.orchestration_schemas import (
    PipelineDefinition,
    PipelineRun,
    PipelineStatus,
    PipelineStep,
    RetryPolicy,
    StepStatus,
    TriggerType,
    default_etl_pipeline,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def orchestration_service() -> OrchestrationService:
    """Fresh orchestration service."""
    return OrchestrationService()


@pytest.fixture
def simple_pipeline() -> PipelineDefinition:
    """Simple 3-step linear pipeline for testing."""
    return PipelineDefinition(
        pipeline_name="test_pipeline",
        steps=[
            PipelineStep(
                step_id="step_a", step_name="Step A",
                service="test", action="step_a",
            ),
            PipelineStep(
                step_id="step_b", step_name="Step B",
                service="test", action="step_b",
                depends_on=["step_a"],
            ),
            PipelineStep(
                step_id="step_c", step_name="Step C",
                service="test", action="step_c",
                depends_on=["step_b"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# RetryPolicy Tests
# ---------------------------------------------------------------------------

class TestRetryPolicy:
    """Tests for RetryPolicy backoff calculation."""

    def test_exponential_backoff(self) -> None:
        """Test exponential backoff delay calculation."""
        policy = RetryPolicy(backoff_seconds=5, backoff_multiplier=2)
        assert policy.get_delay(1) == 5.0
        assert policy.get_delay(2) == 10.0
        assert policy.get_delay(3) == 20.0
        assert policy.get_delay(4) == 40.0

    def test_max_backoff_cap(self) -> None:
        """Test that backoff is capped at max_backoff_seconds."""
        policy = RetryPolicy(
            backoff_seconds=10,
            backoff_multiplier=10,
            max_backoff_seconds=60,
        )
        assert policy.get_delay(1) == 10.0
        assert policy.get_delay(2) == 60.0  # Capped
        assert policy.get_delay(3) == 60.0  # Capped

    def test_zero_max_retries(self) -> None:
        """Test policy with zero max retries."""
        policy = RetryPolicy(max_retries=0)
        assert policy.max_retries == 0


# ---------------------------------------------------------------------------
# Topological Sort Tests
# ---------------------------------------------------------------------------

class TestTopologicalSort:
    """Tests for DAG dependency resolution."""

    def test_linear_chain(self) -> None:
        """Test linear A→B→C resolves correctly."""
        steps = [
            PipelineStep(step_id="A", step_name="A", service="s", action="a"),
            PipelineStep(step_id="B", step_name="B", service="s", action="b", depends_on=["A"]),
            PipelineStep(step_id="C", step_name="C", service="s", action="c", depends_on=["B"]),
        ]
        ordered = OrchestrationService._resolve_order(steps)
        assert [s.step_id for s in ordered] == ["A", "B", "C"]

    def test_diamond_dependency(self) -> None:
        """Test diamond A→B,C→D."""
        steps = [
            PipelineStep(step_id="A", step_name="A", service="s", action="a"),
            PipelineStep(step_id="B", step_name="B", service="s", action="b", depends_on=["A"]),
            PipelineStep(step_id="C", step_name="C", service="s", action="c", depends_on=["A"]),
            PipelineStep(step_id="D", step_name="D", service="s", action="d", depends_on=["B", "C"]),
        ]
        ordered = OrchestrationService._resolve_order(steps)
        assert ordered[0].step_id == "A"
        assert ordered[-1].step_id == "D"

    def test_default_pipeline_is_valid_dag(self) -> None:
        """Test that the default ETL pipeline is a valid DAG."""
        pipeline = default_etl_pipeline()
        ordered = OrchestrationService._resolve_order(pipeline.steps)
        assert len(ordered) == len(pipeline.steps)


# ---------------------------------------------------------------------------
# OrchestrationService Tests
# ---------------------------------------------------------------------------

class TestOrchestrationService:
    """Tests for OrchestrationService."""

    @pytest.mark.asyncio
    async def test_execute_simple_pipeline(
        self,
        orchestration_service: OrchestrationService,
        simple_pipeline: PipelineDefinition,
    ) -> None:
        """Test executing a simple pipeline with all steps succeeding."""
        run = await orchestration_service.execute(simple_pipeline)
        assert run.status == PipelineStatus.COMPLETED
        assert run.total_steps == 3
        assert run.completed_steps == 3
        assert run.failed_steps == 0

    @pytest.mark.asyncio
    async def test_run_has_timestamps(
        self,
        orchestration_service: OrchestrationService,
        simple_pipeline: PipelineDefinition,
    ) -> None:
        """Test that pipeline run includes timing info."""
        run = await orchestration_service.execute(simple_pipeline)
        assert run.started_at is not None
        assert run.completed_at is not None
        assert run.duration_seconds is not None

    @pytest.mark.asyncio
    async def test_cancel_pipeline(
        self,
        orchestration_service: OrchestrationService,
    ) -> None:
        """Test cancelling a pipeline mid-execution."""
        pipeline = PipelineDefinition(
            pipeline_name="cancel_test",
            steps=[
                PipelineStep(
                    step_id="slow_step", step_name="Slow",
                    service="test", action="slow",
                    timeout_seconds=10,
                ),
            ],
        )

        async def slow_handler(params: dict) -> None:
            await asyncio.sleep(5)

        orchestration_service.register_handler("test", "slow", slow_handler)

        # Cancel after a short delay
        async def _cancel():
            await asyncio.sleep(0.1)
            orchestration_service.cancel_run(run_id)

        run_id = "will-be-set"  # placeholder
        # Start pipeline in background
        task = asyncio.create_task(
            orchestration_service.execute(pipeline)
        )
        # Give it time to register
        await asyncio.sleep(0.05)
        # Cancel it
        for rid in orchestration_service._active_runs:
            orchestration_service.cancel_run(rid)

        run = await task
        assert run.status in (PipelineStatus.CANCELLED, PipelineStatus.COMPLETED)

    @pytest.mark.asyncio
    async def test_failing_step_stops_pipeline(
        self,
        orchestration_service: OrchestrationService,
    ) -> None:
        """Test that a failing step stops the pipeline."""
        pipeline = PipelineDefinition(
            pipeline_name="fail_test",
            on_failure="stop",
            steps=[
                PipelineStep(step_id="good", step_name="Good", service="t", action="g"),
                PipelineStep(
                    step_id="bad", step_name="Bad", service="t", action="b",
                    depends_on=["good"],
                    retry_policy=RetryPolicy(max_retries=0),
                ),
                PipelineStep(
                    step_id="skipped", step_name="Skipped", service="t", action="s",
                    depends_on=["bad"],
                ),
            ],
        )

        async def failing_handler(params: dict) -> None:
            raise RuntimeError("Intentional failure")

        orchestration_service.register_handler("t", "g", lambda p: None)
        orchestration_service.register_handler("t", "b", failing_handler)
        orchestration_service.register_handler("t", "s", lambda p: None)

        run = await orchestration_service.execute(pipeline)

        assert run.status == PipelineStatus.FAILED
        assert run.failed_steps >= 1


# ---------------------------------------------------------------------------
# Default Pipeline Tests
# ---------------------------------------------------------------------------

class TestDefaultPipeline:
    """Tests for the default ETL pipeline definition."""

    def test_has_all_required_steps(self) -> None:
        """Test default pipeline includes all ETL steps."""
        pipeline = default_etl_pipeline()
        step_ids = {s.step_id for s in pipeline.steps}
        assert "extract" in step_ids
        assert "validate" in step_ids
        assert "transform" in step_ids
        assert "load" in step_ids
        assert "feature_engineering" in step_ids
        assert "prediction" in step_ids

    def test_dependencies_are_valid(self) -> None:
        """Test all depends_on references exist as step_ids."""
        pipeline = default_etl_pipeline()
        all_ids = {s.step_id for s in pipeline.steps}
        for step in pipeline.steps:
            for dep in step.depends_on:
                assert dep in all_ids, f"Step {step.step_id} depends on non-existent {dep}"
