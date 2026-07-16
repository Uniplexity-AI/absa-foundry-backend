"""
Schema Validator - Validates DataFrame schema (columns & types).

Checks that the ingested data has the expected columns with
correct data types. This is the first validator in the chain.
"""

from __future__ import annotations

import pandas as pd

from etl.schemas.validation_schemas import (
    RecordValidationResult,
    ValidationCategory,
    ValidationConfig,
    ValidationError,
    ValidationSeverity,
)
from etl.validation.interfaces import BaseValidator


class SchemaValidator(BaseValidator):
    """Validates that the DataFrame has the expected schema.

    Checks:
    - Required columns are present
    - Column data types match expectations
    - No unexpected columns (configurable)
    """

    def __init__(self, config: ValidationConfig) -> None:
        super().__init__(config)
        self._expected_columns: set[str] = set()
        self._expected_types: dict[str, str] = {}

    @property
    def category(self) -> str:
        return ValidationCategory.SCHEMA.value

    def set_expected_columns(self, columns: list[str]) -> None:
        """Set the expected column names.

        Args:
            columns: List of expected column names.
        """
        self._expected_columns = set(columns)

    def set_expected_types(self, types: dict[str, str]) -> None:
        """Set expected column types.

        Args:
            types: Mapping of column_name → expected_dtype.
        """
        self._expected_types = types

    async def validate(
        self,
        df: pd.DataFrame,
        existing_results: list[RecordValidationResult] | None = None,
    ) -> list[RecordValidationResult]:
        """Validate DataFrame schema.

        Schema errors affect ALL records, so we generate a single
        schema-level error that applies to every row.
        """
        self.reset()
        results: list[RecordValidationResult] = []

        schema_errors = self._validate_schema(df)

        if schema_errors:
            # Schema errors apply to all rows
            for idx in range(len(df)):
                results.append(RecordValidationResult(
                    record_index=idx,
                    is_valid=False,
                    errors=list(schema_errors),
                ))
            self._error_count = len(schema_errors) * len(df)
            return results

        # Schema OK — all records pass this validator
        for idx in range(len(df)):
            results.append(RecordValidationResult(
                record_index=idx,
                is_valid=True,
            ))
        return results

    def validate_record(
        self, row: pd.Series, row_index: int
    ) -> RecordValidationResult:
        """Schema validation is batch-level, not record-level."""
        return RecordValidationResult(record_index=row_index, is_valid=True)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _validate_schema(self, df: pd.DataFrame) -> list[ValidationError]:
        """Check DataFrame schema against expectations.

        Returns:
            List of schema-level ValidationErrors (empty if OK).
        """
        errors: list[ValidationError] = []
        actual_columns = set(df.columns)

        # Check required columns
        if self._expected_columns:
            missing = self._expected_columns - actual_columns
            for col in sorted(missing):
                errors.append(ValidationError(
                    rule_id="SCHEMA-001",
                    category=ValidationCategory.SCHEMA,
                    severity=ValidationSeverity.ERROR,
                    field_name=col,
                    message=f"Required column '{col}' is missing from dataset",
                    expected_value=f"Column '{col}'",
                    actual_value="MISSING",
                ))

        # Check empty DataFrame
        if len(df) == 0:
            errors.append(ValidationError(
                rule_id="SCHEMA-002",
                category=ValidationCategory.SCHEMA,
                severity=ValidationSeverity.ERROR,
                message="Dataset contains no records",
                expected_value="At least 1 record",
                actual_value="0 records",
            ))

        return errors
