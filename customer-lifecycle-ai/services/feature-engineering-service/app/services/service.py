"""Feature Engineering Service — Business logic for feature computation."""
from __future__ import annotations
from datetime import date

from app.repository.repository import FeatureRepository
from app.schemas.schemas import ComputeBatchResponse, FeatureSnapshot


class FeatureService:
    """Orchestrates point-in-time feature computation and retrieval."""

    def __init__(self, repository: FeatureRepository | None = None) -> None:
        self._repo = repository or FeatureRepository()

    def compute_batch(self, as_of_date: date | None = None) -> ComputeBatchResponse:
        """Compute features for all customers as of a date (default: today)."""
        effective_date = as_of_date or date.today()
        result = self._repo.compute_batch(effective_date)
        return ComputeBatchResponse(**result)

    def get_features(self, customer_id: str, as_of_date: date) -> FeatureSnapshot | None:
        """Fetch a specific feature snapshot. Returns None if not found."""
        row = self._repo.get_features(customer_id, as_of_date)
        return FeatureSnapshot(**row) if row else None

    def get_latest(self, customer_id: str) -> FeatureSnapshot | None:
        """Fetch the most recent feature snapshot."""
        row = self._repo.get_latest(customer_id)
        return FeatureSnapshot(**row) if row else None
