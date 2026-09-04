"""
Gateway ETL Routes — pipeline run history, config management, and trigger.

FR-OPS-01: ETL Run History table
FR-OPS-02: Data Quality Dashboard
FR-OPS-03: System Health
FR-CONFIG: Extraction spec CRUD + pipeline trigger
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.session import get_target_session
from etl.repositories.etl_repository import ETLRepository
from gateway.services.etl_service import ETLService
from gateway.schemas.etl_schemas import ETLDashboardResponse, ETLRunDetailResponse, RunDetail, ValidationDetail

logger = logging.getLogger("gateway.routes.etl")

router = APIRouter(prefix="/api/etl", tags=["ETL Operations"])

# Paths
_SPECS_DIR = Path(__file__).resolve().parent.parent.parent / "etl" / "config" / "extraction_specs"
_RUN_ETL = Path(__file__).resolve().parent.parent.parent / "run_etl.py"
_LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

_LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════
# Config Schemas
# ═══════════════════════════════════════════════════════════════════

class ConfigSummary(BaseModel):
    name: str
    description: str = ""
    status: str = "ok"       # "ok" | "warn"
    last_modified: str | None = None
    size_bytes: int = 0


class ConfigContent(BaseModel):
    name: str
    content: str
    last_modified: str | None = None


class ConfigSaveRequest(BaseModel):
    content: str


class TriggerRequest(BaseModel):
    config_name: str
    dry_run: bool = False


class TriggerResponse(BaseModel):
    status: str              # "triggered" | "error"
    config_name: str
    message: str
    triggered_at: str


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _validate_config_status(content: str) -> str:
    """Lightweight YAML check: has name: and source: → 'ok', else 'warn'."""
    try:
        has_name = bool(re.search(r'^name:\s*\S', content, re.MULTILINE))
        has_source = bool(re.search(r'^source:', content, re.MULTILINE))
        return "ok" if (has_name and has_source) else "warn"
    except Exception:
        return "warn"


def _list_configs() -> list[dict]:
    """List all YAML configs in extraction_specs/ with status check."""
    if not _SPECS_DIR.exists():
        return []
    configs = []
    for f in sorted(_SPECS_DIR.glob("*.yaml")):
        stat = f.stat()
        content = f.read_text(encoding="utf-8", errors="replace")
        desc = ""
        try:
            parsed = yaml.safe_load(content)
            desc = parsed.get("description", "") if isinstance(parsed, dict) else ""
        except Exception:
            pass
        configs.append({
            "name": f.name,
            "description": desc,
            "status": _validate_config_status(content),
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size_bytes": stat.st_size,
        })
    return configs


def _read_config(name: str) -> dict | None:
    """Read a config file's raw content."""
    _check_name(name)
    path = _SPECS_DIR / name
    if not path.exists():
        return None
    stat = path.stat()
    return {
        "name": name,
        "content": path.read_text(encoding="utf-8", errors="replace"),
        "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def _write_config(name: str, content: str) -> bool:
    """Write/update a config file."""
    _check_name(name)
    _SPECS_DIR.mkdir(parents=True, exist_ok=True)
    (_SPECS_DIR / name).write_text(content)
    return True


def _delete_config(name: str) -> bool:
    """Delete a config file."""
    _check_name(name)
    path = _SPECS_DIR / name
    if not path.exists():
        return False
    path.unlink()
    return True


def _check_name(name: str) -> None:
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid config name")


# ═══════════════════════════════════════════════════════════════════
# Config CRUD
# ═══════════════════════════════════════════════════════════════════

@router.get("/configs", response_model=list[ConfigSummary])
async def list_configs():
    return _list_configs()


@router.get("/configs/{name}", response_model=ConfigContent)
async def get_config(name: str):
    cfg = _read_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Config '{name}' not found")
    return cfg


@router.put("/configs/{name}", response_model=ConfigContent)
async def save_config(name: str, body: ConfigSaveRequest):
    if not _write_config(name, body.content):
        raise HTTPException(status_code=400, detail="Failed to write config")
    cfg = _read_config(name)
    return cfg or {"name": name, "content": body.content, "last_modified": None}


@router.post("/configs", response_model=ConfigContent)
async def create_config(body: ConfigSaveRequest):
    # Extract name from YAML content
    try:
        parsed = yaml.safe_load(body.content)
        name = parsed.get("name", "") if isinstance(parsed, dict) else ""
    except Exception:
        name = ""
    if not name:
        name = f"config_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not name.endswith(".yaml"):
        name = f"{name}.yaml"
    if not _write_config(name, body.content):
        raise HTTPException(status_code=400, detail="Failed to create config")
    cfg = _read_config(name)
    return cfg or {"name": name, "content": body.content, "last_modified": None}


@router.delete("/configs/{name}")
async def delete_config(name: str):
    if not _delete_config(name):
        raise HTTPException(status_code=404, detail=f"Config '{name}' not found")
    return {"status": "deleted", "name": name}


# ═══════════════════════════════════════════════════════════════════
# Pipeline Trigger
# ═══════════════════════════════════════════════════════════════════

@router.post("/trigger", response_model=TriggerResponse)
async def trigger_pipeline(body: TriggerRequest):
    config_path = _SPECS_DIR / body.config_name
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config '{body.config_name}' not found")

    triggered_at = datetime.now().isoformat()
    try:
        log_name = f"etl_trigger_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{body.config_name.replace('.yaml','')}.log"
        log_path = _LOGS_DIR / log_name
        with open(log_path, "w") as log_file:
            cmd = [sys.executable, str(_RUN_ETL), "--extraction-spec", str(config_path)]
            if body.dry_run:
                cmd.append("--dry-run")
            subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(_RUN_ETL.parent))
        return TriggerResponse(
            status="triggered", config_name=body.config_name,
            message=f"Pipeline started — logs: logs/{log_name}",
            triggered_at=triggered_at,
        )
    except Exception as e:
        logger.exception("Failed to trigger pipeline")
        raise HTTPException(status_code=500, detail=f"Failed to start pipeline: {str(e)}")


