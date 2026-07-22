"""
ETL Engine Runner -- Production-hardened pipeline for Absa Bank Zambia.

Reads CSV data, validates, transforms, and loads into the etl_clean
target database with compliance-grade audit trails.

Usage:
    python run_etl.py                          # default fixture
    python run_etl.py --csv path/to/data.csv   # custom input
    python run_etl.py --dry-run                # validate only (no DB writes)
    python run_etl.py --force                  # re-process an already-loaded file

Features:
    - Batch bulk insert (psycopg2.extras.execute_values) for performance
    - Idempotency guard (detects duplicate loads by source hash)
    - Data-agnostic invariant checks on every run
    - Structured logging (INFO/WARNING/ERROR with timestamps)
    - DB connection failure recovery with partial audit records
    - Quality score threshold alerts

PII / Compliance Note:
    customer_id and account_id are stored in plaintext in both
    customer_transactions_clean and customer_transactions_rejected
    (and referenced in etl.etl_audit via batch-level metadata).
    For Bank of Zambia data residency compliance, these fields
    should be reviewed for at-rest encryption or tokenization
    before production deployment. The audit trail schema does not
    store individual customer/account values at batch level, but
    the row-level tables do.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

# --- Path setup (safe for both import and direct execution) ---


def _setup_project_path() -> str:
    """Ensure the project root is on sys.path. Returns project root path."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root


_PROJECT_ROOT = _setup_project_path()

import pandas as pd
import psycopg2
from psycopg2 import extras

from etl.config.service import ETLConfig
from etl.schemas.connector_schemas import ConnectorConfig, SourceType
from etl.connectors.factory import create_connector
from etl.validation.service import ValidationService
from etl.transformation.service import TransformationService
from etl.extraction.executor import ExtractionExecutor
from sqlalchemy import MetaData
from shared.config.settings import settings
from shared.database.postgres import get_sync_engine

