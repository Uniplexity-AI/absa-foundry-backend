"""
Referential Integrity Validator - Validates foreign key relationships.

Checks that referenced entities exist in their parent tables:
- customer_id exists in customer_master
- account_id exists in accounts
- branch_code exists in channels
- account belongs to customer
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
from etl.validation.validators.business_rule_validator import LookupProvider


class ReferentialIntegrityValidator(BaseValidator):
    """Validates referential integrity against master data.

    Uses an injected LookupProvider for database/API lookups.
    Results may be cached for performance.
    """

    def __init__(
        self,
        config: ValidationConfig,
        lookup_provider: LookupProvider,
    ) -> None:
        """Initialize with configuration and lookup provider.

        Args:
            config: Validation configuration.
            lookup_provider: Provider for referential lookups.
        """
        super().__init__(config)
        self._lookup = lookup_provider
        self._cache: dict[str, bool] = {}

    @property
    def category(self) -> str:
        return ValidationCategory.REFERENTIAL_INTEGRITY.value

    async def validate(
        self,
        df: pd.DataFrame,
        existing_results: list[RecordValidationResult] | None = None,
    ) -> list[RecordValidationResult]:
        """Validate referential integrity for all records."""
        self.reset()
        results: list[RecordValidationResult] = []

        for idx, (_, row) in enumerate(df.iterrows()):
            if existing_results and idx < len(existing_results):
                prev = existing_results[idx]
                if not prev.is_valid and self.config.stop_on_first_error:
                    results.append(prev)
                    continue
                result = RecordValidationResult(
                    record_index=idx,
                    is_valid=prev.is_valid,
                    errors=list(prev.errors),
                    warnings=list(prev.warnings),
                )
            else:
                result = RecordValidationResult(record_index=idx, is_valid=True)

            ri_errors = await self._check_referential_integrity(row, idx)
            if ri_errors:
                result.errors.extend(ri_errors)
                result.is_valid = False
                self._error_count += len(ri_errors)

            results.append(result)

        return results

    def validate_record(
        self, row: pd.Series, row_index: int
    ) -> RecordValidationResult:
        """Synchronous version — performs batch-level only (sync checks)."""
        return RecordValidationResult(record_index=row_index, is_valid=True)

    def reset(self) -> None:
        """Clear lookup cache."""
        super().reset()
        self._cache.clear()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _check_referential_integrity(
        self, row: pd.Series, row_index: int
    ) -> list[ValidationError]:
        """Check all referential integrity constraints for a record.

        Args:
            row: The data row.
            row_index: Row index for error reporting.

        Returns:
            List of ValidationErrors (empty if all constraints pass).
        """
        errors: list[ValidationError] = []

        if not self.config.referential_integrity_enabled:
            return errors

        # Check customer exists
        if "customer_id" in row.index:
            customer_id = str(row["customer_id"]).strip()
            if customer_id and customer_id != "nan":
                if not await self._cached_lookup(
                    f"customer:{customer_id}",
                    self._lookup.customer_exists,
                    customer_id,
                ):
                    errors.append(ValidationError(
                        rule_id="RI-001",
                        category=ValidationCategory.REFERENTIAL_INTEGRITY,
                        severity=ValidationSeverity.ERROR,
                        field_name="customer_id",
                        message=f"Customer '{customer_id}' does not exist in customer_master",
                        actual_value=customer_id,
                        expected_value="Existing customer_id",
                        record_index=row_index,
                    ))

        # Check account exists
        if "account_id" in row.index:
            account_id = str(row["account_id"]).strip()
            if account_id and account_id != "nan":
                if not await self._cached_lookup(
                    f"account:{account_id}",
                    self._lookup.account_exists,
                    account_id,
                ):
                    errors.append(ValidationError(
                        rule_id="RI-002",
                        category=ValidationCategory.REFERENTIAL_INTEGRITY,
                        severity=ValidationSeverity.ERROR,
                        field_name="account_id",
                        message=f"Account '{account_id}' does not exist in accounts",
                        actual_value=account_id,
                        expected_value="Existing account_id",
                        record_index=row_index,
                    ))

        # Check branch exists
        if "branch_code" in row.index:
            branch_code = str(row["branch_code"]).strip()
            if branch_code and branch_code != "nan":
                if not await self._cached_lookup(
                    f"branch:{branch_code}",
                    self._lookup.branch_exists,
                    branch_code,
                ):
                    errors.append(ValidationError(
                        rule_id="RI-003",
                        category=ValidationCategory.REFERENTIAL_INTEGRITY,
                        severity=ValidationSeverity.ERROR,
                        field_name="branch_code",
                        message=f"Branch '{branch_code}' does not exist in channels",
                        actual_value=branch_code,
                        expected_value="Existing branch_code",
                        record_index=row_index,
                    ))

        # Check account belongs to customer
        if "customer_id" in row.index and "account_id" in row.index:
            customer_id = str(row["customer_id"]).strip()
            account_id = str(row["account_id"]).strip()
            if customer_id and account_id and customer_id != "nan" and account_id != "nan":
                belongs = await self._cached_lookup(
                    f"acct_cust:{account_id}:{customer_id}",
                    self._lookup.account_belongs_to_customer,
                    account_id,
                    customer_id,
                )
                if not belongs:
                    errors.append(ValidationError(
                        rule_id="RI-004",
                        category=ValidationCategory.REFERENTIAL_INTEGRITY,
                        severity=ValidationSeverity.WARNING,
                        field_name="account_id",
                        message=f"Account '{account_id}' may not belong to customer '{customer_id}'",
                        actual_value=f"account={account_id}, customer={customer_id}",
                        expected_value="Account belongs to customer",
                        record_index=row_index,
                    ))

        return errors

    async def _cached_lookup(
        self, cache_key: str, lookup_fn, *args: object
    ) -> bool:
        """Perform a cached lookup.

        Args:
            cache_key: Cache key for deduplication.
            lookup_fn: Async lookup function.
            *args: Arguments to pass to lookup_fn.

        Returns:
            True if the entity exists.
        """
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await lookup_fn(*args)
        self._cache[cache_key] = result
        return result
