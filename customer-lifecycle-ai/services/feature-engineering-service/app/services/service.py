"""Feature Engineering Service — Business logic for feature computation."""
from __future__ import annotations
from datetime import date

from app.repository.repository import FeatureRepository
from app.pipelines.pipeline import FeaturePipeline
from app.schemas.schemas import ComputeBatchResponse, FeatureSnapshot


class FeatureService:
    """Orchestrates point-in-time feature computation and retrieval."""

    def __init__(self, repository: FeatureRepository | None = None) -> None:
        self._repo = repository or FeatureRepository()

    def compute_batch(self, as_of_date: date | None = None) -> ComputeBatchResponse:
        """Compute all features for all customers (Phase 1 + 4 domain generators)."""
        effective_date = as_of_date or date.today()
        pipeline = FeaturePipeline(self._repo)
        result = pipeline.run(effective_date)

        stages = result.get("stages", {})
        profile = stages.get("profile", {})
        customers_processed = profile.get("profile_base", 0)

        return ComputeBatchResponse(
            as_of_date=effective_date,
            customers_processed=customers_processed,
            rows_upserted=stages.get("phase1", {}).get("rows_upserted", 0),
            duration_seconds=result.get("total_duration_seconds", 0),
            status=result.get("status", "COMPLETED"),
        )

    def get_features(self, customer_id: str, as_of_date: date) -> FeatureSnapshot | None:
        """Fetch a specific feature snapshot. Returns None if not found."""
        row = self._repo.get_features(customer_id, as_of_date)
        return FeatureSnapshot(**row) if row else None

    def get_latest(self, customer_id: str) -> FeatureSnapshot | None:
        """Fetch the most recent feature snapshot."""
        row = self._repo.get_latest(customer_id)
        return FeatureSnapshot(**row) if row else None
