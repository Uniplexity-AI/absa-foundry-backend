# Hardcoded Assumptions — Migration Guide

> **Purpose:** When Absa provides a different dataset, this document tells you exactly what to change.
> **Last updated:** 2026-07-29
> **Related:** `shared/config/settings.py` (schema mapping), `docs/architecture/prediction-service.md`

---

## Quick Reference: Config-Driven (No Code Changes)

These are controlled by `shared/config/settings.py` or `.env`. Change the value, restart, done.

| Setting | Default | `.env` Variable |
|---------|---------|-----------------|
| `table_customer_features` | `customer_features` | `TABLE_CUSTOMER_FEATURES` |
| `table_customer_states` | `customer_states` | `TABLE_CUSTOMER_STATES` |
| `table_transactions_clean` | `customer_transactions_clean` | `TABLE_TRANSACTIONS_CLEAN` |
| `table_accounts_clean` | `accounts_clean` | `TABLE_ACCOUNTS_CLEAN` |
| `table_cards_clean` | `cards_clean` | `TABLE_CARDS_CLEAN` |
| `table_loans_clean` | `loans_clean` | `TABLE_LOANS_CLEAN` |
| `table_digital_engagement` | `digital_engagement_clean` | `TABLE_DIGITAL_ENGAGEMENT` |
| `col_customer_id` | `customer_id` | `COL_CUSTOMER_ID` |
| `col_as_of_date` | `as_of_date` | `COL_AS_OF_DATE` |
| `col_transaction_date` | `transaction_date` | `COL_TRANSACTION_DATE` |
| `col_channel` | `channel` | `COL_CHANNEL` |
| `col_transaction_type` | `transaction_type` | `COL_TRANSACTION_TYPE` |
| `col_customer_status` | `rel_customer_status` | `COL_CUSTOMER_STATUS` |
| `label_churn_column` | `rel_customer_status` | `LABEL_CHURN_COLUMN` |
| `label_churn_positive_value` | `Closed` | `LABEL_CHURN_POSITIVE_VALUE` |
| `training_dates` | `2026-07-17,2026-07-22` | `TRAINING_DATES` |
| `training_holdout_date` | `2026-07-27` | `TRAINING_HOLDOUT_DATE` |

**Services that use these automatically:**
- ✅ Behaviour Generator
- ✅ Prediction Repository
- ✅ State Service
- ✅ Training Pipeline

---

## Services Using Shared Config (✅ Survive New Data)

| Service | File | What's Config-Driven |
|---------|------|---------------------|
| Behaviour Generator | `services/feature-engineering-service/app/features/behaviour/generator.py` | All table/column names |
| Prediction Repository | `services/prediction-service/app/repository/repository.py` | All 4 SQL templates |
| State Service | `services/customer-state-service/app/services/state_service.py` | Feature table + customer ID + as_of_date columns |
| Prediction Service | `services/prediction-service/app/services/service.py` | Startup schema validation |
| Training Pipeline | `scripts/train_models.py` | Label column, label value, training dates, non-feature columns, leakage set (dynamic) |

---

## Services Requiring Code Changes (🔴 Will Break)

### Priority 1 — Feature Generators

These generators still use hardcoded SQL. Update each to follow the Behaviour Generator pattern (import `shared.config.settings`, resolve names at `__init__`, build SQL with f-strings).

| File | Hardcoded Table Names | Hardcoded Columns | Hardcoded Values |
|------|----------------------|-------------------|-----------------|
| `channel/generator.py` | `customer_transactions_clean`, `customer_features` | `customer_id`, `transaction_date`, `channel` | `'MOBILE'`, `'ATM'`, `'BRANCH'`, `'ONLINE'`, `'INTERNET'` |
| `customer/generator.py` | `customer_features`, `customers_clean` | `customer_type`, `activation_date`, `date_of_birth`, `onboarding_channel`, `branch_code` | `'<18'`, age buckets, `RIGHT(id,5)` join pattern |
| `financial/generator.py` | `customer_transactions_clean`, `customer_features` | `customer_id`, `transaction_date`, `transaction_type`, `amount` | `'CREDIT'`, `'DEBIT'` |
| `risk/generator.py` | `customer_transactions_clean`, `customer_features` | `customer_id`, `transaction_date`, `transaction_type`, `amount`, `channel` | `'REVERSAL'`, `'ATM'`, `'BRANCH'`, `10000` threshold |
| `temporal/generator.py` | `customer_transactions_clean`, `customer_features` | `customer_id`, `transaction_date` | — |
| `relationship/generator.py` | `customer_features`, `customers_clean`, `accounts_clean`, `loans_clean`, `cards_clean`, `digital_engagement_clean`, `customer_id_mapping` | 15+ column names | `'ACTIVE'`, `'SAVINGS'`, `'INACTIVE'`, `RIGHT(id,5)` join pattern |

### Priority 2 — Repository

| File | Hardcoded |
|------|-----------|
| `feature-engineering-service/app/repository/repository.py` | Table names (`customer_features`, `customer_transactions_clean`), column names, filter values (`'CREDIT'`, `'DEBIT'`), lookback windows |
| `customer-state-service/app/repository/state_repository.py` | Table name (`customer_states`), column names (`customer_id`, `as_of_date`, `state`, etc.) |
| `customer-state-service/app/repository/journey_repository.py` | Table name (`state_transitions`), column names |

