"""Shared loader for inbound data.

Every ingest path funnels through :func:`load_batch`:

* ``etl.ingest.customer_csv`` — operator CSV upload from the My Customers page
* ``etl.ingest.core_banking`` — ETL Engine pull from the core Absa system

The loader owns the only write paths into the clean layer. It validates against
the target dataset's contract (``etl.ingest.customer_schema``), upserts on that
dataset's natural key, records rejects, and appends the compliance audit row.

Supported datasets:

``customers``         → ``public.customers_clean``   key ``customer_id``
``customer_features`` → ``public.customer_features`` key ``(customer_id, as_of_date)``
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import MetaData, Table, text
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert

from etl.ingest.customer_schema import (
    CUSTOMER_ID_FIELD,
    DEFAULT_DATASET,
    REJECTED_TABLE,
    DatasetSpec,
    get_dataset,
)
from shared.constants.market_segments import resolve_market_segment
from shared.database.postgres import get_sync_target_engine

logger = logging.getLogger("etl.ingest.loader")

PIPELINE_NAME = "customer_ingest"
QUALITY_WARN_THRESHOLD = 90.0

# Postgres identifier limits; keeps the reflected Table cache honest.
_TABLE_CACHE: dict[str, Table] = {}


def _reflected_table(engine: Engine, qualified: str) -> Table:
    """Reflect ``public.customers_clean`` once per engine."""
    cache_key = f"{id(engine)}::{qualified}"
    table = _TABLE_CACHE.get(cache_key)
    if table is None:
        schema, _, name = qualified.partition(".")
        table = Table(name, MetaData(), schema=schema or None, autoload_with=engine)
        _TABLE_CACHE[cache_key] = table
    return table


def new_batch_id() -> str:
    """Batch identifier written onto every row of a load."""
    return f"ing_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Row preparation
# ---------------------------------------------------------------------------

def prepare_records(
    records: Sequence[dict[str, Any]],
    *,
    dataset: DatasetSpec,
    batch_id: str,
    loaded_at: datetime,
) -> list[dict[str, Any]]:
    """Project records onto the dataset's columns and apply loader stamps.

    Stamps (``loaded_at``, ``batch_id``, ``computed_at``) are only applied when
    the source left the field empty, so a feature extract that carries its own
    ``computed_at`` keeps it. The market-segment label is resolved from the code
    when the source supplied the code but not the label.
    """
    projected: list[dict[str, Any]] = []

    for record in records:
        row = {column: record.get(column) for column in dataset.data_columns}

        for column, stamp in dataset.stamps.items():
            if row.get(column) is not None:
                continue
            row[column] = batch_id if stamp == "batch" else loaded_at

        if "market_segment" in row and not row.get("market_segment") and row.get("market_segment_code"):
            row["market_segment"] = resolve_market_segment(row["market_segment_code"])

        projected.append(row)

    return projected


def dedupe_by_key(
    records: Sequence[dict[str, Any]], key_columns: Sequence[str]
) -> tuple[list[dict[str, Any]], int]:
    """Keep one row per natural key (last occurrence wins).

    Required for correctness as much as tidiness: Postgres rejects a single
    ``INSERT ... ON CONFLICT`` statement that touches the same key twice.
    """
    seen: dict[tuple, int] = {}
    deduped: list[dict[str, Any]] = []
    duplicates = 0

    for record in records:
        key = tuple(
            str(record.get(column)) if record.get(column) is not None else ""
            for column in key_columns
        )
        if key in seen:
            deduped[seen[key]] = record
            duplicates += 1
        else:
            seen[key] = len(deduped)
            deduped.append(record)

    return deduped, duplicates


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def count_existing(engine: Engine, key_values: Sequence[Any], dataset: str | None = None) -> int:
    """How many of these key values already exist. Diagnostic/back-compat only.

    The insert/update split now comes from the ``xmax = 0`` idiom inside
    :func:`upsert`, which cannot race; this stays for ad-hoc checks.
    """
    if not key_values:
        return 0
    spec = get_dataset(dataset)
    key_column = spec.key_columns[0]
    stmt = text(f"SELECT count(*) FROM {spec.table} WHERE {key_column} = ANY(:ids)")
    with engine.connect() as conn:
        return int(conn.execute(stmt, {"ids": list(key_values)}).scalar_one())


def customer_exists(customer_id: str, engine: Engine | None = None) -> str | None:
    """Whether a customer row already exists: ``"live"``, ``"deleted"`` or ``None``.

    The Add Customer form checks this instead of trusting the upsert, because
    two traps make a blind upsert wrong for manual entry:

    * :func:`upsert` writes **every** data column for the dataset, so an update
      built from a form where the operator only filled some fields would null
      all the others.
    * A soft-deleted customer still has its row (``is_deleted`` = true), so an
      upsert would report success while the customer stayed hidden from every
      list and count.
    """
    engine = engine or get_sync_target_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT is_deleted FROM public.customers_clean WHERE customer_id = :cid"),
            {"cid": customer_id},
        ).first()
    if row is None:
        return None
    return "deleted" if row[0] else "live"


def upsert(
    engine: Engine,
    records: Sequence[dict[str, Any]],
    dataset: DatasetSpec,
    *,
    chunk_size: int = 1000,
) -> tuple[int, int]:
    """Insert-or-update rows on the dataset's natural key.

    Returns ``(inserted, updated)``. The split is derived from Postgres'
    ``xmax = 0`` idiom, which reports the true per-row outcome without a second
    round trip and without a race window (unlike a pre-count of existing keys).

    ``upsert_customers`` below is the single-dataset back-compat wrapper.
    """
    if not records:
        return 0, 0

    table = _reflected_table(engine, dataset.table)
    table_col_names = set(table.columns.keys())
    key_columns = [c for c in dataset.key_columns if c in table_col_names]
    update_columns = [c for c in dataset.data_columns if c not in key_columns and c in table_col_names]

    inserted = 0
    updated = 0

    with engine.begin() as conn:
        for start in range(0, len(records), chunk_size):
            chunk = [
                {k: v for k, v in record.items() if k in table_col_names}
                for record in records[start:start + chunk_size]
            ]
            stmt = pg_insert(table).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=[table.c[column] for column in key_columns],
                set_={column: stmt.excluded[column] for column in update_columns},
            ).returning(text("(xmax = 0) AS was_insert"))
            outcomes = conn.execute(stmt).scalars().all()
            inserted += sum(1 for outcome in outcomes if outcome)
            updated += sum(1 for outcome in outcomes if not outcome)

    logger.info(
        "%s upsert: %d inserted, %d updated", dataset.table, inserted, updated
    )
    return inserted, updated


def upsert_customers(
    engine: Engine,
    records: Sequence[dict[str, Any]],
    *,
    chunk_size: int = 1000,
) -> tuple[int, int]:
    """Back-compat wrapper: upsert into the default (customers) dataset."""
    return upsert(engine, records, get_dataset(DEFAULT_DATASET), chunk_size=chunk_size)


def dedupe_by_customer(
    records: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Back-compat wrapper: dedupe on the default dataset's key."""
    return dedupe_by_key(records, get_dataset(DEFAULT_DATASET).key_columns)


