# Enterprise ETL Engine — Detailed Architecture Design

**Customer Lifecycle Prediction System**
**Date:** 2026-07-20
**Version:** 2.0
**Status:** Production-Hardened — Implementation Complete

---

## 1. Overview

The ETL Engine is the data integration backbone of the Customer Lifecycle Prediction System. It ingests banking transaction data from CSV or database sources, validates every row against 10 configurable business rules, transforms validated data, and loads it into the analytical database with an immutable compliance audit trail.

### 1.1 Core Capabilities

| Capability | Description |
|---|---|
| **Multi-source ingestion** | CSV file connector (production); database, API, and streaming connectors scaffolded for future phases |
| **10-rule validation** | Schema integrity, mandatory fields, business rules (currency, channel, date, amount), duplicate detection, referential integrity |
| **Schema drift detection** | Three modes (strict/warn/off); strict mode fails loudly on missing, extra, or reordered columns with a detailed diff |
| **Bulk loading** | `psycopg2.extras.execute_values` with 5,000-row chunks achieving ~17,000 rows/second |
| **Constraint rescue** | Rows that fail PostgreSQL CHECK/NOT NULL constraints are rescued to the rejected table rather than silently dropped |
| **Immutable audit trail** | Append-only `etl.etl_audit` table with 7-year retention, JSONB tags, and full batch lineage |
| **Idempotency guard** | SHA-256 file hash stored in audit trail; re-running the same file is detected and skipped unless `--force` is used |
| **Data-agnostic invariants** | Post-load conservation check (clean + rejected + rescued = total input), zero-silent-skips verification |

### 1.2 Position in the System

The ETL Engine sits between source data providers (Core Banking System via CSV/DB extract) and the downstream AI pipeline. It feeds `customer_transactions_clean` to the Feature Engineering Service, which computes point-in-time features consumed by the Customer State Service (Layer 1), Prediction Service (Layer 2), and Decision Intelligence Service (Layer 3).

### 1.3 Runtime Model

The ETL Engine runs as a **batch CLI process**, not a persistent service. It is triggered manually via `python run_etl.py` during the PoC, with scheduling (cron/systemd timer) planned for Month 2. This design keeps the ETL stateless between runs — all state is persisted in the database (audit trail, batch IDs, file hashes).

---

## 2. Module Directory Structure

```
etl/
├── connectors/              # Data source abstraction layer
│   ├── interfaces.py        # Connector ABC, DatabaseConnector, FileConnector, ApiConnector
│   ├── factory.py           # Connector registry + create_connector() factory
│   ├── files/
│   │   └── connectors.py    # CsvConnector, ExcelConnector, JsonConnector, XmlConnector
│   ├── database/            # PostgreSQL, SQL Server, Oracle, MySQL connectors (scaffolded)
│   ├── api/                 # REST, SOAP connectors (scaffolded)
│   ├── streaming/           # Kafka, Debezium, CDC connectors (future)
│   └── banking/             # Core banking system-specific adapters (future)
├── ingestion/               # Batch ID generation, checksum computation, metadata capture
├── landing/                 # Immutable raw data storage (time-partitioned)
├── validation/              # Data quality validation engine
│   ├── interfaces.py        # BaseValidator ABC
│   ├── service.py           # ValidationService — orchestrates the validator chain
│   ├── validators/
│   │   ├── schema_validator.py              # SCHEMA-001, SCHEMA-002
│   │   ├── mandatory_field_validator.py     # MANDATORY-{FIELD}
│   │   ├── business_rule_validator.py       # BUSINESS-CUR/CHN/DATE/AMT/TXN-001, -002
│   │   ├── duplicate_detector.py            # DUP-001, DUP-002
│   │   └── referential_integrity_validator.py  # RI-001 through RI-004
│   └── rules/               # Configurable rule definitions
├── transformation/          # Data transformation pipeline
│   ├── mappers/             # Field mapping: source column → target column
│   ├── standardizers/       # Value normalization: dates, currencies, case
│   └── enrichers/           # Derived field computation
├── staging/                 # Temporary validated-data tables
├── loading/                 # Production database loading engine
│   ├── service.py           # LoadingService — topological ordering + execution
│   └── repository.py        # LoadingRepository — upsert/append via SQLAlchemy
├── orchestration/           # DAG-based pipeline orchestration (scaffolded)
├── checkpoint/              # Resumable processing with state persistence (scaffolded)
├── monitoring/              # Real-time pipeline observability (scaffolded)
├── logging/                 # Structured JSON logging (7 log streams)
├── audit/                   # Compliance audit trail service
├── config/                  # Centralized configuration
│   ├── service.py           # ETLConfig — loads from YAML + env var overrides
│   └── etl_config.yaml      # Declarative pipeline configuration
├── pipelines/               # Assembled end-to-end ETL pipeline definitions
├── repositories/            # Data access layer (repository pattern)
├── services/                # Business logic layer
├── models/                  # SQLAlchemy 2.0 ORM models
├── schemas/                 # Pydantic v2 data schemas
│   ├── validation_schemas.py  # ValidationError, ValidationReport, ValidationConfig, etc.
│   ├── connector_schemas.py   # ConnectorConfig, BatchMetadata, Dataset, SourceType
│   ├── loading_schemas.py     # LoadStep, LoadStepResult, LoadPipelineConfig, etc.
│   └── audit_schemas.py       # AuditRecord, AuditConfig
└── utils/                   # Helper utilities (hashing, serialization, retry)
```