# --- Logging ---
logging.basicConfig(
    level=getattr(logging, os.getenv("ETL_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)-7s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("etl_engine")

# Force UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# --- Constants ---
BATCH_SIZE = 5000
QUALITY_WARN_THRESHOLD = 90.0
QUALITY_ERROR_THRESHOLD = 70.0


# ===========================================================================
# Database Helpers
# ===========================================================================


def get_source_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(settings.database_url_sync)


def get_target_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(settings.database_target_url_sync)


def _compute_file_hash(file_path: str) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def check_already_loaded(file_path: str) -> str | None:
    """Check if a source file was already successfully loaded.
    Returns the previous batch_id if found, None otherwise."""
    conn = get_target_conn()
    try:
        cur = conn.cursor()
        file_hash = _compute_file_hash(file_path)
        file_name = os.path.basename(file_path)
        cur.execute(
            "SELECT batch_id FROM etl.etl_audit "
            "WHERE source_name = %s AND tags->>'file_hash' = %s AND status = 'COMPLETED' "
            "ORDER BY id DESC LIMIT 1",
            (file_name, file_hash),
        )
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        conn.close()


def write_audit_record(
    run_id: str,
    batch_id: str,
    source_type: str,
    source_name: str,
    pipeline_name: str,
    started_at: datetime,
    duration_seconds: float,
    rows_received: int,
    rows_valid: int,
    rows_rejected_count: int,
    rows_loaded: int,
    rows_skipped: int,
    duplicates_detected: int,
    warnings_count: int,
    errors_count: int,
    quality_score: float,
    status: str,
    triggered_by: str = "system",
    error_message: str | None = None,
    tags: dict | None = None,
) -> bool:
    """Write a compliance-grade audit record to etl.etl_audit. Returns True on success."""
    try:
        conn = get_target_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO etl.etl_audit (
                audit_id, batch_id, source_type, source_name, pipeline_name,
                started_at, completed_at, duration_seconds,
                rows_received, rows_valid, rows_rejected, rows_loaded, rows_skipped,
                duplicates_detected, warnings_count, errors_count, quality_score,
                status, error_message, triggered_by, tags
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                run_id, batch_id, source_type, source_name, pipeline_name,
                started_at, datetime.now(timezone.utc), duration_seconds,
                rows_received, rows_valid, rows_rejected_count, rows_loaded, rows_skipped,
                duplicates_detected, warnings_count, errors_count, quality_score,
                status, error_message, triggered_by,
                json.dumps(tags) if tags else None,
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("Failed to write audit record: %s", e)
        return False


# ===========================================================================
# Bulk Insert (batched, high-performance with execute_values)
# ===========================================================================


def bulk_insert_clean(records: list[dict], batch_id: str, config) -> tuple[int, int]:
    """Insert cleaned records using batch execute_values.
    Table, columns, and metadata are driven by config (etl_config.yaml → target section).
    Returns (inserted_clean, rescued_to_rejected)."""
    if not records:
        return (0, 0)

    t0 = time.monotonic()
    data_columns = config.target_data_columns
    meta_columns = config.target_meta_columns
    table_columns = data_columns + meta_columns
    clean_table = config.target_clean_table
    rejected_table = config.target_rejected_table

    conn = get_target_conn()
    inserted = 0
    rescued = 0
    now = datetime.now(timezone.utc)
    col_names = ", ".join(table_columns)
    placeholders = ",".join(["%s"] * len(table_columns))

    try:
        cur = conn.cursor()
        for chunk_start in range(0, len(records), BATCH_SIZE):
            chunk = records[chunk_start : chunk_start + BATCH_SIZE]
            values = [
                tuple(rec.get(c) for c in data_columns)
                + _build_meta_tuple(rec, meta_columns, now, batch_id)
                for rec in chunk
            ]
            try:
                extras.execute_values(
                    cur,
                    f"INSERT INTO {clean_table} ({col_names}) VALUES %s",
                    values,
                    template=f"({placeholders})",
                    page_size=BATCH_SIZE,
                )
                conn.commit()
                inserted += len(chunk)
            except Exception as batch_err:
                conn.rollback()
                logger.warning("Batch clean insert failed, falling back row-by-row: %s", batch_err)
                for rec in chunk:
                    try:
                        row_vals = (
                            tuple(rec.get(c) for c in data_columns)
                            + _build_meta_tuple(rec, meta_columns, now, batch_id)
                        )
                        cur.execute(
                            f"INSERT INTO {clean_table} ({col_names}) VALUES ({placeholders})",
                            row_vals,
                        )
                        conn.commit()
                        inserted += 1
                    except Exception as row_err:
                        conn.rollback()
                        try:
                            _rescue_to_rejected(cur, rec, rejected_table, data_columns, now, batch_id, row_err)
                            conn.commit()
                            rescued += 1
                        except Exception:
                            conn.rollback()

        elapsed = time.monotonic() - t0
        rate = inserted / elapsed if elapsed > 0 else 0
        logger.info("Clean insert: %d rows into %s in %.1fs (%.0f rows/s)", inserted, clean_table, elapsed, rate)
        if rescued > 0:
            logger.warning("Rescued %d rows from constraint violations", rescued)
    finally:
        conn.close()
    return (inserted, rescued)


def _build_meta_tuple(rec: dict, meta_columns: list[str], now: datetime, batch_id: str) -> tuple:
    """Build the metadata portion of an insert tuple from meta_columns config."""
    vals = []
    for mc in meta_columns:
        if mc == "loaded_at" or mc == "rejected_at":
            vals.append(now)
        elif mc == "batch_id":
            vals.append(batch_id)
        elif mc == "source_row_id":
            vals.append(rec.get("source_row_id"))
        else:
            vals.append(rec.get(mc))
    return tuple(vals)


def _rescue_to_rejected(cur, rec: dict, rejected_table: str, data_columns: list[str],
                         now: datetime, batch_id: str, error: Exception) -> None:
    """Insert a single rescued row into the rejected table."""
    rej_cols = data_columns + ["rejection_reason", "rejected_at", "batch_id"]
    rej_placeholders = ",".join(["%s"] * len(rej_cols))
    rej_sql = (
        f"INSERT INTO {rejected_table} "
        f"({', '.join(rej_cols)}) "
        f"VALUES ({rej_placeholders})"
    )
    cur.execute(rej_sql, (
        *tuple(rec.get(c) for c in data_columns),
        f"db_constraint_violation: {error}", now, batch_id,
    ))


def bulk_insert_rejected(
    records: list[dict], batch_id: str, reasons: list[str], config
) -> int:
    """Insert rejected records using batch execute_values.
    Table and columns are driven by config (etl_config.yaml → target section)."""
    if not records:
        return 0

    t0 = time.monotonic()
    data_columns = config.target_data_columns
    table_columns = data_columns + ["rejection_reason", "rejected_at", "batch_id"]
    rejected_table = config.target_rejected_table

    conn = get_target_conn()
    inserted = 0
    now = datetime.now(timezone.utc)
    col_names = ", ".join(table_columns)
    placeholders = ",".join(["%s"] * len(table_columns))

    try:
        cur = conn.cursor()
        for chunk_start in range(0, len(records), BATCH_SIZE):
            chunk = records[chunk_start : chunk_start + BATCH_SIZE]
            chunk_reasons = reasons[chunk_start : chunk_start + BATCH_SIZE]
            values = []
            for i, rec in enumerate(chunk):
                reason = (
                    chunk_reasons[i]
                    if i < len(chunk_reasons) and chunk_reasons[i] and chunk_reasons[i].strip()
                    else "Validation failed"
                )
                row = tuple(rec.get(c) for c in data_columns) + (reason, now, batch_id)
                values.append(row)

            try:
                extras.execute_values(
                    cur,
                    f"INSERT INTO {rejected_table} ({col_names}) VALUES %s",
                    values,
                    template=f"({placeholders})",
                    page_size=BATCH_SIZE,
                )
                conn.commit()
                inserted += len(chunk)
            except Exception:
                conn.rollback()
                logger.warning("Batch rejected insert failed, falling back row-by-row")
                for i, rec in enumerate(chunk):
                    reason = (
                        chunk_reasons[i]
                        if i < len(chunk_reasons) and chunk_reasons[i] and chunk_reasons[i].strip()
                        else "Validation failed"
                    )
                    try:
                        row = tuple(rec.get(c) for c in data_columns) + (reason, now, batch_id)
                        cur.execute(
                            f"INSERT INTO {rejected_table} ({col_names}) VALUES ({placeholders})",
                            row,
                        )
                        conn.commit()
                        inserted += 1
                    except Exception:
                        conn.rollback()

        elapsed = time.monotonic() - t0
        rate = inserted / elapsed if elapsed > 0 else 0
        logger.info("Rejected insert: %d rows into %s in %.1fs (%.0f rows/s)", inserted, rejected_table, elapsed, rate)
    finally:
        conn.close()
    return inserted


# ===========================================================================
# Data-Agnostic Invariant Checks
# ===========================================================================


def _run_invariant_checks(
    total_input: int,
    rows_loaded: int,
    reject_count: int,
    rows_rescued: int,
    quality_score: float,
    batch_id: str,
    rejected_table: str = "customer_transactions_rejected",
) -> list[str]:
    """Run data-agnostic invariant checks on every batch.
    These must hold for ANY input data, not just the fixture."""
    issues: list[str] = []

    accounted = rows_loaded + reject_count + rows_rescued
    if accounted != total_input:
        issues.append(
            f"CONSERVATION FAILURE: {rows_loaded} clean + {reject_count} rejected "
            f"+ {rows_rescued} rescued = {accounted}, expected {total_input}"
        )

    if rows_rescued > 0:
        issues.append(
            f"CONSTRAINT VIOLATIONS: {rows_rescued} rows rescued to rejected table"
        )

    if quality_score < QUALITY_ERROR_THRESHOLD:
        issues.append(
            f"QUALITY CRITICAL: {quality_score:.1f}% below error threshold {QUALITY_ERROR_THRESHOLD}%"
        )
    elif quality_score < QUALITY_WARN_THRESHOLD:
        issues.append(
            f"QUALITY WARNING: {quality_score:.1f}% below threshold {QUALITY_WARN_THRESHOLD}%"
        )

    try:
        conn = get_target_conn()
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM {rejected_table} "
            "WHERE batch_id = %s AND (rejection_reason IS NULL OR rejection_reason = '' "
            "OR rejection_reason = 'Validation failed')",
            (batch_id,),
        )
        generic = cur.fetchone()[0]
        if generic > 0:
            issues.append(f"REASON COVERAGE: {generic} rows have generic rejection_reason")
        conn.close()
    except Exception as e:
        issues.append(f"REASON COVERAGE CHECK FAILED: {e}")

    return issues


# ===========================================================================
# Schema Drift Detection
# ===========================================================================


class SchemaDriftError(Exception):
    """Raised when the input schema does not match the expected schema."""


def _validate_schema(
    df: pd.DataFrame,
    expected_columns: list[str],
    mode: str = "strict",
    source_name: str = "",
) -> None:
    """Validate that the DataFrame schema matches the expected columns.

    In 'strict' mode (default for regulated banking), any difference
    raises SchemaDriftError with a clear explanation of what changed.

    Args:
        df: The extracted DataFrame.
        expected_columns: Ordered list of expected column names.
        mode: 'strict' (fail), 'warn' (log only), or 'off' (skip).
        source_name: Name of the source file for error messages.

    Raises:
        SchemaDriftError: If mode='strict' and schema differs.
    """
    if mode == "off":
        return

    actual = list(df.columns)
    expected = list(expected_columns)

    missing = [c for c in expected if c not in actual]
    extra = [c for c in actual if c not in expected]
    reordered = False
    if not missing and not extra and actual != expected:
        reordered = True

    if not missing and not extra and not reordered:
        logger.info("  Schema OK: %d columns match expected", len(actual))
        return

    # Build a clear error message
    lines = [f"SCHEMA DRIFT DETECTED in '{source_name}'"]
    lines.append(f"  Expected {len(expected)} columns: {expected}")
    lines.append(f"  Actual   {len(actual)} columns: {actual}")

    if missing:
        lines.append(f"  MISSING columns ({len(missing)}): {missing}")
    if extra:
        lines.append(f"  EXTRA columns   ({len(extra)}): {extra}")
    if reordered:
        lines.append(f"  REORDERED: columns present but in different order")

    # Type hints for expected columns
    if not missing:
        type_issues = []
        for col in expected:
            actual_dtype = str(df[col].dtype)
            # For banking data, we expect object/string for IDs and codes,
            # float64/int64 for amounts
            type_issues.append(f"    {col}: {actual_dtype}")
        lines.append("  Column dtypes:")
        lines.extend(type_issues)

    msg = "\n".join(lines)

    if mode == "strict":
        logger.error(msg)
        raise SchemaDriftError(msg)
    else:  # warn
        logger.warning(msg)


async def run_etl_pipeline(
    csv_path: str | None = None,
    source_table: str | None = None,
    source_query: str | None = None,
    extraction_spec: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    triggered_by: str = "cli",
) -> dict:
    """Execute the complete ETL pipeline: Extract -> Validate -> Transform -> Load.

    Supports three extraction modes:
    - Extraction Spec mode (primary): --extraction-spec → Dynamic Extractor pre-processor
    - Database mode: --source-table or --source-query
    - CSV mode (fallback): --csv
    """
    run_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())
    start_time = time.monotonic()
    started_at = datetime.now(timezone.utc)

    # Determine extraction mode
    use_extraction_spec = bool(extraction_spec)
    use_db = bool(source_table or source_query)
    source_label = extraction_spec or source_table or source_query or csv_path or "unknown"

    logger.info("=" * 60)
    logger.info("ETL ENGINE STARTED  run=%s  batch=%s", run_id[:8], batch_id[:8])
    if use_extraction_spec:
        logger.info("Source: %s  Mode: EXTRACTION_SPEC", extraction_spec)
    else:
        logger.info("Source: %s  Mode: %s", source_label, "DATABASE" if use_db else "CSV")
    if dry_run:
        logger.info("Mode: DRY RUN (no database writes)")

    # Idempotency check (skip for extraction-spec mode — it's a pre-processor)
    if not dry_run and not force and not use_extraction_spec:
        prev = check_already_loaded(source_label)
        if prev:
            logger.warning(
                "IDEMPOTENCY GUARD: Source already loaded (batch=%s). Use --force to re-process.", prev[:8]
            )
            return {"run_id": run_id, "batch_id": batch_id, "status": "SKIPPED_DUPLICATE", "previous_batch_id": prev}

    # ------------------------------------------------------------------
    # PHASE 0 (OPTIONAL): Dynamic Extractor pre-processor
    # ------------------------------------------------------------------
    if use_extraction_spec:
        logger.info("--- Phase 0/4: DYNAMIC EXTRACTOR ---")
        spec_path = os.path.join(_PROJECT_ROOT, extraction_spec)

        engine = get_sync_engine()  # Synchronous engine for Dynamic Extractor
        metadata = MetaData()

        extractor = ExtractionExecutor(
            engine=engine,
            metadata=metadata,
            engine_version="2.1",
        )
        extraction_result = extractor.execute(spec_path)

        if extraction_result.status == "FAILED":
            logger.error("Dynamic Extractor FAILED: %s", extraction_result.errors)
            return {"run_id": run_id, "batch_id": batch_id, "status": "FAILED",
                    "error": extraction_result.errors}

        df = extraction_result.valid_df
        total_rows = len(df)

        logger.info(
            "  Extractor: %d rows extracted, %d valid, %d rejected (DLQ)",
            extraction_result.rows_extracted,
            extraction_result.rows_valid,
            extraction_result.rows_rejected,
        )

        if df.empty:
            logger.error("No valid records from extraction spec. Aborting.")
            return {"status": "FAILED", "error": "No valid records from Dynamic Extractor"}

        # DLQ entries could be persisted here — skipped for now
        if extraction_result.dlq_entries:
            logger.warning(
                "  %d records routed to DLQ (not yet persisted — DLQ table pending)",
                len(extraction_result.dlq_entries),
            )

    # ------------------------------------------------------------------
    # PHASE 1: EXTRACT (standard mode — skipped if extraction spec used)
    # ------------------------------------------------------------------
    if not use_extraction_spec:
        logger.info("--- Phase 1/4: EXTRACT ---")

    # Load config (needed for both modes)
    config = ETLConfig.load(
        config_path=os.path.join(_PROJECT_ROOT, "etl", "config", "etl_config.yaml")
    )

    if not use_extraction_spec:
        if use_db:
            connector_config = ConnectorConfig(
                source_type=SourceType.POSTGRESQL,
                source_name=source_table or "Custom SQL Query",
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_db,
                username=settings.postgres_user,
                password=settings.postgres_password,
                table_name=source_table,
                query=source_query,
            )
        else:
            connector_config = ConnectorConfig(
                source_type=SourceType.CSV,
                source_name="Customer Transactions CSV",
                file_path=csv_path,
            )
        connector = create_connector(connector_config)
        await connector.connect()

        all_data: list[pd.DataFrame] = []
        async for dataset in connector.extract():
            all_data.append(dataset.data)
            logger.info("  Chunk: %s rows, %s columns", f"{dataset.row_count:,}", len(dataset.column_names))

        df = pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()
        total_rows = len(df)
        logger.info("  Total extracted: %s rows", f"{total_rows:,}")

        if df.empty:
            logger.error("No data extracted. Aborting.")
            return {"status": "FAILED", "error": "No data returned from source"}

        await connector.disconnect()

    # Schema drift check — common to both extraction modes
    _validate_schema(df, config.expected_columns, mode=config.schema_mode,
                     source_name=source_label)

    # ------------------------------------------------------------------
    # PHASE 2: VALIDATE
    # ------------------------------------------------------------------
    logger.info("--- Phase 2/4: VALIDATE ---")
    validation_service = ValidationService(config=config.validation)
    validation_report = await validation_service.validate(df, batch_id)

    logger.info(
        "  Records: %s total, %s valid, %s invalid, %s duplicates, quality=%.1f%%",
        f"{validation_report.total_records:,}",
        f"{validation_report.valid_records:,}",
        f"{validation_report.invalid_records:,}",
        f"{validation_report.duplicate_records:,}",
        validation_report.quality_score,
    )

    for rule, count in sorted(validation_report.error_by_rule.items(), key=lambda x: -x[1])[:5]:
        logger.info("  Rule: [%s] count=%s", rule, f"{count:,}")

    valid_indices: set[int] = set()
    invalid_indices: set[int] = set()
    if validation_report.record_results:
        for result in validation_report.record_results:
            if result.is_valid:
                valid_indices.add(result.record_index)
            else:
                invalid_indices.add(result.record_index)

    valid_df = df.loc[list(valid_indices)] if valid_indices else df.copy()
    invalid_df = df.loc[list(invalid_indices)] if invalid_indices else pd.DataFrame()

    # ------------------------------------------------------------------
    # PHASE 3: TRANSFORM
    # ------------------------------------------------------------------
    logger.info("--- Phase 3/4: TRANSFORM ---")
    transformation_service = TransformationService(config=config.transformation)

    if not valid_df.empty:
        transformed_df, transform_report = await transformation_service.transform(valid_df, batch_id)
        logger.info(
            "  %s -> %s rows (fields_mapped=%d, values_std=%d)",
            f"{transform_report.input_rows:,}", f"{transform_report.output_rows:,}",
            transform_report.fields_mapped, transform_report.values_standardized,
        )
    else:
        transformed_df = valid_df
        logger.info("  No valid records to transform")

    # ------------------------------------------------------------------
    # PHASE 4: LOAD
    # ------------------------------------------------------------------
    logger.info("--- Phase 4/4: LOAD ---")

    rows_loaded = 0
    rows_rescued = 0
    reject_count = 0
    status = "COMPLETED_DRY_RUN" if dry_run else "COMPLETED"

    if not dry_run:
        reason_map: dict[int, str] = {}
        if validation_report.record_results:
            for result in validation_report.record_results:
                if not result.is_valid and result.errors:
                    rule_ids = sorted({e.rule_id for e in result.errors})
                    reason_map[result.record_index] = "; ".join(rule_ids)

        clean_records = transformed_df.to_dict(orient="records") if not transformed_df.empty else []
        rows_loaded, rows_rescued = bulk_insert_clean(clean_records, batch_id, config)
        logger.info("  Clean loaded: %s", f"{rows_loaded:,}")

        rejected_records = invalid_df.to_dict(orient="records") if not invalid_df.empty else []
        rejected_reasons = [reason_map.get(idx, "Validation failed") for idx in sorted(invalid_indices)]
        reject_count = bulk_insert_rejected(rejected_records, batch_id, rejected_reasons, config)
        logger.info("  Rejected: %s", f"{reject_count:,}")

        # Invariant checks
        issues = _run_invariant_checks(
            total_input=total_rows, rows_loaded=rows_loaded,
            reject_count=reject_count, rows_rescued=rows_rescued,
            quality_score=validation_report.quality_score, batch_id=batch_id,
            rejected_table=config.target_rejected_table,
        )
        for issue in issues:
            if "CRITICAL" in issue or "FAILURE" in issue:
                logger.error(issue)
            else:
                logger.warning(issue)

        # Audit
        file_hash = _compute_file_hash(csv_path) if csv_path else hashlib.sha256(source_label.encode()).hexdigest()
        audit_source_type = "CSV" if csv_path else "POSTGRESQL"
        audit_ok = write_audit_record(
            run_id=run_id, batch_id=batch_id,
            source_type=audit_source_type, source_name=source_label,
            pipeline_name="etl_full_pipeline",
            started_at=started_at, duration_seconds=time.monotonic() - start_time,
            rows_received=total_rows,
            rows_valid=validation_report.valid_records,
            rows_rejected_count=validation_report.invalid_records,
            rows_loaded=rows_loaded, rows_skipped=0,
            duplicates_detected=validation_report.duplicate_records,
            warnings_count=validation_report.total_warnings,
            errors_count=validation_report.total_errors,
            quality_score=validation_report.quality_score,
            status="COMPLETED", triggered_by=triggered_by,
            tags={"run_id": run_id, "source": source_label, "file_hash": file_hash},
        )
        if not audit_ok:
            logger.error("Failed to write audit record")

    duration = time.monotonic() - start_time
    logger.info("=" * 60)
    logger.info(
        "ETL COMPLETE  duration=%.1fs  received=%s  valid=%s  rejected=%s  loaded=%s  quality=%.1f%%",
        duration, f"{total_rows:,}", f"{validation_report.valid_records:,}",
        f"{validation_report.invalid_records:,}", f"{rows_loaded:,}",
        validation_report.quality_score,
    )
    logger.info("=" * 60)

    return {
        "run_id": run_id, "batch_id": batch_id, "status": status,
        "rows_received": total_rows, "rows_valid": validation_report.valid_records,
        "rows_rejected": validation_report.invalid_records, "rows_loaded": rows_loaded,
        "rows_rescued": rows_rescued, "quality_score": validation_report.quality_score,
        "duration_seconds": duration,
    }


# ===========================================================================
# CLI Entry Point
# ===========================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="Absa Bank Zambia -- ETL Engine Runner")
    parser.add_argument(
        "--source-table",
        default=None,
        help="Database table to extract from (e.g., 'public.customer_transactions'). Uses PostgreSQL connector.",
    )
    parser.add_argument(
        "--source-query",
        default=None,
        help="Custom SQL query for extraction. Overrides --source-table.",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="CSV file path (fallback mode when --source-table is not used)",
    )
    parser.add_argument(
        "--extraction-spec",
        default=None,
        help="Path to YAML extraction spec for the Dynamic Extractor pre-processor (e.g., 'etl/config/extraction_specs/customer_360.yaml')",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-process even if source was already loaded")
    args = parser.parse_args()

    # Determine extraction mode
    use_extraction_spec = bool(args.extraction_spec)
    use_db = bool(args.source_table or args.source_query)
    use_csv = bool(args.csv)

    if not use_extraction_spec and not use_db and not use_csv:
        logger.error("No source specified. Use --extraction-spec, --source-table, --source-query, or --csv.")
        sys.exit(1)

    if use_extraction_spec and (use_db or use_csv):
        logger.error("Cannot combine --extraction-spec with --source-table/--source-query/--csv.")
        sys.exit(1)

    if use_db and use_csv:
        logger.error("Cannot use both --source-table/--source-query and --csv. Choose one.")
        sys.exit(1)

    if use_csv and not os.path.exists(args.csv):
        logger.error("CSV file not found: %s", args.csv)
        sys.exit(1)

    import asyncio
    result = asyncio.run(run_etl_pipeline(
        csv_path=args.csv,
        source_table=args.source_table,
        source_query=args.source_query,
        extraction_spec=args.extraction_spec,
        dry_run=args.dry_run,
        force=args.force,
    ))

    if result["status"] == "SKIPPED_DUPLICATE":
        logger.info("Source already processed. Use --force to re-run.")
        sys.exit(0)
    if result["status"] not in ("COMPLETED", "COMPLETED_DRY_RUN"):
        sys.exit(1)


if __name__ == "__main__":
    main()
