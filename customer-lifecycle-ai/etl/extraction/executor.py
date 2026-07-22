"""
ETL Extraction Executor — orchestrates the full Dynamic Extractor pipeline.

Ties together: YAML loading → Version Guard → Join Validator → Query Builder
→ Streaming Extraction → Pydantic v2 Validation → Business Rules → DLQ.

Section 5.2 of dynamic-extractor-spec.md.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import sqlalchemy as sa
import yaml
from pydantic import ValidationError

from etl.extraction.config_models import ExtractionConfigSpec
from etl.extraction.version_guard import VersionGuard, IncompatibleSpecError
from etl.extraction.join_validator import JoinValidator, JoinValidationReport
from etl.extraction.query_builder import DynamicQueryBuilder, QueryBuildError
from etl.extraction.schema_factory import DynamicSchemaFactory
from etl.extraction.streaming import StreamingExtractor
from etl.extraction.business_rules import BusinessRuleEngine, BusinessRuleSeverity

logger = logging.getLogger("etl.extraction")


# ===========================================================================
# Data classes
# ===========================================================================

@dataclass
class DLQEntry:
    """A single record routed to the Dead-Letter Queue."""
    rejection_id: str
    batch_id: str
    source_system: str
    entity_name: str
    rejection_tier: str  # 'HARD' or 'SOFT'
    rule_code: str
    error_details: list[dict[str, str]]
    raw_payload: dict[str, Any]


@dataclass
class ExtractionResult:
    """Result of a full extraction pipeline run."""
    dataset_name: str
    batch_id: str
    status: str  # COMPLETED, FAILED, PARTIAL
    rows_extracted: int = 0
    rows_valid: int = 0
    rows_rejected: int = 0
    duration_seconds: float = 0.0
    valid_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    dlq_entries: list[DLQEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ===========================================================================
# Executor
# ===========================================================================

class ExtractionExecutor:
    """Orchestrates the full Dynamic Extractor pipeline end-to-end.

    Usage:
        executor = ExtractionExecutor(engine, metadata, engine_version="2.1")
        result = executor.execute("etl/config/extraction_specs/customer_360.yaml")
        # result.valid_df → feed into run_etl.py
        # result.dlq_entries → persist to audit.rejected_records
    """

    DLQ_SOURCE_SYSTEM = "ETL_DYNAMIC_UNIFIER"

    def __init__(
        self,
        engine: sa.Engine,
        metadata: sa.MetaData,
        engine_version: str = "1.0",
    ) -> None:
        """Initialize the extraction executor.

        Args:
            engine: SQLAlchemy engine connected to the source database.
            metadata: Bound MetaData for table reflection.
            engine_version: Current engine semantic version.
        """
        self._engine = engine
        self._metadata = metadata
        self._version_guard = VersionGuard(engine_version)
        self._join_validator = JoinValidator(engine, metadata)
        self._query_builder = DynamicQueryBuilder(engine, metadata)
        self._streaming = StreamingExtractor(engine)
        self._rule_engine = BusinessRuleEngine()

    def execute(self, spec_path: str | Path) -> ExtractionResult:
        """Execute the full extraction pipeline for a YAML spec.

        Pipeline:
            1. Load & validate YAML → ExtractionConfigSpec
            2. Version guard check
            3. Join validation against live DB schema
            4. Build dynamic SQL query
            5. Stream rows from database
            6. Structural validation (dynamic Pydantic v2)
            7. Business rule evaluation
            8. Route failures to DLQ, return valid DataFrame

        Args:
            spec_path: Path to the YAML extraction spec file.

        Returns:
            ExtractionResult with valid DataFrame and DLQ entries.
        """
        t_start = datetime.now(timezone.utc)
        batch_id = str(uuid.uuid4())

        # ---- 1. Load config ----
        spec = self._load_spec(spec_path)
        result = ExtractionResult(
            dataset_name=spec.dataset_name,
            batch_id=batch_id,
            status="RUNNING",
        )

        logger.info("Extraction started: %s (batch=%s)", spec.dataset_name, batch_id[:8])

        try:
            # ---- 2. Version check ----
            self._version_guard.check(spec)
            logger.info("  Version check: OK")

            # ---- 3. Join validation ----
            join_report = self._join_validator.validate(spec)
            if not join_report.is_valid:
                result.status = "FAILED"
                result.errors = join_report.errors
                logger.error("  Join validation FAILED: %s", join_report.errors)
                return result
            for warn in join_report.warnings:
                logger.warning("  Join warning: %s", warn)
            logger.info("  Join validation: OK")

            # ---- 4. Build query ----
            query = self._query_builder.build(spec)
            logger.info("  Query built: OK")

            # ---- 5. Stream & validate ----
            validation_model = DynamicSchemaFactory.create_model(spec)

            all_valid: list[dict[str, Any]] = []
            dlq_entries: list[DLQEntry] = []
            total_rows = 0

            for chunk in self._streaming.stream(query):
                total_rows += len(chunk)
                for record in chunk:
                    # Tier 1: Structural validation
                    try:
                        validated = validation_model.model_validate(record)
                        record_validated = validated.model_dump()
                    except ValidationError as ve:
                        dlq_entries.append(self._build_dlq(
                            spec, batch_id, record, "HARD",
                            "ERR_STRUCTURAL_SCHEMA_VALIDATION", ve.errors(),
                        ))
                        continue

                    # Tier 2: Business rules
                    if spec.business_rules:
                        rules_report = self._rule_engine.evaluate_all(
                            spec.business_rules, record_validated,
                        )
                        if not rules_report.passed:
                            dlq_entries.append(self._build_dlq(
                                spec, batch_id, record, "HARD",
                                "ERR_BUSINESS_RULE",
                                [{"rule": r.rule_id, "message": r.message}
                                 for r in rules_report.errors],
                            ))
                            continue
                        # Warnings: flag but pass through
                        for w in rules_report.warnings:
                            record_validated[f"_warning_{w.rule_id}"] = w.message

                    all_valid.append(record_validated)

            # ---- Build result ----
            result.rows_extracted = total_rows
            result.rows_valid = len(all_valid)
            result.rows_rejected = len(dlq_entries)
            result.dlq_entries = dlq_entries
            result.valid_df = pd.DataFrame(all_valid) if all_valid else pd.DataFrame()
            result.status = "COMPLETED" if result.rows_rejected == 0 else "PARTIAL"
            result.duration_seconds = (datetime.now(timezone.utc) - t_start).total_seconds()

            logger.info(
                "Extraction complete: %s — %d extracted, %d valid, %d rejected (%.1fs)",
                spec.dataset_name, total_rows,
                result.rows_valid, result.rows_rejected,
                result.duration_seconds,
            )

        except (IncompatibleSpecError, QueryBuildError) as e:
            result.status = "FAILED"
            result.errors.append(str(e))
            logger.error("Extraction FAILED: %s", e)
        except Exception as e:
            result.status = "FAILED"
            result.errors.append(f"{type(e).__name__}: {e}")
            logger.exception("Extraction FAILED with unexpected error")

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_spec(path: str | Path) -> ExtractionConfigSpec:
        """Load and validate a YAML extraction spec."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return ExtractionConfigSpec.model_validate(data)

    @staticmethod
    def _build_dlq(
        spec: ExtractionConfigSpec,
        batch_id: str,
        raw_record: dict[str, Any],
        tier: str,
        rule_code: str,
        errors: list[dict[str, Any]],
    ) -> DLQEntry:
        """Construct a DLQ entry for a failed record."""
        return DLQEntry(
            rejection_id=str(uuid.uuid4()),
            batch_id=batch_id,
            source_system=ExtractionExecutor.DLQ_SOURCE_SYSTEM,
            entity_name=spec.dataset_name,
            rejection_tier=tier,
            rule_code=rule_code,
            error_details=errors,
            raw_payload=raw_record,
        )