---

## 3. Design Principles

| # | Principle | Implementation |
|---|---|---|
| 1 | **Fail Loudly, Never Silently** | Schema drift → `SchemaDriftError`; constraint violations → rescued to rejected table; invariant violations → logged at CRITICAL. Zero rows are ever silently dropped. |
| 2 | **Immutable Audit Trail** | `etl.etl_audit` is append-only; 7-year retention; every batch links to its source file via SHA-256 hash. |
| 3 | **Configurable Everything** | Validation rules, accepted values, field mappings, transformation logic, and loading strategies are all defined in `etl_config.yaml` — no hardcoded business logic. |
| 4 | **Conservation Law** | After every batch: `rows_clean + rows_rejected + rows_rescued = rows_input`. This invariant is programmatically verified. |
| 5 | **Idempotency by Default** | SHA-256 file hash prevents accidental double-processing. `--force` required for intentional re-processing. |
| 6 | **Chain of Responsibility** | Validators execute in fixed order; each receives results from the previous; already-invalid records are skipped by downstream validators. |
| 7 | **Repository Pattern** | All database access goes through repository classes; no raw SQL in services or validators. |
| 8 | **Separation of Concerns** | Extract, validate, transform, and load are distinct, independently testable phases with clear interface contracts. |

---

## 4. Pipeline Execution Architecture

### 4.1 Entry Point: `run_etl.py`

The main CLI entry point is a single-file, self-contained pipeline orchestrator. It can be invoked as a CLI tool or imported as a Python module.

**CLI Interface:**

```
python run_etl.py [--csv PATH] [--dry-run] [--force]
```

| Argument | Default | Description |
|---|---|---|
| `--csv` | `scripts/etl_validation_customers.csv` | Path to input CSV file |
| `--dry-run` | `False` | Validate only — no database writes |
| `--force` | `False` | Bypass idempotency guard and re-process |

**Exit codes:** `0` = success or intentionally skipped; `1` = pipeline failure.

### 4.2 Pipeline Orchestrator: `run_etl_pipeline()`

```
async run_etl_pipeline(csv_path, dry_run=False, force=False, triggered_by="cli") -> dict
```

This is the core orchestrator. It executes four sequential phases:

**Phase 1 — EXTRACT:**
1. Load `ETLConfig` from `etl_config.yaml` (with environment variable overrides).
2. Build `ConnectorConfig(source_type=SourceType.CSV, file_path=csv_path)`.
3. Call `create_connector(config)` → returns `CsvConnector` instance.
4. Iterate `connector.extract()` async iterator; concatenate all chunks into a single `pd.DataFrame`.
5. Run `_validate_schema(df, expected_columns, mode, source_name)`:
   - `strict` mode (default): Missing/extra/reordered columns raise `SchemaDriftError` — pipeline aborts.
   - `warn` mode: Drift logged at WARNING; pipeline continues.
   - `off` mode: Check skipped entirely.

**Phase 2 — VALIDATE:**
1. Instantiate `ValidationService(config=config.validation)`.
2. Call `await validation_service.validate(df, batch_id)` → returns `ValidationReport`.
3. Split DataFrame into `valid_df` (rows where `is_valid=True`) and `invalid_df` (rows where `is_valid=False`).

**Phase 3 — TRANSFORM:**
1. Instantiate `TransformationService(config=config.transformation)`.
2. Call `transform(valid_df, batch_id)` → returns transformed DataFrame with standardized dates, normalized values, and enriched fields.

**Phase 4 — LOAD:**
1. Call `bulk_insert_clean(transformed_records, batch_id)` → `(inserted, rescued)`.
2. Call `bulk_insert_rejected(rejected_records, batch_id, reasons)` → rejected count.
3. Call `_run_invariant_checks(total_input, inserted, rejected_count, rescued, quality_score, batch_id)`.
4. Call `write_audit_record(...)` with complete batch statistics.
5. Return result dictionary with `run_id`, `batch_id`, `status`, row counts, `quality_score`, `duration_seconds`.

### 4.3 Key Constants

| Constant | Value | Purpose |
|---|---|---|
| `BATCH_SIZE` | `5000` | Rows per bulk insert chunk |
| `QUALITY_WARN_THRESHOLD` | `90.0` | Quality score below which a WARNING is emitted |
| `QUALITY_ERROR_THRESHOLD` | `70.0` | Quality score below which a CRITICAL error is raised |

---

## 5. Validation Engine Design

### 5.1 Architecture Pattern: Chain of Responsibility

Five validators execute in a fixed, non-configurable order. Each validator receives the accumulated results from all previous validators. Records already marked invalid by an earlier validator are skipped by downstream validators — preventing duplicate error reporting and reducing unnecessary computation.

