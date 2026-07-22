"""
ETL Extraction Config Models — Pydantic v2 schemas for extraction specs.

Every extraction pipeline is governed by a YAML file validated against these
models at load time. All models use `extra="forbid"` to catch YAML typos early.

Covers sections 4.1, 7, 9–14, 18 of dynamic-extractor-spec.md.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ===========================================================================
# Versioning (Section 7)
# ===========================================================================

class EngineVersionSpec(BaseModel):
    """Engine version identifier for compatibility checking."""
    model_config = {"extra": "forbid"}
    version: str = Field(description="Semantic engine version, e.g. '2.1'")


class DatasetVersionSpec(BaseModel):
    """Dataset version — incremented on schema or logic changes."""
    model_config = {"extra": "forbid"}
    version: int = Field(ge=1, description="Monotonically increasing dataset version")


class SchemaVersionSpec(BaseModel):
    """Schema version — incremented when column definitions change."""
    model_config = {"extra": "forbid", "populate_by_name": True}
    version: int = Field(ge=1, alias="schema_version", description="Monotonically increasing schema version")


class CompatibilitySpec(BaseModel):
    """Minimum engine version required to execute this spec."""
    model_config = {"extra": "forbid"}
    minimum_engine: str = Field(default="1.0", description="Minimum engine version required")


class VersioningSpec(BaseModel):
    """Top-level versioning block in extraction YAML."""
    model_config = {"extra": "forbid", "populate_by_name": True}
    engine: EngineVersionSpec
    dataset: DatasetVersionSpec
    schema_version: SchemaVersionSpec = Field(alias="schema")
    compatibility: CompatibilitySpec = Field(default_factory=CompatibilitySpec)


# ===========================================================================
# Field Validation (Section 4.1)
# ===========================================================================

class FieldType(str, Enum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    DECIMAL = "decimal"
    DATETIME = "datetime"
    BOOL = "bool"


class FieldValidationSpec(BaseModel):
    """Per-field structural validation rules. Drives dynamic Pydantic schema generation."""
    model_config = {"extra": "forbid"}

    type: FieldType = Field(default=FieldType.STR, description="Expected data type")
    required: bool = Field(default=True, description="Field must be present and non-null")
    default: Any = Field(default=None, description="Default value if field is missing")
    regex: str | None = Field(default=None, description="Regex pattern for string validation")
    gt: float | None = Field(default=None, description="Greater than")
    lt: float | None = Field(default=None, description="Less than")
    ge: float | None = Field(default=None, description="Greater than or equal")
    le: float | None = Field(default=None, description="Less than or equal")


class SelectFieldSpec(BaseModel):
    """A single field selected from a source table, with optional alias and validation."""
    model_config = {"extra": "forbid"}

    field: str = Field(description="Column name in the source table")
    alias: str | None = Field(default=None, description="Output column name (defaults to field)")
    validation: FieldValidationSpec = Field(
        default_factory=FieldValidationSpec,
        description="Structural validation rules for this field",
    )

    @property
    def output_name(self) -> str:
        return self.alias or self.field


# ===========================================================================
# Entities & Joins (Sections 3, 10)
# ===========================================================================

class JoinType(str, Enum):
    INNER = "inner"
    LEFT = "left"
    RIGHT = "right"
    FULL = "full"


class JoinCondition(BaseModel):
    """A single join condition: left_column = right_column."""
    model_config = {"extra": "forbid"}
    left: str = Field(description="Left-side column reference, e.g. 'cust.customer_id'")
    right: str = Field(description="Right-side column reference, e.g. 'acc.customer_id'")


class EntitySpec(BaseModel):
    """Primary or secondary entity (table) in the extraction."""
    model_config = {"extra": "forbid"}

    table: str = Field(description="Fully qualified table name, e.g. 'raw.customers'")
    alias: str = Field(description="SQL alias for this entity, e.g. 'cust'")
    select_fields: list[SelectFieldSpec] = Field(
        description="Fields to select from this entity",
    )


class JoinSpec(BaseModel):
    """A JOIN between the primary entity and a secondary entity."""
    model_config = {"extra": "forbid"}

    table: str = Field(description="Table to join, e.g. 'raw.accounts'")
    alias: str = Field(description="SQL alias for the joined table, e.g. 'acc'")
    join_type: JoinType = Field(default=JoinType.LEFT, description="JOIN type")
    on: list[JoinCondition] = Field(
        description="Join conditions (multiple → AND chain)",
    )
    select_fields: list[SelectFieldSpec] = Field(
        description="Fields to select from the joined table",
    )

    @model_validator(mode="after")
    def _check_no_cross_join(self) -> JoinSpec:
        if not self.on:
            raise ValueError(f"Join '{self.alias}' has no ON conditions (cross-join forbidden)")
        return self


# ===========================================================================
# Filters (Section 9)
# ===========================================================================

class FilterOperator(str, Enum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    GREATER_THAN_EQUAL = "GREATER_THAN_EQUAL"
    LESS_THAN_EQUAL = "LESS_THAN_EQUAL"
    BETWEEN = "BETWEEN"
    IN = "IN"
    NOT_IN = "NOT_IN"
    LIKE = "LIKE"
    ILIKE = "ILIKE"
    REGEX = "REGEX"
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"
    DATE_ADD = "DATE_ADD"
    DATE_SUB = "DATE_SUB"
    CURRENT_DATE = "CURRENT_DATE"
    CURRENT_TIMESTAMP = "CURRENT_TIMESTAMP"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    AND = "AND"
    OR = "OR"


class FilterSpec(BaseModel):
    """A single filter condition or composite (AND/OR) filter group."""
    model_config = {"extra": "forbid"}

    field: str | None = Field(
        default=None,
        description="Qualified column, e.g. 'cust.status'. None for composite AND/OR.",
    )
    operator: FilterOperator = Field(description="Filter operator")
    value: Any = Field(
        default=None,
        description="Filter value. For BETWEEN: {min, max}. For IN/NOT_IN: list.",
    )
    conditions: list[FilterSpec] | None = Field(
        default=None,
        description="Nested conditions for AND/OR composite filters",
    )

    @model_validator(mode="after")
    def _check_field_or_conditions(self) -> FilterSpec:
        is_composite = self.operator in (FilterOperator.AND, FilterOperator.OR)
        if is_composite and not self.conditions:
            raise ValueError(f"Composite filter '{self.operator.value}' requires 'conditions'")
        if not is_composite and self.field is None:
            raise ValueError(f"Filter '{self.operator.value}' requires 'field'")
        return self


# ===========================================================================
# Aggregation (Section 11)
# ===========================================================================

class AggregationFunction(str, Enum):
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"
    STDDEV = "STDDEV"
    VARIANCE = "VARIANCE"


class AggregationSpec(BaseModel):
    """An aggregation applied to a field during extraction."""
    model_config = {"extra": "forbid"}

    function: AggregationFunction = Field(description="Aggregation function")
    field: str = Field(description="Column to aggregate, e.g. 'txn.amount'")
    alias: str = Field(description="Output column name for the aggregated value")
    distinct: bool = Field(default=False, description="Apply DISTINCT (only for COUNT)")


# ===========================================================================
# Calculated Fields (Section 12)
# ===========================================================================

class CalculatedFieldSpec(BaseModel):
    """A field derived via SQL expression during extraction."""
    model_config = {"extra": "forbid"}

    name: str = Field(description="Output column name")
    expression: str = Field(description="Raw SQL expression, e.g. 'EXTRACT(YEAR FROM AGE(...))'")
    output_type: FieldType = Field(default=FieldType.INT, description="Result data type")
    description: str | None = Field(default=None, description="Human-readable description")


# ===========================================================================
# Incremental Extraction (Section 13)
# ===========================================================================

class IncrementalStrategy(str, Enum):
    TIMESTAMP = "timestamp"
    CHANGE_TRACKING = "change_tracking"
    CDC = "cdc"


class IncrementalSpec(BaseModel):
    """Configuration for delta/incremental extraction."""
    model_config = {"extra": "forbid"}

    enabled: bool = Field(default=False, description="Enable incremental extraction")
    watermark_column: str = Field(
        default="updated_at",
        description="Column used as the watermark, e.g. 'cust.updated_at'",
    )
    strategy: IncrementalStrategy = Field(
        default=IncrementalStrategy.TIMESTAMP,
        description="Incremental strategy",
    )
    lookback_minutes: int = Field(
        default=60,
        ge=0,
        description="Safety overlap window in minutes",
    )


# ===========================================================================
# Streaming (Section 14)
# ===========================================================================

class FetchStrategy(str, Enum):
    CURSOR = "cursor"
    KEYSET = "keyset"
    OFFSET = "offset"


class StreamingSpec(BaseModel):
    """Configuration for cursor-based streaming extraction."""
    model_config = {"extra": "forbid"}

    enabled: bool = Field(default=False, description="Enable streaming extraction")
    batch_size: int = Field(default=10000, ge=100, description="Rows per chunk")
    fetch_strategy: FetchStrategy = Field(
        default=FetchStrategy.CURSOR,
        description="Pagination strategy",
    )
    keyset_column: str | None = Field(
        default=None,
        description="Column for keyset pagination",
    )


# ===========================================================================
# Business Rules (Section 18)
# ===========================================================================

class BusinessRuleSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class BusinessRuleSpec(BaseModel):
    """A domain-specific business rule evaluated after structural validation."""
    model_config = {"extra": "forbid"}

    id: str = Field(description="Unique rule identifier, e.g. 'BR001'")
    name: str = Field(description="Human-readable rule name")
    expression: str = Field(
        description="Python expression evaluated against the record dict, e.g. 'age >= 18'",
    )
    severity: BusinessRuleSeverity = Field(
        default=BusinessRuleSeverity.ERROR,
        description="ERROR=DLQ, WARNING=flag, INFO=log",
    )
    message: str | None = Field(default=None, description="Error message on failure")


# ===========================================================================
# Top-Level Extraction Config (Section 3)
# ===========================================================================

class ExtractionConfigSpec(BaseModel):
    """Root configuration for a single extraction pipeline.

    Validated by Pydantic v2 on load. A single YAML file deserializes
    into this model, which drives the entire Dynamic Extractor pipeline.
    """
    model_config = {"extra": "forbid"}

    # Identity
    version: str = Field(default="1.0", description="Config format version")
    dataset_name: str = Field(
        description="Unique dataset name, e.g. 'customer_360_daily'",
    )
    description: str | None = Field(default=None, description="Human-readable description")

    # Versioning (Section 7)
    versioning: VersioningSpec | None = Field(
        default=None,
        description="Engine/dataset/schema versioning (recommended for production)",
    )

    # Core extraction
    primary_entity: EntitySpec = Field(description="Driving table for extraction")
    joins: list[JoinSpec] = Field(default_factory=list, description="Secondary entities to join")
    filters: list[FilterSpec] = Field(default_factory=list, description="WHERE clause filters")

    # Advanced features
    aggregations: list[AggregationSpec] = Field(
        default_factory=list,
        description="Aggregations to compute during extraction",
    )
    group_by: list[str] = Field(
        default_factory=list,
        description="GROUP BY columns (required if aggregations present)",
    )
    calculated_fields: list[CalculatedFieldSpec] = Field(
        default_factory=list,
        description="SQL expressions computed during extraction",
    )
    business_rules: list[BusinessRuleSpec] = Field(
        default_factory=list,
        description="Business rules to evaluate after structural validation",
    )

    # Execution modes
    incremental: IncrementalSpec = Field(
        default_factory=IncrementalSpec,
        description="Incremental extraction configuration",
    )
    streaming: StreamingSpec = Field(
        default_factory=StreamingSpec,
        description="Streaming/pagination configuration",
    )

    @model_validator(mode="after")
    def _check_aggregations_have_group_by(self) -> ExtractionConfigSpec:
        if self.aggregations and not self.group_by:
            raise ValueError("Aggregations specified but 'group_by' is empty")
        return self
