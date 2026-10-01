"""Feature Engineering Service — API Routes."""
from __future__ import annotations
from datetime import date

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks

from app.schemas.schemas import ComputeBatchResponse, FeatureSnapshot
from app.services.service import FeatureService

router = APIRouter(prefix="/features", tags=["features"])
_service = FeatureService()


@router.get("/extract-historical/status")
def get_extraction_status():
    """Get the current progress of the historical ETL extraction."""
    import json
    from pathlib import Path
    progress_file = Path(__file__).resolve().parents[4] / "extraction_progress.json"
    if progress_file.exists():
        try:
            with open(progress_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"status": "idle", "current": 0, "total": 24, "current_date": ""}

@router.post("/extract-historical")
def extract_historical(background_tasks: BackgroundTasks):
    """Trigger the 24-month historical ETL extraction in the background."""
    def run_historical_etl():
        import subprocess
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[4]
        subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", "run_historical_etl.ps1"],
            cwd=str(repo_root),
            timeout=3600
        )
    background_tasks.add_task(run_historical_etl)
    return {"status": "extraction_started"}


@router.post("/compute-batch", response_model=ComputeBatchResponse)
def compute_batch(as_of_date: date | None = Query(default=None, description="Date to compute features as-of (default: today)")) -> ComputeBatchResponse:
    """Compute and upsert features for all customers as of the given date."""
    return _service.compute_batch(as_of_date)


@router.get("/{customer_id}", response_model=FeatureSnapshot)
def get_features(
    customer_id: str,
    as_of_date: date = Query(..., description="Exact date for the feature snapshot"),
) -> FeatureSnapshot:
    """Fetch one customer's feature snapshot for a specific date. 404 if not found."""
    result = _service.get_features(customer_id, as_of_date)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No features for customer '{customer_id}' as of {as_of_date}")
    return result


@router.get("/{customer_id}/latest", response_model=FeatureSnapshot)
def get_latest(customer_id: str) -> FeatureSnapshot:
    """Fetch the most recent feature snapshot for a customer."""
    result = _service.get_latest(customer_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No features found for customer '{customer_id}'")
    return result

