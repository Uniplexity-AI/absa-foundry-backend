# Dynamic Extractor, Unifier & Validation Engine

**Component:** Dynamic Extractor, Unifier & Validation Engine
**Document Status:** Specification — Implementation Ready
**Target Environment:** Python 3.12+ | PostgreSQL 16 / SQLAlchemy 2.0 | Pydantic v2

---

## 1. Overview & Purpose

The **Dynamic Extractor, Unifier & Validation Engine** forms the ingestion and gatekeeping tier of the core ETL architecture. In banking environments, customer, account, and transactional data resides across fragmented, domain-isolated database schemas.

This engine provides a **declarative, configuration-driven pipeline** allowing data engineers and data scientists to:

1. Define multi-table extraction and join relationships via standardized YAML files.
2. Dynamically compile SQL queries with safety, performance, and tenant/batch isolation guardrails.
3. Automatically generate runtime **Pydantic v2 schemas** directly from validation rules defined in the extraction configuration.
4. Route failed records to a structured **Dead-Letter Queue (DLQ)** with field-level diagnostic metadata while allowing valid data to proceed to downstream transformations.

---

## 2. System Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                 Config Store (YAML Spec)                    │
│   Source Tables | Join Criteria | Filters | Field Rules    │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│           Dynamic Extraction & Unification Engine           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 1. Config Loader & Pydantic Config Validation        │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ 2. Dynamic SQLAlchemy 2.0 Query Construction         │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ 3. Batch Execution & Streaming Retrieval             │  │
│  └───────────────────────────┬───────────────────────────┘  │
└──────────────────────────────┼──────────────────────────────┘
                               │ Consolidated Record Stream
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Two-Tier Validation Engine                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Tier 1: Dynamic Pydantic v2 Schema Generation & Exec  │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ Tier 2: Business Logic & Domain Constraint Checking   │  │
│  └───────────────┬───────────────────────┬───────────────┘  │
└──────────────────┼───────────────────────┼──────────────────┘
                   │                       │
         [ Valid Records ]         [ Invalid Records ]
                   │                       │
                   ▼                       ▼
      ┌─────────────────────────┐ ┌─────────────────────────┐
      │ Transformation Engine   │ │  Dead-Letter Queue      │
      │ (Feature Store / Clean) │ │  (audit.rejected_recs)  │
      └─────────────────────────┘ └─────────────────────────┘
```

---

## 3. Configuration Specification (YAML DSL)

Every dataset extraction is governed by a declarative YAML configuration.

### 3.1 YAML Schema Reference (`extraction_spec.v1.yaml`)

```yaml
version: "1.0"
dataset_name: "customer_360_daily"
description: "Unified view merging core profiles, deposit accounts, and card transactions."

# Driving table for extraction
primary_entity:
  table: "raw.core_customers"
  alias: "cust"
  select_fields:
    - field: "customer_id"
      alias: "master_customer_id"
      validation:
        type: "str"
        required: true
        regex: "^CUST-[0-9]{8}$"
    - field: "tax_id"
      alias: "tax_id"
      validation:
        type: "str"
        required: true
    - field: "created_at"
      alias: "onboarding_date"
      validation:
        type: "datetime"
        required: true

# Secondary entities to join
joins:
  - table: "raw.core_accounts"
    alias: "acc"
    join_type: "left"  # inner, left, right, full
    on:
      cust.customer_id: "acc.primary_owner_id"
    select_fields:
      - field: "account_number"
        alias: "account_number"
        validation:
          type: "str"
          required: true
      - field: "current_balance"
        alias: "account_balance"
        validation:
          type: "decimal"
          required: false
          default: 0.00
          gt: -1000.00
          lt: 10000000.00

# Extraction filters
filters:
  - field: "cust.status"
    operator: "EQUALS"
    value: "ACTIVE"
  - field: "cust.created_at"
    operator: "GREATER_THAN_EQUAL"
    value: "2020-01-01"
```

---

## 4. Core Subsystem Implementation Details

### 4.1 Configuration Parser & Data Models

Pydantic v2 schemas validate the structure of the YAML specification file prior to job execution.

```python
# config_models.py
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


class FieldValidationSpec(BaseModel):
    type: Literal["str", "int", "float", "decimal", "datetime", "bool"] = "str"
    required: bool = True
    default: Optional[Any] = None
    regex: Optional[str] = None
    gt: Optional[float] = None
    lt: Optional[float] = None
    ge: Optional[float] = None
    le: Optional[float] = None


