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

        # BETWEEN requires {min, max} dict
        if self.operator == FilterOperator.BETWEEN:
            if not isinstance(self.value, dict) or "min" not in self.value or "max" not in self.value:
                raise ValueError(
                    f"BETWEEN filter requires value={{min: ..., max: ...}}, got: {self.value!r}"
                )

        # IN/NOT_IN require a list
        if self.operator in (FilterOperator.IN, FilterOperator.NOT_IN):
            if not isinstance(self.value, list):
                raise ValueError(
                    f"{self.operator.value} filter requires a list value, got: {type(self.value).__name__}"
                )

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
# Pre-Aggregation CTEs (Section 11.1 — fixes multi-table overcount)
# ===========================================================================

class PreAggregationSpec(BaseModel):
    """A standalone aggregation CTE computed BEFORE joining to the main query.

    CRITICAL: When multiple tables are joined to the primary entity and
    aggregations reference columns from those joined tables, flat JOINs
    create row multiplication (tx × interaction per customer).  Pre-
    aggregation CTEs eliminate this by aggregating each side-table
    independently before the join.

    Example:
        pre_aggregations:
          - name: "txn_agg"
            from_table: "public.raw_transactions"
            alias: "txn"
            aggregations:
              - function: COUNT
                field: "transaction_id"
                alias: transaction_count
            group_by: ["txn.customer_id"]
    """
    model_config = {"extra": "forbid"}

    name: str = Field(description="CTE name (referenced in joins.table)")
    from_table: str = Field(description="Source table, e.g. 'public.raw_transactions'")
    alias: str = Field(description="SQL alias for columns, e.g. 'txn'")
    aggregations: list[AggregationSpec] = Field(
        description="Aggregations to compute in this CTE",
    )
    group_by: list[str] = Field(
        description="GROUP BY columns, e.g. ['txn.customer_id']",
    )
    filters: list[FilterSpec] = Field(
        default_factory=list,
        description="Optional filters applied within the CTE",
    )

    @model_validator(mode="after")
    def _check_has_aggregations_and_group_by(self) -> "PreAggregationSpec":
        if not self.aggregations:
            raise ValueError(f"Pre-aggregation '{self.name}' has no aggregations")
        if not self.group_by:
            raise ValueError(f"Pre-aggregation '{self.name}' has no group_by")
        return self


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
# ETL Target Configuration (Section 19 — where cleaned data lands)
# ===========================================================================

class TargetSpec(BaseModel):
    """Declares which target clean table this spec feeds and which columns to write.

    Each extraction spec maps to ONE clean table in etl_clean. The ETL
    bulk_insert_clean function uses this to dynamically build INSERT statements.
    """
    model_config = {"extra": "forbid"}

    clean_table: str = Field(
        description="Target table in etl_clean, e.g. 'accounts_clean'",
    )
    rejected_table: str = Field(
        default="",
        description="Rejected-records table (defaults to <clean_table>_rejected)",
    )
    data_columns: list[str] = Field(
        description="Columns in the clean table to populate from extracted data",
    )
    meta_columns: list[str] = Field(
        default_factory=lambda: ["loaded_at", "batch_id"],
        description="ETL metadata columns appended to each row",
    )

    @model_validator(mode="after")
    def _default_rejected_table(self) -> "TargetSpec":
        if not self.rejected_table:
            self.rejected_table = f"{self.clean_table}_rejected"
        return self


# ===========================================================================
# Transform Overrides (Section 19 — per-dataset type casts & standardization)
# ===========================================================================

class StandardizationMappingSpec(BaseModel):
    """A single value mapping rule for categorical standardization."""
    model_config = {"extra": "forbid"}

    field_name: str = Field(description="Column to standardize, e.g. 'transaction_type'")
    mappings: dict[str, str] = Field(description="source_value → canonical_value, e.g. DR→DEBIT")
    default_value: str | None = Field(default=None, description="Fallback if no mapping matches")
    case_sensitive: bool = Field(default=False)
    trim_whitespace: bool = Field(default=True)


