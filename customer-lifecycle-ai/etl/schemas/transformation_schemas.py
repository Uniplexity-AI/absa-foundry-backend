"""
ETL Transformation Schemas - Pydantic v2 schemas for data transformation.

Defines:
- FieldMapping: Source-to-target column mapping definition
- StandardizationRule: Value normalization rule
- EnrichmentRule: Data enrichment configuration
- DerivedFieldRule: Derived/computed field definition
- TransformationConfig: Engine-wide configuration
- TransformationReport: Post-transform summary
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TransformType(str, Enum):
    """Types of transformation operations."""
    FIELD_MAPPING = "field_mapping"
    STANDARDIZATION = "standardization"
    LOOKUP_RESOLUTION = "lookup_resolution"
    DERIVED_FIELD = "derived_field"
    ENRICHMENT = "enrichment"
    DATE_NORMALIZATION = "date_normalization"
    TYPE_CASTING = "type_casting"


# ---------------------------------------------------------------------------
# Field Mapping
# ---------------------------------------------------------------------------

class FieldMapping(BaseModel):
    """Maps a source column to a target column.

    Supports direct mapping, renaming, and default values.
    """
    model_config = ConfigDict(extra="forbid")

    source_field: str = Field(description="Field name in the source data")
    target_field: str = Field(description="Field name in the target schema")
    data_type: str | None = Field(
        default=None,
        description="Cast to this type: str, int, float, datetime, bool",
    )
    default_value: Any = Field(
        default=None,
        description="Default value if source field is missing or null",
    )
    required: bool = Field(
        default=True,
        description="Whether this field is required in output",
    )
    description: str = Field(
        default="",
        description="Human-readable description of this mapping",
    )


# ---------------------------------------------------------------------------
# Standardization Rule
# ---------------------------------------------------------------------------

class StandardizationRule(BaseModel):
    """Maps source values to standardized target values.

    Examples:
    - DR → DEBIT
    - CR → CREDIT
    - Mobile Banking → MOBILE
    """
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(description="Unique rule identifier")
    field_name: str = Field(description="Field to standardize")
    mappings: dict[str, str] = Field(
        description="source_value → standardized_value mappings (case-insensitive keys)",
    )
    default_value: str | None = Field(
        default=None,
        description="Value to use if no mapping matches (None = keep original)",
    )
    case_sensitive: bool = Field(
        default=False,
        description="Whether matching is case-sensitive",
    )
    trim_whitespace: bool = Field(
        default=True,
        description="Trim whitespace before matching",
    )


# ---------------------------------------------------------------------------
# Derived Field Rule
# ---------------------------------------------------------------------------

class DerivedFieldRule(BaseModel):
    """Defines a field computed from other fields.

    Examples:
    - is_high_value = transaction_amount > 100000
    - year_month = transaction_date[:7]
    - full_name = first_name + " " + last_name
    """
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(description="Unique rule identifier")
    target_field: str = Field(description="Name of the derived field to create")
    expression: str = Field(description="Python expression or pre-defined function name")
    source_fields: list[str] = Field(
        default_factory=list,
        description="Source fields used in the expression",
    )
    data_type: str = Field(
        default="str",
        description="Target data type: str, int, float, bool, datetime",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional parameters for the expression",
    )
    description: str = Field(default="", description="What this derived field represents")


# ---------------------------------------------------------------------------
# Enrichment Rule
# ---------------------------------------------------------------------------

class EnrichmentRule(BaseModel):
    """Adds data from external sources via lookups.

    Examples:
    - branch_code → branch_name, branch_region
    - customer_id → customer_segment, risk_category
    """
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(description="Unique rule identifier")
    source_field: str = Field(description="Field to use as lookup key")
    lookup_type: str = Field(description="Type of lookup: branch, customer, product, etc.")
    enrich_fields: list[str] = Field(
        description="Fields to add from the enrichment source",
    )
    default_values: dict[str, Any] = Field(
        default_factory=dict,
        description="Default values if lookup fails",
    )
    description: str = Field(default="", description="What this enrichment provides")


# ---------------------------------------------------------------------------
# Transformation Config
# ---------------------------------------------------------------------------

class TransformationConfig(BaseModel):
    """Engine-wide transformation configuration.

    All mappings are stored here — nothing hardcoded in code.
    """
    model_config = ConfigDict(extra="forbid")

    # Field mappings (source → target)
    field_mappings: list[FieldMapping] = Field(
        default_factory=list,
        description="Source-to-target column mappings",
    )

    # Standardization rules
    standardization_rules: list[StandardizationRule] = Field(
        default_factory=list,
        description="Value standardization rules",
    )

    # Derived field rules
    derived_field_rules: list[DerivedFieldRule] = Field(
        default_factory=list,
        description="Computed/derived field definitions",
    )

    # Enrichment rules
    enrichment_rules: list[EnrichmentRule] = Field(
        default_factory=list,
        description="Data enrichment rules",
    )

    # Date normalization
    date_fields: list[str] = Field(
        default_factory=list,
        description="Fields to normalize to ISO date format",
    )
    date_input_formats: list[str] = Field(
        default_factory=lambda: ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"],
        description="Accepted input date formats to try",
    )
    date_output_format: str = Field(
        default="%Y-%m-%d",
        description="Output date format (ISO 8601)",
    )

    # Type casting
    type_casts: dict[str, str] = Field(
        default_factory=dict,
        description="Field → target type: str, int, float, bool",
    )

    # Column operations
    drop_columns: list[str] = Field(
        default_factory=list,
        description="Columns to drop after transformation",
    )
    reorder_columns: list[str] | None = Field(
        default=None,
        description="Desired column order (None = keep as-is)",
    )

    # Execution
    batch_size: int = Field(
        default=50000,
        ge=1,
        description="Rows per transform batch",
    )
    null_fill_values: dict[str, Any] = Field(
        default_factory=dict,
        description="Field → default value for null filling",
    )


# ---------------------------------------------------------------------------
# Transformation Report
# ---------------------------------------------------------------------------

class TransformationReport(BaseModel):
    """Summary report after transformation completes."""
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(description="Batch identifier")
    input_rows: int = Field(default=0, description="Rows before transformation")
    output_rows: int = Field(default=0, description="Rows after transformation")
    input_columns: int = Field(default=0, description="Columns before transformation")
    output_columns: int = Field(default=0, description="Columns after transformation")
    fields_mapped: int = Field(default=0, description="Number of fields mapped")
    values_standardized: int = Field(default=0, description="Number of values standardized")
    fields_derived: int = Field(default=0, description="Number of derived fields created")
    enrichments_applied: int = Field(default=0, description="Number of enrichments applied")
    dates_normalized: int = Field(default=0, description="Number of date fields normalized")
    nulls_filled: int = Field(default=0, description="Number of null values filled")
    columns_dropped: int = Field(default=0, description="Number of columns dropped")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings",
    )
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    completed_at: datetime | None = Field(default=None)
    duration_seconds: float | None = Field(default=None)