class SelectFieldSpec(BaseModel):
    field: str
    alias: Optional[str] = None
    validation: FieldValidationSpec = Field(default_factory=FieldValidationSpec)

    @property
    def output_name(self) -> str:
        return self.alias or self.field


class EntitySpec(BaseModel):
    table: str
    alias: str
    select_fields: List[SelectFieldSpec]


class JoinSpec(BaseModel):
    table: str
    alias: str
    join_type: Literal["inner", "left", "right", "full"] = "left"
    on: Dict[str, str]  # e.g. {"cust.customer_id": "acc.primary_owner_id"}
    select_fields: List[SelectFieldSpec]


class FilterSpec(BaseModel):
    field: str
    operator: Literal["EQUALS", "NOT_EQUALS", "GREATER_THAN_EQUAL", "LESS_THAN_EQUAL", "IN"]
    value: Any


class ExtractionConfigSpec(BaseModel):
    version: str
    dataset_name: str
    description: Optional[str] = None
    primary_entity: EntitySpec
    joins: List[JoinSpec] = Field(default_factory=list)
    filters: List[FilterSpec] = Field(default_factory=list)
```

### 4.2 Dynamic Query Builder Subsystem

The `DynamicQueryBuilder` generates parameterized SQLAlchemy `Select` statements to prevent SQL injection and enforce schema qualification.

```python
# query_builder.py
from typing import Dict
from sqlalchemy import select, Table, MetaData, create_engine
from sqlalchemy.sql import Select
from config_models import ExtractionConfigSpec


class DynamicQueryBuilder:
    def __init__(self, engine, metadata: MetaData):
        self.engine = engine
        self.metadata = metadata

    def _get_table_alias(self, table_name: str, alias_name: str):
        schema, tbl = table_name.split(".") if "." in table_name else (None, table_name)
        return Table(tbl, self.metadata, schema=schema, autoload_with=self.engine).alias(alias_name)

    def build_query(self, config: ExtractionConfigSpec) -> Select:
        prim_spec = config.primary_entity
        primary_table = self._get_table_alias(prim_spec.table, prim_spec.alias)

        alias_map: Dict[str, Any] = {prim_spec.alias: primary_table}
        columns_to_select = []

        # Select Primary Fields
        for f in prim_spec.select_fields:
            columns_to_select.append(primary_table.c[f.field].label(f.output_name))

        joined_target = primary_table

        # Process Joins
        for j_spec in config.joins:
            sec_table = self._get_table_alias(j_spec.table, j_spec.alias)
            alias_map[j_spec.alias] = sec_table

            # Parse Join Keys
            left_key, right_key = list(j_spec.on.items())[0]
            left_alias, left_col = left_key.split(".")
            right_alias, right_col = right_key.split(".")

            on_clause = (alias_map[left_alias].c[left_col] == alias_map[right_alias].c[right_col])
            is_outer = (j_spec.join_type.lower() == "left")

            joined_target = joined_target.join(sec_table, onclause=on_clause, isouter=is_outer)

            for f in j_spec.select_fields:
                columns_to_select.append(sec_table.c[f.field].label(f.output_name))

        stmt = select(*columns_to_select).select_from(joined_target)

        # Apply Filters
        for flt in config.filters:
            tbl_alias, col_name = flt.field.split(".")
            target_col = alias_map[tbl_alias].c[col_name]

            if flt.operator == "EQUALS":
                stmt = stmt.where(target_col == flt.value)
            elif flt.operator == "GREATER_THAN_EQUAL":
                stmt = stmt.where(target_col >= flt.value)
            elif flt.operator == "LESS_THAN_EQUAL":
                stmt = stmt.where(target_col <= flt.value)
            elif flt.operator == "IN":
                stmt = stmt.where(target_col.in_(flt.value))

        return stmt
```

### 4.3 Dynamic Schema Generation Factory

Transforms validation requirements into in-memory Pydantic v2 models at runtime.

```python
# schema_factory.py
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type, Annotated
from pydantic import BaseModel, Field, StringConstraints, create_model
from config_models import ExtractionConfigSpec, SelectFieldSpec

TYPE_MAPPING = {
    "str": str,
    "int": int,
    "float": float,
    "decimal": Decimal,
    "datetime": datetime,
    "bool": bool,
}


