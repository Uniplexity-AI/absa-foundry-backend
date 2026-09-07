"""
ETL Extraction Schema Factory — dynamic Pydantic v2 model generation.

Transforms validation rules from extraction specs into runtime Pydantic models
for record-level structural validation. Each extraction spec produces a unique
model with field types, bounds, regex, and required/optional constraints.

Section 4.3 of dynamic-extractor-spec.md.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, create_model, field_validator

from etl.extraction.config_models import (
    ExtractionConfigSpec,
    FieldType,
    SelectFieldSpec,
)

logger = logging.getLogger("etl.extraction.schema_factory")

# Map config field types to Python types.
# DATETIME maps to `object` to accept date, datetime, and string values
# from databases (PostgreSQL DATE columns return `datetime.date`, etc.).
# INT/FLOAT/DECIMAL also use `object` to handle SQLAlchemy Decimal/float/int variants.
_TYPE_MAP: dict[FieldType, type] = {
    FieldType.STR: str,
    FieldType.INT: int,
    FieldType.FLOAT: float,
    FieldType.DECIMAL: object,  # PostgreSQL NUMERIC → Decimal
    FieldType.DATETIME: object,  # Accepts date, datetime, str from DB drivers
    FieldType.BOOL: bool,
}


class DynamicSchemaFactory:
    """Generates in-memory Pydantic v2 models from extraction specs.

    Usage:
        spec = ExtractionConfigSpec.model_validate(yaml_dict)
        Model = DynamicSchemaFactory.create_model(spec)
        validated = Model.model_validate(record_dict)
    """

    @classmethod
    def create_model(cls, config: ExtractionConfigSpec) -> type[BaseModel]:
        """Create a Pydantic v2 model from an extraction config.

        Args:
            config: Validated extraction configuration.

        Returns:
            A dynamically generated Pydantic BaseModel subclass.
        """
        field_defs: dict[str, Any] = {}
        seen_names: dict[str, str] = {}  # field_name → source (for collision detection)

        # Primary entity fields
        for name, defn in cls._build_fields(config.primary_entity.select_fields).items():
            field_defs[name] = defn
            seen_names[name] = f"primary_entity.{config.primary_entity.alias}"

        # Join entity fields — warn on overwrite
        for join in config.joins:
            for name, defn in cls._build_fields(join.select_fields).items():
                if name in seen_names:
                    logger.warning(
                        "Field collision: '%s' from join '%s' overwrites field from %s",
                        name, join.alias, seen_names[name],
                    )
                field_defs[name] = defn
                seen_names[name] = f"join.{join.alias}"

        # Calculated fields (treated as optional since they're derived)
        for cf in config.calculated_fields:
            py_type = _TYPE_MAP.get(cf.output_type, str)
            field_defs[cf.name] = (py_type | None, Field(default=None))

        # Aggregation fields (may be Decimal, int, or float from SQL)
        for agg in config.aggregations:
            field_defs[agg.alias] = (float | int | None, Field(default=None))

        model_name = f"{config.dataset_name.title().replace('_', '')}Model"
        logger.info(
            "Schema created: %s (%d fields from %d entities)",
            model_name, len(field_defs), 1 + len(config.joins),
        )
        return create_model(model_name, **field_defs)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _build_fields(fields: list[SelectFieldSpec]) -> dict[str, Any]:
        """Convert a list of SelectFieldSpecs into Pydantic field definitions."""
        defs: dict[str, Any] = {}
        for f in fields:
            v = f.validation
            py_type = _TYPE_MAP.get(v.type, str)
            kwargs: dict[str, Any] = {}

            # Bounds — only for numeric types
            if v.type in (FieldType.INT, FieldType.FLOAT, FieldType.DECIMAL):
                for bound in ("gt", "lt", "ge", "le"):
                    val = getattr(v, bound)
                    if val is not None:
                        kwargs[bound] = val

            # Required vs optional
            if v.required:
                field_type: Any = py_type
            else:
                field_type = py_type | None
                kwargs["default"] = v.default

            # Regex constraint — only for string fields
            if v.type == FieldType.STR and v.regex:
                field_type = Annotated[str, StringConstraints(pattern=v.regex)]

            defs[f.output_name] = (field_type, Field(**kwargs) if kwargs else ...)

        return defs
