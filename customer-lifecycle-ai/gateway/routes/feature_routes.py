"""
Gateway Feature Routes — proxy to the Feature Engineering Service.

The feature service runs as a standalone FastAPI app (port 8002) but
is imported directly here for the PoC monolith deployment.

All routes require DATA_SCIENTIST or ADMIN role (RBAC enforced).

FR-DS-03: Feature drift monitoring (future)
FR-DS-04: Prediction log browser (future)
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status

from gateway.dependencies import require_auth
from shared.auth.models import UserContext

# ── Import FeatureService from the standalone service ──
_FEATURE_SVC_ROOT = (
    Path(__file__).resolve().parent.parent.parent
    / "services" / "feature-engineering-service"
)
if str(_FEATURE_SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(_FEATURE_SVC_ROOT))

from app.services.service import FeatureService  # noqa: E402
from app.schemas.schemas import FeatureSnapshot, ComputeBatchResponse, GapActivityResponse  # noqa: E402

router = APIRouter(prefix="/features", tags=["Feature Engineering"])
_service = FeatureService()


# ===========================================================================
# POST /features/compute-batch
# ===========================================================================

@router.post("/compute-batch", response_model=ComputeBatchResponse)
def compute_batch(
    as_of_date: date | None = Query(
        default=None,
        description="Date to compute features as-of (default: today)",
    ),
    user: UserContext = Depends(require_auth),
) -> ComputeBatchResponse:
    """Compute and upsert features for all customers as of the given date.

    Requires: ADMIN or DATA_SCIENTIST role.
    """
    try:
        return _service.compute_batch(as_of_date)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feature computation failed",
        )


# ===========================================================================
# GET /features/{customer_id}
# ===========================================================================

@router.get("/{customer_id}", response_model=FeatureSnapshot)
def get_features(
    customer_id: str,
    as_of_date: date = Query(
        ...,
        description="Exact date for the feature snapshot",
    ),
    user: UserContext = Depends(require_auth),
) -> FeatureSnapshot:
    """Fetch one customer's feature snapshot for a specific date.

    Requires: ADMIN or DATA_SCIENTIST role.
    """
    result = _service.get_features(customer_id, as_of_date)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No features for customer '{customer_id}' as of {as_of_date}",
        )
    return result



@router.get("/{customer_id}/nearest", response_model=FeatureSnapshot)
def get_nearest(
    customer_id: str,
    as_of_date: date = Query(..., description="Date to find snapshot before or on"),
    user: UserContext = Depends(require_auth),
) -> FeatureSnapshot:
    result = _service.get_nearest(customer_id, as_of_date)
    if result is None:
        raise HTTPException(status_code=404, detail="No snapshot found before date")
    return result

@router.get("/{customer_id}/gap-activity", response_model=GapActivityResponse)
def get_gap_activity(
    customer_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    user: UserContext = Depends(require_auth),
) -> GapActivityResponse:
    result = _service.get_gap_activity(customer_id, start_date, end_date)
    return result


# ===========================================================================
# GET /features/{customer_id}/latest
# ===========================================================================

@router.get("/{customer_id}/latest", response_model=FeatureSnapshot)
def get_latest(
    customer_id: str,
    user: UserContext = Depends(require_auth),
) -> FeatureSnapshot:
    """Fetch the most recent feature snapshot for a customer.

    Requires: ADMIN or DATA_SCIENTIST role.
    """
    result = _service.get_latest(customer_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No features found for customer '{customer_id}'",
        )
    return result
