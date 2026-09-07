"""Tests for DynamicSchemaFactory — field generation, collision detection."""
from __future__ import annotations

from etl.extraction.config_models import ExtractionConfigSpec
from etl.extraction.schema_factory import DynamicSchemaFactory


def _make_spec(
    join_fields: list[dict] | None = None,
    agg_fields: list[dict] | None = None,
    calc_fields: list[dict] | None = None,
    group_by: list[str] | None = None,
) -> ExtractionConfigSpec:
    data: dict = {
        "dataset_name": "test_schema",
        "primary_entity": {
            "table": "public.customers", "alias": "cust",
            "select_fields": [
                {"field": "customer_id", "alias": "customer_id",
                 "validation": {"type": "str", "required": True}},
                {"field": "status", "alias": "status",
                 "validation": {"type": "str", "required": False, "default": "UNKNOWN"}},
            ],
        },
    }
    if join_fields is not None:
        data["joins"] = [{
            "table": "public.transactions", "alias": "txn", "join_type": "left",
            "on": [{"left": "cust.customer_id", "right": "txn.customer_id"}],
            "select_fields": join_fields,
        }]
    if agg_fields is not None:
        data["aggregations"] = agg_fields
        data["group_by"] = group_by or ["cust.customer_id"]
    if calc_fields is not None:
        data["calculated_fields"] = calc_fields
    return ExtractionConfigSpec.model_validate(data)


class TestSchemaFactory:
    def test_primary_fields_in_model(self):
        spec = _make_spec()
        Model = DynamicSchemaFactory.create_model(spec)
        fields = Model.model_fields
        assert "customer_id" in fields
        assert "status" in fields

    def test_required_field_no_default(self):
        spec = _make_spec()
        Model = DynamicSchemaFactory.create_model(spec)
        assert Model.model_fields["customer_id"].is_required()

    def test_optional_field_has_default(self):
        spec = _make_spec()
        Model = DynamicSchemaFactory.create_model(spec)
        assert Model.model_fields["status"].default == "UNKNOWN"

    def test_join_fields_in_model(self):
        spec = _make_spec(join_fields=[
            {"field": "amount", "alias": "amount",
             "validation": {"type": "float", "required": False}},
        ])
        Model = DynamicSchemaFactory.create_model(spec)
        assert "amount" in Model.model_fields

    def test_aggregation_fields_in_model(self):
        spec = _make_spec(
            agg_fields=[{"function": "COUNT", "field": "txn.transaction_id", "alias": "txn_count"}],
            group_by=["cust.customer_id"],
        )
        Model = DynamicSchemaFactory.create_model(spec)
        assert "txn_count" in Model.model_fields

    def test_calculated_fields_in_model(self):
        spec = _make_spec(calc_fields=[
            {"name": "age", "expression": "42", "output_type": "int"},
        ])
        Model = DynamicSchemaFactory.create_model(spec)
        assert "age" in Model.model_fields

    def test_field_collision_detected(self, caplog):
        """When a join field name collides with a primary field, it should warn."""
        spec = _make_spec(join_fields=[
            {"field": "status", "alias": "customer_id",  # Collides with primary
             "validation": {"type": "str", "required": False}},
        ])
        DynamicSchemaFactory.create_model(spec)
        # The warning is emitted but the model still creates — last write wins
        warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any("customer_id" in w for w in warnings), f"No collision warning in: {warnings}"

    def test_int_field_with_bounds(self):
        spec_data = {
            "dataset_name": "test_bounds",
            "primary_entity": {
                "table": "public.cust", "alias": "c",
                "select_fields": [{
                    "field": "age", "alias": "age",
                    "validation": {"type": "int", "required": True, "gt": 0, "lt": 150},
                }],
            },
        }
        spec = ExtractionConfigSpec.model_validate(spec_data)
        Model = DynamicSchemaFactory.create_model(spec)
        assert "age" in Model.model_fields
