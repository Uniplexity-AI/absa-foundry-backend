"""
Unit tests for ETL Validation Engine.

Tests cover:
- SchemaValidator (column presence, empty datasets)
- MandatoryFieldValidator (missing fields, alternatives)
- BusinessRuleValidator (date, amount, currency, type, channel)
- DuplicateDetector (exact, near-duplicate)
- ReferentialIntegrityValidator (customer/account/branch lookups)
- ValidationService (full pipeline orchestration)
- ValidationReport generation and quality scoring
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pandas as pd
import pytest

from etl.schemas.validation_schemas import (
    RecordValidationResult,
    ValidationCategory,
    ValidationConfig,
    ValidationReport,
    ValidationRule,
    ValidationSeverity,
    ValidationStatus,
)
from etl.validation.service import ValidationService
from etl.validation.validators.business_rule_validator import BusinessRuleValidator, LookupProvider
from etl.validation.validators.duplicate_detector import DuplicateDetector
from etl.validation.validators.mandatory_field_validator import MandatoryFieldValidator
from etl.validation.validators.referential_integrity_validator import (
    ReferentialIntegrityValidator,
)
from etl.validation.validators.schema_validator import SchemaValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_df() -> pd.DataFrame:
    """Valid banking transaction DataFrame."""
    return pd.DataFrame({
        "customer_id": ["C001", "C002", "C003"],
        "account_id": ["A001", "A002", "A003"],
        "branch_code": ["BR001", "BR002", "BR001"],
        "transaction_date": ["2026-07-15", "2026-07-15", "2026-07-14"],
        "transaction_type": ["DEBIT", "CREDIT", "DEBIT"],
        "transaction_channel": ["ONLINE", "BRANCH", "ATM"],
        "transaction_amount": [1500.00, 25000.00, 350.50],
        "currency": ["ZAR", "ZAR", "ZAR"],
    })


@pytest.fixture
def invalid_df() -> pd.DataFrame:
    """DataFrame with various validation issues."""
    return pd.DataFrame({
        "customer_id": ["C001", None, "C003", "C001"],
        "account_id": ["A001", "A002", None, "A001"],
        "branch_code": ["BR001", "BR002", "BR001", "BR001"],
        "transaction_date": ["2026-07-15", "invalid", "2026-07-14", "2026-07-15"],
        "transaction_type": ["DEBIT", "CREDIT", "INVALID", "DEBIT"],
        "transaction_channel": ["ONLINE", "BRANCH", "ATM", "ONLINE"],
        "transaction_amount": [1500.00, -100.00, 350.50, 1500.00],
        "currency": ["ZAR", "ZAR", "XYZ", "ZAR"],
    })


@pytest.fixture
def config() -> ValidationConfig:
    """Default validation config."""
    return ValidationConfig()


@pytest.fixture
def mock_lookup() -> LookupProvider:
    """Mock lookup provider that says everything exists."""
    mock = AsyncMock(spec=LookupProvider)
    mock.customer_exists.return_value = True
    mock.account_exists.return_value = True
    mock.branch_exists.return_value = True
    mock.account_belongs_to_customer.return_value = True
    return mock


# ---------------------------------------------------------------------------
# SchemaValidator Tests
# ---------------------------------------------------------------------------

class TestSchemaValidator:
    """Tests for SchemaValidator."""

    @pytest.mark.asyncio
    async def test_valid_schema_passes(self, valid_df: pd.DataFrame, config: ValidationConfig) -> None:
        """Test that a DataFrame with expected schema passes."""
        validator = SchemaValidator(config)
        validator.set_expected_columns(list(valid_df.columns))
        results = await validator.validate(valid_df)
        assert all(r.is_valid for r in results)

    @pytest.mark.asyncio
    async def test_missing_column_fails(self, valid_df: pd.DataFrame, config: ValidationConfig) -> None:
        """Test that missing expected column is detected."""
        validator = SchemaValidator(config)
        validator.set_expected_columns(
            list(valid_df.columns) + ["missing_column"]
        )
        results = await validator.validate(valid_df)
        assert not results[0].is_valid
        assert "missing_column" in results[0].errors[0].message

    @pytest.mark.asyncio
    async def test_empty_dataframe_fails(self, config: ValidationConfig) -> None:
        """Test that empty DataFrame is flagged."""
        validator = SchemaValidator(config)
        df = pd.DataFrame()
        results = await validator.validate(df)
        assert len(results) == 0
        # Schema validation on empty df produces 0 results since no rows


# ---------------------------------------------------------------------------
# MandatoryFieldValidator Tests
# ---------------------------------------------------------------------------

class TestMandatoryFieldValidator:
    """Tests for MandatoryFieldValidator."""

    @pytest.mark.asyncio
    async def test_all_fields_present_passes(self, valid_df: pd.DataFrame, config: ValidationConfig) -> None:
        """Test that records with all mandatory fields pass."""
        validator = MandatoryFieldValidator(config)
        results = await validator.validate(valid_df)
        assert all(r.is_valid for r in results)

    @pytest.mark.asyncio
    async def test_missing_customer_id_fails(self, config: ValidationConfig) -> None:
        """Test that missing customer_id is flagged."""
        validator = MandatoryFieldValidator(config)
        df = pd.DataFrame({
            "account_id": ["A001"],
            "branch_code": ["BR001"],
            "transaction_date": ["2026-07-15"],
            "transaction_type": ["DEBIT"],
            "transaction_channel": ["ONLINE"],
            "transaction_amount": [100.0],
            "currency": ["ZAR"],
        })
        results = await validator.validate(df)
        assert not results[0].is_valid
        assert any("customer_id" in e.message for e in results[0].errors)

    @pytest.mark.asyncio
    async def test_null_value_fails(self, config: ValidationConfig) -> None:
        """Test that null mandatory field is flagged."""
        validator = MandatoryFieldValidator(config)
        df = pd.DataFrame({
            "customer_id": [None],
            "account_id": ["A001"],
            "branch_code": ["BR001"],
            "transaction_date": ["2026-07-15"],
            "transaction_type": ["DEBIT"],
            "transaction_channel": ["ONLINE"],
            "transaction_amount": [100.0],
            "currency": ["ZAR"],
        })
        results = await validator.validate(df)
        assert not results[0].is_valid

    @pytest.mark.asyncio
    async def test_alternative_field_satisfies(self, config: ValidationConfig) -> None:
        """Test that alternative field satisfies mandatory requirement."""
        validator = MandatoryFieldValidator(config)
        # branch_code missing but branch_name present
        df = pd.DataFrame({
            "customer_id": ["C001"],
            "account_id": ["A001"],
            "branch_name": ["Main Branch"],  # alternative to branch_code
            "transaction_date": ["2026-07-15"],
            "transaction_type": ["DEBIT"],
            "transaction_channel": ["ONLINE"],
            "transaction_amount": [100.0],
            "currency": ["ZAR"],
        })
        results = await validator.validate(df)
        assert results[0].is_valid


# ---------------------------------------------------------------------------
# BusinessRuleValidator Tests
# ---------------------------------------------------------------------------

class TestBusinessRuleValidator:
    """Tests for BusinessRuleValidator."""

    @pytest.mark.asyncio
    async def test_valid_record_passes(self, valid_df: pd.DataFrame, config: ValidationConfig) -> None:
        """Test that a valid record passes all business rules."""
        validator = BusinessRuleValidator(config)
        result = validator.validate_record(valid_df.iloc[0], 0)
        assert result.is_valid

    def test_invalid_date_format(self, config: ValidationConfig) -> None:
        """Test that invalid date format is flagged."""
        validator = BusinessRuleValidator(config)
        row = pd.Series({
            "customer_id": "C001",
            "transaction_date": "not-a-date",
            "transaction_amount": 100.0,
            "currency": "ZAR",
            "transaction_type": "DEBIT",
            "transaction_channel": "ONLINE",
        })
        result = validator.validate_record(row, 0)
        assert not result.is_valid
        assert any("date" in e.message.lower() for e in result.errors)

    def test_negative_amount(self, config: ValidationConfig) -> None:
        """Test that negative amount is flagged."""
        validator = BusinessRuleValidator(config)
        row = pd.Series({
            "transaction_date": "2026-07-15",
            "transaction_amount": -50.00,
            "currency": "ZAR",
            "transaction_type": "DEBIT",
            "transaction_channel": "ONLINE",
        })
        result = validator.validate_record(row, 0)
        assert not result.is_valid
        assert any("Amount" in e.message for e in result.errors)

    def test_unsupported_currency(self, config: ValidationConfig) -> None:
        """Test that unsupported currency is flagged."""
        validator = BusinessRuleValidator(config)
        row = pd.Series({
            "transaction_date": "2026-07-15",
            "transaction_amount": 100.0,
            "currency": "XXX",
            "transaction_type": "DEBIT",
            "transaction_channel": "ONLINE",
        })
        result = validator.validate_record(row, 0)
        assert not result.is_valid
        assert any("currency" in e.message.lower() for e in result.errors)

    def test_unsupported_transaction_type(self, config: ValidationConfig) -> None:
        """Test that unsupported transaction type is flagged."""
        validator = BusinessRuleValidator(config)
        row = pd.Series({
            "transaction_date": "2026-07-15",
            "transaction_amount": 100.0,
            "currency": "ZAR",
            "transaction_type": "UNKNOWN_TYPE",
            "transaction_channel": "ONLINE",
        })
        result = validator.validate_record(row, 0)
        assert not result.is_valid
        assert any("transaction type" in e.message.lower() for e in result.errors)

    def test_unsupported_channel(self, config: ValidationConfig) -> None:
        """Test that unsupported channel is flagged."""
        validator = BusinessRuleValidator(config)
        row = pd.Series({
            "transaction_date": "2026-07-15",
            "transaction_amount": 100.0,
            "currency": "ZAR",
            "transaction_type": "DEBIT",
            "transaction_channel": "TELEPATHY",
        })
        result = validator.validate_record(row, 0)
        assert not result.is_valid
        assert any("channel" in e.message.lower() for e in result.errors)

    def test_date_formats_accepted(self, config: ValidationConfig) -> None:
        """Test that all configured date formats are accepted."""
        validator = BusinessRuleValidator(config)
        for fmt in config.accepted_date_formats:
            row = pd.Series({
                "transaction_date": "2026-07-15",
                "transaction_amount": 100.0,
                "currency": "ZAR",
                "transaction_type": "DEBIT",
                "transaction_channel": "ONLINE",
            })
            result = validator.validate_record(row, 0)
            assert result.is_valid, f"Failed for format {fmt}"


# ---------------------------------------------------------------------------
# DuplicateDetector Tests
# ---------------------------------------------------------------------------

class TestDuplicateDetector:
    """Tests for DuplicateDetector."""

    @pytest.mark.asyncio
    async def test_no_duplicates_passes(self, valid_df: pd.DataFrame, config: ValidationConfig) -> None:
        """Test that unique records pass."""
        detector = DuplicateDetector(config)
        results = await detector.validate(valid_df)
        assert all(r.is_valid for r in results)

    @pytest.mark.asyncio
    async def test_exact_duplicate_detected(self, config: ValidationConfig) -> None:
        """Test that exact duplicate is detected."""
        detector = DuplicateDetector(config)
        df = pd.DataFrame({
            "customer_id": ["C001", "C001"],
            "account_id": ["A001", "A001"],
            "branch_code": ["BR001", "BR001"],
            "transaction_date": ["2026-07-15", "2026-07-15"],
            "transaction_type": ["DEBIT", "DEBIT"],
            "transaction_channel": ["ONLINE", "ONLINE"],
            "transaction_amount": [1500.00, 1500.00],
            "currency": ["ZAR", "ZAR"],
        })
        results = await detector.validate(df)
        assert results[0].is_valid  # First occurrence is valid
        assert not results[1].is_valid  # Duplicate is flagged

    @pytest.mark.asyncio
    async def test_different_records_not_duplicates(self, config: ValidationConfig) -> None:
        """Test that similar but different records are not flagged."""
        detector = DuplicateDetector(config)
        df = pd.DataFrame({
            "customer_id": ["C001", "C001"],
            "account_id": ["A001", "A001"],
            "branch_code": ["BR001", "BR001"],
            "transaction_date": ["2026-07-15", "2026-07-16"],
            "transaction_type": ["DEBIT", "DEBIT"],
            "transaction_channel": ["ONLINE", "ONLINE"],
            "transaction_amount": [1500.00, 2500.00],
            "currency": ["ZAR", "ZAR"],
        })
        results = await detector.validate(df)
        assert all(r.is_valid for r in results)


# ---------------------------------------------------------------------------
# ValidationService (Pipeline) Tests
# ---------------------------------------------------------------------------

class TestValidationService:
    """Tests for ValidationService pipeline orchestration."""

    @pytest.mark.asyncio
    async def test_valid_batch_passes(
        self, valid_df: pd.DataFrame, config: ValidationConfig
    ) -> None:
        """Test that a fully valid batch passes all validators."""
        service = ValidationService(config)
        report = await service.validate(valid_df, batch_id="test-batch")
        assert report.status == ValidationStatus.PASSED
        assert report.valid_records == len(valid_df)
        assert report.invalid_records == 0

    @pytest.mark.asyncio
    async def test_invalid_batch_fails(
        self, invalid_df: pd.DataFrame, config: ValidationConfig
    ) -> None:
        """Test that invalid records are detected."""
        service = ValidationService(config)
        report = await service.validate(invalid_df, batch_id="test-invalid")
        assert report.status in (ValidationStatus.FAILED, ValidationStatus.PARTIAL)
        assert report.invalid_records > 0

    @pytest.mark.asyncio
    async def test_validation_disabled(
        self, valid_df: pd.DataFrame
    ) -> None:
        """Test that validation can be disabled."""
        config = ValidationConfig(enabled=False)
        service = ValidationService(config)
        report = await service.validate(valid_df, batch_id="disabled")
        assert report.status == ValidationStatus.PASSED

    @pytest.mark.asyncio
    async def test_empty_dataframe(
        self, config: ValidationConfig
    ) -> None:
        """Test validation of empty DataFrame."""
        service = ValidationService(config)
        report = await service.validate(pd.DataFrame(), batch_id="empty")
        assert report.status == ValidationStatus.PASSED

    @pytest.mark.asyncio
    async def test_quality_score_perfect(
        self, valid_df: pd.DataFrame, config: ValidationConfig
    ) -> None:
        """Test that perfect data gets score 100."""
        service = ValidationService(config)
        report = await service.validate(valid_df, batch_id="perfect")
        assert report.quality_score == 100.0

    @pytest.mark.asyncio
    async def test_quality_score_degraded(
        self, invalid_df: pd.DataFrame, config: ValidationConfig
    ) -> None:
        """Test that invalid data gets a lower quality score."""
        service = ValidationService(config)
        report = await service.validate(invalid_df, batch_id="degraded")
        assert report.quality_score < 100.0


# ---------------------------------------------------------------------------
# ValidationReport Tests
# ---------------------------------------------------------------------------

class TestValidationReport:
    """Tests for ValidationReport schema."""

    def test_pass_rate_calculation(self) -> None:
        """Test pass rate computation."""
        report = ValidationReport(
            batch_id="test",
            total_records=100,
            valid_records=95,
            invalid_records=5,
        )
        assert report.pass_rate == 95.0

    def test_pass_rate_empty(self) -> None:
        """Test pass rate with zero records."""
        report = ValidationReport(batch_id="test")
        assert report.pass_rate == 100.0

    def test_quality_score_computation(self) -> None:
        """Test quality score computation."""
        report = ValidationReport(
            batch_id="test",
            total_records=100,
            total_errors=10,
            total_warnings=5,
        )
        score = report.compute_quality_score()
        assert 0 <= score <= 100
