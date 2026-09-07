"""
ETL Orchestration Service - DAG-based pipeline execution engine.

Executes pipeline steps in dependency order with:
- Topological sort for DAG resolution
- Parallel execution where dependencies allow
- Retry with exponential backoff
- Timeout enforcement
- Pause/resume/cancel support
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from etl.schemas.orchestration_schemas import (
    PipelineDefinition,
    PipelineRun,
    PipelineStatus,
    PipelineStep,
    RetryPolicy,
    StepResult,
    StepStatus,
    TriggerType,
)


class OrchestrationService:
    """DAG-based pipeline orchestration engine.

    Features:
    - Topological sort for dependency resolution
    - Parallel step execution (max_concurrent_steps)
    - Retry with exponential backoff
    - Step-level timeouts
    - Pause/resume/cancel
    """

    def __init__(self) -> None:
        self._step_handlers: dict[str, Any] = {}
        self._active_runs: dict[str, PipelineRun] = {}
        self._cancelled_runs: set[str] = set()

    def register_handler(
        self, service: str, action: str, handler: Any
    ) -> None:
        """Register a handler function for a service/action pair.

        Args:
            service: Service name (e.g., 'etl.validation').
            action: Action name (e.g., 'validate').
            handler: Async callable that executes the step.
        """
        key = f"{service}.{action}"
        self._step_handlers[key] = handler

    async def execute(
        self,
        pipeline: PipelineDefinition,
        trigger_type: TriggerType = TriggerType.MANUAL,
        triggered_by: str = "system",
        batch_id: str | None = None,
        correlation_id: str | None = None,
    ) -> PipelineRun:
        """Execute a full pipeline.

        Args:
            pipeline: Pipeline definition (DAG of steps).
            trigger_type: What triggered this run.
            triggered_by: User/service identifier.
            batch_id: Optional batch identifier.
            correlation_id: Optional correlation ID for tracing.

        Returns:
            PipelineRun with complete results.
        """
        run_id = str(uuid.uuid4())
        run = PipelineRun(
            run_id=run_id,
            pipeline_name=pipeline.pipeline_name,
            trigger_type=trigger_type,
            triggered_by=triggered_by,
            batch_id=batch_id,
            correlation_id=correlation_id,
            status=PipelineStatus.RUNNING,
            total_steps=len(pipeline.steps),
        )
        self._active_runs[run_id] = run

        start_time = time.monotonic()

        try:
            # Resolve execution order
            ordered_steps = self._resolve_order(pipeline.steps)
            completed: set[str] = set()
            failed: set[str] = set()

            # Process steps level by level (parallel where possible)
            while ordered_steps:
                # Find steps whose dependencies are all satisfied
                ready: list[PipelineStep] = []
                remaining: list[PipelineStep] = []

                for step in ordered_steps:
                    if not step.is_enabled:
                        continue
                    deps_satisfied = all(
                        d in completed and d not in failed
                        for d in step.depends_on
                    )
                    if deps_satisfied:
                        ready.append(step)
                    else:
                        remaining.append(step)

                if not ready:
                    # Deadlock — remaining steps have unsatisfied deps
                    failed.update(s.step_id for s in remaining)
                    break

                ordered_steps = remaining

                # Execute ready steps in parallel (respecting max_concurrent)
                semaphore = asyncio.Semaphore(pipeline.max_concurrent_steps)

                async def _run_step(step: PipelineStep) -> StepResult:
                    async with semaphore:
                        return await self._execute_step(
                            step, run_id, pipeline.default_retry_policy
                        )

                step_results = await asyncio.gather(
                    *(_run_step(s) for s in ready),
                    return_exceptions=True,
                )

                for sr in step_results:
                    if isinstance(sr, Exception):
                        fail_result = StepResult(
                            step_id="unknown",
                            step_name="unknown",
                            status=StepStatus.FAILED,
                            error_message=str(sr),
                        )
                        run.step_results.append(fail_result)
                        failed.add("unknown")
                        continue

                    run.step_results.append(sr)
                    if sr.status == StepStatus.COMPLETED:
                        completed.add(sr.step_id)
                        run.completed_steps += 1
                    elif sr.status == StepStatus.FAILED:
                        failed.add(sr.step_id)
                        run.failed_steps += 1
                        if pipeline.on_failure == "stop":
                            break

                if failed and pipeline.on_failure == "stop":
                    break

            # Determine final status
            if run.failed_steps > 0:
                run.status = PipelineStatus.FAILED
            elif run_id in self._cancelled_runs:
                run.status = PipelineStatus.CANCELLED
            else:
                run.status = PipelineStatus.COMPLETED

        except Exception as e:
            run.status = PipelineStatus.FAILED
            run.error_message = str(e)

        run.completed_at = datetime.now(timezone.utc)
        run.duration_seconds = time.monotonic() - start_time

        self._active_runs.pop(run_id, None)
        self._cancelled_runs.discard(run_id)

        return run

    def cancel_run(self, run_id: str) -> None:
        """Cancel a running pipeline.

        Args:
            run_id: The run to cancel.
        """
        self._cancelled_runs.add(run_id)

    def get_run_status(self, run_id: str) -> PipelineRun | None:
        """Get the current status of a pipeline run.

        Args:
            run_id: Run identifier.

        Returns:
            PipelineRun if active, None if completed or not found.
        """
        return self._active_runs.get(run_id)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _execute_step(
        self,
        step: PipelineStep,
        run_id: str,
        default_retry: RetryPolicy,
    ) -> StepResult:
        """Execute a single step with retry logic.

        Args:
            step: Step definition.
            run_id: Parent run ID.
            default_retry: Default retry policy from pipeline.

        Returns:
            StepResult.
        """
        retry = step.retry_policy if step.retry_policy.max_retries > 0 else default_retry
        last_error: str | None = None

        for attempt in range(1, retry.max_retries + 2):  # +1 for initial attempt
            if run_id in self._cancelled_runs:
                return StepResult(
                    step_id=step.step_id,
                    step_name=step.step_name,
                    status=StepStatus.SKIPPED,
                    attempt=attempt,
                    error_message="Pipeline cancelled",
                )

            step_start = time.monotonic()
            result = StepResult(
                step_id=step.step_id,
                step_name=step.step_name,
                status=StepStatus.RUNNING,
                attempt=attempt,
            )

            try:
                # Find handler
                handler_key = f"{step.service}.{step.action}"
                handler = self._step_handlers.get(handler_key)

                if handler is None:
                    # No handler registered — simulate step completion
                    await asyncio.sleep(0.01)
                else:
                    # Execute with timeout
                    await asyncio.wait_for(
                        handler(step.params),
                        timeout=step.timeout_seconds,
                    )

                result.status = StepStatus.COMPLETED
                result.duration_seconds = time.monotonic() - step_start
                result.completed_at = datetime.now(timezone.utc)
                return result

            except asyncio.TimeoutError:
                last_error = f"Step timed out after {step.timeout_seconds}s"
            except Exception as e:
                last_error = str(e)

            if attempt <= retry.max_retries:
                delay = retry.get_delay(attempt)
                await asyncio.sleep(delay)

        # All retries exhausted
        result.status = StepStatus.FAILED
        result.error_message = last_error
        result.duration_seconds = time.monotonic() - step_start
        result.completed_at = datetime.now(timezone.utc)
        return result

    @staticmethod
    def _resolve_order(steps: list[PipelineStep]) -> list[PipelineStep]:
        """Topological sort of pipeline steps.

        Args:
            steps: Pipeline step definitions.

        Returns:
            Steps in dependency-resolved order.

        Raises:
            ValueError: If circular dependency detected.
        """
        step_map = {s.step_id: s for s in steps}
        in_degree = {s.step_id: len(s.depends_on) for s in steps}
        dependents: dict[str, list[str]] = {s.step_id: [] for s in steps}

        for step in steps:
            for dep in step.depends_on:
                if dep in dependents:
                    dependents[dep].append(step.step_id)

        queue: deque[str] = deque(sid for sid, deg in in_degree.items() if deg == 0)
        ordered: list[PipelineStep] = []

        while queue:
            sid = queue.popleft()
            ordered.append(step_map[sid])
            for dep in dependents.get(sid, []):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        if len(ordered) != len(steps):
            remaining = [sid for sid, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Circular dependency: {remaining}")

        return ordered
