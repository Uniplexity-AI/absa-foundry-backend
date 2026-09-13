"""Gateway routes — customer data ingest (CSV upload + core-banking pull).

FR-INGEST-01: load customer data from a CSV with an explicit column → field
              mapping that documents the expected format of every target field.
FR-INGEST-02: ETL Engine job that pulls customer data from the core Absa system
              and lands it in Postgres for downstream analysis.

Mounted at ``/api/v1/ingest`` (see shared/auth/permissions.py) so the RM
workspace can load data without OPERATIONS-only ``/api/etl`` access.

Write path: both endpoints funnel through ``etl.ingest.loader.load_batch``,
which validates against the selected dataset's contract
(``etl.ingest.customer_schema``), upserts on that dataset's natural key and
writes a compliance row to ``etl.etl_audit``.

Loadable datasets (``dataset`` parameter):

* ``customers``         → ``public.customers_clean``   key ``customer_id``
* ``customer_features`` → ``public.customer_features`` key ``(customer_id, as_of_date)``
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from etl.ingest import customer_csv
from etl.ingest.core_banking import (
    CORE_DATASETS,
    CoreExtractionError,
    describe_datasets,
    run_core_banking_load,
)
from etl.ingest.customer_schema import (
    DEFAULT_DATASET,
    DATASETS,
    coerce_row,
    describe_schema,
    get_dataset,
)
from etl.ingest.loader import customer_exists, load_batch, recent_ingest_runs, row_count

logger = logging.getLogger("gateway.routes.ingest")

router = APIRouter(prefix="/api/v1/ingest", tags=["Customer Ingest"])


# ═══════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════

class CsvLoadRequest(BaseModel):
    """Commit a staged CSV upload using the operator-confirmed mapping."""

    upload_id: str = Field(..., description="Upload id returned by /csv/preview")
    mapping: dict[str, str | None] = Field(
        ...,
        description="source CSV column -> target field of the selected dataset (null to skip)",
    )
    dataset: str = Field(
        default=DEFAULT_DATASET,
        description=f"Target dataset. One of: {', '.join(DATASETS)}",
    )
    filename: str | None = Field(default=None, description="Original filename, for the audit trail")
    dry_run: bool = Field(default=False, description="Validate and report without writing any rows")


class CoreBankingRunRequest(BaseModel):
    """Trigger the ETL Engine pull from the core Absa system."""

    dataset: str = Field(
        default="customers_core",
        description=f"One of: {', '.join(CORE_DATASETS)}",
    )
    limit: int | None = Field(
        default=None, ge=1, le=100_000,
        description="Cap the number of core rows pulled (useful for a trial run)",
    )
    dry_run: bool = Field(default=False, description="Extract + validate without writing to Postgres")
    as_of_date: str | None = Field(default=None, description="Recorded on the run for lineage")


class CustomerAddRequest(BaseModel):
    """One customer submitted from the Add Customer form (no CSV involved)."""

    row: dict[str, Any] = Field(
        ...,
        description=(
            "Target field name -> value for the chosen dataset. "
            "See GET /api/v1/ingest/schema for the field catalogue and formats."
        ),
    )
    dataset: str = Field(
        default=DEFAULT_DATASET,
        description=(
            f"Target dataset. One of: {', '.join(DATASETS)}. 'customers' is the "
            "master record (identity), 'customer_features' is one snapshot row per "
            "(customer_id, as_of_date)."
        ),
    )
    dry_run: bool = Field(default=False, description="Validate and report without writing any row")
    allow_update: bool = Field(
        default=False,
        description=(
            "Permit overwriting an existing customer id in the MASTER dataset. Off by "
            "default: the upsert writes every column, so a partially filled form would "
            "null the fields it did not carry, and a soft-deleted customer would stay "
            "hidden. Feature snapshots are always upserted on (customer_id, as_of_date)."
        ),
    )


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _actor(request: Request) -> str:
    """Best-effort caller identity for the audit trail."""
    user = getattr(request.state, "user", None)
    username = getattr(user, "username", None)
    if username:
        return str(username)
    service = getattr(request.state, "service", None)
    if service is not None:
        return f"service:{getattr(service, 'name', 'unknown')}"
    return "api"


def _dataset_row_counts() -> dict[str, int | None]:
    """Best-effort row count per loadable dataset, for the modal's target summary."""
    counts: dict[str, int | None] = {}
    for key in DATASETS:
        try:
            counts[key] = row_count(key)
        except Exception as exc:  # noqa: BLE001 - a probe failure must not break the schema
            logger.warning("Could not count %s: %s", key, exc)
            counts[key] = None
    return counts