**Execution order:** SchemaValidator → MandatoryFieldValidator → BusinessRuleValidator → DuplicateDetector → ReferentialIntegrityValidator

### 5.2 Base Class: `BaseValidator` (ABC)

```
class BaseValidator(ABC):
    def __init__(self, config: ValidationConfig) -> None
    @property @abstractmethod
    def category(self) -> str
    @abstractmethod
    async def validate(self, df: pd.DataFrame, existing_results: list[RecordValidationResult] | None = None) -> list[RecordValidationResult]
    @abstractmethod
    def validate_record(self, row: dict, row_index: int) -> RecordValidationResult
    @property
    def error_count(self) -> int
    def reset(self) -> None
```

Each validator tracks its own `_error_count`. The `reset()` method zeroes it before each batch run.

### 5.3 Orchestrator: `ValidationService`

```
class ValidationService:
    def __init__(self, config: ValidationConfig | None = None, lookup_provider: LookupProvider | None = None)
    async def validate(self, df: pd.DataFrame, batch_id: str) -> ValidationReport
```

**Validation flow:**
1. If `config.enabled` is `False`, return `PASSED` report immediately — no validators execute.
2. Instantiate all five validators via `_build_validator_chain()`.
3. For each validator in chain order:
   - Skip if its category is not in `config.categories`.
   - Call `validator.reset()`.
   - Call `await validator.validate(df, existing_results)`.
   - Pass results to next validator as `existing_results`.
4. Aggregate all results into a `ValidationReport`:
   - Compute `quality_score` from error/warning counts.
   - Set status: `PASSED` (0 invalid), `FAILED` (0 valid), `PARTIAL` (mixed).

### 5.4 Validator Specifications

#### 5.4.1 SchemaValidator

| Attribute | Detail |
|---|---|
| **Category** | `schema` |
| **Type** | Batch-level (not per-record) |
| **Rules** | `SCHEMA-001`: Missing/extra/reordered columns → ERROR on all rows |
| | `SCHEMA-002`: Empty DataFrame (0 rows) → ERROR |
| **Behavior** | If schema errors exist, ALL rows are marked invalid with the same schema errors. Otherwise all rows pass. This validator gates the entire pipeline — if the schema is wrong, nothing proceeds. |

#### 5.4.2 MandatoryFieldValidator

| Attribute | Detail |
|---|---|
| **Category** | `mandatory_fields` |
| **Type** | Per-record |
| **Fields Checked** | `customer_id`, `account_id`, `branch_code`, `transaction_date`, `transaction_type`, `channel`, `currency`, `amount` |
| **Rules** | `MANDATORY-CUSTOMER_ID`, `MANDATORY-ACCOUNT_ID`, `MANDATORY-BRANCH_CODE`, `MANDATORY-TRANSACTION_DATE`, `MANDATORY-TRANSACTION_TYPE`, `MANDATORY-CHANNEL`, `MANDATORY-CURRENCY`, `MANDATORY-AMOUNT` |
| **Missing Detection** | Field not in row keys, value is `None`, `pd.isna()` returns `True`, or value is empty string after stripping |
| **Alternative Fields** | Config supports `alternative_fields` mapping (e.g., `branch_code` can be satisfied by `branch_name` if present) |
| **Skip Logic** | Records already invalid from SchemaValidator are skipped |

#### 5.4.3 BusinessRuleValidator

| Attribute | Detail |
|---|---|
| **Category** | `business_rule` |
| **Type** | Per-record |
| **Rules** | 6 rule categories producing up to 10 distinct rule IDs |

**Rule Details:**

| Rule ID | Category | Check | Strategy |
|---|---|---|---|
| `BUSINESS-CUR-001` | Currency | `currency` not in `config.accepted_currencies` (ZMW, ZAR, USD, EUR, GBP) | Reject |
| `BUSINESS-CHN-001` | Channel | `channel` not in `config.accepted_channels` (BRANCH, ATM, POS, ONLINE, MOBILE, INTERNET) | Reject |
| `BUSINESS-DATE-001` | Date Format | `transaction_date` does not match any `config.accepted_date_formats` | Reject |
| `BUSINESS-DATE-002` | Future Date | `transaction_date` > `today + config.max_future_date_days` (default 365) | Reject |
| `BUSINESS-AMT-001` | Amount | `amount` <= 0 | Reject |
| `BUSINESS-AMT-002` | Amount | `amount` > `config.max_transaction_amount` (default 100,000,000) | Reject |
| `BUSINESS-AMT-003` | Amount | `amount` is non-numeric (cannot be cast to float) | Reject |
| `BUSINESS-TXN-001` | Transaction Type | `transaction_type` not in `config.accepted_transaction_types` (CREDIT, DEBIT, TRANSFER, PAYMENT) | Reject |

**Config-driven rules:** In addition to the hardcoded checks above, `BusinessRuleValidator` evaluates any rules defined in `config.rules[]`. Each rule specifies a `condition` (`"not_null"`, `"positive"`, `"in_list"`, `"not_in_list"`), a `field_name`, and `params` (e.g., the list of accepted values). This allows new business rules to be added declaratively without code changes.

