"""CSV onboarding for customer data (My Customers page → Postgres).

Flow
----
1. ``POST /api/v1/ingest/csv/preview`` stores the upload under
   ``datasets/landing/ingest/`` and returns the detected columns, sample rows,
   an auto-proposed column→field mapping and the format contract for each
   target field of the selected dataset.
2. The operator corrects the mapping in the UI (and may switch dataset, which
   re-previewes the already-staged file without re-uploading).
3. ``POST /api/v1/ingest/csv/load`` replays the stored file through
   :mod:`etl.ingest.loader` and writes it to the dataset's target table.

Only the stdlib ``csv`` module is used, so the gateway inherits no extra
runtime dependency from this path.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from etl.ingest.customer_schema import (
    DEFAULT_DATASET,
    FieldValueError,
    get_dataset,
    auto_map,
    coerce_row,
    coerce_value,
    validate_mapping,
)
from etl.ingest.loader import load_batch

logger = logging.getLogger("etl.ingest.csv")

_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB — plenty for a customer extract

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = _PROJECT_ROOT / "datasets" / "landing" / "ingest"


class UploadError(ValueError):
    """Raised for an unusable upload (missing, oversized, unparseable)."""


@dataclass(frozen=True)
class StoredUpload:
    upload_id: str
    filename: str
    path: Path
    size_bytes: int


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def save_upload(filename: str, content: bytes) -> StoredUpload:
    """Persist an uploaded CSV in the landing zone and return its handle."""
    if not content:
        raise UploadError("The uploaded file is empty.")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise UploadError(
            f"File is {len(content) / 1_048_576:.1f} MB — the limit is {_MAX_UPLOAD_BYTES // 1_048_576} MB."
        )

    safe_name = Path(str(filename or "upload.csv")).name
    upload_id = str(uuid.uuid4())
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{upload_id}.csv"
    path.write_bytes(content)

    logger.info("Stored upload %s (%s, %d bytes)", upload_id, safe_name, len(content))
    return StoredUpload(upload_id=upload_id, filename=safe_name, path=path, size_bytes=len(content))


def resolve_upload(upload_id: str) -> Path:
    """Map an upload id back to its landing-zone path (traversal-safe)."""
    if not _UPLOAD_ID_RE.match(str(upload_id or "")):
        raise UploadError("Unknown upload id — re-upload the file and try again.")
    path = UPLOAD_DIR / f"{upload_id}.csv"
    if not path.exists():
        raise UploadError("The staged upload has expired or was removed — please re-upload.")
    return path


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8 (with replacements)"


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;|\t").delimiter
    except csv.Error:
        return ","


def iter_rows(path: Path, *, limit: int | None = None) -> Iterator[dict[str, str]]:
    """Yield rows as ``{header: value}`` dicts."""
    raw = path.read_bytes()
    text, _encoding = _decode(raw)
    delimiter = _sniff_delimiter(text[:4096])

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise UploadError("The file has no header row.")

    for index, row in enumerate(reader, start=1):
        if limit is not None and index > limit:
            return
        yield {str(k).strip(): ("" if v is None else str(v).strip()) for k, v in row.items() if k is not None}


def read_upload(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read the whole file (headers + rows)."""
    raw = path.read_bytes()
    text, _encoding = _decode(raw)
    delimiter = _sniff_delimiter(text[:4096])

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise UploadError("The file has no header row.")

    columns = [str(c).strip() for c in reader.fieldnames]
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append({str(k).strip(): ("" if v is None else str(v).strip()) for k, v in row.items() if k is not None})
    return columns, rows


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def build_preview(
    path: Path,
    *,
    filename: str,
    sample_size: int = 5,
    dataset: str | None = None,
) -> dict[str, Any]:
    """Column detection + proposed mapping + per-column format checks."""
    raw = path.read_bytes()
    text, encoding = _decode(raw)
    delimiter = _sniff_delimiter(text[:4096])

    spec = get_dataset(dataset)
    fields_by_name = spec.fields_by_name

    sample_rows: list[dict[str, str]] = []
    columns: list[str] = []
    row_count = 0

    for index, row in enumerate(iter_rows(path), start=1):
        if index == 1:
            columns = list(row.keys())
        if len(sample_rows) < sample_size:
            sample_rows.append(row)
        row_count += 1

    if not columns:
        raise UploadError("The file has no header row.")

    mapping = auto_map(columns, dataset)
    mapping_errors = validate_mapping(mapping, dataset)

    # Per-column sample validation, so the operator sees format problems before loading.
    column_checks: list[dict[str, Any]] = []
    for column in columns:
        target = mapping.get(column)
        field_spec = fields_by_name.get(target) if target else None
        issues: list[str] = []
        valid_samples = 0

        if field_spec is not None:
            for row in sample_rows:
                try:
                    coerce_value(field_spec, row.get(column))
                    valid_samples += 1
                except FieldValueError as exc:
                    issues.append(str(exc))

        column_checks.append({
            "source_column": column,
            "target_field": target,
            "target_label": field_spec.label if field_spec else None,
            "expected_format": field_spec.format if field_spec else None,
            "required": bool(field_spec.required) if field_spec else False,
            "sample_value": sample_rows[0].get(column) if sample_rows else None,
            "sample_valid": valid_samples,
            "sample_checked": len(sample_rows) if field_spec else 0,
            "issues": issues[:3],
        })

    return {
        "upload_id": path.stem,
        "filename": filename,
        "dataset": spec.key,
        "dataset_label": spec.label,
        "target_table": spec.table,
        "key_columns": list(spec.key_columns),
        "size_bytes": len(raw),
        "encoding": encoding,
        "delimiter": delimiter,
        "row_count": row_count,
        "columns": columns,
        "sample_rows": sample_rows,
        "mapping": mapping,
        "column_checks": column_checks,
        "mapping_errors": mapping_errors,
        "required_fields": [
            {"name": f.name, "label": f.label, "format": f.format, "example": f.example}
            for f in spec.fields if f.required
        ],
        "unmapped_required": [
            f.name for f in spec.fields
            if f.required and f.name not in {t for t in mapping.values() if t}
        ],
        "field_formats": {f.name: f.describe() for f in spec.fields},
    }


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_upload(
    path: Path,
    mapping: dict[str, str | None],
    *,
    filename: str = "",
    triggered_by: str = "api",
    dataset: str | None = None,
    dry_run: bool = False,
    row_limit: int | None = None,
) -> dict[str, Any]:
    """Validate every row against ``mapping`` and load the valid ones."""
    started_at = datetime.now(timezone.utc)
    spec = get_dataset(dataset)

    errors = validate_mapping(mapping, dataset)
    if errors:
        raise UploadError(" ".join(errors))

    columns, rows = read_upload(path)
    if not columns:
        raise UploadError("The file has no header row.")

    unknown = [c for c in mapping if c not in columns]
    if unknown:
        raise UploadError(
            f"Mapping references column(s) not present in the file: {', '.join(unknown)}"
        )

    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        if row_limit is not None and index > row_limit:
            break
        record, row_errors = coerce_row(row, mapping, dataset)
        if row_errors:
            rejects.append({
                "row_number": index,
                "customer_id": record.get("customer_id"),
                "raw_row": row,
                "errors": row_errors,
            })
        else:
            records.append(record)

    return load_batch(
        records,
        rejects,
        source_type="CSV",
        source_name=filename or path.name,
        triggered_by=triggered_by,
        dataset=spec.key,
        started_at=started_at,
        dry_run=dry_run,
        extra_tags={
            "upload_id": path.stem,
            "file_size_bytes": path.stat().st_size,
            "dataset": spec.key,
            "target_table": spec.table,
        },
    )
