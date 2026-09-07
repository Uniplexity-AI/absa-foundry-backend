"""
ETL Loading Service - Orchestrates production database loading.

Executes load steps in strict dependency order using topological sort.
Each step reads from a staging table and writes to a production table
using upsert/append/replace strategies.

After successful load, truncates staging tables.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone

import pandas as pd

from etl.loading.repository import LoadingRepository
from etl.schemas.loading_schemas import (
    LoadPipelineConfig,
    LoadPipelineResult,
    LoadStep,
    LoadStepResult,
    LoadStepStatus,
    LoadStrategy,
)
from etl.schemas.staging_schemas import StagingTable
from etl.staging.repository import StagingRepository


class LoadingService:
    """Orchestrates ordered loading from staging to production.

    Loading order (strict):
    1. Customers → 2. Accounts → 3. Branches → 4. Transactions

    After transactions are loaded, marks qualifying financial activities
    (DEBIT, CREDIT, TRANSFER) for downstream feature engineering.

    Dependencies are resolved via topological sort —
    a step only runs after all its depends_on steps succeed.
    """

    def __init__(
        self,
        loading_repo: LoadingRepository,
        staging_repo: StagingRepository | None = None,
        config: LoadPipelineConfig | None = None,
    ) -> None:
        self._load_repo = loading_repo
        self._staging_repo = staging_repo
        self.config = config or LoadPipelineConfig()

    async def execute(self, batch_id: str) -> LoadPipelineResult:
        """Execute the full loading pipeline.

        Args:
            batch_id: Batch identifier for staging and audit.

        Returns:
            LoadPipelineResult with per-step results.
        """
        start_time = time.monotonic()
        result = LoadPipelineResult(
            batch_id=batch_id,
            pipeline_name=self.config.pipeline_name,
            total_steps=len(self.config.steps),
        )

        # Resolve execution order (topological sort)
        try:
            ordered_steps = self._resolve_order(self.config.steps)
        except ValueError as e:
            result.status = LoadStepStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now(timezone.utc)
            return result

        completed: set[str] = set()
        total_loaded = 0

        for step in ordered_steps:
            if not step.is_enabled:
                result.skipped_steps += 1
                continue

            step_result = await self._execute_step(step, batch_id)

            if step_result.status == LoadStepStatus.COMPLETED:
                completed.add(step.step_id)
                result.completed_steps += 1
                total_loaded += step_result.rows_loaded
            elif step_result.status == LoadStepStatus.SKIPPED:
                result.skipped_steps += 1
            else:
                result.failed_steps += 1
                if self.config.stop_on_failure:
                    result.status = LoadStepStatus.FAILED
                    result.error_message = step_result.error_message
                    break

            result.step_results.append(step_result)

        # Post-load: mark qualifying activities
        if result.failed_steps == 0:
            await self._load_repo.mark_qualifying_activities(batch_id)

        # Truncate staging on success
        if (result.failed_steps == 0
                and self.config.truncate_staging_on_success
                and self._staging_repo):
            await self._truncate_staging(batch_id)
            result.staging_truncated = True

        if result.status != LoadStepStatus.FAILED:
            result.status = LoadStepStatus.COMPLETED

        result.total_rows_loaded = total_loaded
        result.completed_at = datetime.now(timezone.utc)
        result.duration_seconds = time.monotonic() - start_time

        return result

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _execute_step(
        self, step: LoadStep, batch_id: str
    ) -> LoadStepResult:
        """Execute a single loading step.

        Reads data from staging, loads into production.

        Args:
            step: Load step definition.
            batch_id: Batch identifier.

        Returns:
            LoadStepResult.
        """
        step_start = time.monotonic()
        result = LoadStepResult(
            step_id=step.step_id,
            step_name=step.step_name,
            status=LoadStepStatus.RUNNING,
        )

        try:
            if not self._staging_repo:
                raise RuntimeError("StagingRepository is required for loading")

            # Map staging table string to StagingTable enum
            staging_table = self._get_staging_table(step.staging_table)

            # Count rows in staging for this batch
            row_count = await self._staging_repo.get_row_count(
                staging_table, batch_id
            )
            if row_count == 0:
                result.status = LoadStepStatus.SKIPPED
                result.completed_at = datetime.now(timezone.utc)
                result.duration_seconds = time.monotonic() - step_start
                return result

            # Read from staging
            if staging_table == StagingTable.CUSTOMER:
                records = await self._staging_repo.get_staging_customers(batch_id)
            elif staging_table == StagingTable.ACCOUNT:
                records = await self._staging_repo.get_staging_accounts(batch_id)
            elif staging_table == StagingTable.TRANSACTION:
                records = await self._staging_repo.get_staging_transactions(batch_id)
            elif staging_table == StagingTable.BRANCH:
                records = await self._staging_repo.get_staging_branches(batch_id)
            else:
                records = []

            if not records:
                result.status = LoadStepStatus.SKIPPED
                result.completed_at = datetime.now(timezone.utc)
                return result

            # Convert ORM objects to dicts
            record_dicts = [
                {
                    c.name: getattr(r, c.name)
                    for c in r.__table__.columns
                    if c.name not in ("id", "created_at", "updated_at", "batch_id", "raw_data")
                }
                for r in records
            ]

            # Load into production
            loaded, updated = await self._load_repo.upsert(
                target_schema=step.target_schema,
                target_table=step.target_table,
                records=record_dicts,
                conflict_columns=step.conflict_columns,
                update_columns=step.update_columns or None,
            )

            await self._load_repo.commit()

            result.rows_loaded = loaded
            result.rows_updated = updated
            result.status = LoadStepStatus.COMPLETED

        except Exception as e:
            result.status = LoadStepStatus.FAILED
            result.error_message = str(e)

        result.completed_at = datetime.now(timezone.utc)
        result.duration_seconds = time.monotonic() - step_start
        return result

    async def _truncate_staging(self, batch_id: str) -> None:
        """Truncate all staging tables for a batch after successful load."""
        if not self._staging_repo:
            return
        for table in StagingTable:
            await self._staging_repo.truncate_table(table, batch_id)

    @staticmethod
    def _get_staging_table(name: str) -> StagingTable:
        """Map staging table name string to StagingTable enum."""
        mapping = {
            "stg_customer": StagingTable.CUSTOMER,
            "stg_account": StagingTable.ACCOUNT,
            "stg_transaction": StagingTable.TRANSACTION,
            "stg_branch": StagingTable.BRANCH,
        }
        return mapping[name]

    @staticmethod
    def _resolve_order(steps: list[LoadStep]) -> list[LoadStep]:
        """Resolve load step execution order via topological sort.

        Ensures steps with dependencies run after their prerequisites.

        Args:
            steps: Load step definitions.

        Returns:
            Steps in dependency-resolved execution order.

        Raises:
            ValueError: If a circular dependency is detected.
        """
        step_map = {s.step_id: s for s in steps}
        in_degree: dict[str, int] = {s.step_id: len(s.depends_on) for s in steps}
        dependents: dict[str, list[str]] = {s.step_id: [] for s in steps}

        for step in steps:
            for dep in step.depends_on:
                if dep in dependents:
                    dependents[dep].append(step.step_id)

        # Start with steps that have no dependencies
        queue: deque[str] = deque(
            sid for sid, deg in in_degree.items() if deg == 0
        )
        ordered: list[LoadStep] = []

        while queue:
            sid = queue.popleft()
            ordered.append(step_map[sid])
            for dependent in dependents.get(sid, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(ordered) != len(steps):
            remaining = [sid for sid, deg in in_degree.items() if deg > 0]
            raise ValueError(
                f"Circular dependency detected among steps: {remaining}"
            )

        return ordered
