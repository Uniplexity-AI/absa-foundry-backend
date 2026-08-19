# ABSA Real Data → Foundry Backend — Mapping & Gap Analysis

> **Purpose:** Map the anonymised bank metadata (Tables 1–17 + additional data)
> onto the backend's existing source/clean table model, so real data can be wired
> into the Customer Lifecycle Prediction PoC with minimal redevelopment.
> **Last updated:** 2026-08-19

---

## 1. Verdict Summary

| Category | Tables | Priority for PoC |
|----------|--------|------------------|
| **Critical — must have** | Table 16 (customer master), Table 1 (accounts), Table 2/3 (customer↔account map) | 🔴 |
| **High value — wire early** | Table 7 (customer + demographics), Table 9/10 (employment/income), Table 17 (product counts) | 🟠 |
| **Useful enrichment** | Table 5 (contacts), Table 6 (demographics), Table 4 (notifications), Table 11 (notes), Table 12 (products) | 🟡 |
| **Low priority for retail churn** | Table 8 (geo lookup), Table 13 (relationships), Table 14 (account-owner), Table 15 (business customers) | ⚪ |
| **Still missing (flagged by you)** | Transaction history, Balance history, Digital activity, Lifecycle benchmark, RM interactions | 🔴 |

The biggest structural finding: **your data is keyed by `account_number` and
`customer_number` on separate tables**, while the backend currently assumes
`customer_id` exists on every row. Tables 2/3 are the bridge that resolves this —
they must be loaded first and used to denormalise `customer_number` onto the
account/transaction tables.

---

## 2. Table-by-Table Mapping

Each real table maps to a backend source table → clean table → feature group.

| Real table | Backend source table | Clean table | Feature groups unlocked |
|------------|---------------------|-------------|-------------------------|
| Table 1 — accounts | `accounts_manual` | `accounts_clean` | Relationship (`rel_accounts_active`, `rel_has_savings`, `rel_products_owned`) |
| Table 2 — customer↔account map | **new bridge table** | `accounts_clean` (join key) | Relationship hierarchy, primary account |
| Table 3 — customer↔account map (alt) | **new bridge table** | `accounts_clean` (join key) | Same as Table 2 |
| Table 4 — notifications | `digital_engagement` (partial) | `digital_engagement_clean` | Engagement, digital adoption |
| Table 5 — contacts | `customers_core` + `demographics_hr` | `customers_clean`, `demographics_clean` | Customer (age), contactability |
| Table 6 — demographics | `demographics_hr` | `demographics_clean` | Demographic segmentation |
| Table 7 — customer + demographics | `raw_customers`/`customers_core` + `demographics_hr` | `customers_clean` + `demographics_clean` | Customer profile, age, tenure |
| Table 8 — geo lookup | *(new lookup)* | — | Location segmentation (future) |
| Table 9 — employment/income | `demographics_hr` | `demographics_clean` | CLV, income, affordability |
| Table 10 — employment (subset) | `demographics_hr` | `demographics_clean` | Income stability |
| Table 11 — notes/interactions | `raw_interactions` | interaction history | Engagement timeline |
| Table 12 — products | `loans_los` / `cards_clean` (by product type) | `loans_clean`, `cards_clean` | Product ownership |
| Table 13 — relationships | *(new)* | — | Corporate hierarchy (future) |
| Table 14 — account-owner | `accounts_manual` join | `accounts_clean` | Branch analysis |
| Table 15 — business customers | `customers_core` | `customers_clean` | `customer_type` = Corporate/SME |
| Table 16 — customer master | `raw_customers` / `customers_core` | `customers_clean` | **Churn label**, profile, risk, digital |
| Table 17 — product counts | *(pre-aggregated)* | — | `rel_products_owned`, product diversity |

---

## 3. High-Value Field Mapping (source → backend column)

### 3.1 Table 16 — Customer Master (the most important table)

This is your `raw_customers` / `customers_core`. Field translation:

