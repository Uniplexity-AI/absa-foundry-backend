"""
ETL Extraction Executor — orchestrates the full Dynamic Extractor pipeline.

Ties together: YAML loading → Version Guard → Join Validator → Query Builder
→ Streaming Extraction → Pydantic v2 Validation → Business Rules → DLQ.

Section 5.2 of dynamic-extractor-spec.md.
"""

from __future__ import annotations

import json
import logging
import tempfile
import time as _time
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
from etl.extraction.watermark_store import WatermarkStore
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
    valid_path: str | None = None  # Staging file when streamed to disk
    watermark_candidate: datetime | None = None
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
    _DEFAULT_WATERMARK_PATH = Path("etl/checkpoint/extraction_watermarks.json")

    def __init__(
        self,
        engine: sa.Engine,
        metadata: sa.MetaData,
        engine_version: str = "1.0",
        watermark_store: WatermarkStore | None = None,
    ) -> None:
        """Initialize the extraction executor.

        Args:
            engine: SQLAlchemy engine connected to the source database.
            metadata: Bound MetaData for table reflection.
            engine_version: Current engine semantic version.
            watermark_store: Persisted watermark store for incremental runs.
                Defaults to etl/checkpoint/extraction_watermarks.json.
        """
        self._engine = engine
        self._metadata = metadata
        self._version_guard = VersionGuard(engine_version)
        self._join_validator = JoinValidator(engine, metadata)
        self._query_builder = DynamicQueryBuilder(engine, metadata)
        self._rule_engine = BusinessRuleEngine()
        self._watermarks = watermark_store or WatermarkStore(self._DEFAULT_WATERMARK_PATH)

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

        MAX_RETRIES = 3
        RETRY_BASE_DELAY = 2.0  # doubles each retry

        for attempt in range(1, MAX_RETRIES + 1):
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

                # ---- 4. Build query (with incremental watermark if enabled) ----
                last_watermark: datetime | None = None
                if spec.incremental.enabled:
                    last_watermark = self._watermarks.get(spec.dataset_name)
                    if last_watermark:
                        logger.info("  Incremental: resuming from %s", last_watermark.isoformat())
                    else:
                        logger.info("  Incremental: first run, using %d-min lookback",
                                    spec.incremental.lookback_minutes)

                query = self._query_builder.build(spec, last_watermark=last_watermark)
                logger.info("  Query built: OK")

                # ---- 5. Stream & validate (memory-safe with disk staging) ----
                validation_model = DynamicSchemaFactory.create_model(spec)

                # Use spec.streaming config (fixes Issue 4 — was always 10,000 default)
                batch_size = spec.streaming.batch_size if spec.streaming.enabled else 10000
                streaming = StreamingExtractor(self._engine, batch_size=batch_size)

                # Buffer accumulates up to batch_size, then flushes to disk (fixes Issue 3)
                buffer: list[dict[str, Any]] = []
                chunk_files: list[Path] = []
                dlq_entries: list[DLQEntry] = []
                total_rows = 0
                total_valid = 0
                watermark_candidate: datetime | None = None
                staging_dir = Path(tempfile.gettempdir()) / f"etl_{spec.dataset_name}_{batch_id[:8]}"
                staging_dir.mkdir(parents=True, exist_ok=True)
                chunk_idx = 0

                for chunk in streaming.stream(query):
                    total_rows += len(chunk)
                    for record in chunk:
                        if spec.incremental.enabled:
                            candidate = self._as_utc_datetime(record.get("_extraction_watermark"))
                            if candidate and (watermark_candidate is None or candidate > watermark_candidate):
                                watermark_candidate = candidate
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
                            for w in rules_report.warnings:
                                record_validated[f"_warning_{w.rule_id}"] = w.message

                        buffer.append(record_validated)
                        total_valid += 1

                        # Flush buffer to disk when full — constant memory regardless of dataset size
                        if len(buffer) >= batch_size:
                            chunk_path = staging_dir / f"chunk_{chunk_idx:06d}.parquet"
                            pd.DataFrame(buffer).to_parquet(chunk_path, index=False)
                            chunk_files.append(chunk_path)
                            chunk_idx += 1
                            buffer.clear()

                # Final flush of remaining buffer
                if buffer:
                    chunk_path = staging_dir / f"chunk_{chunk_idx:06d}.parquet"
                    pd.DataFrame(buffer).to_parquet(chunk_path, index=False)
                    chunk_files.append(chunk_path)

                # Read all chunks back (O(n) total I/O — each chunk written & read once)
                if chunk_files:
                    result.valid_df = pd.concat(
                        [pd.read_parquet(f) for f in sorted(chunk_files)],
                        ignore_index=True,
                    )
                    result.valid_df = result.valid_df.drop(columns=["_extraction_watermark"], errors="ignore")
                    result.valid_path = str(staging_dir)
                elif buffer:
                    result.valid_df = pd.DataFrame(buffer)
                else:
                    result.valid_df = pd.DataFrame()

                # ---- Build result ----
                result.rows_extracted = total_rows
                result.rows_valid = total_valid
                result.rows_rejected = len(dlq_entries)
                result.dlq_entries = dlq_entries
                result.watermark_candidate = watermark_candidate
                result.status = "COMPLETED" if result.rows_rejected == 0 else "PARTIAL"
                result.duration_seconds = (datetime.now(timezone.utc) - t_start).total_seconds()

                logger.info(
                    "Extraction complete: %s — %d extracted, %d valid, %d rejected (%.1fs)",
                    spec.dataset_name, total_rows,
                    result.rows_valid, result.rows_rejected,
                    result.duration_seconds,
                )
                break  # Success — exit retry loop

            except sa.exc.OperationalError as e:
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "  DB connection lost (attempt %d/%d), retrying in %.1fs: %s",
                        attempt, MAX_RETRIES, delay, e,
                    )
                    _time.sleep(delay)
                else:
                    result.status = "FAILED"
                    result.errors.append(f"DB connection failed after {MAX_RETRIES} retries: {e}")
                    logger.error("Extraction FAILED after retries: %s", e)

            except (IncompatibleSpecError, QueryBuildError) as e:
                result.status = "FAILED"
                result.errors.append(str(e))
                logger.error("Extraction FAILED: %s", e)
                break

            except Exception as e:
                result.status = "FAILED"
                result.errors.append(f"{type(e).__name__}: {e}")
                logger.exception("Extraction FAILED with unexpected error")
            break

        return result

    def commit_watermark(self, dataset_name: str, watermark: datetime | None) -> None:
        """Advance state only after the ETL load has been durably published."""
        if watermark is None:
            return
        self._watermarks.set(dataset_name, watermark)
        logger.info("  Watermark committed: %s", watermark.isoformat())

    # ------------------------------------------------------------------
    # DLQ persistence
    # ------------------------------------------------------------------

    @staticmethod
    def persist_dlq(dlq_entries: list[DLQEntry], output_dir: str | Path = "etl/audit") -> Path:
        """Write DLQ entries to a timestamped JSON file in the audit directory.

        Args:
            dlq_entries: List of DLQEntry objects from an extraction run.
            output_dir: Directory for DLQ files (created if missing).

        Returns:
            Path to the written file.

        Raises:
            OSError: If the file cannot be written.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = out / f"dlq_{ts}.json"

        records = []
        for entry in dlq_entries:
            records.append({
                "rejection_id": entry.rejection_id,
                "batch_id": entry.batch_id,
                "source_system": entry.source_system,
                "entity_name": entry.entity_name,
                "rejection_tier": entry.rejection_tier,
                "rule_code": entry.rule_code,
                "error_details": entry.error_details,
                "raw_payload": entry.raw_payload,
            })

        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, default=str)

        logger.info("  DLQ persisted: %d records → %s", len(records), path)
        return path

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
    def _as_utc_datetime(value: Any) -> datetime | None:
        """Normalise database timestamp values for watermark comparison.

        Returns None (instead of raising) for unsupported types so that
        a single bad row does not crash the entire extraction.
        """
        if value is None:
            return None
        try:
            if isinstance(value, pd.Timestamp):
                value = value.to_pydatetime()
            if isinstance(value, str):
                value = datetime.fromisoformat(value)
            if not isinstance(value, datetime):
                return None
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            return None

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