class DynamicSchemaFactory:
    @staticmethod
    def _build_field_definitions(fields: List[SelectFieldSpec]) -> Dict[str, Any]:
        defs = {}
        for f in fields:
            v_spec = f.validation
            base_type = TYPE_MAPPING.get(v_spec.type, str)
            field_kwargs = {}

            # Bounds Check
            for kw in ["gt", "lt", "ge", "le"]:
                val = getattr(v_spec, kw)
                if val is not None:
                    field_kwargs[kw] = val

            # Type Assignment
            if not v_spec.required:
                field_type = Optional[base_type]
                field_kwargs["default"] = v_spec.default
            else:
                field_type = base_type
                field_kwargs["default"] = ...

            # Regex Constraint
            if v_spec.type == "str" and v_spec.regex:
                field_type = Annotated[field_type, StringConstraints(pattern=v_spec.regex)]

            defs[f.output_name] = (field_type, Field(**field_kwargs))
        return defs

    @classmethod
    def create_model_from_config(cls, config: ExtractionConfigSpec) -> Type[BaseModel]:
        all_defs = {}
        all_defs.update(cls._build_field_definitions(config.primary_entity.select_fields))

        for j in config.joins:
            all_defs.update(cls._build_field_definitions(j.select_fields))

        model_name = f"{config.dataset_name.title().replace('_', '')}DynamicModel"
        return create_model(model_name, **all_defs)
```

---

## 5. Dead-Letter Queue (DLQ) Integration

Records failing structural or business validation are diverted to `audit.rejected_records` with error details, original batch contexts, and immutable payload copies.

### 5.1 Storage DDL

```sql
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE audit.rejected_records (
    rejection_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id          UUID NOT NULL,
    source_system     VARCHAR(50) NOT NULL,
    entity_name       VARCHAR(50) NOT NULL,
    rejection_tier    VARCHAR(10) NOT NULL,  -- 'HARD' or 'SOFT'
    status            VARCHAR(20) NOT NULL DEFAULT 'NEW',  -- NEW, RESOLVED, REPLAYED
    rule_code         VARCHAR(50) NOT NULL,
    error_details     JSONB NOT NULL,
    raw_payload       JSONB NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at       TIMESTAMPTZ NULL,
    resolved_by       VARCHAR(100) NULL
);

CREATE INDEX idx_dlq_batch_id ON audit.rejected_records(batch_id);
CREATE INDEX idx_dlq_status_tier ON audit.rejected_records(status, rejection_tier);
```

### 5.2 Execution Engine & Route Controller

```python
# executor.py
import uuid
from typing import List, Dict, Any
from pydantic import ValidationError
from config_models import ExtractionConfigSpec
from schema_factory import DynamicSchemaFactory


class IngestionPipelineExecutor:
    def __init__(self, config: ExtractionConfigSpec, batch_id: uuid.UUID):
        self.config = config
        self.batch_id = batch_id
        self.validation_model = DynamicSchemaFactory.create_model_from_config(config)

    def process_records(self, raw_records: List[Dict[str, Any]]):
        valid_records = []
        dlq_entries = []

        for record in raw_records:
            try:
                validated_obj = self.validation_model.model_validate(record)
                valid_records.append(validated_obj.model_dump())
            except ValidationError as ve:
                dlq_entries.append({
                    "rejection_id": str(uuid.uuid4()),
                    "batch_id": str(self.batch_id),
                    "source_system": "ETL_DYNAMIC_UNIFIER",
                    "entity_name": self.config.dataset_name,
                    "rejection_tier": "HARD",
                    "status": "NEW",
                    "rule_code": "ERR_STRUCTURAL_SCHEMA_VALIDATION",
                    "error_details": [
                        {
                            "field": ".".join(str(loc) for loc in err["loc"]),
                            "message": err["msg"],
                            "type": err["type"]
                        }
                        for err in ve.errors()
                    ],
                    "raw_payload": record
                })

        return valid_records, dlq_entries