| Source field | Backend column | Notes |
|--------------|----------------|-------|
| `customer_number` | `customer_id` | **Canonical join key** |
| `first_name` + `family_name` | `full_name` | concatenate |
| `sex` | `gender` | standardise `MALE`/`FEMALE` |
| `customer_status` | `status` | **Defines the churn label** (see §5) |
| `date_of_status` | *(status change date)* | needed for point-in-time churn labels |
| `customer_creation_date` | `activation_date` / `customer_since_date` | tenure calc |
| `market_segment` | `customer_type` | Retail / SME / Premium / Corporate |
| `internet_bank_ind` | digital-adoption flag | feeds engagement scoring |
| `risk_score` / `risk_level` | risk fields | feeds risk features |
| `credit_rating` / `credit_rating_date` | credit fields | CLV / value scoring |
| `pep_ind`, `kyc_status` | compliance flags | reporting / segmentation |
| `marketing_opt_out` | contactability flag | engagement scoring |
| `relationship_established` | relationship start date | tenure |

### 3.2 Table 1 — Accounts

| Source field | Backend column | Notes |
|--------------|----------------|-------|
| `account_number` | `account_id` | |
| `account_status` | `status` | `Active`/`Inactive`/`Dormant`/`Closed` |
| `account_type` | `account_type` | Savings / Current / Fixed Deposit / Loan |
| `branch_number` | `branch_code` | |
| `date_opened` | `opened_date` | account age |
| `country_currency_number` / `currency_swift_code` | `currency` | |
| `location_code` / `sales_location` | *(new)* `location_code` | branch/location segmentation |

> ⚠️ Table 1 has **no `customer_number`** in the listed fields — it is keyed by
> `account_number`. Resolve ownership via Table 2/3.

### 3.3 Tables 2 & 3 — Customer↔Account Bridge (load first)

| Source field | Role |
|--------------|------|
| `customer_number` | → `customer_id` (denormalise onto accounts) |
| `account_number` | → `account_id` |
| `primary_account_indicator` | primary account flag (new column) |
| `sms_alert_ind` | communication preference |
| `contact_status` | servicing preference |

**Recommendation:** build a `customer_account_map` staging table (or a SQL view)
that resolves `account_number → customer_number`. Point a new extraction spec at it
so every downstream account/transaction row carries a `customer_id`.

### 3.4 Table 7 — Customer + Demographics

| Source field | Backend column |
|--------------|----------------|
| `customer_number` | `customer_id` |
| `date_of_birth` | `date_of_birth` |
| `marital_status` | `marital_status` |
| `phone_number` / `mobile_number` / `email_address` | contactability |
| `residential_status` | residential status |
| `place_of_birth` | — |

### 3.5 Tables 9 & 10 — Employment / Income

| Source field | Backend column |
|--------------|----------------|
| `employment_status` | `employment_status` |
| `employment_type` | `employment_type` |
| `employer` | `employer_name` |
| `gross_income` | `monthly_income_declared` |
| `other_income` | `other_income` |
| `gross_currency` / `other_currency` | currency |
| `source_of_funds` | source of funds |
| `designation` | job title |

> Maps 1:1 onto `demographics_clean`. Confirm the join key (Table 9 does not list
> `customer_number` — likely joins via an employee/party number).

### 3.6 Table 11 — Notes / Interactions

| Source field | Backend column |
|--------------|----------------|
| `note_date` | interaction timestamp |
| `note_type` | interaction type |
| `action_date` | follow-up date |
| `comments` | free text (skip for training) |

> Maps onto `raw_interactions` (currently only used for `interaction_count`). Add
> `customer_number` to make it usable.

### 3.7 Table 17 — Product Counts (shortcut)

| Source field | Value |
|--------------|-------|
| `current_count`, `savings_count`, `term_deposit_count`, `investment_count`, `secured_count`, `unsecured_count` | direct `rel_products_owned` / product diversity |
| `risk_score` / `risk_level` | risk features |

> This is a **pre-aggregated product summary**. If loading individual account/loan/
> card tables is heavy, this single table can feed the relationship product features
> immediately.

---

## 4. What's Still Required (your "Additional Data")

