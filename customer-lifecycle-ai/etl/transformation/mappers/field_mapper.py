"""
Field Mapper - Maps source columns to target columns.

Handles column renaming, type casting, default values, and
dropping unmapped columns per TransformationConfig.
"""

from __future__ import annotations

import pandas as pd

from etl.schemas.transformation_schemas import TransformationConfig
from etl.transformation.interfaces import BaseTransform


class FieldMapper(BaseTransform):
    """Maps source columns to target columns based on configuration.

    For each FieldMapping in config:
    1. Renames source_field → target_field
    2. Casts to data_type if specified
    3. Fills with default_value if source is missing/null
    """

    @property
    def transform_name(self) -> str:
        return "Field Mapping"

    async def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply field mappings to the DataFrame.

        Args:
            df: Source DataFrame.

        Returns:
            DataFrame with mapped columns.
        """
        self.reset_stats()

        if not self.config.field_mappings:
            return df

        result = df.copy()
        mapped_count = 0

        for mapping in self.config.field_mappings:
            if mapping.source_field in result.columns:
                # Rename to target
                if mapping.source_field != mapping.target_field:
                    result = result.rename(
                        columns={mapping.source_field: mapping.target_field}
                    )
                mapped_count += 1

                # Type cast
                if mapping.data_type:
                    result[mapping.target_field] = self._cast_column(
                        result[mapping.target_field], mapping.data_type
                    )

            elif mapping.required:
                # Source missing but required — create with default
                result[mapping.target_field] = mapping.default_value
                mapped_count += 1

        # Type casts for fields not in mappings
        for field, dtype in self.config.type_casts.items():
            if field in result.columns:
                result[field] = self._cast_column(result[field], dtype)

        # Drop unwanted columns
        if self.config.drop_columns:
            drop = [c for c in self.config.drop_columns if c in result.columns]
            result = result.drop(columns=drop)

        # Reorder columns if specified
        if self.config.reorder_columns:
            available = [c for c in self.config.reorder_columns if c in result.columns]
            remaining = [c for c in result.columns if c not in available]
            result = result[available + remaining]

        self._stats["fields_mapped"] = mapped_count
        self._stats["columns_dropped"] = len(
            [c for c in self.config.drop_columns if c in df.columns]
        )
        return result

    @staticmethod
    def _cast_column(series: pd.Series, dtype: str) -> pd.Series:
        """Cast a pandas Series to the target type.

        Args:
            series: Column to cast.
            dtype: Target type: str, int, float, bool, datetime.

        Returns:
            Cast Series.
        """
        dtype_map = {
            "str": "string",
            "int": "Int64",
            "float": "float64",
            "bool": "boolean",
            "datetime": "datetime64[ns]",
        }
        target = dtype_map.get(dtype, dtype)
        try:
            if dtype == "datetime":
                return pd.to_datetime(series, errors="coerce")
            return series.astype(target)
        except (ValueError, TypeError):
            return series
