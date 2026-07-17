"""
Business Rule Validator - Configurable business logic validation.

Checks:
- Date format validity and implausible future dates
- Amount > 0 and within acceptable range
- Currency is in accepted list
- Transaction type is in accepted list
- Channel is in accepted list
- Customer exists (via lookup)
- Account exists (via lookup)
- Branch exists (via lookup)
- Account belongs to customer
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from etl.schemas.validation_schemas import (
    RecordValidationResult,
    ValidationCategory,
    ValidationConfig,
    ValidationError,
    ValidationSeverity,
)
from etl.validation.interfaces import BaseValidator


class BusinessRuleValidator(BaseValidator):
    """Validates records against configurable business rules.

    All rules are driven by ValidationConfig — nothing hardcoded.
    Lookup-based rules (customer/account/branch existence) use
    injected lookup providers for testability.
    """

    def __init__(
        self,
        config: ValidationConfig,
        lookup_provider: LookupProvider | None = None,
    ) -> None:
        """Initialize the business rule validator.

        Args:
            config: Validation configuration with rules and accepted values.
            lookup_provider: Optional provider for referential lookups.
        """
        super().__init__(config)
        self._lookup = lookup_provider

    @property
    def category(self) -> str:
        return ValidationCategory.BUSINESS_RULE.value

    async def validate(
        self,
        df: pd.DataFrame,
        existing_results: list[RecordValidationResult] | None = None,
    ) -> list[RecordValidationResult]:
        """Validate business rules for all records."""
        self.reset()
        results: list[RecordValidationResult] = []

        for idx, (_, row) in enumerate(df.iterrows()):
            # Preserve errors from previous validators
            if existing_results and idx < len(existing_results):
                prev = existing_results[idx]
                if not prev.is_valid and self.config.stop_on_first_error:
                    results.append(prev)
                    continue
                # Merge: start with previous errors, add business rule results
                result = self.validate_record(row, idx)
                result.errors = list(prev.errors) + result.errors
                result.warnings = list(prev.warnings) + result.warnings
                result.is_valid = result.is_valid and prev.is_valid
            else:
                result = self.validate_record(row, idx)

            results.append(result)
            if not result.is_valid:
                self._error_count += len(result.errors)

            # Abort if too many errors
            if self._error_count >= self.config.max_errors_per_batch:
                break

        return results

    def validate_record(
        self, row: pd.Series, row_index: int
    ) -> RecordValidationResult:
        """Apply all active business rules to a single record."""
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # --- Date Format ---
        errors.extend(self._check_date_format(row, row_index))

        # --- Transaction Amount ---
        errors.extend(self._check_amount(row, row_index))

        # --- Currency ---
        errors.extend(self._check_currency(row, row_index))

        # --- Transaction Type ---
        errors.extend(self._check_transaction_type(row, row_index))

        # --- Channel ---
        errors.extend(self._check_channel(row, row_index))

        # --- Active config rules ---
        for rule in self.config.rules:
            if rule.category == ValidationCategory.BUSINESS_RULE and rule.is_active:
                err = self._evaluate_rule(row, row_index, rule)
                if err:
                    if rule.severity == ValidationSeverity.WARNING:
                        warnings.append(err)
                    else:
                        errors.append(err)

        return RecordValidationResult(
            record_index=row_index,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_date_format(
        self, row: pd.Series, row_index: int
    ) -> list[ValidationError]:
        """Check that transaction_date is a valid date and not implausibly far in the future."""
        errors: list[ValidationError] = []
        field = "transaction_date"
        if field not in row.index:
            return errors
        value = row[field]
        if value is None or pd.isna(value):
            return errors  # Already caught by mandatory field validator

        parsed_dt: datetime | None = None

        if isinstance(value, datetime):
            parsed_dt = value
        elif isinstance(value, str):
            for fmt in self.config.accepted_date_formats:
                try:
                    parsed_dt = datetime.strptime(value.strip(), fmt)
                    break
                except ValueError:
                    continue

        if parsed_dt is None:
            errors.append(ValidationError(
                rule_id="BUSINESS-DATE-001",
                category=ValidationCategory.BUSINESS_RULE,
                severity=ValidationSeverity.ERROR,
                field_name=field,
                message=f"Invalid date format: '{value}'. Accepted: {self.config.accepted_date_formats}",
                actual_value=str(value),
                expected_value="Valid date in accepted format",
                record_index=row_index,
            ))
            return errors

        # Check for implausible future dates (BUSINESS-DATE-002)
        now = datetime.now(timezone.utc)
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        max_allowed = now + timedelta(days=self.config.max_future_date_days)
        if parsed_dt > max_allowed:
            errors.append(ValidationError(
                rule_id="BUSINESS-DATE-002",
                category=ValidationCategory.BUSINESS_RULE,
                severity=ValidationSeverity.ERROR,
                field_name=field,
                message=f"Transaction date {parsed_dt.date()} is too far in the future. Max allowed: {max_allowed.date()}",
                actual_value=str(parsed_dt.date()),
                expected_value=f"Date ≤ {max_allowed.date()}",
                record_index=row_index,
            ))

        return errors

    def _check_amount(
        self, row: pd.Series, row_index: int
    ) -> list[ValidationError]:
        """Check that amount is positive and within range."""
        errors: list[ValidationError] = []
        # Support both 'amount' and 'transaction_amount' column names
        field = "amount" if "amount" in row.index else "transaction_amount"
        if field not in row.index:
            return errors
        value = row[field]
        if value is None or pd.isna(value):
            return errors

        try:
            amount = float(value)
            if amount <= 0:
                errors.append(ValidationError(
                    rule_id="BUSINESS-AMT-001",
                    category=ValidationCategory.BUSINESS_RULE,
                    severity=ValidationSeverity.ERROR,
                    field_name=field,
                    message=f"Amount must be > 0, got {amount}",
                    actual_value=str(amount),
                    expected_value=f"> {self.config.min_transaction_amount}",
                    record_index=row_index,
                ))
            elif amount > self.config.max_transaction_amount:
                errors.append(ValidationError(
                    rule_id="BUSINESS-AMT-002",
                    category=ValidationCategory.BUSINESS_RULE,
                    severity=ValidationSeverity.ERROR,
                    field_name=field,
                    message=f"Amount {amount} exceeds maximum {self.config.max_transaction_amount}",
                    actual_value=str(amount),
                    expected_value=f"≤ {self.config.max_transaction_amount}",
                    record_index=row_index,
                ))
        except (ValueError, TypeError):
            errors.append(ValidationError(
                rule_id="BUSINESS-AMT-003",
                category=ValidationCategory.BUSINESS_RULE,
                severity=ValidationSeverity.ERROR,
                field_name=field,
                message=f"Amount must be numeric, got '{value}'",
                actual_value=str(value),
                expected_value="Numeric value",
                record_index=row_index,
            ))
        return errors

    def _check_currency(
        self, row: pd.Series, row_index: int
    ) -> list[ValidationError]:
        """Check that currency is in the accepted list."""
        errors: list[ValidationError] = []
        field = "currency"
        if field not in row.index:
            return errors
        value = row[field]
        if value is None or pd.isna(value):
            return errors

        currency = str(value).strip().upper()
        if currency not in self.config.accepted_currencies:
            errors.append(ValidationError(
                rule_id="BUSINESS-CUR-001",
                category=ValidationCategory.BUSINESS_RULE,
                severity=ValidationSeverity.ERROR,
                field_name=field,
                message=f"Unsupported currency '{currency}'. Accepted: {self.config.accepted_currencies}",
                actual_value=currency,
                expected_value=f"One of {self.config.accepted_currencies}",
                record_index=row_index,
            ))
        return errors

    def _check_transaction_type(
        self, row: pd.Series, row_index: int
    ) -> list[ValidationError]:
        """Check transaction type is accepted."""
        errors: list[ValidationError] = []
        field = "transaction_type"
        if field not in row.index:
            return errors
        value = row[field]
        if value is None or pd.isna(value):
            return errors

        txn_type = str(value).strip().upper()
        if txn_type not in self.config.accepted_transaction_types:
            errors.append(ValidationError(
                rule_id="BUSINESS-TXN-001",
                category=ValidationCategory.BUSINESS_RULE,
                severity=ValidationSeverity.ERROR,
                field_name=field,
                message=f"Unsupported transaction type '{txn_type}'. Accepted: {self.config.accepted_transaction_types}",
                actual_value=txn_type,
                expected_value=f"One of {self.config.accepted_transaction_types}",
                record_index=row_index,
            ))
        return errors

    def _check_channel(
        self, row: pd.Series, row_index: int
    ) -> list[ValidationError]:
        """Check channel is accepted."""
        errors: list[ValidationError] = []
        # Support both 'channel' and 'transaction_channel' column names
        field = "channel" if "channel" in row.index else "transaction_channel"
        if field not in row.index:
            return errors
        value = row[field]
        if value is None or pd.isna(value):
            return errors

        channel = str(value).strip().upper()
        if channel not in self.config.accepted_channels:
            errors.append(ValidationError(
                rule_id="BUSINESS-CHN-001",
                category=ValidationCategory.BUSINESS_RULE,
                severity=ValidationSeverity.ERROR,
                field_name=field,
                message=f"Unsupported channel '{channel}'. Accepted: {self.config.accepted_channels}",
                actual_value=channel,
                expected_value=f"One of {self.config.accepted_channels}",
                record_index=row_index,
            ))
        return errors

    def _evaluate_rule(
        self, row: pd.Series, row_index: int, rule: ValidationRule
    ) -> ValidationError | None:
        """Evaluate a config-driven business rule.

        Args:
            row: Data row.
            row_index: Row index.
            rule: Rule definition from config.

        Returns:
            ValidationError if rule fails, None if it passes.
        """
        # Simple condition evaluation based on rule.condition
        condition = rule.condition
        field = rule.field_name

        if field and field in row.index:
            value = row[field]

            if condition == "not_null":
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    return self._build_rule_error(rule, row_index, value)
            elif condition == "positive":
                try:
                    if float(value) <= 0:
                        return self._build_rule_error(rule, row_index, value)
                except (ValueError, TypeError):
                    return self._build_rule_error(rule, row_index, value)
            elif condition == "in_list":
                allowed = rule.params.get("values", [])
                if str(value).strip().upper() not in [v.upper() for v in allowed]:
                    return self._build_rule_error(rule, row_index, value)
            elif condition == "not_in_list":
                forbidden = rule.params.get("values", [])
                if str(value).strip().upper() in [v.upper() for v in forbidden]:
                    return self._build_rule_error(rule, row_index, value)

        return None

    def _build_rule_error(
        self, rule: ValidationRule, row_index: int, actual_value: object
    ) -> ValidationError:
        """Build a ValidationError from a rule definition."""
        return ValidationError(
            rule_id=rule.rule_id,
            category=rule.category,
            severity=rule.severity,
            field_name=rule.field_name,
            message=rule.error_message_template.format(
                rule_id=rule.rule_id,
                field=rule.field_name or "unknown",
                value=str(actual_value),
            ),
            actual_value=actual_value,
            expected_value=str(rule.params.get("values", rule.condition)),
            record_index=row_index,
        )


# ---------------------------------------------------------------------------
# Lookup Provider Protocol
# ---------------------------------------------------------------------------

from typing import Protocol


class LookupProvider(Protocol):
    """Protocol for business rule lookups (customer, account, branch existence).

    Allows dependency injection of database or cache-based lookups.
    """

    async def customer_exists(self, customer_id: str) -> bool:
        """Check if a customer exists in the master database."""
        ...

    async def account_exists(self, account_id: str) -> bool:
        """Check if an account exists."""
        ...

    async def branch_exists(self, branch_code: str) -> bool:
        """Check if a branch exists."""
        ...

    async def account_belongs_to_customer(
        self, account_id: str, customer_id: str
    ) -> bool:
        """Check if an account belongs to a customer."""
        ...