**Merging:** New errors are appended to `prev.errors` from earlier validators — the BusinessRuleValidator never discards MandatoryFieldValidator results. Processing aborts if `_error_count >= config.max_errors_per_batch` (default 10,000) to prevent runaway error accumulation.

#### 5.4.4 DuplicateDetector

| Attribute | Detail |
|---|---|
| **Category** | `duplicate` |
| **Type** | Per-record with internal state |
| **State** | Maintains `_seen_hashes` (set of SHA-256 hashes) and `_seen_fuzzy` (set of fuzzy keys) across all records in the batch |

**Two-tier detection:**

| Rule ID | Type | Method | Strategy |
|---|---|---|---|
| `DUP-001` | Exact duplicate | SHA-256 hash of 8-field composite key: `customer_id + account_id + branch_code + transaction_date + amount + transaction_type + channel + currency`. All values normalized: strings → `.strip().lower()`, floats → `round(val, 2)`. | Configurable: `reject` → ERROR; `flag` → WARNING |
| `DUP-002` | Near-duplicate | Fuzzy hash on 7 fields (excludes `amount`) with amount rounded to nearest 100. Designed to catch data entry variations (e.g., same transaction entered twice with slightly different amounts). | Configurable: `reject` → ERROR; `flag` → WARNING |

**`reset()` behavior:** Clears both `_seen_hashes` and `_seen_fuzzy` sets. Called before each batch.

#### 5.4.5 ReferentialIntegrityValidator

| Attribute | Detail |
|---|---|
| **Category** | `referential_integrity` |
| **Type** | Per-record with cached lookups |
| **Prerequisite** | Requires a `LookupProvider` implementation (database-backed in production) |

**Rules:**

| Rule ID | Check | Severity |
|---|---|---|
| `RI-001` | `customer_exists(customer_id)` returns `False` | ERROR |
| `RI-002` | `account_exists(account_id)` returns `False` | ERROR |
| `RI-003` | `branch_exists(branch_code)` returns `False` | ERROR |
| `RI-004` | `account_belongs_to_customer(account_id, customer_id)` returns `False` | WARNING |

**Caching:** All lookup results are cached per batch via `_cached_lookup(cache_key, lookup_fn, *args)` — a single customer ID is looked up once regardless of how many transactions reference it. Cache is cleared on `reset()`.

**Conditional inclusion:** Only added to the validator chain if `lookup_provider` is supplied to `ValidationService` AND `config.referential_integrity_enabled` is `True`.

### 5.5 `LookupProvider` Protocol

```
class LookupProvider(Protocol):
    async def customer_exists(self, customer_id: str) -> bool: ...
    async def account_exists(self, account_id: str) -> bool: ...
    async def branch_exists(self, branch_code: str) -> bool: ...
    async def account_belongs_to_customer(self, account_id: str, customer_id: str) -> bool: ...
```

A database-backed implementation queries `customer_transactions_clean` and reference tables. A mock implementation (returning `True` for all checks) is used in tests when referential integrity validation is not the focus.

### 5.6 Quality Scoring

```
error_penalty = min(total_errors * 5.0 / total_records * 100, 80)
warning_penalty = min(total_warnings * 1.0 / total_records * 100, 20)
quality_score = max(100.0 - error_penalty - warning_penalty, 0.0)
```

**Design rationale:** Errors are weighted 5× higher than warnings because an error represents a definitively invalid record, while a warning flags a potential concern. The caps (80 for errors, 20 for warnings) ensure a batch with a single systemic schema error doesn't score 0 — the quality score remains interpretable even under degraded conditions.

### 5.7 `ValidationReport` Structure

| Field | Type | Description |
|---|---|---|
| `batch_id` | `str` | UUID linking to the ETL batch |
| `status` | `ValidationStatus` | `PASSED`, `FAILED`, or `PARTIAL` |
| `total_records` | `int` | Total rows processed |
| `valid_records` | `int` | Rows passing all validators |
| `invalid_records` | `int` | Rows failing at least one validator |
| `warning_records` | `int` | Rows with warnings only (no errors) |
| `duplicate_records` | `int` | Rows flagged by DuplicateDetector |
| `total_errors` | `int` | Sum of all error-level validation failures |
| `total_warnings` | `int` | Sum of all warning-level validation results |
| `error_by_category` | `dict[str, int]` | Error count per validation category |
| `error_by_rule` | `dict[str, int]` | Error count per rule ID |
| `record_results` | `list[RecordValidationResult]` | Per-row results (errors, warnings, validity) |
| `quality_score` | `float` | 0.0–100.0 composite quality metric |
| `pass_rate` | `float` | `valid_records / total_records` |

---

## 6. Configuration Architecture

### 6.1 `ETLConfig` — Central Configuration Object

```
class ETLConfig:
    landing: LandingZoneConfig
    staging: StagingConfig
    checkpoint: CheckpointConfig
    logging: LoggingConfig
    audit: AuditConfig
    monitoring: MonitoringConfig
    loading: LoadPipelineConfig
    orchestration_pipeline: PipelineDefinition
    validation: ValidationConfig
    transformation: TransformationConfig
    schema_mode: str = "strict"       # "strict" | "warn" | "off"
    expected_columns: list[str]        # 9 expected columns
```