# ═══════════════════════════════════════════════════════════════════
# Schema / status
# ═══════════════════════════════════════════════════════════════════

@router.get("/schema")
async def get_ingest_schema():
    """The ingest contract: loadable datasets, field formats and core feeds.

    Powers the mapping table on the My Customers page — each CSV column is
    matched to one field of the selected dataset, and the field's
    ``format``/``allowed_values`` is what the operator sees as "this is how the
    data must be formatted".
    """
    try:
        counts = await run_in_threadpool(_dataset_row_counts)
    except Exception as exc:  # noqa: BLE001 - schema is still useful without a DB probe
        logger.warning("Could not count ingest target rows: %s", exc)
        counts = {}

    return {
        **describe_schema(),
        "target_row_count": counts.get(DEFAULT_DATASET),
        "target_row_counts": counts,
        "core_datasets": describe_datasets(),
    }


@router.get("/runs")
async def list_ingest_runs(limit: int = Query(default=20, ge=1, le=200)):
    """Recent ingest runs (CSV and core-banking) from the shared audit trail."""
    try:
        return await run_in_threadpool(recent_ingest_runs, limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to read ingest runs")
        raise HTTPException(status_code=500, detail=f"Failed to read ingest runs: {exc}") from exc


# ═══════════════════════════════════════════════════════════════════
# CSV upload
# ═══════════════════════════════════════════════════════════════════

@router.post("/csv/preview")
async def preview_csv(
    request: Request,
    file: UploadFile | None = File(default=None),
    upload_id: str | None = Form(default=None),
    dataset: str = Form(default=DEFAULT_DATASET),
):
    """Stage an uploaded CSV (or re-preview a staged one) against a dataset.

    Pass ``file`` to stage a new upload; pass ``upload_id`` instead to re-map an
    already-staged file — that is how the UI re-previewes when the operator
    switches target dataset, with no second upload.
    """
    try:
        if file is not None and file.filename:
            content = await file.read()
            stored = await run_in_threadpool(customer_csv.save_upload, file.filename, content)
        elif upload_id:
            stored = customer_csv.StoredUpload(
                upload_id=upload_id,
                filename=upload_id,
                path=customer_csv.resolve_upload(upload_id),
                size_bytes=customer_csv.resolve_upload(upload_id).stat().st_size,
            )
        else:
            raise HTTPException(
                status_code=400, detail="Provide either a file or an upload_id to preview."
            )

        preview = await run_in_threadpool(
            customer_csv.build_preview,
            stored.path,
            filename=stored.filename,
            dataset=dataset,
        )
    except customer_csv.UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:  # unknown dataset key
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info(
        "CSV preview %s (%s) -> %s: %d rows, %d columns, %d mapping issue(s) [by %s]",
        stored.upload_id, stored.filename, preview["dataset"], preview["row_count"],
        len(preview["columns"]), len(preview["mapping_errors"]), _actor(request),
    )
    return preview


@router.post("/csv/load")
async def load_csv(request: Request, body: CsvLoadRequest):
    """Validate every row against the mapping and load the valid ones."""
    try:
        path = customer_csv.resolve_upload(body.upload_id)
        result = await run_in_threadpool(
            customer_csv.load_upload,
            path,
            body.mapping,
            filename=body.filename or path.name,
            triggered_by=_actor(request),
            dataset=body.dataset,
            dry_run=body.dry_run,
        )
    except customer_csv.UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:  # unknown dataset key
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("CSV load failed for upload %s", body.upload_id)
        raise HTTPException(status_code=500, detail=f"CSV load failed: {exc}") from exc

    logger.info(
        "CSV load %s -> %s: valid=%d rejected=%d inserted=%d updated=%d dry_run=%s",
        result["batch_id"], result["target_table"], result["rows_valid"],
        result["rows_rejected"], result["rows_inserted"], result["rows_updated"],
        result["dry_run"],
    )
    return result


# ═══════════════════════════════════════════════════════════════════
# Single customer (Add Customer form)
# ═══════════════════════════════════════════════════════════════════

@router.post("/customer")
async def add_customer(request: Request, body: CustomerAddRequest):
    """Add one customer from the Add Customer form — no CSV required.

    Handles both loadable datasets, so the same form can write the identity
    master record (``customers`` → ``public.customers_clean``) and/or a feature
    snapshot (``customer_features`` → ``public.customer_features``).

    Values are coerced and validated against the selected dataset's spec and
    land through ``loader.load_batch``, so the form is bound by exactly the
    contract the CSV upload and the loader enforce (same target table, same
    rejects, same ``etl.etl_audit`` row).

    Create-only for the master dataset — see ``CustomerAddRequest.allow_update``
    for why an existing id is reported as a conflict rather than silently
    overwritten. Feature snapshots are keyed on ``(customer_id, as_of_date)`` so
    re-submitting the same snapshot is a normal upsert.
    """
    try:
        spec = get_dataset(body.dataset)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    unknown = sorted(key for key in body.row if key not in spec.fields_by_name)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown field(s) for dataset '{spec.key}': {', '.join(unknown)}. "
                f"Valid fields: {', '.join(spec.fields_by_name)}"
            ),
        )
    if not body.row:
        raise HTTPException(status_code=400, detail="No customer fields were supplied.")

    # Identity mapping: the form already submits target field names.
    mapping = {name: name for name in spec.fields_by_name}
    try:
        record, errors = coerce_row(body.row, mapping, spec.key)
    except KeyError as exc:  # unknown dataset key
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if errors:
        # Field-level problems come back as a list so the form can show them
        # per field; nothing is written and no rejection row is created.
        raise HTTPException(status_code=400, detail=errors)

    customer_id = record.get("customer_id")
    if spec.key == DEFAULT_DATASET and customer_id and not body.allow_update:
        existing = await run_in_threadpool(customer_exists, str(customer_id))
        if existing == "deleted":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Customer {customer_id} was deleted. Restore it from My Customers "
                    "instead of re-adding it."
                ),
            )
        if existing == "live":
            raise HTTPException(
                status_code=409,
                detail=f"Customer {customer_id} already exists.",
            )

    try:
        result = await run_in_threadpool(
            load_batch,
            [record],
            [],
            source_type="manual_entry",
            source_name="Add customer form",
            triggered_by=_actor(request),
            dataset=spec.key,
            dry_run=body.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Add customer failed for %s (%s)", customer_id, spec.key)
        raise HTTPException(status_code=500, detail=f"Add customer failed: {exc}") from exc

    logger.info(
        "Add customer %s -> %s: inserted=%d updated=%d dry_run=%s [by %s]",
        customer_id, result["target_table"], result["rows_inserted"],
        result["rows_updated"], result["dry_run"], _actor(request),
    )
    return result


# ═══════════════════════════════════════════════════════════════════
# Core banking pull (ETL Engine)
# ═══════════════════════════════════════════════════════════════════

@router.post("/core-banking/run")
async def run_core_banking(request: Request, body: CoreBankingRunRequest):
    """Pull one core-system dataset and load it into Postgres."""
    try:
        return await run_core_banking_load(
            body.dataset,
            limit=body.limit,
            dry_run=body.dry_run,
            triggered_by=_actor(request),
            as_of_date=body.as_of_date,
        )
    except CoreExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Core banking pull failed for dataset %s", body.dataset)
        raise HTTPException(status_code=500, detail=f"Core banking pull failed: {exc}") from exc