```

---

## 6. Security, Compliance & Governance

1. **PII Masking & Tokenization:** Fields containing PCI/PII data (e.g., `tax_id`, `card_number`) must be tokenized or masked prior to persistence in `audit.rejected_records`.
2. **Circuit Breakers:** Pipeline execution halts if the failure rate exceeds configured thresholds (e.g., >5% batch rejection) to prevent DLQ bloat and system degradation.
3. **Query Safety:** Cross-joins are explicitly forbidden. All joins require pre-indexed foreign keys, enforced during YAML validation.
4. **Audit Trail:** Every DLQ mutation or re-injection is logged to maintain full compliance and lineage tracing.

---

## 7. YAML Configuration Versioning

### Purpose

Introduce explicit version control for extraction specifications to enable backward compatibility, configuration auditing, controlled migrations, and long-term maintainability.

### Why It Is Needed

A bare `version: "1.0"` does not distinguish between engine version, schema version, and dataset version. Large banking systems evolve continuously. Without versioning:

- Existing pipelines break on engine upgrades
- Older datasets cannot be replayed
- Historical batches become unreproducible

### Proposed YAML

```yaml
engine:
  version: "2.1"

dataset:
  version: 15

schema:
  version: 4

compatibility:
  minimum_engine: "2.0"
```

### Validation Logic

The Configuration Loader validates compatibility before execution:

```python
class VersionGuard:
    def check(self, spec: ExtractionConfigSpec, engine_version: str) -> None:
        if parse_version(spec.compatibility.minimum_engine) > parse_version(engine_version):
            raise IncompatibleSpecError(
                f"Spec requires engine >= {spec.compatibility.minimum_engine}, "
                f"current engine is {engine_version}"
            )
```

---

## 8. Join Validation Engine

### Purpose

Validate every configured join before query generation begins. If validation fails, query generation never starts — preventing runtime SQL errors.

### Architecture

```
YAML Config
     │
     ▼
Join Validator ──► Metadata Inspector (SQLAlchemy reflection)
     │
     ▼
Validation Report ──► PASS → Query Builder
     │
     └── FAIL → Abort with detailed errors
```

### Validations Performed

| Check | Description |
|---|---|
| Table exists | Verify `schema.table` is present in the database |
| Schema exists | Verify the target schema is accessible |
| Alias uniqueness | No duplicate aliases across primary entity and joins |
| Join columns exist | All referenced columns exist on their respective tables |
| Compatible datatypes | Left and right join columns share compatible types |
| Indexed foreign keys | Join columns have appropriate indexes for performance |
| Cross-join prohibition | At least one ON condition per join (no cartesian products) |
| Cyclic join detection | No circular dependencies in join graph |

### Implementation Sketch

```python
# join_validator.py
from dataclasses import dataclass, field

@dataclass
class JoinValidationReport:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class JoinValidator:
    def __init__(self, engine, metadata: MetaData):
        self._engine = engine
        self._metadata = metadata

    def validate(self, config: ExtractionConfigSpec) -> JoinValidationReport:
        report = JoinValidationReport()
        seen_aliases: set[str] = {config.primary_entity.alias}
        join_graph: dict[str, set[str]] = {}

        for join in config.joins:
            # Alias uniqueness
            if join.alias in seen_aliases:
                report.errors.append(f"Duplicate alias: {join.alias}")
            seen_aliases.add(join.alias)

            # Table existence
            schema, table = join.table.split(".") if "." in join.table else (None, join.table)
            if not self._table_exists(schema, table):
                report.errors.append(f"Table not found: {join.table}")

            # Cross-join check
            if not join.on:
                report.errors.append(f"Join '{join.alias}' has no ON clause (cross-join forbidden)")

            for left_ref, right_ref in join.on.items():
                self._validate_join_columns(left_ref, right_ref, report)

        # Cyclic detection via DFS
        if self._has_cycle(join_graph):
            report.errors.append("Cyclic join dependency detected")

        report.is_valid = len(report.errors) == 0
        return report
