"""
Mandatory Fields Validator - Ensures required fields are present.

Rejects records missing any mandatory field per the banking specification:
Customer ID, Account ID, Branch Code (or Branch Name), Transaction Date,
Transaction Type, Transaction Channel, Transaction Amount, Currency.
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


class MandatoryFieldValidator(BaseValidator):
    """Validates that every record has all mandatory fields populated.

    Supports alternative fields (e.g., branch_code OR branch_name)
    as defined in ValidationConfig.alternative_fields.
    """

    @property
    def category(self) -> str:
        return ValidationCategory.MANDATORY_FIELDS.value

    async def validate(
        self,
        df: pd.DataFrame,
        existing_results: list[RecordValidationResult] | None = None,
    ) -> list[RecordValidationResult]:
        """Validate mandatory fields for all records.

        Args:
            df: DataFrame to validate.
            existing_results: Results from schema validator.

        Returns:
            Per-record validation results.
        """
        self.reset()
        results: list[RecordValidationResult] = []

        for idx, (_, row) in enumerate(df.iterrows()):
            # Skip records already invalid from schema validation
            if existing_results and idx < len(existing_results):
                if not existing_results[idx].is_valid:
                    results.append(existing_results[idx])
                    continue

            result = self.validate_record(row, idx)
            results.append(result)

            if not result.is_valid:
                self._error_count += len(result.errors)

        return results

    def validate_record(
        self, row: pd.Series, row_index: int
    ) -> RecordValidationResult:
        """Validate mandatory fields for a single record.

        Args:
            row: A single row of data.
            row_index: Row index.

        Returns:
            Validation result.
        """
        errors: list[ValidationError] = []

        for field in self.config.mandatory_fields:
            is_missing = self._is_field_missing(row, field)

            # Check alternatives if field is missing
            if is_missing and field in self.config.alternative_fields:
                alternatives = self.config.alternative_fields[field]
                has_alternative = any(
                    not self._is_field_missing(row, alt)
                    for alt in alternatives
                )
                if has_alternative:
                    continue  # Alternative satisfied

            if is_missing:
                errors.append(ValidationError(
                    rule_id=f"MANDATORY-{field.upper()}",
                    category=ValidationCategory.MANDATORY_FIELDS,
                    severity=ValidationSeverity.ERROR,
                    field_name=field,
                    message=(
                        f"Mandatory field '{field}' is missing, null, or empty"
                    ),
                    actual_value=None,
                    expected_value="Non-null, non-empty value",
                    record_index=row_index,
                ))

        return RecordValidationResult(
            record_index=row_index,
            is_valid=len(errors) == 0,
            errors=errors,
        )

    @staticmethod
    def _is_field_missing(row: pd.Series, field: str) -> bool:
        """Check if a field is missing, null, or empty.

        Args:
            row: The data row.
            field: Field name to check.

        Returns:
            True if the field is effectively missing.
        """
        if field not in row.index:
            return True
        value = row[field]
        if value is None:
            return True
        if pd.isna(value):
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        return False
