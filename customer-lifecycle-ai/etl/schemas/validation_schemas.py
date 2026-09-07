"""
ETL Validation Schemas - Pydantic v2 schemas for validation engine.

Defines data structures for:
- ValidationRule: Individual validation rule definition
- ValidationResult: Per-record validation outcome
- ValidationReport: Aggregate validation summary for a batch
- ValidationConfig: Engine-wide configuration
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ValidationSeverity(str, Enum):
    """Severity level of a validation failure."""
    ERROR = "ERROR"       # Record must be rejected
    WARNING = "WARNING"   # Record accepted but flagged
    INFO = "INFO"         # Informational only


class ValidationCategory(str, Enum):
    """Category of validation rule."""
    SCHEMA = "schema"
    MANDATORY_FIELDS = "mandatory_fields"
    BUSINESS_RULE = "business_rule"
    DUPLICATE = "duplicate"
    REFERENTIAL_INTEGRITY = "referential_integrity"


class ValidationStatus(str, Enum):
    """Overall status of a validation run."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"  # Some records valid, some not


# ---------------------------------------------------------------------------
# Validation Rule Definition
# ---------------------------------------------------------------------------

class ValidationRule(BaseModel):
    """Definition of a single validation rule.

    Rules are stored in configuration and loaded at runtime.
    Nothing is hardcoded — every check is defined here.
    """
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(
        description="Unique rule identifier (e.g., 'MANDATORY-001')",
    )
    category: ValidationCategory = Field(
        description="Category this rule belongs to",
    )
    name: str = Field(
        description="Human-readable rule name",
    )
    description: str = Field(
        description="What this rule checks",
    )
    severity: ValidationSeverity = Field(
        default=ValidationSeverity.ERROR,
        description="Severity if this rule fails",
    )
    field_name: str | None = Field(
        default=None,
        description="Target field for field-level validations",
    )
    condition: str = Field(
        description="Python expression or rule key for evaluation",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the rule condition",
    )
    is_active: bool = Field(
        default=True,
        description="Whether this rule is currently active",
    )
    error_message_template: str = Field(
        default="Validation failed for rule {rule_id}",
        description="Template for error messages (supports {field}, {value}, {rule_id})",
    )
    apply_to_sources: list[str] = Field(
        default_factory=list,
        description="Source types this rule applies to (empty = all)",
    )
    priority: int = Field(
        default=100,
        ge=1,
        description="Execution priority (lower = runs first)",
    )


# ---------------------------------------------------------------------------
# Per-Record Validation Result
# ---------------------------------------------------------------------------

class ValidationError(BaseModel):
    """A single validation error for a specific record."""
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(description="Rule that detected the error")
    category: ValidationCategory = Field(description="Validation category")
    severity: ValidationSeverity = Field(description="Error severity")
    field_name: str | None = Field(default=None, description="Field that failed")
    message: str = Field(description="Human-readable error message")
    record_index: int = Field(default=0, ge=0, description="Row index in the batch")
    actual_value: Any = Field(default=None, description="Actual value that failed")
    expected_value: Any = Field(default=None, description="Expected value or pattern")


class RecordValidationResult(BaseModel):
    """Validation result for a single record/row."""
    model_config = ConfigDict(extra="forbid")

    record_index: int = Field(description="Row index in the dataset")
    is_valid: bool = Field(default=True, description="Whether the record passed all validations")
    errors: list[ValidationError] = Field(
        default_factory=list, description="Validation errors for this record"
    )
    warnings: list[ValidationError] = Field(
        default_factory=list, description="Non-fatal warnings"
    )
    duplicate_of: int | None = Field(
        default=None, description="Record index this is a duplicate of (if applicable)"
    )


# ---------------------------------------------------------------------------
# Batch-Level Validation Report
# ---------------------------------------------------------------------------

class ValidationReport(BaseModel):
    """Aggregate validation report for an entire batch.

    Summarizes validation outcomes for the batch including
    record-level results and overall statistics.
    """
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(description="Batch identifier")
    status: ValidationStatus = Field(
        default=ValidationStatus.PENDING,
        description="Overall validation status",
    )
    total_records: int = Field(default=0, ge=0, description="Total records validated")
    valid_records: int = Field(default=0, ge=0, description="Records passing all validations")
    invalid_records: int = Field(default=0, ge=0, description="Records with at least one error")
    warning_records: int = Field(default=0, ge=0, description="Records with warnings only")
    duplicate_records: int = Field(default=0, ge=0, description="Duplicate records detected")
    total_errors: int = Field(default=0, ge=0, description="Total error count across all records")
    total_warnings: int = Field(default=0, ge=0, description="Total warning count")
    error_by_category: dict[str, int] = Field(
        default_factory=dict,
        description="Error count per validation category",
    )
    error_by_rule: dict[str, int] = Field(
        default_factory=dict,
        description="Error count per rule ID",
    )
    rule_results: dict[str, bool] = Field(
        default_factory=dict,
        description="Per-rule pass/fail status",
    )
    record_results: list[RecordValidationResult] = Field(
        default_factory=list,
        description="Detailed per-record results",
    )
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When validation started",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="When validation completed",
    )
    duration_seconds: float | None = Field(
        default=None,
        description="Total validation duration",
    )
    quality_score: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="Data quality score (0-100)",
    )

    @property
    def pass_rate(self) -> float:
        """Percentage of records that passed."""
        if self.total_records == 0:
            return 100.0
        return (self.valid_records / self.total_records) * 100.0

    def compute_quality_score(self) -> float:
        """Compute a quality score based on error rates.

        Weighted: errors count 5x more than warnings.
        Maximum penalty per record is capped.
        """
        if self.total_records == 0:
            return 100.0
        error_penalty = min(self.total_errors * 5.0 / self.total_records * 100, 80)
        warning_penalty = min(self.total_warnings * 1.0 / self.total_records * 100, 20)
        return max(100.0 - error_penalty - warning_penalty, 0.0)


