"""
ETL Transformation Service - Orchestrates the transformation pipeline.

Executes transforms in order:
FieldMapper → ValueStandardizer → DataEnricher

Generates a TransformationReport with complete statistics.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from etl.schemas.transformation_schemas import TransformationConfig, TransformationReport
from etl.transformation.enrichers.data_enricher import DataEnricher, EnrichmentLookupProvider
from etl.transformation.interfaces import BaseTransform
from etl.transformation.mappers.field_mapper import FieldMapper
from etl.transformation.standardizers.value_standardizer import ValueStandardizer


class TransformationService:
    """Orchestrates the complete transformation pipeline.

    Applies transforms in a fixed, configurable order:
    1. FieldMapper — column renaming, type casting, column management
    2. ValueStandardizer — categorical value normalization
    3. DataEnricher — lookups, derived fields, dates, null filling

    All transforms are idempotent — running twice produces the same result.
    """

    def __init__(
        self,
        config: TransformationConfig | None = None,
        lookup_provider: EnrichmentLookupProvider | None = None,
    ) -> None:
        """Initialize the transformation service.

        Args:
            config: Transformation configuration. Uses defaults if None.
            lookup_provider: Provider for enrichment lookups.
        """
        self.config = config or TransformationConfig()
        self._lookup = lookup_provider
        self._transforms: list[BaseTransform] = []
        self._build_transform_chain()

    async def transform(
        self, df: pd.DataFrame, batch_id: str
    ) -> tuple[pd.DataFrame, TransformationReport]:
        """Execute the full transformation pipeline.

        Args:
            df: Validated DataFrame ready for transformation.
            batch_id: Batch identifier for the report.

        Returns:
            Tuple of (transformed DataFrame, TransformationReport).
        """
        start_time = time.monotonic()

        report = TransformationReport(
            batch_id=batch_id,
            input_rows=len(df),
            input_columns=len(df.columns),
            started_at=datetime.now(timezone.utc),
        )

        result = df.copy()

        for transform in self._transforms:
            transform.reset_stats()
            result = await transform.apply(result)

            # Collect stats
            if transform.transform_name == "Field Mapping":
                report.fields_mapped = transform.stats.get("fields_mapped", 0)
                report.columns_dropped = transform.stats.get("columns_dropped", 0)
            elif transform.transform_name == "Value Standardization":
                report.values_standardized = transform.stats.get("values_standardized", 0)
            elif transform.transform_name == "Data Enrichment":
                report.enrichments_applied = transform.stats.get("enrichments_applied", 0)
                report.fields_derived = transform.stats.get("fields_derived", 0)
                report.dates_normalized = transform.stats.get("dates_normalized", 0)
                report.nulls_filled = transform.stats.get("nulls_filled", 0)

        report.output_rows = len(result)
        report.output_columns = len(result.columns)
        report.completed_at = datetime.now(timezone.utc)
        report.duration_seconds = time.monotonic() - start_time

        return result, report

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_transform_chain(self) -> None:
        """Build the ordered chain of transforms."""
        self._transforms = [
            FieldMapper(self.config),
            ValueStandardizer(self.config),
            DataEnricher(self.config, self._lookup),
        ]