class TransformOverridesSpec(BaseModel):
    """Per-dataset transform configuration embedded in the extraction spec.

    The Dynamic Extractor handles column selection and renaming (via aliases),
    but type casting and value standardization need to happen in the transform phase.
    This section declares those rules so run_etl.py can merge them into the
    TransformationConfig before the transform phase runs.
    """
    model_config = {"extra": "forbid"}

    type_casts: dict[str, str] = Field(
        default_factory=dict,
        description="Column → target type: str, int, float, bool, datetime",
    )
    drop_columns: list[str] = Field(
        default_factory=list,
        description="Columns to drop after transformation",
    )
    standardization: list[StandardizationMappingSpec] = Field(
        default_factory=list,
        description="Categorical value standardization rules",
    )


# ===========================================================================
# Validation Overrides (Section 19 — per-spec mandatory-field override)
# ===========================================================================

class ValidationOverrideSpec(BaseModel):
    """Per-spec validation overrides merged into the ETL ValidationConfig.

    Lets a non-customer extraction spec declare its own mandatory fields
    instead of inheriting the customer-centric defaults from etl_config.yaml.
    Merged by run_etl.py before Phase 2 (ValidationService).
    """
    model_config = {"extra": "forbid"}

    enabled: bool | None = Field(
        default=None,
        description="Override validation.enabled (None = inherit global)",
    )
    mandatory_fields: list[str] | None = Field(
        default=None,
        description="Override validation.mandatory_fields (None = inherit global)",
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

    # Trust level — gates raw-SQL features (calculated_fields, EXISTS, etc.)
    # Defaults to False for production safety.  Internal specs must explicitly
    # opt in with `trusted_config: true`.
    trusted_config: bool = Field(
        default=False,
        description="If False, raw SQL expressions (calculated_fields, EXISTS) are rejected",
    )

    # Versioning (Section 7)
    versioning: VersioningSpec | None = Field(
        default=None,
        description="Engine/dataset/schema versioning (recommended for production)",
    )

    # Core extraction
    primary_entity: EntitySpec = Field(description="Driving table for extraction")
    joins: list[JoinSpec] = Field(default_factory=list, description="Secondary entities to join")
    filters: list[FilterSpec] = Field(default_factory=list, description="WHERE clause filters")

    # Pre-aggregation CTEs — prevents row multiplication from multi-table JOINs
    pre_aggregations: list[PreAggregationSpec] = Field(
        default_factory=list,
        description="CTEs pre-aggregated before joins (no row multiplication)",
    )

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

    # Per-dataset transform overrides (type casts, standardization)
    transform: TransformOverridesSpec | None = Field(
        default=None,
        description="Transform-phase type casts and standardizations for this dataset",
    )

    # ETL target configuration — where cleaned data lands in etl_clean
    target: TargetSpec | None = Field(
        default=None,
        description="Target clean table and column mapping for ETL bulk insert",
    )

    # Per-spec validation overrides (mandatory fields) for run_etl.py Phase 2
    validation: ValidationOverrideSpec | None = Field(
        default=None,
        description="Override validation.mandatory_fields / enabled for this dataset",
    )

    @model_validator(mode="after")
    def _check_aggregations_have_group_by(self) -> ExtractionConfigSpec:
        if self.aggregations and not self.group_by:
            raise ValueError("Aggregations specified but 'group_by' is empty")
        cte_names = [cte.name for cte in self.pre_aggregations]
        cte_aliases = [cte.alias for cte in self.pre_aggregations]
        if len(cte_names) != len(set(cte_names)):
            raise ValueError("Pre-aggregation CTE names must be unique")
        if len(cte_aliases) != len(set(cte_aliases)):
            raise ValueError("Pre-aggregation CTE aliases must be unique")
        unknown_cte_joins = [
            join.table for join in self.joins
            if join.table in cte_names and join.alias not in cte_aliases
        ]
        if unknown_cte_joins:
            raise ValueError(
                "A CTE join must use the alias declared by its pre-aggregation: "
                + ", ".join(sorted(set(unknown_cte_joins)))
            )
        return self