# ---------------------------------------------------------------------------
# Validation Configuration
# ---------------------------------------------------------------------------

class ValidationConfig(BaseModel):
    """Engine-wide validation configuration.

    Controls how validators execute, which rules are active,
    and behavior for edge cases.
    """
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Master switch for validation")
    categories: list[ValidationCategory] = Field(
        default_factory=lambda: list(ValidationCategory),
        description="Categories to execute (all by default)",
    )
    rules: list[ValidationRule] = Field(
        default_factory=list,
        description="Active validation rules (loaded from config)",
    )

    # Mandatory fields (banking-specific)
    mandatory_fields: list[str] = Field(
        default_factory=lambda: [
            "customer_id", "account_id", "branch_code",
            "transaction_date", "transaction_type",
            "channel", "amount", "currency",
        ],
        description="Fields that must be present and non-null",
    )
    alternative_fields: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "branch_code": ["branch_name"],
        },
        description="Alternative fields that can satisfy mandatory requirements",
    )

    # Accepted values
    accepted_currencies: list[str] = Field(
        default_factory=lambda: ["ZMW", "ZAR", "USD", "EUR", "GBP", "BWP", "NAD", "SZL", "LSL"],
        description="Whitelist of accepted currency codes",
    )
    accepted_transaction_types: list[str] = Field(
        default_factory=lambda: [
            "CREDIT", "DEBIT", "TRANSFER", "PAYMENT",
            "FEE", "INTEREST", "REVERSAL",
        ],
        description="Whitelist of accepted transaction types",
    )
    accepted_channels: list[str] = Field(
        default_factory=lambda: [
            "BRANCH", "ATM", "POS", "ONLINE", "MOBILE",
            "INTERNET", "USSD", "E_WALLET", "DIRECT_DEBIT", "EFT",
        ],
        description="Whitelist of accepted transaction channels",
    )
    accepted_date_formats: list[str] = Field(
        default_factory=lambda: ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"],
        description="Accepted date string formats",
    )

    # Amount validation
    min_transaction_amount: float = Field(
        default=0.01, gt=0,
        description="Minimum valid transaction amount",
    )
    max_transaction_amount: float = Field(
        default=100_000_000.00, gt=0,
        description="Maximum valid transaction amount",
    )

    # Duplicate detection
    duplicate_detection_enabled: bool = Field(
        default=True,
        description="Enable duplicate detection",
    )
    duplicate_keys: list[str] = Field(
        default_factory=lambda: [
            "customer_id", "account_id", "branch_code",
            "transaction_date", "amount",
            "transaction_type", "channel", "currency",
        ],
        description="Fields forming the duplicate detection composite key",
    )
    near_duplicate_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Similarity threshold for near-duplicate detection (0-1)",
    )
    exact_duplicate_strategy: str = Field(
        default="reject",
        description="Strategy for exact duplicates: reject, flag, skip",
    )
    near_duplicate_strategy: str = Field(
        default="flag",
        description="Strategy for near-duplicates: reject, flag, skip",
    )

    # Referential integrity
    referential_integrity_enabled: bool = Field(
        default=True,
        description="Enable referential integrity checks",
    )
    referential_checks: dict[str, str] = Field(
        default_factory=lambda: {
            "customer_id": "customer_master.customer",
            "account_id": "accounts.account",
            "branch_code": "channels.branch",
        },
        description="Field → reference table mapping for RI checks",
    )

    # Execution
    stop_on_first_error: bool = Field(
        default=False,
        description="Stop validating a record after the first error",
    )
    max_errors_per_batch: int = Field(
        default=10000,
        ge=0,
        description="Maximum errors before aborting the batch",
    )
    max_future_date_days: int = Field(
        default=365,
        ge=0,
        description="Maximum days into the future a transaction date can be before rejection",
    )
    parallel_validation: bool = Field(
        default=False,
        description="Validate records in parallel (for large batches)",
    )