### 6.2 Configuration Precedence

1. **Base:** `etl/config/etl_config.yaml` — declarative defaults for all settings.
2. **Override:** Environment variables — any `ETL_*` env var overrides the corresponding YAML key.
3. **Runtime:** `ETLConfig.load(config_path)` accepts an optional path to an alternative YAML file for environment-specific configurations.

### 6.3 `etl_config.yaml` — Key Sections

**Schema:**
```yaml
schema:
  mode: strict
  expected_columns: [customer_id, account_id, branch_code, transaction_date, transaction_type, channel, currency, amount, data_issue]
```

**Validation:**
```yaml
validation:
  enabled: true
  mandatory_fields: [customer_id, account_id, branch_code, transaction_date, transaction_type, channel, currency, amount]
  accepted_currencies: [ZMW, ZAR, USD, EUR, GBP]
  accepted_transaction_types: [CREDIT, DEBIT, TRANSFER, PAYMENT]
  accepted_channels: [BRANCH, ATM, POS, ONLINE, MOBILE, INTERNET]
  accepted_date_formats: ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]
  min_transaction_amount: 0.01
  max_transaction_amount: 100000000
  max_future_date_days: 365
  duplicate_detection_enabled: true
  duplicate_keys: [customer_id, account_id, branch_code, transaction_date, amount, transaction_type, channel, currency]
  exact_duplicate_strategy: reject
  near_duplicate_strategy: flag
  referential_integrity_enabled: false
  stop_on_first_error: false
  max_errors_per_batch: 10000
```

**Transformation:**
```yaml
transformation:
  date_fields: [transaction_date]
  date_output_format: "%Y-%m-%d"
  null_fill_values:
    branch_name: "UNKNOWN"
    currency: "ZAR"
```

### 6.4 `ValidationConfig` — Complete Schema

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | `bool` | `True` | Master switch — if `False`, validation is bypassed entirely |
| `categories` | `list[str]` | All 5 | Which validator categories to execute |
| `rules` | `list[ValidationRule]` | `[]` | Additional config-driven business rules |
| `mandatory_fields` | `list[str]` | 8 fields | Fields that must be non-null and non-empty |
| `alternative_fields` | `dict[str, str]` | `{}` | Alternative field names (e.g., `branch_code` → `branch_name`) |
| `accepted_currencies` | `list[str]` | 5 currencies | Valid currency codes |
| `accepted_transaction_types` | `list[str]` | 4 types | Valid transaction types |
| `accepted_channels` | `list[str]` | 6 channels | Valid transaction channels |
| `accepted_date_formats` | `list[str]` | 3 formats | Valid date string formats |
| `min_transaction_amount` | `float` | `0.01` | Minimum valid amount |
| `max_transaction_amount` | `float` | `100000000` | Maximum valid amount |
| `max_future_date_days` | `int` | `365` | Maximum days into the future a date can be |
| `duplicate_detection_enabled` | `bool` | `True` | Enable duplicate detection |
| `duplicate_keys` | `list[str]` | 8 fields | Composite key for exact duplicate hashing |
| `near_duplicate_threshold` | `float` | `0.95` | Similarity threshold for near-duplicate detection |
| `exact_duplicate_strategy` | `str` | `"reject"` | `"reject"` or `"flag"` |
| `near_duplicate_strategy` | `str` | `"flag"` | `"reject"` or `"flag"` |
| `referential_integrity_enabled` | `bool` | `False` | Enable referential integrity checks |
| `stop_on_first_error` | `bool` | `False` | Abort on first error (debugging) |
| `max_errors_per_batch` | `int` | `10000` | Maximum errors before aborting validation |

---

## 7. Connector Architecture

### 7.1 Abstract Hierarchy

```
Connector (ABC)
├── connect() / disconnect()
├── extract() -> AsyncIterator[Dataset]
├── validate_connection()
├── __aenter__ / __aexit__ (async context manager)
│
├── DatabaseConnector(Connector, ABC)
│   └── get_table_names() / get_table_schema() / get_row_count()
│
├── FileConnector(Connector, ABC)
│   └── list_files() / get_file_metadata()
│
└── ApiConnector(Connector, ABC)
    └── get_endpoints()
```

### 7.2 Factory + Registry Pattern

Connectors are registered via a decorator-based registry:

```python
@register_connector(SourceType.CSV, ConnectorInfo(display_name="CSV File", ...))
class CsvConnector(BaseFileConnector):
    ...
```

The factory function `create_connector(config: ConnectorConfig) -> Connector` looks up the registry by `config.source_type` and instantiates the matching connector. Unregistered source types raise `ValueError`.

### 7.3 `CsvConnector` — Primary Production Connector

