"""
ETL Transformation Interfaces - Abstract base for all transforms.

Each transform takes a DataFrame and returns a transformed DataFrame.
All transforms must be idempotent and composable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from etl.schemas.transformation_schemas import TransformationConfig


class BaseTransform(ABC):
    """Abstract base class for all data transformation steps.

    Every transform is a self-contained, idempotent operation
    that takes a DataFrame and returns a transformed DataFrame.
    """

    def __init__(self, config: TransformationConfig) -> None:
        self.config = config
        self._stats: dict[str, int] = {}

    @abstractmethod
    async def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply the transformation to a DataFrame.

        Args:
            df: Input DataFrame.

        Returns:
            Transformed DataFrame (may be the same or a new instance).
        """
        ...

    @property
    @abstractmethod
    def transform_name(self) -> str:
        """Human-readable name of this transform."""
        ...

    @property
    def stats(self) -> dict[str, int]:
        """Statistics about the last transform execution."""
        return dict(self._stats)

    def reset_stats(self) -> None:
        """Reset transformation statistics."""
        self._stats.clear()
