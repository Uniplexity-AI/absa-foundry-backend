"""
Gateway ETL Routes — pipeline run history and data quality dashboard.

FR-OPS-01: ETL Run History table
FR-OPS-02: Data Quality Dashboard
FR-OPS-03: System Health

API Contract (Section 8):
    GET /api/etl/runs?page=1&limit=25&status=

Layer separation:
    Route → ETLService → ETLRepository → AuditRecord (etl.etl_audit)
    Route is thin. All business logic in service. All data access in repository.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.session import get_target_session
from etl.repositories.etl_repository import ETLRepository
from gateway.services.etl_service import ETLService
from gateway.schemas.etl_schemas import ETLDashboardResponse

logger = logging.getLogger("gateway.routes.etl")

router = APIRouter(prefix="/api/etl", tags=["ETL Operations"])


# ===========================================================================
# Dependency Injection
# ===========================================================================

def get_etl_service(
    session: AsyncSession = Depends(get_target_session),
) -> ETLService:
    """FastAPI dependency: construct ETLService with repository."""
    repository = ETLRepository(session)
    return ETLService(repository)


# ===========================================================================
# GET /api/etl/runs
# ===========================================================================

@router.get("/runs", response_model=ETLDashboardResponse)
async def get_etl_runs(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(25, ge=1, le=100, description="Items per page"),
    status: str | None = Query(None, description="Filter: COMPLETED, FAILED"),
    service: ETLService = Depends(get_etl_service),
):
    """
    Return paginated ETL run history with aggregated dashboard KPIs.

    FR-OPS-01: Execution history table
    FR-OPS-02: Quality trend (last 10 completed runs)
    FR-OPS-03: Operational status panel
    """
    try:
        return await service.get_dashboard(page=page, limit=limit, status=status)
    except Exception:
        logger.exception("Failed to fetch ETL dashboard")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query ETL pipeline data",
        )