| Attribute | Detail |
|---|---|
| **Class** | `CsvConnector(BaseFileConnector)` |
| **Registration** | `@register_connector(SourceType.CSV, ...)` |
| **Read Method** | `pd.read_csv(file_path, delimiter=config.delimiter, encoding=config.encoding, header=0 if config.has_header else None, low_memory=False)` |
| **Extract Method** | `async def extract() -> AsyncIterator[Dataset]` — yields one `Dataset` per file. Each `Dataset` contains a `pd.DataFrame` and `BatchMetadata` with `batch_id` (UUID), `source_type`, `source_name`, `extracted_at`, `total_rows`, `total_chunks`, `file_path`, `checksum_sha256`. |
| **Error Handling** | `RuntimeError` if not connected; wraps original exception in `RuntimeError` on read failure. |

---

## 8. Loading Engine & Bulk Insert Strategy

### 8.1 Bulk Insert: `bulk_insert_clean()`

```
bulk_insert_clean(records: list[dict], batch_id: str) -> tuple[int, int]
```

Returns `(inserted_count, rescued_count)`.

**Algorithm:**
1. Convert `records` to list of tuples matching column order: `(customer_id, account_id, branch_code, transaction_date, transaction_type, channel, currency, amount, loaded_at, source_row_id, batch_id)`.
2. Call `psycopg2.extras.execute_values(cursor, sql, values, template=..., page_size=5000)` — inserts 5,000 rows per round-trip.
3. On batch failure → rollback to savepoint → fall back to row-by-row insert.
4. On single-row failure during fallback → rollback → insert row into `customer_transactions_rejected` with `rejection_reason="db_constraint_violation: {PostgreSQL error message}"`.
5. Return `(successfully_inserted, rescued_to_rejected)`.

**Performance:** ~17,000 rows/second on the provisioned 8-core CPU with 70K-row batches.

### 8.2 Rejected Row Insert: `bulk_insert_rejected()`

```
bulk_insert_rejected(records: list[dict], batch_id: str, reasons: list[str]) -> int
```

Same batch/fallback pattern as `bulk_insert_clean`. Default rejection reason is `"Validation failed"`. The `reasons` list is parallel to `records` — `reasons[i]` corresponds to `records[i]`.

### 8.3 `LoadingService` — Ordered Production Load

```
class LoadingService:
    def __init__(self, loading_repo: LoadingRepository, staging_repo: StagingRepository | None = None, config: LoadPipelineConfig | None = None)
    async def execute(self, batch_id: str) -> LoadPipelineResult
```

**Load order (topological sort by `depends_on`):**
1. `load_customers` → `clean.customer` (UPSERT on `customer_id`)
2. `load_accounts` → `clean.account` (UPSERT on `account_id`; depends on customers)
3. `load_branches` → `clean.branch` (UPSERT on `branch_code`)
4. `load_transactions` → `clean.customer_transactions_clean` (APPEND; depends on all above; triggers `feature_engineering` post-load action)

---

## 9. Data Model

### 9.1 Source Database: `etl_validation`

The source database receives raw CSV extracts from the Core Banking System. Each CSV file maps to a staging table before the ETL pipeline ingests it.

### 9.2 Target Database: `etl_clean`

#### `public.customer_transactions_clean`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `int` | `PRIMARY KEY` | Surrogate key |
| `customer_id` | `text` | `NOT NULL` | Customer identifier |
| `account_id` | `text` | `NOT NULL` | Account identifier |
| `branch_code` | `text` | `NOT NULL` | Branch code |
| `transaction_date` | `date` | `NOT NULL` | Date of transaction |
| `transaction_type` | `text` | `NOT NULL` | CREDIT, DEBIT, TRANSFER, PAYMENT |
| `channel` | `text` | `NOT NULL` | BRANCH, ATM, POS, ONLINE, MOBILE, INTERNET |
| `currency` | `text` | `NOT NULL` | ISO currency code |
| `amount` | `numeric` | `NOT NULL` | Transaction amount |
| `loaded_at` | `timestamp` | `NOT NULL` | When this row was loaded by ETL |
| `source_row_id` | `int` | | Row index in the source CSV |
| `batch_id` | `text` | `FOREIGN KEY → etl.etl_audit.batch_id` | Links to the ETL batch that loaded this row |

#### `public.customer_transactions_rejected`

Same columns as `customer_transactions_clean` plus:

| Column | Type | Description |
|---|---|---|
| `rejection_reason` | `text` | Specific reason (rule ID + message) for rejection |
| `rejected_at` | `timestamp` | When this row was rejected |

#### `etl.etl_audit`