# ═══════════════════════════════════════════════════════════════════
# Existing: GET /api/etl/runs
# ═══════════════════════════════════════════════════════════════════

def get_etl_service(
    session: AsyncSession = Depends(get_target_session),
) -> ETLService:
    repository = ETLRepository(session)
    return ETLService(repository)


@router.get("/runs", response_model=ETLDashboardResponse)
async def get_etl_runs(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(25, ge=1, le=100, description="Items per page"),
    status_filter: str | None = Query(None, alias="status", description="Filter: COMPLETED, FAILED"),
    service: ETLService = Depends(get_etl_service),
):
    try:
        return await service.get_dashboard(page=page, limit=limit, status=status_filter)
    except Exception:
        logger.exception("Failed to fetch ETL dashboard")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query ETL pipeline data",
        )


# ═══════════════════════════════════════════════════════════════════
# GET /api/etl/runs/{runId} — Batch Detail
# ═══════════════════════════════════════════════════════════════════

def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def _format_number(n: int | None) -> str:
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


@router.get("/runs/{run_id}", response_model=ETLRunDetailResponse)
async def get_run_detail(
    run_id: str,
    session: AsyncSession = Depends(get_target_session),
):
    repo = ETLRepository(session)
    row = await repo.get_run_by_id(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    # Validation data — may not exist, handle gracefully
    batch_id = row.get("batch_id")
    val_row = None
    if batch_id:
        try:
            val_row = await repo.get_validation_for_batch(batch_id)
        except Exception:
            logger.warning("Validation table not available for batch %s", batch_id)

    duration_s = row.get("duration_seconds")
    run_detail = RunDetail(
        id=row["id"],
        runId=row["audit_id"],
        batchId=row.get("batch_id"),
        status=row.get("status", "UNKNOWN"),
        pipelineName=row.get("pipeline_name"),
        triggeredBy=row.get("triggered_by") or "system",
        startedAt=row["started_at"].isoformat() if row.get("started_at") else None,
        completedAt=row["completed_at"].isoformat() if row.get("completed_at") else None,
        durationSeconds=float(duration_s) if duration_s else None,
        duration=_format_duration(duration_s),
        rowsReceived=row.get("rows_received") or 0,
        rowsValid=row.get("rows_valid") or 0,
        rowsLoaded=row.get("rows_loaded") or 0,
        rowsRejected=row.get("rows_rejected") or 0,
        rowsSkipped=row.get("rows_skipped") or 0,
        duplicatesDetected=row.get("duplicates_detected") or 0,
        warningsCount=row.get("warnings_count") or 0,
        errorsCount=row.get("errors_count") or 0,
        qualityScore=round(float(row["quality_score"]), 1) if row.get("quality_score") else None,
        errorMessage=row.get("error_message"),
        sourceType=row.get("source_type"),
        sourceName=row.get("source_name"),
    )

    validation_detail = None
    if val_row:
        validation_detail = ValidationDetail(
            validationRunId=val_row.get("run_id"),
            status=val_row.get("status"),
            totalRecords=val_row.get("total_records") or 0,
            validRecords=val_row.get("valid_records") or 0,
            invalidRecords=val_row.get("invalid_records") or 0,
            duplicateRecords=val_row.get("duplicate_records") or 0,
            totalErrors=val_row.get("total_errors") or 0,
            totalWarnings=val_row.get("total_warnings") or 0,
            qualityScore=round(float(val_row["quality_score"]), 1) if val_row.get("quality_score") else None,
            errorByCategory=val_row.get("error_by_category"),
            errorByRule=val_row.get("error_by_rule"),
        )

    return ETLRunDetailResponse(run=run_detail, validation=validation_detail)