### Priority 3 — Business Logic

| File | Hardcoded |
|------|-----------|
| `customer-state-service/app/services/state_engine.py` | Feature names (`days_since_last_txn`, `engagement_score`, etc.), state values (`"CHURNED"`, `"DORMANT"`, etc.), filter value `"Closed"`, threshold `30` |
| `customer-state-service/app/services/transition_analyzer.py` | Same feature names + state values, thresholds `365`, `90`, `30`, `10`, `20` |
| `customer-state-service/app/services/journey_analyzer.py` | Table names, column names, state values |

### Priority 4 — ETL Layer

| File | Hardcoded |
|------|-----------|
| `etl/config/service.py` | Target table names, expected column lists |
| `etl/schemas/validation_schemas.py` | Mandatory fields, accepted currencies (9), accepted transaction types (7), accepted channels (10), duplicate key fields, referential checks |
| `etl/schemas/loading_schemas.py` | Staging/target table mappings, conflict columns |

### Priority 5 — Scripts & DDL

| File | Hardcoded |
|------|-----------|
| `scripts/seed_states.py` | Table name, feature column names |
| `scripts/add_feature_indexes.py` | Table names, index columns |
| `scripts/verify_feature_to_state.py` | Table names, feature column names, default date |
| `scripts/generate_synthetic_feature_store_data.py` | DDL for 7 tables, value distributions |
| `database/feature_store/001_customer_features.sql` | Table + all column definitions + CHECK constraints |
| `database/state_engine/001_customer_states.sql` | Table + column definitions + state CHECK constraint |
| Various `_*.py` scripts | Hardcoded dates `"2026-07-27"`, customer IDs |

---

## Feature Name Dependencies

These feature column names are referenced across multiple files and would need updating if feature engineering changes:

| Feature Name | Referenced In |
|-------------|--------------|
| `days_since_last_txn` | State engine, transition analyzer, seed_states, verify scripts, training LEAKAGE_FEATURES |
| `engagement_score` | State engine, transition analyzer, health scorer (via API), training LEAKAGE_FEATURES |
| `rel_customer_status` | State engine, transition analyzer, label generator, training LEAKAGE_FEATURES |
| `risk_dormant_indicator` | State engine, transition analyzer, training LEAKAGE_FEATURES |
| `txn_count_90d` | State engine, transition analyzer, seed_states, verify scripts |
| `total_amount_90d` | CLV percentile SQL, verify scripts |

---

## State Value Dependencies

These state classification values are used across the codebase:

| Value | Referenced In |
|-------|--------------|
| `"ACTIVE"` | State engine, transition analyzer, journey analyzer, DDL CHECK constraint |
| `"AT_RISK"` | State engine, transition analyzer, journey analyzer, DDL CHECK constraint |
| `"DORMANT"` | State engine, transition analyzer, journey analyzer, DDL CHECK constraint |
| `"CHURNED"` | State engine, transition analyzer, journey analyzer, DDL CHECK constraint |
| `"Closed"` | State engine (`rel_customer_status` filter), label generator, training config |

---

## Migration Checklist for New Dataset

### Step 1: Update `.env` (no code changes)
```bash
TABLE_TRANSACTIONS_CLEAN=<absa_txn_table>
TABLE_CUSTOMER_FEATURES=<absa_feature_table>
COL_TRANSACTION_DATE=<absa_date_column>
COL_CHANNEL=<absa_channel_column>
COL_CUSTOMER_STATUS=<absa_status_column>
LABEL_CHURN_COLUMN=<absa_status_column>
LABEL_CHURN_POSITIVE_VALUE=<absa_closed_value>
TRAINING_DATES=<absa_training_dates>
TRAINING_HOLDOUT_DATE=<absa_holdout_date>
```

### Step 2: Run schema validation
```bash
# Start any service — validation runs at startup
uv run --directory services/prediction-service uvicorn main:app --port 8004
# Check logs for schema warnings
```

### Step 3: Update generators (code changes needed)
Apply the Behaviour Generator pattern to each remaining generator:
1. Import `from shared.config.settings import settings as shared`
2. Resolve table/column names at `__init__`
3. Build SQL as f-strings with `{self._table_name}` placeholders
4. Keep `%(name)s` psycopg2 parameters for data values

### Step 4: Update repositories (code changes needed)
Apply the Prediction Repository pattern to Feature Repository and State Repository.

### Step 5: Update business logic (code changes needed)
Replace hardcoded feature names and state values in state engine, transition analyzer, and journey analyzer with config-driven references.

### Step 6: Update ETL (code changes needed)
Update validation schemas, loading schemas, and extraction configs to match Absa's data dictionary.

### Step 7: Regenerate DDL (code changes needed)
Update `database/` SQL files to match Absa's schema or run migrations against Absa's existing tables.

---

## Estimated Effort

| Priority | Files | Est. Hours |
|----------|-------|-----------|
| P1 — Generators | 6 files | 3-4 hours |
| P2 — Repositories | 3 files | 2-3 hours |
| P3 — Business Logic | 3 files | 2 hours |
| P4 — ETL | 3 files | 2-3 hours |
| P5 — Scripts/DDL | 10+ files | 2-4 hours |
| **Total** | **25+ files** | **11-16 hours** |