| Column | Type | Description |
|---|---|---|
| `id` | `bigint` | `PRIMARY KEY` |
| `audit_id` | `text` | `UNIQUE` — UUID for this audit record |
| `batch_id` | `text` | UUID linking all rows from this batch |
| `source_type` | `text` | e.g., `"CSV"` |
| `source_name` | `text` | Filename or source identifier |
| `pipeline_name` | `text` | e.g., `"customer_transaction_etl"` |
| `started_at` | `timestamp` | Pipeline start time |
| `completed_at` | `timestamp` | Pipeline end time |
| `duration_seconds` | `float` | Wall-clock duration |
| `rows_received` | `bigint` | Total rows extracted |
| `rows_valid` | `bigint` | Rows passing all validators |
| `rows_rejected` | `bigint` | Rows failing validation |
| `rows_loaded` | `bigint` | Rows successfully inserted into clean table |
| `rows_skipped` | `bigint` | Rows skipped (should always be 0) |
| `duplicates_detected` | `bigint` | Rows flagged by DuplicateDetector |
| `warnings_count` | `bigint` | Total warning-level results |
| `errors_count` | `bigint` | Total error-level results |
| `quality_score` | `float` | 0.0–100.0 composite quality metric |
| `status` | `text` | `COMPLETED`, `FAILED`, `SKIPPED` |
| `error_message` | `text` | Error details if `status = FAILED` |
| `triggered_by` | `text` | `"cli"`, `"system"`, `"api"` |
| `operator_id` | `text` | Identity of operator who triggered the pipeline |
| `tags` | `jsonb` | Extensible metadata: `file_hash`, `file_size`, environment info |
| `extra` | `jsonb` | Additional extensible metadata |

---

## 10. Idempotency Guard

### 10.1 Design

```
check_already_loaded(file_path: str) -> str | None
```

1. Computes SHA-256 hash of the input file (64 KB chunked reads).
2. Queries `etl.etl_audit` for a record where:
   - `source_name` matches the file basename
   - `tags->>'file_hash'` matches the computed hash
   - `status` is `"COMPLETED"`
3. Returns the previous `batch_id` if found — pipeline skips with a log message.
4. Returns `None` if not found — pipeline proceeds.

### 10.2 Override

The `--force` flag bypasses the idempotency guard, allowing intentional re-processing of a previously loaded file.

---

## 11. Schema Drift Detection

```
_validate_schema(df, expected_columns, mode="strict", source_name="") -> None
```

Three modes:

| Mode | Behavior |
|---|---|
| `strict` | Missing, extra, or reordered columns raise `SchemaDriftError` with a detailed diff: which columns are missing, which are unexpected, and what the order difference is. Pipeline aborts immediately. |
| `warn` | Drift is logged at WARNING with the same diff. Pipeline continues — useful for development environments. |
| `off` | No schema check performed. Not recommended for production. |

`SchemaDriftError` carries detailed diff information: `missing_columns`, `extra_columns`, and `order_mismatch`.

---

## 12. Invariant Checks

```
_run_invariant_checks(total_input, rows_loaded, reject_count, rows_rescued, quality_score, batch_id) -> list[str]
```

Four data-agnostic checks run after every batch:

| # | Check | Condition | Severity |
|---|---|---|---|
| 1 | **Conservation** | `rows_loaded + reject_count + rows_rescued == total_input` | CRITICAL if violated |
| 2 | **Constraint violations** | `rows_rescued > 0` | WARNING — indicates CHECK/NOT NULL constraints firing at the database level |
| 3 | **Quality threshold** | `quality_score < 70` | CRITICAL |
| | | `quality_score < 90` | WARNING |
| 4 | **Reason coverage** | Queries rejected table for generic `rejection_reason = "Validation failed"` — indicates a bug where a specific reason wasn't propagated | WARNING if found |

---

## 13. Error Handling & Resilience

### 13.1 Design Philosophy

The ETL Engine follows a **fail-loudly, never-silently** philosophy. Every error condition produces one of three outcomes:

1. **Abort with clear error:** Irrecoverable conditions (schema drift in strict mode, database connection loss) abort the pipeline with a specific exception and exit code 1.
2. **Rescue to rejected table:** Recoverable per-row failures (constraint violations) move the offending row to `customer_transactions_rejected` with a specific reason. The pipeline continues.
3. **Log and continue:** Non-blocking issues (quality score below threshold) are logged at appropriate severity but do not interrupt processing.

### 13.2 Constraint Rescue Pattern

Rows that pass all application-level validators but fail PostgreSQL CHECK or NOT NULL constraints during insert:

1. Batch insert wrapped in savepoint.
2. Batch fails → rollback to savepoint.
3. Fall back to row-by-row insert.
4. Each row wrapped in its own savepoint.
5. Single row fails → rollback → insert into `customer_transactions_rejected` with `rejection_reason = "db_constraint_violation: {error}"`.
6. Continue with remaining rows.

### 13.3 Partial Audit on Failure

If the pipeline fails after partial writes, `write_audit_record()` is called with `status="FAILED"` — the audit trail records the attempt even when incomplete.

---

## 14. Performance Characteristics

| Metric | Value |
|---|---|
| **Bulk insert throughput** | ~17,000 rows/second |
| **70K-row batch duration** | ~50 seconds end-to-end |
| **Chunk size** | 5,000 rows |
| **Row-by-row fallback** | ~1,100 rows/second |
| **Validation throughput** | ~70,000 rows/second |
| **Memory (peak)** | ~3 GB during 70K-row batch |

### 14.1 Scaling Properties

| Dimension | Behavior |
|---|---|
| **Row count** | Linear — total duration scales linearly with row count |
| **Column count** | Constant — validation operates on named fields only |
| **Validator count** | Sub-linear — already-invalid rows are skipped by downstream validators |
| **Concurrent batches** | Not supported — single-threaded, one batch at a time |

---

## 15. Security Design