| Required dataset | Backend target | Status |
|------------------|----------------|--------|
| **Transaction history** (`customer_id`, `account_number`, `transaction_date`, `transaction_amount`, `transaction_type`, `transaction_channel`) | `customer_transactions_clean` | 🔴 **Not provided — highest priority.** Recency/frequency/monetary features all come from here. |
| **Balance history** (`customer_id`, `account_number`, `snapshot_date`, `average_balance`, `closing_balance`) | *(new)* `balances_clean` | 🔴 Not currently modelled. Needed for the `GROWING` state (balance growth) and CLV. |
| **Digital activity** (mobile/internet banking, channel usage) | `digital_engagement_clean` | 🟠 Provided partially via Table 4; needs login/platform/session detail. |
| **Existing lifecycle classification** (`customer_id`, `snapshot_month`, `lifecycle_stage`) | *(new)* `lifecycle_benchmark` | 🟡 Use as a **validation benchmark** against the state engine, not as a training feature. |
| **RM interaction history** (engagement activities, outcomes) | `raw_interactions` | 🟡 Table 11 partially covers this. |

---

## 5. Churn Label Definition (critical decision)

The backend currently defines churn as `rel_customer_status = 'Closed'` (configurable
via `LABEL_CHURN_COLUMN` / `LABEL_CHURN_POSITIVE_VALUE`). With real data you have a
better source:

| Source | Field | Recommended use |
|--------|-------|-----------------|
| Table 16 | `customer_status` | primary label |
| Table 16 | `date_of_status` | **when** the customer churned (enables point-in-time labelling) |
| Table 1 | `account_status` | secondary signal (all accounts closed) |

**Action:** agree on the churn definition with the business (e.g. `customer_status
IN ('Closed','Dormant')`), set `LABEL_CHURN_POSITIVE_VALUE` accordingly, and use
`date_of_status` to build the training holdout dates in `TRAINING_DATES` /
`TRAINING_HOLDOUT_DATE`.

---

## 6. Field-Name Translation Cheat Sheet

Consolidated source → backend column map for the ETL standardisation step:

| Bank source field | Backend column |
|-------------------|----------------|
| `customer_number` | `customer_id` |
| `account_number` | `account_id` |
| `branch_number` | `branch_code` |
| `date_opened` | `opened_date` |
| `customer_creation_date` / `relationship_established` | `activation_date` / `customer_since_date` |
| `sex` | `gender` |
| `customer_status` | `status` |
| `account_status` | `status` (accounts) |
| `market_segment` | `customer_type` |
| `gross_income` | `monthly_income_declared` |
| `employer` | `employer_name` |
| `emp_status` / `employment_status` | `employment_status` |
| `marital` / `marital_status` | `marital_status` |
| `internet_bank_ind` | digital-adoption flag |
| `primary_account_indicator` | primary account flag |
| `sms_alert_ind` | sms alert flag |

---

## 7. Recommended Implementation Order

Run the specs in this order (all built — see §8):

1. **`customer_account_map.yaml`** — Tables 2/3 → `customer_account_map` (account → customer bridge).
2. **`customer_master.yaml`** — Table 16 → `customers_clean` (churn label, profile, tenure).
3. **`accounts.yaml`** — Table 1 → `accounts_clean` (joins the bridge for `customer_id`).
4. **`employment_income.yaml`** + **`customer_demographics.yaml`** — Tables 9 & 7 → `demographics_clean` (see PK-conflict note in §9).
5. **Table 17** → feed relationship product features (spec not yet built — it's a
   pre-aggregated summary that can short-circuit the account/loan/card specs).
6. **Obtain transaction history** → `customer_transactions_clean` (unblocks the
   core churn features).
7. **Obtain balance history** → new `balances_clean` + wire `GROWING` state.
8. **Obtain digital activity** → `digital_engagement_clean`.

Run any spec with:

```powershell
.\.venv\Scripts\python.exe run_etl.py --extraction-spec etl/config/extraction_specs/<name>.yaml
```

---

## 8. Extraction Specs Built

Five specs were added under `etl/config/extraction_specs/`. Each has a header
comment listing the exact source→backend field mapping.

**Source table names are driven by `etl/config/pilot_data_config.yaml`** — the
specs reference them via `${source_tables.<entity>}` placeholders. To point the
whole pipeline at real tables, edit that one config file only.

