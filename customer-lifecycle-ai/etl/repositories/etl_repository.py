"""
ETL Repository — async data access for pipeline audit records.

Uses raw SQL via sqlalchemy.text() because the ORM model (AuditRecord)
declares columns not present in the table created by run_etl.py (raw psycopg2).
This is intentional — run_etl.py owns the etl.etl_audit table schema via
DDL executed at pipeline start.  The ORM model and the table will converge
in a future migration that adds updated_at to etl.etl_audit.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ETLRepository:
    """Async data access for ETL audit records (raw SQL)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Aggregated KPIs (today)
    # ------------------------------------------------------------------

    async def get_todays_kpis(self) -> dict:
        stmt = text("""
            SELECT
                COUNT(*)                                                    AS total,
                COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END), 0) AS successful,
                COALESCE(SUM(CASE WHEN status IN ('FAILED','ERROR') THEN 1 ELSE 0 END), 0) AS failed,
                0                                                          AS running
            FROM etl.etl_audit
        """)
        result = await self._session.execute(stmt)
        row = result.fetchone()
        total = row.total
        successful = row.successful
        failed = row.failed

        avg_q = await self._session.scalar(text("""
            SELECT COALESCE(AVG(quality_score), 0)
            FROM etl.etl_audit
        """))

        avg_d = await self._session.scalar(text("""
            SELECT COALESCE(AVG(duration_seconds), 0)
            FROM etl.etl_audit
            WHERE duration_seconds IS NOT NULL
        """))

        return {
            "todays_runs": total,
            "successful_runs": successful,
            "failed_runs": failed,
            "running_runs": 0,
            "avg_quality": round(float(avg_q or 0), 1),
            "avg_duration_seconds": float(avg_d or 0),
            "success_rate": round(successful / total * 100, 1) if total > 0 else 0.0,
        }

    # ------------------------------------------------------------------
    # Status Panel
    # ------------------------------------------------------------------

    async def get_status_panel(self) -> dict:
        last = await self._session.execute(text("""
            SELECT audit_id, pipeline_name, completed_at, duration_seconds,
                   rows_loaded, quality_score
            FROM etl.etl_audit
            WHERE status = 'COMPLETED'
            ORDER BY completed_at DESC LIMIT 1
        """))
        lc = last.fetchone()

        failed = await self._session.execute(text("""
            SELECT audit_id, rows_rejected, quality_score
            FROM etl.etl_audit
            WHERE status IN ('FAILED','ERROR')
            ORDER BY completed_at DESC LIMIT 1
        """))
        lf = failed.fetchone()

        latest = await self._session.execute(text("""
            SELECT rows_received, quality_score
            FROM etl.etl_audit
            ORDER BY completed_at DESC LIMIT 1
        """))
        lt = latest.fetchone()

        return {
            "current_status": "Operational",
            "current_status_since": lc.completed_at.isoformat() if lc and lc.completed_at else None,
            "current_pipeline": lc.pipeline_name if lc else None,
            "last_successful_run": lc.audit_id if lc else None,
            "last_successful_duration": float(lc.duration_seconds) if lc and lc.duration_seconds else None,
            "last_successful_rows": lc.rows_loaded if lc else None,
            "last_successful_quality": round(float(lc.quality_score), 1) if lc and lc.quality_score else None,
            "latest_quality": round(float(lt.quality_score), 1) if lt and lt.quality_score else None,
            "latest_quality_rows": lt.rows_received if lt else None,
            "sla_threshold": 95.0,
            "last_failure_run": lf.audit_id if lf else None,
            "last_failure_detail": (
                f"{lf.rows_rejected:,} rejected · Quality {lf.quality_score:.1f}%"
                if lf and lf.rows_rejected and float(lf.quality_score or 0) < 95.0
                else None
            ),
        }

    # ------------------------------------------------------------------
    # Quality Trend (last 10)
    # ------------------------------------------------------------------

    async def get_quality_trend(self, limit: int = 10) -> list[dict]:
        result = await self._session.execute(text("""
            SELECT completed_at, quality_score, rows_received, rows_rejected
            FROM etl.etl_audit
            WHERE quality_score IS NOT NULL
            ORDER BY completed_at DESC
            LIMIT :limit
        """), {"limit": limit})
        rows = list(result.fetchall())
        rows.reverse()

        return [
            {
                "label": (
                    r.completed_at.strftime("%H:%M")
                    if r.completed_at
                    else f"Run {i + 1}"
                ),
                "value": round(float(r.quality_score), 1),
                "rows": r.rows_received or 0,
                "rejected": r.rows_rejected or 0,
                "failed": float(r.quality_score or 100) < 95.0,
            }
            for i, r in enumerate(rows)
        ]

    # ------------------------------------------------------------------
    # Paginated Runs
    # ------------------------------------------------------------------

    async def get_runs(
        self,
        page: int = 1,
        limit: int = 25,
        status: str | None = None,
    ) -> tuple[list[dict], int]:
        where = ""
        params = {}
        if status:
            where = "WHERE status = :status"
            params["status"] = status.upper()

        # Total count
        count = await self._session.scalar(
            text(f"SELECT COUNT(*) FROM etl.etl_audit {where}"), params,
        )
        total = count or 0

        # Paginated results
        offset = (page - 1) * limit
        result = await self._session.execute(
            text(f"""
                SELECT id, audit_id, batch_id, status, duration_seconds,
                       rows_received, rows_valid, rows_loaded, rows_rejected, quality_score
                FROM etl.etl_audit
                {where}
                ORDER BY completed_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {**params, "limit": limit, "offset": offset},
        )
        runs = [dict(r._mapping) for r in result.fetchall()]

        return runs, total

    # ------------------------------------------------------------------
    # Single Run Detail
    # ------------------------------------------------------------------

    async def get_run_by_id(self, run_id: str) -> dict | None:
        """Fetch full audit record for a single run by audit_id or batch_id."""
        result = await self._session.execute(
            text("""
                SELECT id, audit_id, batch_id, status, pipeline_name,
                       triggered_by, started_at, completed_at, duration_seconds,
                       rows_received, rows_valid, rows_loaded, rows_rejected,
                       rows_skipped, duplicates_detected, warnings_count,
                       errors_count, quality_score, error_message,
                       source_type, source_name
                FROM etl.etl_audit
                WHERE audit_id = :run_id OR batch_id = :run_id
                ORDER BY completed_at DESC
                LIMIT 1
            """),
            {"run_id": run_id},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_validation_for_batch(self, batch_id: str) -> dict | None:
        """Fetch validation run summary for a given batch_id."""
        result = await self._session.execute(
            text("""
                SELECT run_id, status, total_records, valid_records,
                       invalid_records, duplicate_records, total_errors,
                       total_warnings, quality_score,
                       error_by_category, error_by_rule
                FROM etl.etl_validation_run
                WHERE batch_id = :batch_id
                ORDER BY completed_at DESC
                LIMIT 1
            """),
            {"batch_id": batch_id},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None