| Control | Implementation |
|---|---|
| **SQL Injection Prevention** | All queries use parameterized statements — no string interpolation |
| **Input Validation** | All data passes through Pydantic v2 validation before any database operation |
| **Least Privilege** | ETL database user has `INSERT` and `SELECT` only — no `DROP`, `ALTER`, or `TRUNCATE` |
| **Secrets Management** | Database credentials from environment variables — never hardcoded |
| **Audit Trail Integrity** | `etl.etl_audit` is append-only at both application and database level |
| **No Internet Dependency** | All dependencies vendored; air-gapped environment |

---

## 16. CLI Interface

### 16.1 `main()` Function

```
python run_etl.py [--csv PATH] [--dry-run] [--force]
```

Exit codes: `0` = success/skipped; `1` = failure.

### 16.2 Result Dictionary

```python
{
    "run_id": "uuid",
    "batch_id": "uuid",
    "status": "completed" | "failed" | "skipped",
    "rows_received": 70472,
    "rows_valid": 69672,
    "rows_rejected": 800,
    "rows_loaded": 69672,
    "rows_rescued": 0,
    "quality_score": 96.4,
    "duration_seconds": 48.7,
}
```

---

## 17. Integration Contracts

### 17.1 Upstream: Core Banking System

| Element | Detail |
|---|---|
| **Format** | CSV file with header row |
| **Columns** | 9 columns matching `expected_columns` |
| **Delivery** | File drop or direct database view |
| **Frequency** | Daily/weekly batch (PoC: manual) |
| **Schema Stability** | Enforced by schema drift detection in `strict` mode |

### 17.2 Downstream: Feature Engineering Service

| Element | Detail |
|---|---|
| **Trigger** | Post-load action triggers feature recomputation |
| **Data** | `customer_transactions_clean` with `batch_id` |
| **Consistency** | Feature Engineering uses `as_of_date` point-in-time queries |

---

## 18. Technology Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| **Language** | Python | 3.10.9 | Primary runtime |
| **Data Processing** | pandas | 2.x | DataFrame operations |
| **Database Driver** | psycopg2 | 2.9+ | Synchronous PostgreSQL with `execute_values` |
| **ORM** | SQLAlchemy | 2.0+ | Async ORM for repository layer |
| **Validation** | Pydantic | 2.x | Schema validation |
| **Testing** | pytest | 8.x | Unit and fixture regression tests |
| **Database** | PostgreSQL | 18 | Source and target databases |

---

## 19. Testing Strategy

| Category | File | Description |
|---|---|---|
| **Fixture Regression** | `tests/test_validation_ground_truth.py` | Runs pipeline against immutable 70,472-row fixture. 6 assertions. ~25s runtime. |
| **Ground Truth Verification** | `verify.py` | 16 checks across all 10 validation rules. `--verbose` for per-rule breakdown. |
| **Unit Tests** | Validator-specific files | Each validator tested in isolation with edge cases. |

The regression fixture (`tests/fixtures/etl_validation_customers.csv`) contains 70,472 rows with 800 known-dirty rows across all 10 categories. This fixture is **frozen** — it must never be modified, serving as the permanent canary for validation correctness.

---

## Appendix A: Key Files Reference

| File | Purpose |
|---|---|
| `run_etl.py` | CLI entry point and pipeline orchestrator |
| `etl/config/etl_config.yaml` | Declarative pipeline configuration |
| `etl/config/service.py` | `ETLConfig` loader with YAML + env var precedence |
| `etl/validation/service.py` | `ValidationService` — orchestrates the 5-validator chain |
| `etl/validation/interfaces.py` | `BaseValidator` ABC |
| `etl/validation/validators/schema_validator.py` | Schema integrity validation |
| `etl/validation/validators/mandatory_field_validator.py` | Mandatory field presence validation |
| `etl/validation/validators/business_rule_validator.py` | Business rule validation (6 categories) |
| `etl/validation/validators/duplicate_detector.py` | Exact and near-duplicate detection |
| `etl/validation/validators/referential_integrity_validator.py` | Referential integrity checks (4 rules) |
| `etl/schemas/validation_schemas.py` | Pydantic v2 schemas for validation domain |
| `etl/schemas/connector_schemas.py` | Pydantic v2 schemas for connector domain |
| `etl/schemas/loading_schemas.py` | Pydantic v2 schemas for loading domain |
| `etl/schemas/audit_schemas.py` | Pydantic v2 schemas for audit domain |
| `etl/connectors/interfaces.py` | Connector ABC hierarchy |
| `etl/connectors/factory.py` | Connector registry + factory |
| `etl/connectors/files/connectors.py` | `CsvConnector` implementation |
| `etl/loading/service.py` | `LoadingService` — ordered production load |
| `etl/loading/repository.py` | `LoadingRepository` — upsert/append operations |
| `verify.py` | Ground-truth comparison tool (16 checks) |
| `tests/test_validation_ground_truth.py` | Fixture regression test (6 assertions) |

---

*Document prepared by Uniplexity AI — Enterprise Architecture Practice*
*Confidential — Absa Bank Zambia*
*Version 2.0 — July 2026*
