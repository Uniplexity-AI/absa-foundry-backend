"""ETL Engine job — pull customer data from the core Absa system into Postgres.

The core banking estate lives in the **source** database
(``POSTGRES_*`` / ``etl_validation``); the analytics clean layer lives in the
**target** database (``POSTGRES_TARGET_*`` / ``etl_clean``). This module is the
bridge between the two.

Extraction uses the ETL Engine connector abstraction — ``CoreBankingConnector``
registered for ``SourceType.CORE_BANKING`` in ``etl/connectors/banking`` — which
in turn delegates to the PostgreSQL connector against the core system of record.
If the async connector stack is unavailable, the job degrades to a direct
SQLAlchemy read of the same table and reports which path it used, so an operator
always knows how the rows arrived.

Every mapped row is then normalised against :mod:`etl.ingest.customer_schema`
(the same contract the CSV path uses) and written to ``public.customers_clean``
by :mod:`etl.ingest.loader`, with a compliance row appended to ``etl.etl_audit``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text

from anyio import to_thread

from etl.ingest.customer_schema import coerce_row
from etl.ingest.loader import load_batch
from shared.config.settings import settings
from shared.database.postgres import get_sync_engine

logger = logging.getLogger("etl.ingest.core_banking")

#: Core-banking extracts are always customer-master data, never feature snapshots.
TARGET_DATASET = "customers"


@dataclass(frozen=True)
class CoreDataset:
    """A declarative core-system → ``customers_clean`` extraction contract."""

    key: str
    label: str
    table: str
    description: str
    #: core column → canonical ``CustomerField`` name
    field_map: dict[str, str]
    #: canonical field → literal value applied when the core extract omits it
    defaults: dict[str, Any] = field(default_factory=dict)
    #: documented quirks an operator should know about
    notes: str = ""


CORE_DATASETS: dict[str, CoreDataset] = {
    "customers_core": CoreDataset(
        key="customers_core",
        label="Core Banking — Customer Master (System of Record)",
        table="public.customers_core",
        description=(
            "Customer master extract from the core banking platform. Column names "
            "already mirror customers_clean; values arrive in mixed formats and are "
            "normalised on ingest."
        ),
        field_map={
            "customer_id": "customer_id",
            "full_name": "full_name",
            "date_of_birth": "date_of_birth",
            "gender": "gender",
            "branch_code": "branch_code",
            "customer_since_date": "customer_since_date",
            "kyc_tier": "kyc_tier",
            "nationality": "nationality",
        },
        # The core master has no status column; the lifecycle status is derived
        # from account state downstream, so active is the safe arrival default.
        defaults={"status": "Active"},
        notes=(
            "Dates are mixed ISO / MM-DD-YYYY / DD Mon YYYY and gender is coded "
            "M/F — both are normalised to the customers_clean contract. No status "
            "column: rows land as Active until the account-status feed is mapped."
        ),
    ),
    "customers_crm": CoreDataset(
        key="customers_crm",
        label="Core Banking — CRM Customer Extract",
        table="public.customers_crm",
        description=(
            "Customer extract from the CRM channel system. Uses abbreviated column "
            "names (customerid, fullname, dob, kyctier, nationalitycode)."
        ),
        field_map={
            "customerid": "customer_id",
            "fullname": "full_name",
            "dob": "date_of_birth",
            "gender": "gender",
            "branchcode": "branch_code",
            "kyctier": "kyc_tier",
            "nationalitycode": "nationality",
        },
        defaults={"status": "Active"},
        notes=(
            "No customer_since_date in this extract, so tenure features stay unset "
            "for CRM-sourced customers until the accounts feed is mapped."
        ),
    ),
}


class CoreExtractionError(RuntimeError):
    """Raised when the core system cannot be read at all."""


def describe_datasets() -> list[dict[str, Any]]:
    """Catalogue for the ingest UI (which core feeds can be pulled)."""
    return [
        {
            "key": ds.key,
            "label": ds.label,
            "table": ds.table,
            "description": ds.description,
            "notes": ds.notes,
            "mapped_fields": [
                {"source_column": column, "target_field": target}
                for column, target in ds.field_map.items()
            ],
            "defaults": dict(ds.defaults),
        }
        for ds in CORE_DATASETS.values()
    ]


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _connector_config(ds: CoreDataset, batch_size: int):
    """Build the ETL Engine connector config for one core dataset."""
    from etl.schemas.connector_schemas import ConnectorConfig, SourceType

    return ConnectorConfig(
        source_type=SourceType.CORE_BANKING,
        source_name=ds.label,
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        username=settings.postgres_user,
        password=settings.postgres_password,
        table_name=ds.table,
        batch_size=batch_size,
        extra_params={"underlying_source_type": "postgresql"},
    )


async def _extract_via_connector(ds: CoreDataset, limit: int | None) -> list[dict[str, Any]]:
    """Primary path: extract through the registered CoreBankingConnector."""
    import etl.connectors.banking.connectors  # noqa: F401 — registers CORE_BANKING
    import etl.connectors.database.connectors  # noqa: F401 — registers POSTGRESQL
    from etl.connectors.factory import create_connector

    batch_size = min(limit or 5000, 5000)
    connector = create_connector(_connector_config(ds, batch_size))

    rows: list[dict[str, Any]] = []
    await connector.connect()
    try:
        async for dataset in connector.extract():
            frame = dataset.data
            if frame is None or len(frame) == 0:
                continue
            rows.extend(frame.to_dict(orient="records"))
            if limit is not None and len(rows) >= limit:
                break
    finally:
        await connector.disconnect()

    if limit is not None:
        rows = rows[:limit]
    return rows


def _extract_via_sql(ds: CoreDataset, limit: int | None) -> list[dict[str, Any]]:
    """Fallback path: read the same table with plain SQLAlchemy.

    Used when the async connector stack (asyncpg/pandas) is not installed in the
    running gateway. The extraction mode is reported back to the caller either
    way, so a fallback load is never silently indistinguishable from the
    connector path.
    """
    engine = get_sync_engine()
    statement = f"SELECT * FROM {ds.table}"
    params: dict[str, Any] = {}
    if limit is not None:
        statement += " LIMIT :limit"
        params["limit"] = int(limit)

    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(text(statement), params).mappings().all()]


async def extract_core_rows(
    ds: CoreDataset, limit: int | None = None
) -> tuple[list[dict[str, Any]], str]:
    """Return ``(rows, extraction_mode)`` for one core dataset."""
    try:
        rows = await _extract_via_connector(ds, limit)
        return rows, "CORE_BANKING_CONNECTOR"
    except Exception as exc:  # noqa: BLE001 — fall back rather than fail the pull
        logger.warning(
            "CoreBankingConnector extraction failed for %s (%s); falling back to direct SQL",
            ds.table, exc,
        )

    rows = await to_thread.run_sync(_extract_via_sql, ds, limit)
    return rows, "SQL_DIRECT"


# ---------------------------------------------------------------------------
# Mapping + load
# ---------------------------------------------------------------------------

def map_core_rows(
    rows: list[dict[str, Any]], ds: CoreDataset
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply the dataset's field map and the shared value-formatting contract."""
    mapping = {source: target for source, target in ds.field_map.items()}
    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        record, errors = coerce_row(row, mapping, TARGET_DATASET)

        # Defaults only fill fields the extract did not supply at all.
        for target, value in ds.defaults.items():
            if not record.get(target):
                record[target] = value
                errors = [e for e in errors if target not in e]

        if errors:
            rejects.append({
                "row_number": index,
                "customer_id": record.get("customer_id"),
                "raw_row": row,
                "errors": errors,
            })
        else:
            records.append(record)

    return records, rejects


