"""
ETL Validation Service - Orchestrates the validation pipeline.

Runs all validators in the configured order:
Schema → MandatoryFields → BusinessRules → Duplicates → ReferentialIntegrity

Generates a ValidationReport with aggregate statistics and
per-record results for downstream decision-making.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import pandas as pd

from etl.schemas.validation_schemas import (
    RecordValidationResult,
    ValidationCategory,
    ValidationConfig,
    ValidationReport,
    ValidationStatus,
)
from etl.validation.interfaces import BaseValidator
from etl.validation.validators.business_rule_validator import LookupProvider
from etl.validation.validators.duplicate_detector import DuplicateDetector
from etl.validation.validators.mandatory_field_validator import MandatoryFieldValidator
from etl.validation.validators.referential_integrity_validator import (
    ReferentialIntegrityValidator,
)
from etl.validation.validators.schema_validator import SchemaValidator


class ValidationService:
    """Orchestrates the complete validation pipeline.

    Executes validators in a configurable chain, collecting results
    and generating a comprehensive ValidationReport.
    """

    def __init__(
        self,
        config: ValidationConfig | None = None,
        lookup_provider: LookupProvider | None = None,
    ) -> None:
        """Initialize the validation service.

        Args:
            config: Validation configuration. Uses defaults if None.
            lookup_provider: Provider for referential lookups (RI checks).
        """
        self.config = config or ValidationConfig()
        self._lookup = lookup_provider
        self._validators: list[BaseValidator] = []
        self._build_validator_chain()

    async def validate(
        self,
        df: pd.DataFrame,
        batch_id: str,
    ) -> ValidationReport:
        """Execute the full validation pipeline on a dataset.

        Args:
            df: DataFrame containing records to validate.
            batch_id: Batch identifier for the report.

        Returns:
            ValidationReport with complete results and statistics.
        """
        if not self.config.enabled:
            return ValidationReport(
                batch_id=batch_id,
                status=ValidationStatus.PASSED,
                total_records=len(df),
                valid_records=len(df),
            )

        start_time = time.monotonic()
        report = ValidationReport(
            batch_id=batch_id,
            status=ValidationStatus.RUNNING,
            total_records=len(df),
            started_at=datetime.now(timezone.utc),
        )

        if df.empty:
            report.status = ValidationStatus.PASSED
            report.completed_at = datetime.now(timezone.utc)
            report.duration_seconds = time.monotonic() - start_time
            return report

        existing_results: list[RecordValidationResult] | None = None

        for validator in self._validators:
            if not self._is_category_enabled(validator.category):
                continue

            validator.reset()
            results = await validator.validate(df, existing_results)
            existing_results = results

        # Aggregate results
        if existing_results:
            self._aggregate_results(report, existing_results)

        report.completed_at = datetime.now(timezone.utc)
        report.duration_seconds = time.monotonic() - start_time
        report.quality_score = report.compute_quality_score()

        # Determine overall status
        if report.invalid_records == 0:
            report.status = ValidationStatus.PASSED
        elif report.valid_records == 0:
            report.status = ValidationStatus.FAILED
        else:
            report.status = ValidationStatus.PARTIAL

        return report

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_validator_chain(self) -> None:
        """Build the validator chain from configuration.

        Order: Schema → MandatoryFields → BusinessRules → Duplicates → RI
        """
        self._validators = [
            SchemaValidator(self.config),
            MandatoryFieldValidator(self.config),
            BusinessRuleValidator(self.config, self._lookup),
            DuplicateDetector(self.config),
            ReferentialIntegrityValidator(self.config, self._lookup) if self._lookup else None,
        ]
        # Remove None validators (e.g., RI when no lookup provider)
        self._validators = [v for v in self._validators if v is not None]

    def _is_category_enabled(self, category: str) -> bool:
        """Check if a validation category is enabled in config."""
        for cat in self.config.categories:
            if cat.value == category:
                return True
        return False

    def _aggregate_results(
        self,
        report: ValidationReport,
        results: list[RecordValidationResult],
    ) -> None:
        """Aggregate per-record results into the report.

        Args:
            report: Report to populate.
            results: Per-record validation results from the chain.
        """
        report.record_results = results

        for r in results:
            if r.is_valid and not r.errors and not r.warnings:
                report.valid_records += 1
            else:
                has_errors = any(
                    e.severity == "ERROR" for e in r.errors
                )
                if has_errors:
                    report.invalid_records += 1
                elif r.warnings:
                    report.warning_records += 1

            if r.duplicate_of is not None:
                report.duplicate_records += 1

            for err in r.errors:
                report.total_errors += 1
                cat = err.category.value if hasattr(err.category, "value") else str(err.category)
                report.error_by_category[cat] = report.error_by_category.get(cat, 0) + 1
                report.error_by_rule[err.rule_id] = report.error_by_rule.get(err.rule_id, 0) + 1

            for warn in r.warnings:
                report.total_warnings += 1

        report.valid_records = max(
            0,
            report.total_records - report.invalid_records,
        )
