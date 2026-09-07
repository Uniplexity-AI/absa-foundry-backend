from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from etl.extraction.config_models import ExtractionConfigSpec
from etl.extraction.join_validator import JoinValidator
from etl.extraction.watermark_store import WatermarkStore


class _Inspector:
    """Small deterministic inspector for join-validation unit tests."""

    def get_schema_names(self):
        return ["public"]

    def get_table_names(self, schema):
        return ["customers", "transactions"]

    def get_columns(self, table_name, schema):
        return {
            "customers": [{"name": "customer_id", "type": "VARCHAR"}],
            "transactions": [{"name": "customer_id", "type": "VARCHAR"}],
        }[table_name]

    def get_indexes(self, table_name, schema):
        return [{"column_names": ["customer_id"]}]


def test_customer_360_multi_spec_is_valid() -> None:
    spec_path = Path("etl/config/extraction_specs/customer_360_multi.yaml")
    spec = ExtractionConfigSpec.model_validate(yaml.safe_load(spec_path.read_text(encoding="utf-8")))

    assert spec.dataset_name == "customer_360_multi"
    assert [cte.name for cte in spec.pre_aggregations] == ["txn_agg", "intr_agg"]
    assert len(spec.joins) == 2


def test_join_validator_accepts_cte_join(monkeypatch) -> None:
    import etl.extraction.join_validator as validator_module

    monkeypatch.setattr(validator_module, "inspect", lambda engine: _Inspector())
    spec = ExtractionConfigSpec.model_validate({
        "dataset_name": "cte_test",
        "primary_entity": {
            "table": "public.customers", "alias": "cust",
            "select_fields": [{"field": "customer_id"}],
        },
        "pre_aggregations": [{
            "name": "txn_agg", "from_table": "public.transactions", "alias": "txn",
            "aggregations": [{"function": "COUNT", "field": "transaction_id", "alias": "transaction_count"}],
            "group_by": ["txn.customer_id"],
        }],
        "joins": [{
            "table": "txn_agg", "alias": "txn", "join_type": "left",
            "on": [{"left": "cust.customer_id", "right": "txn.customer_id"}],
            "select_fields": [{"field": "transaction_count"}],
        }],
    })

    report = JoinValidator(object(), object()).validate(spec)

    assert report.is_valid, report.errors


def test_watermark_store_round_trip_and_corruption_recovery(tmp_path: Path) -> None:
    store = WatermarkStore(tmp_path / "watermarks.json")
    watermark = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)

    store.set("customer_360", watermark)
    assert store.get("customer_360") == watermark

    # Corrupt JSON is treated as empty (first-run recovery), not a crash
    (tmp_path / "watermarks.json").write_text("not json", encoding="utf-8")
    assert store.get("customer_360") is None  # Treated as first run

    # Re-set after corruption works
    store.set("customer_360", watermark)
    assert store.get("customer_360") == watermark