async def run_core_banking_load(
    dataset: str = "customers_core",
    *,
    limit: int | None = None,
    dry_run: bool = False,
    triggered_by: str = "api",
    as_of_date: date | str | None = None,
) -> dict[str, Any]:
    """Pull one core dataset and load it into ``public.customers_clean``."""
    ds = CORE_DATASETS.get(str(dataset))
    if ds is None:
        raise CoreExtractionError(
            f"Unknown core dataset {dataset!r}. Available: {', '.join(CORE_DATASETS)}"
        )

    started_at = datetime.now(timezone.utc)
    rows, extraction_mode = await extract_core_rows(ds, limit)
    records, rejects = map_core_rows(rows, ds)

    result = await to_thread.run_sync(
        lambda: load_batch(
            records,
            rejects,
            source_type="CORE_BANKING",
            source_name=ds.table,
            triggered_by=triggered_by,
            dataset=TARGET_DATASET,
            started_at=started_at,
            dry_run=dry_run,
            extra_tags={
                "core_dataset": ds.key,
                "extraction_mode": extraction_mode,
                "as_of_date": str(as_of_date) if as_of_date else None,
            },
        )
    )

    result["core_dataset"] = ds.key
    result["core_dataset_label"] = ds.label
    result["source_table"] = ds.table
    result["extraction_mode"] = extraction_mode
    result["rows_extracted"] = len(rows)
    result["notes"] = ds.notes
    return result