```

---

## 9. Advanced Filter Operators

### Purpose

The initial implementation supports only `EQUALS`, `>=`, `<=`, and `IN`. Enterprise ETL requires far richer filtering.

### Supported Operators

```
EQUALS              # =
NOT_EQUALS          # !=
GREATER_THAN        # >
LESS_THAN           # <
GREATER_THAN_EQUAL  # >=
LESS_THAN_EQUAL     # <=
BETWEEN             # col BETWEEN min AND max
IN                  # col IN (...)
NOT_IN              # col NOT IN (...)
LIKE                # col LIKE 'pattern'
ILIKE               # col ILIKE 'pattern' (case-insensitive)
REGEX               # col ~ 'regex'
IS_NULL             # col IS NULL
IS_NOT_NULL         # col IS NOT NULL
DATE_ADD            # col + INTERVAL
DATE_SUB            # col - INTERVAL
CURRENT_DATE        # col = CURRENT_DATE
CURRENT_TIMESTAMP   # col = CURRENT_TIMESTAMP
EXISTS              # EXISTS (subquery)
NOT_EXISTS          # NOT EXISTS (subquery)
AND                 # Logical AND between filters
OR                  # Logical OR between filters
```

### Example YAML

```yaml
filters:
  - field: "cust.customer_age"
    operator: BETWEEN
    value:
      min: 18
      max: 65

  - field: "cust.email"
    operator: LIKE
    value: "%@gmail.com"

  - field: "acc.balance"
    operator: GREATER_THAN
    value: 5000.00

  - field: "cust.last_login"
    operator: IS_NOT_NULL

  - operator: AND
    conditions:
      - field: "cust.country"
        operator: EQUALS
        value: "ZM"
      - field: "acc.currency"
        operator: EQUALS
        value: "ZMW"
```

### Updated FilterSpec

```python
class FilterSpec(BaseModel):
    field: str | None = None
    operator: FilterOperator
    value: Any | None = None
    conditions: list["FilterSpec"] | None = None  # For AND/OR composite filters
```

---

## 10. Multi-Column Join Engine

### Purpose

Banking systems frequently require composite keys. The original single-column `on:` syntax is insufficient.

### Old YAML (single column)

```yaml
on:
  cust.customer_id: acc.customer_id
```

### New YAML (multi-column)

```yaml
joins:
  - table: raw.accounts
    alias: acc
    join_type: left
    on:
      - left: cust.customer_id
        right: acc.customer_id
      - left: cust.branch_id
        right: acc.branch_id
      - left: cust.tenant_id
        right: acc.tenant_id
    select_fields:
      - field: account_number
```

### Generated SQL

```sql
LEFT JOIN raw.accounts AS acc
  ON  cust.customer_id = acc.customer_id
  AND cust.branch_id   = acc.branch_id
  AND cust.tenant_id   = acc.tenant_id
```

### Updated JoinSpec

```python
class JoinCondition(BaseModel):
    left: str
    right: str

class JoinSpec(BaseModel):
    table: str
    alias: str
    join_type: Literal["inner", "left", "right", "full"] = "left"
    on: list[JoinCondition]          # N conditions → AND chain
    select_fields: list[SelectFieldSpec]
```

---

## 11. Aggregation Framework

### Purpose

Enable SQL aggregation via declarative YAML without writing raw SQL. Useful for summary datasets, reporting feeds, and feature engineering.

### Supported Functions

| Function | SQL |
|---|---|
| COUNT | `COUNT(field)` |
| COUNT_DISTINCT | `COUNT(DISTINCT field)` |
| SUM | `SUM(field)` |
| AVG | `AVG(field)` |
| MIN | `MIN(field)` |
| MAX | `MAX(field)` |
| STDDEV | `STDDEV(field)` |
| VARIANCE | `VARIANCE(field)` |

### Example YAML

```yaml
aggregations:
  - function: SUM
    field: "txn.amount"
    alias: total_spending
  - function: COUNT
    field: "txn.transaction_id"
    alias: transaction_count
  - function: AVG
    field: "txn.amount"
    alias: avg_transaction_value
  - function: COUNT_DISTINCT
    field: "txn.merchant_id"
    alias: unique_merchants

group_by:
  - "cust.customer_id"
  - "cust.branch_code"
```

### Pydantic Model

```python
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
    function: AggregationFunction
    field: str
    alias: str
    distinct: bool = False
```

---

## 12. Calculated Field Engine

### Purpose

Create derived fields during extraction to prevent unnecessary downstream transformations.

### Configuration YAML

```yaml
calculated_fields:
  - name: customer_age
    expression: "EXTRACT(YEAR FROM AGE(CURRENT_DATE, cust.date_of_birth))"
    output_type: int

  - name: tenure_days
    expression: "CURRENT_DATE - cust.activation_date::DATE"
    output_type: int

  - name: risk_score
    expression: >
      CASE
        WHEN cust.status = 'DORMANT' THEN 80
        WHEN acc.balance < 100 THEN 60
        ELSE 20
      END
    output_type: int
