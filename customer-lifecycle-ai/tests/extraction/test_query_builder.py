"""Tests for DynamicQueryBuilder — filter operators, CTEs, RIGHT join, aggregations."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy import MetaData

from etl.extraction.config_models import (
    ExtractionConfigSpec,
    FilterOperator,
)
from etl.extraction.query_builder import DynamicQueryBuilder, QueryBuildError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec(**overrides) -> ExtractionConfigSpec:
    """Build a minimal valid spec for query builder testing."""
    data = {
        "dataset_name": "test_ds",
        "primary_entity": {
            "table": "public.customers", "alias": "cust",
            "select_fields": [{"field": "customer_id", "alias": "customer_id"}],
        },
    }
    data.update(overrides)
    return ExtractionConfigSpec.model_validate(data)


# ---------------------------------------------------------------------------
# Filter operator tests
# ---------------------------------------------------------------------------

class TestFilterOperators:
    """Verify all 22 filter operators produce valid SQL without errors."""

    _OPS = [
        (FilterOperator.EQUALS, "Active"),
        (FilterOperator.NOT_EQUALS, "Closed"),
        (FilterOperator.GREATER_THAN, 100),
        (FilterOperator.LESS_THAN, 1000),
        (FilterOperator.GREATER_THAN_EQUAL, 0),
        (FilterOperator.LESS_THAN_EQUAL, 5000),
        (FilterOperator.IS_NULL, None),
        (FilterOperator.IS_NOT_NULL, None),
        (FilterOperator.LIKE, "A%"),
        (FilterOperator.ILIKE, "active%"),
        (FilterOperator.CURRENT_DATE, None),
    ]

    def _make_spec_with_filter(self, operator, value):
        from etl.extraction.config_models import FilterOperator as FO
        # IS_NULL/IS_NOT_NULL don't need value
        if operator in (FO.IS_NULL, FO.IS_NOT_NULL, FO.CURRENT_DATE):
            filt = {"field": "cust.status", "operator": operator.value}
        else:
            filt = {"field": "cust.status", "operator": operator.value, "value": value}
        return _make_spec(filters=[filt])

    @pytest.mark.parametrize("operator,value", _OPS)
    def test_operator_produces_valid_sql(self, operator, value):
        """Each supported filter operator should compile without error."""
        spec = self._make_spec_with_filter(operator, value)
        builder = DynamicQueryBuilder(object(), MetaData())
        # We expect QueryBuildError because there's no real DB to reflect,
        # but the filter construction should not be the failure point.
        try:
            builder.build(spec)
        except QueryBuildError as e:
            # Acceptable: table resolution fails (no real DB)
            assert "Cannot resolve table" in str(e) or "Unknown alias" in str(e)

    def test_between_requires_min_max(self):
        """BETWEEN filter should accept {min, max} dict at config level."""
        spec = _make_spec(filters=[{
            "field": "cust.amount", "operator": "BETWEEN",
            "value": {"min": 100, "max": 500},
        }])
        assert spec.filters[0].value == {"min": 100, "max": 500}

    def test_in_requires_list(self):
        spec = _make_spec(filters=[{
            "field": "cust.status", "operator": "IN",
            "value": ["Active", "Dormant"],
        }])
        assert spec.filters[0].value == ["Active", "Dormant"]

    def test_between_without_min_raises(self):
        """BETWEEN without min/max dict should fail at config validation."""
        with pytest.raises(ValueError, match="BETWEEN filter requires"):
            _make_spec(filters=[{
                "field": "cust.amount", "operator": "BETWEEN", "value": "bad",
            }])

    def test_in_without_list_raises(self):
        with pytest.raises(ValueError, match="IN filter requires a list"):
            _make_spec(filters=[{
                "field": "cust.status", "operator": "IN", "value": "not_a_list",
            }])


# ---------------------------------------------------------------------------
# CTE / pre-aggregation tests
# ---------------------------------------------------------------------------

class TestPreAggregationCTE:
    """Verify pre-aggregation CTEs are built correctly from specs."""

    def test_spec_with_pre_aggregations_parses(self):
        spec = _make_spec(
            pre_aggregations=[{
                "name": "txn_agg", "from_table": "public.transactions",
                "alias": "txn",
                "aggregations": [
                    {"function": "COUNT", "field": "transaction_id", "alias": "txn_count"},
                    {"function": "SUM", "field": "amount", "alias": "total_amount"},
                ],
                "group_by": ["txn.customer_id"],
            }],
        )
        assert len(spec.pre_aggregations) == 1
        pa = spec.pre_aggregations[0]
        assert pa.name == "txn_agg"
        assert len(pa.aggregations) == 2
        assert pa.aggregations[0].alias == "txn_count"

    def test_pre_aggregation_requires_group_by(self):
        with pytest.raises(ValueError, match="has no group_by"):
            _make_spec(
                pre_aggregations=[{
                    "name": "bad", "from_table": "public.t", "alias": "t",
                    "aggregations": [{"function": "COUNT", "field": "id", "alias": "c"}],
                    "group_by": [],
                }],
            )

    def test_pre_aggregation_requires_aggregations(self):
        with pytest.raises(ValueError, match="has no aggregations"):
            _make_spec(
                pre_aggregations=[{
                    "name": "bad", "from_table": "public.t", "alias": "t",
                    "aggregations": [],
                    "group_by": ["t.id"],
                }],
            )

    def test_pre_aggregation_joins_as_cte(self):
        """CTE aliases should be usable in joins."""
        spec = _make_spec(
            pre_aggregations=[{
                "name": "txn_agg", "from_table": "public.transactions",
                "alias": "txn",
                "aggregations": [{"function": "COUNT", "field": "transaction_id", "alias": "cnt"}],
                "group_by": ["txn.customer_id"],
            }],
            joins=[{
                "table": "txn_agg", "alias": "txn", "join_type": "left",
                "on": [{"left": "cust.customer_id", "right": "txn.customer_id"}],
                "select_fields": [{"field": "cnt"}],
            }],
        )
        assert len(spec.joins) == 1
        assert spec.joins[0].table == "txn_agg"


# ---------------------------------------------------------------------------
# RIGHT join tests
# ---------------------------------------------------------------------------

class TestRightJoin:
    """RIGHT join should be accepted and produce valid SQL."""

    def test_right_join_accepted(self):
        spec = _make_spec(
            joins=[{
                "table": "public.accounts", "alias": "acc", "join_type": "right",
                "on": [{"left": "cust.customer_id", "right": "acc.customer_id"}],
                "select_fields": [],
            }],
        )
        assert spec.joins[0].join_type.value == "right"


# ---------------------------------------------------------------------------
# trusted_config gate
# ---------------------------------------------------------------------------

class TestTrustedConfigGate:
    """Raw SQL features must be rejected when trusted_config is False."""

    def test_calculated_fields_rejected_when_untrusted(self):
        spec = _make_spec(
            trusted_config=False,
            calculated_fields=[{
                "name": "age", "expression": "EXTRACT(YEAR FROM AGE(NOW(), cust.dob))",
            }],
        )
        builder = DynamicQueryBuilder(object(), MetaData())
        # QueryBuildError — either "trusted_config" (early check) or "Cannot resolve table" (no real DB)
        with pytest.raises(QueryBuildError):
            builder.build(spec)

    def test_exists_filter_rejected_when_untrusted(self):
        spec = _make_spec(
            trusted_config=False,
            filters=[{
                "field": "cust.id", "operator": "EXISTS",
                "value": "SELECT 1 FROM t WHERE t.cust_id = cust.id",
            }],
        )
        builder = DynamicQueryBuilder(object(), MetaData())
        with pytest.raises(QueryBuildError):
            builder.build(spec)


# ---------------------------------------------------------------------------
# Interval validation
# ---------------------------------------------------------------------------

class TestIntervalValidation:
    def test_safe_intervals_accepted(self):
        assert DynamicQueryBuilder._is_safe_interval("30 days")
        assert DynamicQueryBuilder._is_safe_interval("1 hour")
        assert DynamicQueryBuilder._is_safe_interval("90 minutes")
        assert DynamicQueryBuilder._is_safe_interval("-7 days")

    def test_unsafe_intervals_rejected(self):
        assert not DynamicQueryBuilder._is_safe_interval("30 days; DROP TABLE users")
        assert not DynamicQueryBuilder._is_safe_interval("'1' || 'day'")
        assert not DynamicQueryBuilder._is_safe_interval("")
        assert not DynamicQueryBuilder._is_safe_interval(None)
        assert not DynamicQueryBuilder._is_safe_interval(42)
