"""
ETL Validation Interfaces - Abstract base for all validators.

Defines the BaseValidator ABC that all concrete validators implement.
Uses Strategy Pattern — each validator is independently testable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from etl.schemas.validation_schemas import RecordValidationResult, ValidationConfig


class BaseValidator(ABC):
    """Abstract base class for all data validators.

    Each validator checks one aspect of data quality:
    schema, mandatory fields, business rules, duplicates, or referential integrity.

    Validators are designed to be:
    - Independently testable
    - Composable in a validation chain
    - Configurable via ValidationConfig
    """

    def __init__(self, config: ValidationConfig) -> None:
        """Initialize the validator with configuration.

        Args:
            config: Validation engine configuration containing rules.
        """
        self.config = config
        self._error_count: int = 0

    @property
    @abstractmethod
    def category(self) -> str:
        """Return the validation category this validator handles.

        Returns:
            Category string matching ValidationCategory enum.
        """
        ...

    @abstractmethod
    async def validate(
        self,
        df: pd.DataFrame,
        existing_results: list[RecordValidationResult] | None = None,
    ) -> list[RecordValidationResult]:
        """Validate all records in the DataFrame.

        Args:
            df: DataFrame containing records to validate.
            existing_results: Results from previous validators in the chain
                              (for skip-if-already-invalid logic).

        Returns:
            List of RecordValidationResult, one per row.
        """
        ...

    @abstractmethod
    def validate_record(
        self, row: pd.Series, row_index: int
    ) -> RecordValidationResult:
        """Validate a single record.

        Args:
            row: A single row as a pandas Series.
            row_index: The row's index in the DataFrame.

        Returns:
            Validation result for this record.
        """
        ...

    @property
    def error_count(self) -> int:
        """Number of errors detected by this validator."""
        return self._error_count

    def reset(self) -> None:
        """Reset internal state between validation runs."""
        self._error_count = 0