| Spec file | Source | Target clean table | Key mappings |
|-----------|--------|--------------------|--------------|
| `customer_account_map.yaml` | Tables 2/3 | `customer_account_map` *(new)* | `customer_number`→`customer_id`, `account_number`→`account_id`, `primary_account_indicator`→`is_primary` |
| `customer_master.yaml` | Table 16 (+ Table 7 for DOB) | `customers_clean` | `sex`→`gender`, `customer_status`→`status`, `customer_creation_date`→`activation_date`, `market_segment`→`customer_type`, `kyc_status`→`kyc_tier` |
| `accounts.yaml` | Table 1 (+ bridge) | `accounts_clean` | `account_status`→`status`, `date_opened`→`opened_date`, `customer_number` from bridge |
| `customer_demographics.yaml` | Table 7 | `demographics_clean` | `marital_status`→`marital_status` |
| `employment_income.yaml` | Table 9 | `demographics_clean` | `employer`→`employer_name`, `gross_income`→`monthly_income_declared` |

All five pass the extraction config schema validation.

---

## 9. Remaining Gaps & Pre-Flight Checklist

### 9.1 Set source table names (now config-driven)

Edit `etl/config/pilot_data_config.yaml` → `source_tables:` and set each logical
entity to the real table name. The specs pick this up automatically via
`${source_tables.*}` placeholders (no spec edits needed). Also confirm the
**join-key columns** in the same file (`join_keys:`):

- Table 16 and Table 9 field lists **omit `customer_number`** — confirm the actual
  key column name before running.
- Table 1 has no `customer_number` — it is resolved via the Table 2/3 bridge.

### 9.2 Clean-table DDL alignment (feature engine contract)

The feature engine reads specific columns that the current synthetic DDL does not
fully cover. Before running the specs, ensure `etl_clean` tables have:

| Table | Must-have columns the feature engine reads |
|-------|---------------------------------------------|
| `customers_clean` | `customer_id`, `customer_type`, `activation_date`, `date_of_birth`, `onboarding_channel`, `branch_code`, `status` |
| `accounts_clean` | `customer_id`, `account_type`, `status` (values `ACTIVE`, `SAVINGS`, …) |
| `customer_account_map` | *(new)* `customer_id`, `account_id`, `is_primary`, `sms_alert_ind`, `contact_status` |
| `demographics_clean` | `customer_id`, `employment_status`, `employer_name`, `monthly_income_declared`, `marital_status` |

### 9.3 `etl_config.yaml` mandatory-field validation — RESOLVED

`run_etl.py` Phase 2 applies `etl_config.yaml` `validation.mandatory_fields`
(customer-centric) to **every** spec, which would reject non-customer rows.
**Fixed:** extraction specs can now declare a per-spec `validation:` block that
overrides `mandatory_fields` (and optionally `enabled`). `run_etl.py` merges it
before Phase 2, and `ExtractionConfigSpec` gained a `ValidationOverrideSpec`.

```yaml
validation:
  mandatory_fields:
    - account_id
    - status
```

The 5 new specs already carry the right mandatory fields. The transaction
pipeline's global mandatory fields are untouched.

### 9.4 Primary-key conflict on `demographics_clean`

`employment_income.yaml` and `customer_demographics.yaml` both write
`demographics_clean` (PK `customer_id`), and `bulk_insert_clean` uses plain `INSERT`
(no upsert). Merge them into one spec (join Table 9 + Table 7 on `customer_number`)
or add an `ON CONFLICT DO UPDATE` upsert before running both.

### 9.5 Still-missing datasets (unchanged from §4)

- 🔴 **Transaction history** — no spec can substitute for this; it is the core
  feature source. Columns: `customer_id, account_number, transaction_date,
  transaction_amount, transaction_type, transaction_channel`.
- 🔴 **Balance history** — new `balances_clean` table + `GROWING`-state wiring.
- 🟠 **Digital activity** — login/platform/session detail for `digital_engagement_clean`.
- 🟡 **Lifecycle benchmark** — validation only.
- 🟡 **RM interaction history** — `raw_interactions` enrichment.

### 9.6 Customer-ID format

The feature engine joins `customer_features` (`CUST#####`) to `customers_clean`
(`C01######`) via `RIGHT(id, 5)` and a `customer_id_mapping` table. Pick one
canonical `customer_number` format and confirm the mapping table is populated, or
the feature engine's ID mapping will silently drop rows.