```

### Pydantic Model

```python
class CalculatedFieldSpec(BaseModel):
    name: str
    expression: str              # Raw SQL expression
    output_type: Literal["str", "int", "float", "decimal", "datetime", "bool"]
    description: str | None = None
```

---

## 13. Incremental Extraction Engine

### Purpose

Extract only changed records since the last successful run, dramatically reducing load times and database impact.

### Architecture

```
Watermark Store (etl.extraction_watermarks)
     │
     ▼
Read last successful run timestamp
     │
     ▼
Query Builder appends: WHERE updated_at > {watermark}
     │
     ▼
Extract delta records
     │
     ▼
After success → update watermark
```

### Configuration YAML

```yaml
incremental:
  enabled: true
  watermark_column: "cust.updated_at"
  strategy: timestamp          # timestamp | change_tracking | cdc
  lookback_minutes: 60         # safety overlap window
```

### Watermark Store DDL

```sql
CREATE TABLE etl.extraction_watermarks (
    dataset_name    VARCHAR(100) PRIMARY KEY,
    last_extracted  TIMESTAMPTZ NOT NULL,
    batch_id        UUID NOT NULL,
    records_count   BIGINT NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## 14. Streaming & Pagination Engine

### Purpose

Replace bulk `List[Dict]` loading with cursor-based streaming. Memory usage remains constant regardless of dataset size.

### Architecture

```
Database Cursor (server-side)
     │
     ▼
Generator yields chunks
     ├─► Chunk 1 (10K rows) → Validate → Persist
     ├─► Chunk 2 (10K rows) → Validate → Persist
     └─► ...
```

### Configuration YAML

```yaml
streaming:
  enabled: true
  batch_size: 10000
  fetch_strategy: cursor        # cursor | keyset | offset
  keyset_column: "customer_id"  # for keyset pagination
```

### Implementation Sketch

```python
class StreamingExtractor:
    def extract(self, query: Select, batch_size: int = 10000):
        with self.engine.connect() as conn:
            result = conn.execution_options(
                stream_results=True,
                max_row_buffer=batch_size
            ).execute(query)

            for partition in result.partitions(batch_size):
                yield [row._asdict() for row in partition]
```

---

## 15. Parallel Execution Framework

### Purpose

Run multiple extraction jobs concurrently for independent datasets (e.g., Customer, Account, Card, Loan extractions simultaneously).

### Architecture

```
┌─────────────┐
│  Scheduler  │  (cron / Prefect / Airflow trigger)
└──────┬──────┘
       ▼
┌─────────────┐
│  Task Queue │  (Redis / RabbitMQ)
└──────┬──────┘
       ▼
┌──────────────────────────────────────────────┐
│              Worker Pool                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ Worker 1 │ │ Worker 2 │ │ Worker N │      │
│  │ Customer │ │ Account  │ │   Card   │      │
│  └──────────┘ └──────────┘ └──────────┘      │
└──────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│ Result Merge │
└──────────────┘
```

### Recommended Technologies

| Layer | Options |
|---|---|
| Orchestration | Prefect, Apache Airflow, Dagster |
| Task Queue | Redis + RQ, Celery + RabbitMQ |
| Concurrency | `asyncio`, `concurrent.futures.ProcessPoolExecutor` |
| Distributed | Ray (for ML-heavy workloads) |

### Example — asyncio-based parallelism

```python
import asyncio

async def run_parallel_extractions(specs: list[ExtractionConfigSpec]):
    tasks = [
        asyncio.to_thread(execute_extraction, spec)
        for spec in specs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

---

## 16. Metadata Repository

### Purpose

Store metadata for every extraction job, dataset, and pipeline run. Enables lineage, auditing, governance, impact analysis, and reproducibility.

### Core Tables

```sql
-- Dataset registry
CREATE TABLE etl.datasets (
    dataset_id      SERIAL PRIMARY KEY,
    dataset_name    VARCHAR(100) UNIQUE NOT NULL,
    description     TEXT,
    source_system   VARCHAR(50) NOT NULL,
    owner           VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Versioned dataset definitions
CREATE TABLE etl.dataset_versions (
    version_id      SERIAL PRIMARY KEY,
    dataset_id      INT REFERENCES etl.datasets(dataset_id),
    version_number  INT NOT NULL,
    yaml_spec       JSONB NOT NULL,
    checksum        VARCHAR(64) NOT NULL,  -- SHA-256 of YAML
    created_by      VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(dataset_id, version_number)
);

-- Pipeline execution history
CREATE TABLE etl.pipeline_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_name    VARCHAR(100) NOT NULL,
    version_number  INT,
    batch_id        UUID NOT NULL,
    status          VARCHAR(20) NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    rows_extracted  BIGINT DEFAULT 0,
    rows_valid      BIGINT DEFAULT 0,
    rows_rejected   BIGINT DEFAULT 0,
    duration_seconds NUMERIC(10,2),
    error_message   TEXT,
    triggered_by    VARCHAR(100)
);

-- Field-level lineage
CREATE TABLE etl.field_mappings (
    mapping_id      SERIAL PRIMARY KEY,
    dataset_name    VARCHAR(100) NOT NULL,
    source_table    VARCHAR(100) NOT NULL,
    source_column   VARCHAR(100) NOT NULL,
    target_column   VARCHAR(100) NOT NULL,
    transformation  TEXT,
    version_number  INT
);

-- Configuration change log
CREATE TABLE etl.config_versions (
    change_id       SERIAL PRIMARY KEY,
    dataset_name    VARCHAR(100) NOT NULL,
    old_checksum    VARCHAR(64),
    new_checksum    VARCHAR(64),
    diff            JSONB,
    changed_by      VARCHAR(100),
    changed_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

---

## 17. Observability & Monitoring

### Purpose

Every pipeline execution emits structured metrics for real-time monitoring, alerting, and dashboarding.

### Metrics

| Metric | Type | Description |
|---|---|---|
| `records_extracted` | Counter | Total rows pulled from source |
| `records_valid` | Counter | Rows passing all validation |
| `records_failed` | Counter | Rows routed to DLQ |
| `rows_per_second` | Gauge | Extraction throughput |
| `memory_usage_mb` | Gauge | Current process memory |
| `cpu_usage_pct` | Gauge | Current process CPU |
| `retry_count` | Counter | Extraction retries |
| `validation_time_ms` | Histogram | Validation duration |
| `query_time_ms` | Histogram | SQL execution duration |
| `pipeline_duration_seconds` | Gauge | Full pipeline wall-clock time |
| `dlq_rate_pct` | Gauge | (failed / total) × 100 |

### Technology Stack

```
Application → OpenTelemetry SDK → Prometheus → Grafana → AlertManager
```

### Alert Rules

```yaml
alerts:
  - name: HighDLQRate
    condition: dlq_rate_pct > 5
    severity: warning
    action: slack

  - name: PipelineStalled
    condition: pipeline_duration_seconds > 3600
    severity: critical
    action: pagerduty

  - name: ExtractionFailure
    condition: status == "FAILED"
    severity: critical
    action: pagerduty
```

---

## 18. Business Rules Engine

### Purpose

Structural validation (types, nulls, regex) is insufficient. Business constraints must execute as a separate, configurable tier.

### Architecture

```
Raw Records
     │
     ▼
Tier 1: Structural Validation (Pydantic v2)
     │ valid records
     ▼
Tier 2: Business Rules Engine (expression evaluator)
     ├── PASS → Transformation Engine
     └── FAIL → DLQ with rule_code
```

### Configuration YAML

```yaml
business_rules:
  - id: BR001
    name: "Account balance must be non-negative"
    expression: "account_balance >= 0"
    severity: ERROR
    message: "Negative balance detected"

  - id: BR002
    name: "Customer must be 18 or older"
    expression: "customer_age >= 18"
    severity: ERROR

  - id: BR003
    name: "Premium customers must have minimum balance"
    expression: "customer_type != 'PREMIUM' OR account_balance >= 50000"
    severity: WARNING
```

### Pydantic Model

```python
class BusinessRuleSeverity(str, Enum):
    ERROR = "ERROR"     # Route to DLQ, halt if threshold exceeded
    WARNING = "WARNING" # Accept record but flag
    INFO = "INFO"       # Log only


class BusinessRuleSpec(BaseModel):
    id: str
    name: str
    expression: str       # Python expression evaluated against record dict
    severity: BusinessRuleSeverity = BusinessRuleSeverity.ERROR
    message: str | None = None
```

### Benefits

- No hardcoded business logic in extraction code
- Rules are reusable across datasets
- Configurable per dataset without code changes
- Clean separation: structural checks vs. domain rules
