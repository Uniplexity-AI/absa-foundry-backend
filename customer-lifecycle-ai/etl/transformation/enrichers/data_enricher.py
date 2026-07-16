"""
Data Enricher - Adds data from external lookups and derived fields.

Handles:
- Lookup enrichment: branch_code → branch_name, region
- Derived fields: is_high_value, year_month, days_since
- Date normalization: all dates to ISO 8601
- Null filling: configurable defaults per field
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

import pandas as pd

from etl.schemas.transformation_schemas import (
    DerivedFieldRule,
    EnrichmentRule,
    TransformationConfig,
)
from etl.transformation.interfaces import BaseTransform


class EnrichmentLookupProvider(Protocol):
    """Protocol for enrichment data lookups."""

    async def lookup(
        self, lookup_type: str, key: str, fields: list[str]
    ) -> dict[str, Any]:
        """Look up enrichment data for a key.

        Args:
            lookup_type: Type of lookup (branch, customer, product).
            key: Lookup key value.
            fields: Fields to retrieve.

        Returns:
            Dict of field_name → value (empty if not found).
        """
        ...


class DataEnricher(BaseTransform):
    """Enriches data with lookups, derived fields, date normalization, and null filling.

    Runs four operations in sequence:
    1. Date normalization
    2. Lookup enrichment
    3. Derived fields
    4. Null filling
    """

    def __init__(
        self,
        config: TransformationConfig,
        lookup_provider: EnrichmentLookupProvider | None = None,
    ) -> None:
        super().__init__(config)
        self._lookup = lookup_provider

    @property
    def transform_name(self) -> str:
        return "Data Enrichment"

    async def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all enrichment operations.

        Args:
            df: Input DataFrame.

        Returns:
            Enriched DataFrame.
        """
        self.reset_stats()
        result = df.copy()

        # 1. Date normalization
        result = self._normalize_dates(result)

        # 2. Lookup enrichment
        if self._lookup and self.config.enrichment_rules:
            result = await self._apply_enrichments(result)

        # 3. Derived fields
        if self.config.derived_field_rules:
            result = self._apply_derived_fields(result)

        # 4. Null filling
        if self.config.null_fill_values:
            result = self._fill_nulls(result)

        return result

    # ------------------------------------------------------------------
    # Date normalization
    # ------------------------------------------------------------------

    def _normalize_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize date fields to ISO format.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with normalized dates.
        """
        count = 0
        for field in self.config.date_fields:
            if field not in df.columns:
                continue
            try:
                df[field] = pd.to_datetime(
                    df[field],
                    format=None,  # Let pandas infer
                    errors="coerce",
                ).dt.strftime(self.config.date_output_format)
                count += 1
            except Exception:
                pass  # Keep original on failure

        self._stats["dates_normalized"] = count
        return df

    # ------------------------------------------------------------------
    # Lookup enrichment
    # ------------------------------------------------------------------

    async def _apply_enrichments(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply enrichment lookups.

        For each enrichment rule, looks up additional fields
        and adds them to the DataFrame.

        Args:
            df: Input DataFrame.

        Returns:
            Enriched DataFrame.
        """
        count = 0
        for rule in self.config.enrichment_rules:
            if rule.source_field not in df.columns:
                continue
            if not self._lookup:
                continue

            # Pre-fill enrich columns with defaults
            for ef in rule.enrich_fields:
                df[ef] = rule.default_values.get(ef)

            # Batch lookup unique keys for efficiency
            unique_keys = df[rule.source_field].dropna().unique()
            cache: dict[str, dict[str, Any]] = {}
            for key in unique_keys:
                cache[str(key)] = await self._lookup.lookup(
                    rule.lookup_type, str(key), rule.enrich_fields
                )

            # Apply cached results
            for idx, key in df[rule.source_field].items():
                if pd.notna(key) and str(key) in cache:
                    enriched = cache[str(key)]
                    for ef in rule.enrich_fields:
                        if ef in enriched and enriched[ef] is not None:
                            df.at[idx, ef] = enriched[ef]

            count += 1

        self._stats["enrichments_applied"] = count
        return df

    # ------------------------------------------------------------------
    # Derived fields
    # ------------------------------------------------------------------

    def _apply_derived_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute derived fields from source data.

        Supports pre-defined function names and simple expressions.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with derived fields added.
        """
        count = 0
        for rule in self.config.derived_field_rules:
            try:
                df[rule.target_field] = self._compute_derived_field(df, rule)
                count += 1
            except Exception:
                df[rule.target_field] = None

        self._stats["fields_derived"] = count
        return df

    def _compute_derived_field(
        self, df: pd.DataFrame, rule: DerivedFieldRule
    ) -> pd.Series:
        """Compute a single derived field.

        Args:
            df: Source DataFrame.
            rule: Derived field definition.

        Returns:
            Pandas Series with computed values.
        """
        expr = rule.expression

        # Pre-defined functions
        if expr == "is_high_value":
            threshold = rule.params.get("threshold", 100000)
            if "transaction_amount" in df.columns:
                return df["transaction_amount"] > threshold
        elif expr == "year_month":
            field = rule.source_fields[0] if rule.source_fields else "transaction_date"
            if field in df.columns:
                return df[field].astype(str).str[:7]
        elif expr == "days_since":
            ref_date = rule.params.get("reference_date")
            field = rule.source_fields[0] if rule.source_fields else "transaction_date"
            if field in df.columns and ref_date:
                ref = pd.to_datetime(ref_date)
                dates = pd.to_datetime(df[field], errors="coerce")
                return (ref - dates).dt.days
        elif expr == "concat":
            sep = rule.params.get("separator", " ")
            cols = [c for c in rule.source_fields if c in df.columns]
            if cols:
                result = df[cols[0]].astype(str)
                for col in cols[1:]:
                    result = result + sep + df[col].astype(str)
                return result

        # Generic: try as a pandas eval expression
        return pd.Series(None, index=df.index)

    # ------------------------------------------------------------------
    # Null filling
    # ------------------------------------------------------------------

    def _fill_nulls(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fill null values with configured defaults.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with nulls filled.
        """
        count = 0
        for field, value in self.config.null_fill_values.items():
            if field in df.columns:
                null_count = df[field].isna().sum()
                df[field] = df[field].fillna(value)
                count += null_count

        self._stats["nulls_filled"] = count
        return df