def insert_rejections(
    engine: Engine,
    rejects: Sequence[dict[str, Any]],
    *,
    batch_id: str,
    source_name: str,
) -> int:
    """Persist rejected rows so operators can fix and re-upload them.

    Silently degrades to a no-op if the reject table has not been migrated yet —
    a missing reject table must never fail an otherwise valid load.
    """
    if not rejects:
        return 0

    payload = [
        {
            "batch_id": batch_id,
            "source_name": source_name,
            "row_number": reject.get("row_number"),
            "customer_id": reject.get("customer_id"),
            "raw_row": json.dumps(reject.get("raw_row") or {}, default=str),
            "rejection_reason": "; ".join(reject.get("errors") or [])[:2000],
            "rejected_at": datetime.now(timezone.utc),
        }
        for reject in rejects
    ]

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {REJECTED_TABLE}
                        (batch_id, source_name, row_number, customer_id, raw_row,
                         rejection_reason, rejected_at)
                    VALUES
                        (:batch_id, :source_name, :row_number, :customer_id,
                         CAST(:raw_row AS JSONB), :rejection_reason, :rejected_at)
                    """
                ),
                payload,
            )
    except Exception as exc:  # noqa: BLE001 - rejects are advisory, not critical path
        logger.warning("Could not persist rejects to %s: %s", REJECTED_TABLE, exc)
        return 0
    return len(payload)


def write_audit_record(
    engine: Engine,
    *,
    run_id: str,
    batch_id: str,
    source_type: str,
    source_name: str,
    started_at: datetime,
    rows_received: int,
    rows_valid: int,
    rows_rejected: int,
    rows_loaded: int,
    errors_count: int,
    status: str,
    triggered_by: str,
    tags: dict[str, Any],
    duplicates_detected: int = 0,
    error_message: str | None = None,
) -> bool:
    """Append the compliance audit row to ``etl.etl_audit``.

    Mirrors ``run_etl.write_audit_record`` so ingest runs appear in the same
    ETL Run History / quality dashboards.
    """
    duration = (datetime.now(timezone.utc) - started_at).total_seconds()
    quality_score = round((rows_valid / rows_received) * 100, 2) if rows_received else 100.0

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO etl.etl_audit (
                        audit_id, batch_id, source_type, source_name, pipeline_name,
                        started_at, completed_at, duration_seconds,
                        rows_received, rows_valid, rows_rejected, rows_loaded, rows_skipped,
                        duplicates_detected, warnings_count, errors_count, quality_score,
                        status, error_message, triggered_by, tags
                    ) VALUES (
                        :audit_id, :batch_id, :source_type, :source_name, :pipeline_name,
                        :started_at, :completed_at, :duration_seconds,
                        :rows_received, :rows_valid, :rows_rejected, :rows_loaded, 0,
                        :duplicates_detected, 0, :errors_count, :quality_score,
                        :status, :error_message, :triggered_by, CAST(:tags AS JSONB)
                    )
                    """
                ),
                {
                    "audit_id": run_id,
                    "batch_id": batch_id,
                    "source_type": source_type,
                    "source_name": source_name,
                    "pipeline_name": PIPELINE_NAME,
                    "started_at": started_at,
                    "completed_at": datetime.now(timezone.utc),
                    "duration_seconds": duration,
                    "rows_received": rows_received,
                    "rows_valid": rows_valid,
                    "rows_rejected": rows_rejected,
                    "rows_loaded": rows_loaded,
                    "duplicates_detected": duplicates_detected,
                    "errors_count": errors_count,
                    "quality_score": quality_score,
                    "status": status,
                    "error_message": error_message,
                    "triggered_by": triggered_by,
                    "tags": json.dumps(tags, default=str),
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to write ingest audit record: %s", exc)
        return False
    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def load_batch(
    records: Sequence[dict[str, Any]],
    rejects: Sequence[dict[str, Any]],
    *,
    source_type: str,
    source_name: str,
    triggered_by: str,
    dataset: str | None = None,
    started_at: datetime | None = None,
    dry_run: bool = False,
    engine: Engine | None = None,
    extra_tags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate-and-load one batch of already-coerced records into a dataset."""
    started_at = started_at or datetime.now(timezone.utc)
    engine = engine or get_sync_target_engine()
    spec = get_dataset(dataset)

    batch_id = new_batch_id()
    run_id = str(uuid.uuid4())
    loaded_at = datetime.now(timezone.utc)

    rows_received = len(records) + len(rejects)
    rows_valid = len(records)
    rows_rejected = len(rejects)
    quality = round((rows_valid / rows_received) * 100, 2) if rows_received else 100.0

    base = {
        "run_id": run_id,
        "batch_id": batch_id,
        "dataset": spec.key,
        "dataset_label": spec.label,
        "target_table": spec.table,
        "key_columns": list(spec.key_columns),
        "source_type": source_type,
        "source_name": source_name,
        "rows_received": rows_received,
        "rows_valid": rows_valid,
        "rows_rejected": rows_rejected,
        "quality_score": quality,
    }

    if dry_run:
        return {
            **base,
            "status": "DRY_RUN",
            "rows_inserted": 0,
            "rows_updated": 0,
            "rows_loaded": 0,
            "duration_seconds": round((datetime.now(timezone.utc) - started_at).total_seconds(), 3),
            "rejected_samples": list(rejects[:20]),
            "dry_run": True,
        }

    prepared = prepare_records(records, dataset=spec, batch_id=batch_id, loaded_at=loaded_at)
    prepared, duplicates = dedupe_by_key(prepared, spec.key_columns)
    if duplicates:
        logger.warning(
            "Batch %s contained %d duplicate %s rows (last wins)",
            batch_id, duplicates, "/".join(spec.key_columns),
        )

    inserted, updated = upsert(engine, prepared, spec)
    rejected_written = insert_rejections(
        engine, rejects, batch_id=batch_id, source_name=source_name
    )

    status = "COMPLETED" if rows_rejected == 0 else "COMPLETED_WITH_REJECTS"
    if quality < QUALITY_WARN_THRESHOLD:
        logger.warning("Ingest quality %.2f%% below warn threshold (batch %s)", quality, batch_id)

    write_audit_record(
        engine,
        run_id=run_id,
        batch_id=batch_id,
        source_type=source_type,
        source_name=source_name,
        started_at=started_at,
        rows_received=rows_received,
        rows_valid=rows_valid,
        rows_rejected=rows_rejected,
        rows_loaded=inserted + updated,
        errors_count=rows_rejected,
        duplicates_detected=duplicates,
        status=status,
        triggered_by=triggered_by,
        tags={
            "source": "customer_ingest",
            "source_name": source_name,
            "dataset": spec.key,
            "target_table": spec.table,
            **(extra_tags or {}),
        },
    )

    duration = round((datetime.now(timezone.utc) - started_at).total_seconds(), 3)
    logger.info(
        "Ingest %s (%s) complete: %d inserted, %d updated, %d rejected in %.2fs",
        batch_id, spec.table, inserted, updated, rows_rejected, duration,
    )

    return {
        **base,
        "status": status,
        "rows_inserted": inserted,
        "rows_updated": updated,
        "rows_loaded": inserted + updated,
        "duplicates_detected": duplicates,
        "rejects_persisted": rejected_written,
        "duration_seconds": duration,
        "rejected_samples": list(rejects[:20]),
        "dry_run": False,
    }


def load_customer_batch(
    records: Sequence[dict[str, Any]],
    rejects: Sequence[dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    """Back-compat wrapper: load into the default (customers) dataset."""
    kwargs.setdefault("dataset", DEFAULT_DATASET)
    return load_batch(records, rejects, **kwargs)


def recent_ingest_runs(limit: int = 20, engine: Engine | None = None) -> list[dict[str, Any]]:
    """Latest ingest runs from the shared ETL audit trail."""
    engine = engine or get_sync_target_engine()
    stmt = text(
        """
        SELECT audit_id, batch_id, source_type, source_name, status,
               rows_received, rows_valid, rows_rejected, rows_loaded,
               quality_score, duration_seconds, started_at, completed_at,
               triggered_by, tags
        FROM etl.etl_audit
        WHERE pipeline_name = :pipeline
        ORDER BY started_at DESC
        LIMIT :limit
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt, {"pipeline": PIPELINE_NAME, "limit": limit}).mappings().all()
    return [dict(row) for row in rows]


def row_count(dataset: str | None = None, engine: Engine | None = None) -> int:
    """Current row count of a dataset's target table (shown in the ingest UI)."""
    spec = get_dataset(dataset)
    engine = engine or get_sync_target_engine()
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT count(*) FROM {spec.table}")).scalar_one())


def customer_count(engine: Engine | None = None) -> int:
    """Back-compat wrapper: row count of the default (customers) dataset."""
    return row_count(DEFAULT_DATASET, engine)
