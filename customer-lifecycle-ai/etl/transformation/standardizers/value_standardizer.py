"""
Value Standardizer - Normalizes categorical values to canonical forms.

Applies configured mappings like:
- DR / dr / Dr → DEBIT
- CR / cr / Cr → CREDIT
- Mobile Banking / mobile banking → MOBILE
- Branch deposits / BRANCH DEPOSIT → BRANCH
"""

from __future__ import annotations

import pandas as pd

from etl.schemas.transformation_schemas import StandardizationRule, TransformationConfig
from etl.transformation.interfaces import BaseTransform


class ValueStandardizer(BaseTransform):
    """Standardizes categorical values to canonical forms.

    Uses case-insensitive matching by default with trim_whitespace.
    Values not in the mapping are kept as-is (or set to default_value).
    """

    @property
    def transform_name(self) -> str:
        return "Value Standardization"

    async def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all standardization rules to the DataFrame.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with standardized values.
        """
        self.reset_stats()
        result = df.copy()
        total_standardized = 0

        for rule in self.config.standardization_rules:
            if rule.field_name not in result.columns:
                continue

            standardized, count = self._apply_rule(result[rule.field_name], rule)
            result[rule.field_name] = standardized
            total_standardized += count

        self._stats["values_standardized"] = total_standardized
        return result

    def _apply_rule(
        self, series: pd.Series, rule: StandardizationRule
    ) -> tuple[pd.Series, int]:
        """Apply a single standardization rule to a column.

        Args:
            series: Column to standardize.
            rule: Standardization rule definition.

        Returns:
            Tuple of (standardized_series, change_count).
        """
        # Build lookup: lowercase keys → target values
        lookup: dict[str, str] = {}
        for key, value in rule.mappings.items():
            lookup_key = key if rule.case_sensitive else key.lower()
            lookup[lookup_key] = value

        change_count = 0

        def _standardize(value: object) -> object:
            nonlocal change_count
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return rule.default_value if rule.default_value else value

            s = str(value)
            if rule.trim_whitespace:
                s = s.strip()
            lookup_key = s if rule.case_sensitive else s.lower()

            if lookup_key in lookup:
                change_count += 1
                return lookup[lookup_key]
            return rule.default_value if rule.default_value else value

        return series.apply(_standardize), change_count
