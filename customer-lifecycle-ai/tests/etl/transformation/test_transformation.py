"""
Unit tests for ETL Transformation Engine.

Tests cover:
- FieldMapper: column renaming, type casting, dropping, reordering
- ValueStandardizer: categorical normalization, case handling
- DataEnricher: date normalization, derived fields, null filling
- TransformationService: full pipeline orchestration
- TransformationReport generation
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pandas as pd
import pytest

from etl.schemas.transformation_schemas import (
    DerivedFieldRule,
    FieldMapping,
    StandardizationRule,
    TransformationConfig,
)
from etl.transformation.enrichers.data_enricher import DataEnricher
from etl.transformation.mappers.field_mapper import FieldMapper
from etl.transformation.service import TransformationService
from etl.transformation.standardizers.value_standardizer import ValueStandardizer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source_df() -> pd.DataFrame:
    """Raw source DataFrame before transformation."""
    return pd.DataFrame({
        "CUST_ID": ["C001", "C002", "C003"],
        "ACCT_ID": ["A001", "A002", "A003"],
        "BRANCH_NM": ["Sandton", "Rosebank", "Sandton"],
        "TXN_DATE": ["2026/07/15", "2026/07/15", "15-07-2026"],
        "TXN_TYPE": ["DR", "CR", "dr"],
        "TXN_CHANNEL": ["Mobile Banking", "Internet Banking", "mobile banking"],
        "TXN_AMT": ["1,500.00", "25000", "350.5"],
        "CURRENCY": ["zar", "ZAR", "Zar"],
    })


@pytest.fixture
def mapping_config() -> TransformationConfig:
    """Config with standard banking field mappings."""
    return TransformationConfig(
        field_mappings=[
            FieldMapping(source_field="CUST_ID", target_field="customer_id"),
            FieldMapping(source_field="ACCT_ID", target_field="account_id"),
            FieldMapping(source_field="BRANCH_NM", target_field="branch_name"),
            FieldMapping(source_field="TXN_DATE", target_field="transaction_date"),
            FieldMapping(source_field="TXN_TYPE", target_field="transaction_type"),
            FieldMapping(source_field="TXN_CHANNEL", target_field="transaction_channel"),
            FieldMapping(source_field="TXN_AMT", target_field="transaction_amount", data_type="float"),
            FieldMapping(source_field="CURRENCY", target_field="currency"),
        ],
        type_casts={"transaction_amount": "float"},
        date_fields=["transaction_date"],
        drop_columns=["BRANCH_NM", "TXN_DATE", "TXN_TYPE", "TXN_CHANNEL", "TXN_AMT", "CURRENCY"],
    )


@pytest.fixture
def full_config() -> TransformationConfig:
    """Full transformation config with mappings, standardization, and derived fields."""
    return TransformationConfig(
        field_mappings=[
            FieldMapping(source_field="CUST_ID", target_field="customer_id"),
            FieldMapping(source_field="ACCT_ID", target_field="account_id"),
            FieldMapping(source_field="BRANCH_NM", target_field="branch_name"),
            FieldMapping(source_field="TXN_DATE", target_field="transaction_date"),
            FieldMapping(source_field="TXN_TYPE", target_field="transaction_type"),
            FieldMapping(source_field="TXN_CHANNEL", target_field="transaction_channel"),
            FieldMapping(source_field="TXN_AMT", target_field="transaction_amount", data_type="float"),
            FieldMapping(source_field="CURRENCY", target_field="currency"),
        ],
        standardization_rules=[
            StandardizationRule(
                rule_id="STD-TXN-001",
                field_name="transaction_type",
                mappings={"DR": "DEBIT", "CR": "CREDIT"},
            ),
            StandardizationRule(
                rule_id="STD-CHN-001",
                field_name="transaction_channel",
                mappings={
                    "Mobile Banking": "MOBILE",
                    "Internet Banking": "ONLINE",
                },
            ),
        ],
        derived_field_rules=[
            DerivedFieldRule(
                rule_id="DER-001",
                target_field="is_high_value",
                expression="is_high_value",
                source_fields=["transaction_amount"],
                data_type="bool",
                params={"threshold": 10000},
            ),
        ],
        date_fields=["transaction_date"],
        null_fill_values={"branch_name": "UNKNOWN"},
    )


# ---------------------------------------------------------------------------
# FieldMapper Tests
# ---------------------------------------------------------------------------

class TestFieldMapper:
    """Tests for FieldMapper."""

    @pytest.mark.asyncio
    async def test_renames_columns(
        self, source_df: pd.DataFrame, mapping_config: TransformationConfig
    ) -> None:
        """Test that columns are renamed per mapping."""
        mapper = FieldMapper(mapping_config)
        result = await mapper.apply(source_df)
        assert "customer_id" in result.columns
        assert "CUST_ID" not in result.columns
        assert "transaction_amount" in result.columns

    @pytest.mark.asyncio
    async def test_drops_columns(
        self, source_df: pd.DataFrame, mapping_config: TransformationConfig
    ) -> None:
        """Test that configured columns are dropped after mapping."""
        mapper = FieldMapper(mapping_config)
        result = await mapper.apply(source_df)
        for col in mapping_config.drop_columns:
            assert col not in result.columns

    @pytest.mark.asyncio
    async def test_no_mappings_returns_same(
        self, source_df: pd.DataFrame
    ) -> None:
        """Test that no mappings leaves DataFrame unchanged."""
        config = TransformationConfig()
        mapper = FieldMapper(config)
        result = await mapper.apply(source_df)
        pd.testing.assert_frame_equal(result, source_df)

    @pytest.mark.asyncio
    async def test_stats_tracked(
        self, source_df: pd.DataFrame, mapping_config: TransformationConfig
    ) -> None:
        """Test that mapper tracks statistics."""
        mapper = FieldMapper(mapping_config)
        await mapper.apply(source_df)
        assert mapper.stats["fields_mapped"] > 0


# ---------------------------------------------------------------------------
# ValueStandardizer Tests
# ---------------------------------------------------------------------------

class TestValueStandardizer:
    """Tests for ValueStandardizer."""

    @pytest.mark.asyncio
    async def test_standardizes_values(self) -> None:
        """Test that values are standardized per rules."""
        config = TransformationConfig(
            standardization_rules=[
                StandardizationRule(
                    rule_id="TST-001",
                    field_name="txn_type",
                    mappings={"DR": "DEBIT", "CR": "CREDIT"},
                ),
            ],
        )
        df = pd.DataFrame({"txn_type": ["DR", "dr", "CR", "cr", "UNKNOWN"]})
        standardizer = ValueStandardizer(config)
        result = await standardizer.apply(df)

        assert result["txn_type"].iloc[0] == "DEBIT"
        assert result["txn_type"].iloc[1] == "DEBIT"  # case insensitive
        assert result["txn_type"].iloc[2] == "CREDIT"
        assert result["txn_type"].iloc[3] == "CREDIT"
        assert result["txn_type"].iloc[4] == "UNKNOWN"  # not in mapping

    @pytest.mark.asyncio
    async def test_standardizes_channels(self) -> None:
        """Test channel standardization."""
        config = TransformationConfig(
            standardization_rules=[
                StandardizationRule(
                    rule_id="CHN-001",
                    field_name="channel",
                    mappings={
                        "Mobile Banking": "MOBILE",
                        "Internet Banking": "ONLINE",
                        "Branch": "BRANCH",
                    },
                ),
            ],
        )
        df = pd.DataFrame({
            "channel": ["Mobile Banking", "mobile banking", "Internet Banking", "ATM"],
        })
        standardizer = ValueStandardizer(config)
        result = await standardizer.apply(df)

        assert result["channel"].iloc[0] == "MOBILE"
        assert result["channel"].iloc[1] == "MOBILE"
        assert result["channel"].iloc[2] == "ONLINE"
        assert result["channel"].iloc[3] == "ATM"  # not mapped

    @pytest.mark.asyncio
    async def test_whitespace_trimmed(self) -> None:
        """Test that whitespace is trimmed before matching."""
        config = TransformationConfig(
            standardization_rules=[
                StandardizationRule(
                    rule_id="TST-001",
                    field_name="type",
                    mappings={"DR": "DEBIT"},
                    trim_whitespace=True,
                ),
            ],
        )
        df = pd.DataFrame({"type": ["  DR  ", "DR", " dr "]})
        standardizer = ValueStandardizer(config)
        result = await standardizer.apply(df)
        assert all(v == "DEBIT" for v in result["type"])

    @pytest.mark.asyncio
    async def test_default_value_for_unmapped(self) -> None:
        """Test default_value is used for unmapped values."""
        config = TransformationConfig(
            standardization_rules=[
                StandardizationRule(
                    rule_id="TST-001",
                    field_name="type",
                    mappings={"DR": "DEBIT"},
                    default_value="OTHER",
                ),
            ],
        )
        df = pd.DataFrame({"type": ["DR", "XYZ"]})
        standardizer = ValueStandardizer(config)
        result = await standardizer.apply(df)
        assert result["type"].iloc[0] == "DEBIT"
        assert result["type"].iloc[1] == "OTHER"


# ---------------------------------------------------------------------------
# DataEnricher Tests
# ---------------------------------------------------------------------------

class TestDataEnricher:
    """Tests for DataEnricher."""

    def test_date_normalization(self) -> None:
        """Test date fields are normalized to ISO format."""
        import asyncio

        config = TransformationConfig(
            date_fields=["transaction_date"],
        )
        df = pd.DataFrame({
            "transaction_date": ["2026/07/15", "15-07-2026", "2026-07-15"],
        })
        enricher = DataEnricher(config)
        result = asyncio.run(enricher.apply(df))
        # All should be 2026-07-15
        assert all(v == "2026-07-15" for v in result["transaction_date"])

    def test_null_filling(self) -> None:
        """Test null values are filled with defaults."""
        import asyncio

        config = TransformationConfig(
            null_fill_values={"branch_name": "UNKNOWN", "currency": "ZAR"},
        )
        df = pd.DataFrame({
            "branch_name": ["Sandton", None, None],
            "currency": ["ZAR", None, "USD"],
        })
        enricher = DataEnricher(config)
        result = asyncio.run(enricher.apply(df))
        assert result["branch_name"].iloc[1] == "UNKNOWN"
        assert result["currency"].iloc[1] == "ZAR"

    def test_derived_field_is_high_value(self) -> None:
        """Test is_high_value derived field."""
        import asyncio

        config = TransformationConfig(
            derived_field_rules=[
                DerivedFieldRule(
                    rule_id="DER-001",
                    target_field="is_high_value",
                    expression="is_high_value",
                    source_fields=["transaction_amount"],
                    data_type="bool",
                    params={"threshold": 10000},
                ),
            ],
        )
        df = pd.DataFrame({
            "transaction_amount": [5000.0, 15000.0, 100000.0],
        })
        enricher = DataEnricher(config)
        result = asyncio.run(enricher.apply(df))
        assert not result["is_high_value"].iloc[0]
        assert result["is_high_value"].iloc[1]
        assert result["is_high_value"].iloc[2]

    def test_derived_field_year_month(self) -> None:
        """Test year_month derived field."""
        import asyncio

        config = TransformationConfig(
            derived_field_rules=[
                DerivedFieldRule(
                    rule_id="DER-002",
                    target_field="year_month",
                    expression="year_month",
                    source_fields=["transaction_date"],
                    data_type="str",
                ),
            ],
        )
        df = pd.DataFrame({
            "transaction_date": ["2026-07-15", "2026-01-01"],
        })
        enricher = DataEnricher(config)
        result = asyncio.run(enricher.apply(df))
        assert result["year_month"].iloc[0] == "2026-07"
        assert result["year_month"].iloc[1] == "2026-01"


# ---------------------------------------------------------------------------
# TransformationService Tests
# ---------------------------------------------------------------------------

class TestTransformationService:
    """Tests for TransformationService pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline(
        self, source_df: pd.DataFrame, full_config: TransformationConfig
    ) -> None:
        """Test the complete transformation pipeline."""
        service = TransformationService(full_config)
        result_df, report = await service.transform(source_df, batch_id="test-batch")

        # Check mappings
        assert "customer_id" in result_df.columns
        assert "CUST_ID" not in result_df.columns

        # Check standardization
        assert result_df["transaction_type"].iloc[0] == "DEBIT"
        assert result_df["transaction_channel"].iloc[0] == "MOBILE"

        # Check derived field
        assert "is_high_value" in result_df.columns

        # Check report
        assert report.input_rows == len(source_df)
        assert report.output_rows == len(source_df)
        assert report.fields_mapped > 0
        assert report.values_standardized > 0

    @pytest.mark.asyncio
    async def test_empty_config_no_change(
        self, source_df: pd.DataFrame
    ) -> None:
        """Test that empty config leaves data unchanged."""
        config = TransformationConfig()
        service = TransformationService(config)
        result_df, report = await service.transform(source_df, batch_id="noop")
        pd.testing.assert_frame_equal(result_df, source_df)

    @pytest.mark.asyncio
    async def test_report_has_timestamps(
        self, source_df: pd.DataFrame
    ) -> None:
        """Test that report includes timing information."""
        config = TransformationConfig()
        service = TransformationService(config)
        _, report = await service.transform(source_df, batch_id="timing")
        assert report.started_at is not None
        assert report.completed_at is not None
        assert report.duration_seconds is not None
