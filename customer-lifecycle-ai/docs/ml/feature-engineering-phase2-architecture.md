# Feature Engineering — Phase 2 Architecture

## Generators, Pipeline Orchestration, and SQL Design

> **Version:** 1.0  
> **Date:** 2026-07-26  
> **Status:** Design Complete — Ready for Implementation  
> **Depends On:** Phase 1 (Gateway wiring + RBAC) — Complete  
> **Estimated Effort:** 4 hours  
> **Target:** 30 features in `customer_features` (21 existing + 9 new)

---

## Table of Contents

1. [System Context](#1-system-context)
2. [Input Tables](#2-input-tables)
3. [Target Schema](#3-target-schema)
4. [Generator 1: Customer Profile](#4-generator-1-customer-profile)
5. [Generator 2: Behaviour Features](#5-generator-2-behaviour-features)
6. [Generator 3: CLV Features](#6-generator-3-clv-features)
7. [Pipeline Orchestration](#7-pipeline-orchestration)
8. [Repository Methods](#8-repository-methods)
9. [Error Handling & Edge Cases](#9-error-handling--edge-cases)
10. [Testing Strategy](#10-testing-strategy)
11. [Implementation Checklist](#11-implementation-checklist)

---

## 1. System Context

### Where This Fits

```
run_etl.py (CLI)
  ↓ bulk_insert_clean
customers_clean (15,200 rows)
customer_transactions_clean (209K rows)
  ↓
Phase 1 SQL (FEATURE_SQL + PHASE2_SQL) — ALREADY BUILT
  ↓ 21 transaction-aggregate features
customer_features (partial — 21 of 30 columns filled)
  ↓
Phase 2 Generators — THIS DOCUMENT
  ↓ 9 new features + fills 4 existing stubs
customer_features (complete — 30 columns filled)
  ↓
Downstream consumers:
  Layer 1: Customer State Service (Markov)
  Layer 2: Prediction Service (XGBoost/LightGBM)
  Layer 3: Decision Intelligence (NBA)
  RM Dashboard API
```

### Why Generators Instead of One Giant SQL

The Phase 1 SQL computes features that require raw transaction scans (COUNT, SUM, AVG, STDDEV with FILTER clauses on date ranges). These are expensive — they aggregate 209K rows per customer group.

Generators 1-3 compute features that are **derived from already-aggregated data**. They read from `customer_features` (one row per customer per as_of_date) and `customers_clean` (one row per customer). These are lightweight UPDATE operations that run in seconds.

Separating them into generators also makes each one independently testable and the pipeline resumable — if Generator 2 fails, Generators 1 and 3 results are still valid.

### Runtime Estimates

| Step | Rows Processed | Estimated Time |
|---|---|---|
| Phase 1 SQL (existing) | 209K → 15.2K groups | 2-5 seconds |
| Generator 1 (customer) | 15.2K | under 1 second |
| Generator 2 (behaviour) | 15.2K + 209K subqueries | 5-10 seconds |
| Generator 3 (CLV) | 15.2K | under 1 second |
| **Total pipeline** | — | **10-20 seconds** |

---

## 2. Input Tables

### 2.1 `customers_clean`

- **Database:** `etl_clean`
- **Row count:** 15,200
- **Provenance:** `raw_customers.csv` → `run_etl.py` → `bulk_insert_clean`
- **Primary key:** `customer_id`
- **Used by:** Generator 1

| Column | Type | Description | Generator Use |
|---|---|---|---|
| `customer_id` | VARCHAR(64) | Unique identifier | JOIN key |
| `activation_date` | DATE | Account opening date | tenure calculation |
| `customer_type` | VARCHAR(32) | Retail, SME, Premium, Corporate | segment feature |
| `date_of_birth` | DATE | Customer date of birth | age calculation |
| `onboarding_channel` | VARCHAR(32) | Branch, App, USSD, Web, ATM, Agent | channel feature |
| `branch_code` | VARCHAR(16) | Branch identifier | not used (available for future) |
| `country` | VARCHAR(2) | ISO country code | not used |
| `gender` | VARCHAR(1) | M, F | not used (available for future) |
| `status` | VARCHAR(16) | Active, Dormant, Closed, Suspended | not used |
| `loaded_at` | TIMESTAMPTZ | ETL load timestamp | metadata — ignored |
| `batch_id` | VARCHAR(64) | ETL batch identifier | metadata — ignored |

### 2.2 `customer_transactions_clean`

- **Database:** `etl_clean`
- **Row count:** ~209,000
- **Provenance:** `customer_transactions` (source DB) → `run_etl.py` → `bulk_insert_clean`
- **Primary key:** `customer_id` + `transaction_date` (not enforced, logical)
- **Used by:** Generator 2 (behaviour subqueries)

| Column | Type | Description | Generator Use |
|---|---|---|---|
| `customer_id` | VARCHAR(64) | FK to customers_clean | JOIN + GROUP BY |
| `account_id` | VARCHAR(64) | Account identifier | not used |
| `branch_code` | VARCHAR(16) | Branch code | not used |
| `transaction_date` | DATE/TIMESTAMP | Date of transaction | date range filters |
| `transaction_type` | VARCHAR(16) | CREDIT, DEBIT, TRANSFER, PAYMENT | type filters |
| `channel` | VARCHAR(16) | BRANCH, ATM, POS, ONLINE, MOBILE, INTERNET | not used directly (already in Phase 1) |
| `currency` | VARCHAR(4) | ZMW, ZAR, USD, EUR, GBP | not used |
| `amount` | NUMERIC | Transaction amount | SUM, COUNT, HAVING |
| `loaded_at` | TIMESTAMPTZ | ETL load timestamp | metadata — ignored |
| `source_row_id` | INTEGER | Source table row ID | metadata — ignored |
| `batch_id` | VARCHAR(64) | ETL batch identifier | metadata — ignored |

### 2.3 `customer_features` (Existing — Phase 1 Output)

- **Database:** `etl_clean`
- **Created by:** `services/feature-engineering-service/app/repository/repository.py`
- **Primary key:** `(customer_id, as_of_date)` — unique constraint enforced
- **Used by:** Generators 2 and 3 (read existing columns, write new columns)

**Existing 21 columns from Phase 1:**

| Column | Type | Phase |
|---|---|---|
| `customer_id` | VARCHAR(64) | PK |
| `as_of_date` | DATE | PK |
| `days_since_last_txn` | INTEGER | Phase 1 |
| `days_since_first_txn` | INTEGER | Phase 1 |
| `txn_count_30d` | INTEGER | Phase 1 |
| `txn_count_90d` | INTEGER | Phase 1 |
| `txn_count_180d` | INTEGER | Phase 1 |
| `txn_count_365d` | INTEGER | Phase 2 SQL |
| `avg_days_between_txn` | FLOAT | Phase 1 |
| `total_amount_90d` | FLOAT | Phase 1 |
| `avg_amount_90d` | FLOAT | Phase 1 |
| `total_amount_180d` | FLOAT | Phase 1 |
| `amount_growth_ratio` | FLOAT | Phase 1 |
| `credit_sum_30d` | FLOAT | Phase 2 SQL |
| `debit_sum_30d` | FLOAT | Phase 2 SQL |
| `credit_to_debit_ratio_90d` | FLOAT | **STUB — filled by Generator 2** |
| `balance_trend_90d` | VARCHAR(16) | **STUB — deferred (needs accounts table)** |
| `has_salary_credit` | BOOLEAN | **STUB — filled by Generator 2** |
| `monthly_income_estimate` | FLOAT | **STUB — filled by Generator 2** |
| `distinct_channels_90d` | INTEGER | Phase 1 |
| `distinct_txn_types_90d` | INTEGER | Phase 1 |
| `dominant_channel` | VARCHAR(32) | Phase 1 |
| `amount_stddev_90d` | FLOAT | Phase 1 |
| `computed_at` | TIMESTAMPTZ | Phase 1 |

---

## 3. Target Schema

After Phase 2, `customer_features` will have **30 columns** (9 new, 21 existing, 1 deferred).

### Migration SQL

Run once against `etl_clean` before deploying generators:

```sql
-- Generator 1: Customer profile features
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS customer_tenure_days INTEGER;
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS customer_segment VARCHAR(32);
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS age_years INTEGER;
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS onboarding_channel VARCHAR(32);

-- Generator 2: Behaviour features
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS inactivity_streak_days INTEGER;
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS txn_frequency_trend FLOAT;
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS engagement_score FLOAT;

-- Generator 3: CLV features
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS revenue_trend_6m VARCHAR(16);
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS predicted_annual_value FLOAT;
```

### Complete Column Map (30 Features)

| # | Column | Type | Category | Source Generator |
|---|---|---|---|---|
| 1 | `customer_id` | VARCHAR(64) | Key | Phase 1 |
| 2 | `as_of_date` | DATE | Key | Phase 1 |
| 3 | `days_since_last_txn` | INTEGER | Recency | Phase 1 |
| 4 | `days_since_first_txn` | INTEGER | Tenure | Phase 1 |
| 5 | `txn_count_30d` | INTEGER | Frequency | Phase 1 |
| 6 | `txn_count_90d` | INTEGER | Frequency | Phase 1 |
| 7 | `txn_count_180d` | INTEGER | Frequency | Phase 1 |
| 8 | `txn_count_365d` | INTEGER | Frequency | Phase 2 SQL |
| 9 | `avg_days_between_txn` | FLOAT | Frequency | Phase 1 |
| 10 | `total_amount_90d` | FLOAT | Monetary | Phase 1 |
| 11 | `avg_amount_90d` | FLOAT | Monetary | Phase 1 |
| 12 | `total_amount_180d` | FLOAT | Monetary | Phase 1 |
| 13 | `amount_growth_ratio` | FLOAT | Monetary | Phase 1 |
| 14 | `credit_sum_30d` | FLOAT | Monetary | Phase 2 SQL |
| 15 | `debit_sum_30d` | FLOAT | Monetary | Phase 2 SQL |
| 16 | `credit_to_debit_ratio_90d` | FLOAT | Monetary | Generator 2 |
| 17 | `balance_trend_90d` | VARCHAR(16) | Balance | Deferred |
| 18 | `has_salary_credit` | BOOLEAN | Income | Generator 2 |
| 19 | `monthly_income_estimate` | FLOAT | Income | Generator 2 |
| 20 | `distinct_channels_90d` | INTEGER | Diversity | Phase 1 |
| 21 | `distinct_txn_types_90d` | INTEGER | Diversity | Phase 1 |
| 22 | `dominant_channel` | VARCHAR(32) | Diversity | Phase 1 |
| 23 | `amount_stddev_90d` | FLOAT | Volatility | Phase 1 |
| 24 | `customer_tenure_days` | INTEGER | Profile | Generator 1 |
| 25 | `customer_segment` | VARCHAR(32) | Profile | Generator 1 |
| 26 | `age_years` | INTEGER | Profile | Generator 1 |
| 27 | `onboarding_channel` | VARCHAR(32) | Profile | Generator 1 |
| 28 | `inactivity_streak_days` | INTEGER | Behaviour | Generator 2 |
| 29 | `txn_frequency_trend` | FLOAT | Behaviour | Generator 2 |
| 30 | `engagement_score` | FLOAT | Behaviour | Generator 2 |
| 31 | `revenue_trend_6m` | VARCHAR(16) | CLV | Generator 3 |
| 32 | `predicted_annual_value` | FLOAT | CLV | Generator 3 |
| — | `computed_at` | TIMESTAMPTZ | Meta | Phase 1 |

---

## 4. Generator 1: Customer Profile

### Purpose

Enrich `customer_features` with static customer-level attributes from `customers_clean`. These features do not change per transaction window — they are the same for every `as_of_date` snapshot of a given customer.

### File

`services/feature-engineering-service/app/features/customer/generator.py`

### Class

```python
class CustomerProfileGenerator:
    """Generates customer-level profile features from customers_clean."""

    def __init__(self, conn: psycopg2.extensions.connection):
        self._conn = conn

    def generate(self, as_of_date: date) -> int:
        """Update customer_features with profile features.

        Returns:
            Number of rows updated.
        """
```

### SQL

Single UPDATE statement joining `customer_features` to `customers_clean`:

```sql
UPDATE customer_features cf
SET
    customer_tenure_days = (
        %(as_of_date)s::date - cc.activation_date::date
    ),
    customer_segment = cc.customer_type,
    age_years = EXTRACT(
        YEAR FROM AGE(%(as_of_date)s::date, cc.date_of_birth::date)
    ),
    onboarding_channel = cc.onboarding_channel
FROM customers_clean cc
WHERE cf.customer_id = cc.customer_id
  AND cf.as_of_date = %(as_of_date)s::date;
```

### Parameters

| Parameter | Type | Source |
|---|---|---|
| `%(as_of_date)s` | DATE | Pipeline input, e.g. `date.today()` |

### Edge Cases

| Scenario | Behaviour |
|---|---|
| Customer not in `customers_clean` | Row skipped (INNER JOIN via WHERE clause). Feature columns remain NULL. |
| `date_of_birth` is NULL | `age_years` evaluates to NULL. Valid — unknown age. |
| `activation_date` is NULL | `customer_tenure_days` evaluates to NULL. Valid — unknown tenure. |
| Generator runs twice on same `as_of_date` | Idempotent — same values overwritten with same values. |
| Generator runs before Phase 1 SQL | No rows match `as_of_date` in `customer_features`. Zero rows updated. Safe no-op. |

### Dependencies

- **Requires:** `customers_clean` table must exist and be populated
- **Requires:** `customer_features` must have rows for the given `as_of_date` (Phase 1 must have run)
- **Required by:** Generator 2 (uses `customer_segment` indirectly via engagement), Generator 3 (uses `customer_tenure_days`)

---

## 5. Generator 2: Behaviour Features

### Purpose

Compute engagement metrics, income estimates, and credit/debit patterns from already-aggregated transaction features and raw transaction data.

### File

`services/feature-engineering-service/app/features/behaviour/generator.py`

### Class

```python
class BehaviourGenerator:
    """Generates behaviour, engagement, and income features."""

    def __init__(self, conn: psycopg2.extensions.connection):
        self._conn = conn

    def generate(self, as_of_date: date) -> dict:
        """Run all behaviour feature SQL statements.

        Returns:
            Dict with row counts per feature:
            {
                "inactivity_streak": int,
                "frequency_trend": int,
                "engagement_score": int,
                "salary_credit": int,
                "monthly_income": int,
                "credit_debit_ratio": int
            }
        """
```

### Feature 5.1: `inactivity_streak_days`

**Logic:** Simply copies the already-computed `days_since_last_txn`. This is a semantic alias — "inactivity streak" is more meaningful to downstream consumers (state service, churn model) than "days since last transaction."

```sql
UPDATE customer_features
SET inactivity_streak_days = days_since_last_txn
WHERE as_of_date = %(as_of_date)s::date;
```

**Edge cases:**
- NULL `days_since_last_txn` → NULL `inactivity_streak_days` (customer has zero transactions)
- Both values always identical by design

### Feature 5.2: `txn_frequency_trend`

**Logic:** Compares recent transaction rate (30-day window) to historical rate (90-day window). A ratio above 1.0 means the customer is transacting more frequently than their historical average — a positive signal. A ratio below 1.0 means declining engagement.

```
rate_30d  = txn_count_30d / 30 days
rate_90d  = txn_count_90d / 90 days
trend     = rate_30d / rate_90d
```

```sql
UPDATE customer_features
SET txn_frequency_trend = CASE
    WHEN txn_count_90d IS NULL OR txn_count_90d = 0 THEN NULL
    WHEN txn_count_30d IS NULL THEN 0.0
    ELSE ROUND(
        (txn_count_30d::float / 30.0) /
        NULLIF(txn_count_90d::float / 90.0, 0),
        2
    )
END
WHERE as_of_date = %(as_of_date)s::date;
```

**Edge cases:**
- Zero transactions in 90 days → NULL (can't compute trend)
- Zero transactions in 30 days but some in 90 days → 0.0 (complete stop)
- NULL guard on `txn_count_90d` via CASE WHEN

### Feature 5.3: `engagement_score`

**Logic:** Composite 0-100 score combining three dimensions. Designed so that a customer who transacted today, transacts daily, and uses multiple channels gets close to 100. A dormant customer gets close to 0.

**Component 1 — Recency (0-40 points):**
```
score = 40 - MIN(40, (days_since_last_txn / 90.0) × 40)
```
- 0 days since last txn → 40 points (transacted today)
- 45 days → 20 points
- 90+ days → 0 points

**Component 2 — Frequency (0-35 points):**
```
score = MIN(35, (txn_count_30d / 30.0) × 35)
```
- 30+ transactions in 30 days → 35 points (daily user)
- 15 transactions → 17.5 points
- 0 transactions → 0 points

**Component 3 — Diversity (0-25 points):**
```
channel_score  = MIN(12.5, (distinct_channels_90d / 5.0) × 12.5)
type_score     = MIN(12.5, (distinct_txn_types_90d / 5.0) × 12.5)
diversity      = channel_score + type_score
```
- 5+ distinct channels → 12.5 points
- 5+ distinct transaction types → 12.5 points

```sql
UPDATE customer_features
SET engagement_score = ROUND(
    -- Recency (40%)
    LEAST(40, GREATEST(0,
        40.0 - LEAST(40.0,
            (COALESCE(days_since_last_txn, 90)::float / 90.0) * 40.0
        )
    ))
    +
    -- Frequency (35%)
    LEAST(35, GREATEST(0,
        (COALESCE(txn_count_30d, 0)::float / 30.0) * 35.0
    ))
    +
    -- Diversity (25%)
    LEAST(25, GREATEST(0,
        (COALESCE(distinct_channels_90d, 0)::float / 5.0) * 12.5
        +
        (COALESCE(distinct_txn_types_90d, 0)::float / 5.0) * 12.5
    )),
    0
)
WHERE as_of_date = %(as_of_date)s::date;
```

**Edge cases:**
- Customer with zero transactions → 0.0 (recency: 0, frequency: 0, diversity: 0)
- All NULL inputs → COALESCE defaults prevent NULL propagation
- Score always clamped to [0, 100] via LEAST/GREATEST

### Feature 5.4: `has_salary_credit`

**Logic:** Detects salary deposits by looking for recurring large CREDIT transactions. Threshold: at least 2 credits of 2,000 ZMW or more within 90 days. The 2,000 ZMW threshold is configurable — it should be adjusted based on the bank's typical salary ranges per segment.

```sql
UPDATE customer_features cf
SET has_salary_credit = EXISTS (
    SELECT 1 FROM customer_transactions_clean t
    WHERE t.customer_id = cf.customer_id
      AND t.transaction_date::date > (
          cf.as_of_date - INTERVAL '90 days'
      )
      AND t.transaction_date::date <= cf.as_of_date
      AND t.transaction_type = 'CREDIT'
      AND t.amount >= 2000
    HAVING COUNT(*) >= 2
)
WHERE cf.as_of_date = %(as_of_date)s::date;
```

**Edge cases:**
- Zero transactions → FALSE (EXISTS subquery returns empty)
- One large credit only → FALSE (HAVING COUNT(*) >= 2 fails)
- Regular small credits → FALSE (amount filter)
- Configurable threshold — consider making `salary_threshold` a settings parameter

### Feature 5.5: `monthly_income_estimate`

**Logic:** Estimates monthly income from total CREDIT transactions in 90 days divided by 3 months. Excludes micro-credits under 500 ZMW which are likely refunds, reversals, or interest payments rather than income.

```
monthly_income = SUM(CREDIT amounts >= 500 in 90d) / 3
```

```sql
UPDATE customer_features cf
SET monthly_income_estimate = (
    SELECT COALESCE(SUM(amount), 0) / 3.0
    FROM customer_transactions_clean t
    WHERE t.customer_id = cf.customer_id
      AND t.transaction_date::date > (
          cf.as_of_date - INTERVAL '90 days'
      )
      AND t.transaction_date::date <= cf.as_of_date
      AND t.transaction_type = 'CREDIT'
      AND t.amount >= 500
)
WHERE cf.as_of_date = %(as_of_date)s::date;
```

**Edge cases:**
- Zero credits → 0.0 (COALESCE handles NULL)
- Only micro-credits → 0.0 (amount filter)
- Single large salary deposit → amount / 3 (approximates monthly)
- NULL amounts → excluded by amount >= 500 filter

### Feature 5.6: `credit_to_debit_ratio_90d`

**Logic:** Ratio of total credits to total debits in 90 days. A ratio above 1.0 means the customer receives more than they spend — positive cash flow. Below 1.0 means net spender.

```sql
UPDATE customer_features cf
SET credit_to_debit_ratio_90d = (
    SELECT CASE
        WHEN COALESCE(
            SUM(amount) FILTER (WHERE transaction_type = 'DEBIT'), 0
        ) = 0 THEN NULL
        ELSE ROUND(
            COALESCE(
                SUM(amount) FILTER (WHERE transaction_type = 'CREDIT'), 0
            ) /
            NULLIF(
                SUM(amount) FILTER (WHERE transaction_type = 'DEBIT'), 0
            ),
            2
        )
    END
    FROM customer_transactions_clean t
    WHERE t.customer_id = cf.customer_id
      AND t.transaction_date::date > (
          cf.as_of_date - INTERVAL '90 days'
      )
      AND t.transaction_date::date <= cf.as_of_date
)
WHERE cf.as_of_date = %(as_of_date)s::date;
```

**Edge cases:**
- Zero debits → NULL (division by zero guarded)
- Zero credits → 0.0
- Zero transactions → 0.0 (both sums NULL, COALESCE → 0, ratio = 0/0 → NULL via NULLIF)
- Only CREDIT → NULL (no debits to compare against)

---

## 6. Generator 3: CLV Features

### Purpose

Compute Customer Lifetime Value indicators from revenue trends and income estimates.

### File

`services/feature-engineering-service/app/features/clv/generator.py`

### Class

```python
class CLVGenerator:
    """Generates Customer Lifetime Value features from revenue trends."""

    def __init__(self, conn: psycopg2.extensions.connection):
        self._conn = conn

    def generate(self, as_of_date: date) -> dict:
        """Run all CLV feature SQL statements.

        Returns:
            Dict with row counts:
            {
                "revenue_trend": int,
                "predicted_annual_value": int
            }
        """
```

### Feature 6.1: `revenue_trend_6m`

**Logic:** Compares average monthly revenue in the most recent 3 months (90 days) to the previous 3 months (days 90-180). Classifies into three buckets based on the ratio.

```
recent_monthly   = total_amount_90d / 3
previous_monthly = (total_amount_180d - total_amount_90d) / 3
ratio            = recent_monthly / previous_monthly

> 1.2   → "increasing"
0.8-1.2 → "stable"
< 0.8   → "declining"
```

**Step 1 — Compute ratio:**
```sql
UPDATE customer_features
SET revenue_trend_6m = CASE
    WHEN total_amount_180d IS NULL OR total_amount_90d IS NULL THEN NULL
    WHEN total_amount_180d = 0 THEN NULL
    WHEN (total_amount_180d - total_amount_90d) <= 0 THEN NULL
    ELSE ROUND(
        (total_amount_90d / 3.0) /
        NULLIF((total_amount_180d - total_amount_90d) / 3.0, 0),
        2
    )
END
WHERE as_of_date = %(as_of_date)s::date;
```

**Step 2 — Classify:**
```sql
UPDATE customer_features
SET revenue_trend_6m = CASE
    WHEN revenue_trend_6m IS NULL THEN NULL
    WHEN revenue_trend_6m::float > 1.2 THEN 'increasing'
    WHEN revenue_trend_6m::float >= 0.8 THEN 'stable'
    ELSE 'declining'
END
WHERE as_of_date = %(as_of_date)s::date
  AND revenue_trend_6m IS NOT NULL
  AND revenue_trend_6m !~ '^[a-z]';  -- skip already-classified rows
```

**Edge cases:**
- Zero historical revenue → NULL (can't compute trend)
- Recent revenue only (new customer) → NULL (no previous period to compare)
- Exact boundary values (0.8, 1.2) → "stable" / "increasing" respectively (>=)
- Already classified rows → skipped on re-run (regex guard)

### Feature 6.2: `predicted_annual_value`

**Logic:** Simple heuristic CLV proxy using income estimate and a retention factor based on inactivity. This is NOT a trained ML model — it's a transparent, explainable heuristic suitable for PoC. The actual XGBoost/LightGBM CLV model in Layer 2 will replace this in post-PoC.

```
retention_factor = 1 - MIN(1.0, days_since_last_txn / 365)
annual_value     = monthly_income_estimate × 12 × retention_factor
```

A customer who transacted today (retention_factor = 1.0) gets full annual value. A customer inactive for 365+ days gets 0.

```sql
UPDATE customer_features
SET predicted_annual_value = ROUND(
    COALESCE(monthly_income_estimate, 0) * 12.0 *
    (1.0 - LEAST(1.0,
        COALESCE(days_since_last_txn, 365)::float / 365.0
    )),
    2
)
WHERE as_of_date = %(as_of_date)s::date;
```

**Edge cases:**
- Zero income → 0.0
- Active daily customer → monthly_income × 12 (full value)
- 182 days inactive → monthly_income × 12 × 0.5 (50% haircut)
- 365+ days inactive → 0.0 (retention_factor = 0)
- NULL income → 0.0 (COALESCE to 0)

---

## 7. Pipeline Orchestration

### File

`services/feature-engineering-service/app/pipelines/pipeline.py`

### Class

```python
import time
from datetime import date

import psycopg2

from app.repository.repository import FeatureRepository
from app.features.customer.generator import CustomerProfileGenerator
from app.features.behaviour.generator import BehaviourGenerator
from app.features.clv.generator import CLVGenerator


class FeaturePipeline:
    """Orchestrates all feature generators in dependency order.

    Pipeline DAG:
        Phase 1 SQL (repo.compute_batch)
            ↓
        Generator 1: Customer Profile (customers_clean → features)
            ↓
        Generator 2: Behaviour (transactions + features → features)
            ↓
        Generator 3: CLV (features → features)
    """

    def __init__(self, conn: psycopg2.extensions.connection):
        self._repo = FeatureRepository(conn)
        self._customer_gen = CustomerProfileGenerator(conn)
        self._behaviour_gen = BehaviourGenerator(conn)
        self._clv_gen = CLVGenerator(conn)

    def run(self, as_of_date: date | None = None) -> dict:
        """Execute the full feature pipeline.

        Args:
            as_of_date: Date to compute features as-of (default: today).

        Returns:
            Dict with timing and row counts per stage:
            {
                "as_of_date": "2026-07-26",
                "status": "COMPLETED",
                "total_duration_seconds": 12.5,
                "stages": {
                    "phase1": {
                        "customers_processed": 15200,
                        "rows_upserted": 15200,
                        "phase2_updated": 15200,
                        "duration_seconds": 3.2
                    },
                    "customer_profile": {
                        "rows_updated": 15200,
                        "duration_seconds": 0.5
                    },
                    "behaviour": {
                        "inactivity_streak": 15200,
                        "frequency_trend": 14800,
                        "engagement_score": 15200,
                        "salary_credit": 15200,
                        "monthly_income": 15200,
                        "credit_debit_ratio": 14500,
                        "duration_seconds": 8.1
                    },
                    "clv": {
                        "revenue_trend": 12000,
                        "predicted_annual_value": 15200,
                        "duration_seconds": 0.7
                    }
                }
            }
        """
        effective_date = as_of_date or date.today()
        t0 = time.time()
        stages = {}

        # Stage 0: Phase 1 transaction aggregates
        t_start = time.time()
        phase1 = self._repo.compute_batch(effective_date)
        stages["phase1"] = {**phase1, "duration_seconds": round(time.time() - t_start, 2)}

        # Stage 1: Customer profile
        t_start = time.time()
        n = self._customer_gen.generate(effective_date)
        stages["customer_profile"] = {
            "rows_updated": n,
            "duration_seconds": round(time.time() - t_start, 2),
        }

        # Stage 2: Behaviour
        t_start = time.time()
        behaviour_results = self._behaviour_gen.generate(effective_date)
        stages["behaviour"] = {
            **behaviour_results,
            "duration_seconds": round(time.time() - t_start, 2),
        }

        # Stage 3: CLV
        t_start = time.time()
        clv_results = self._clv_gen.generate(effective_date)
        stages["clv"] = {
            **clv_results,
            "duration_seconds": round(time.time() - t_start, 2),
        }

        return {
            "as_of_date": effective_date.isoformat(),
            "status": "COMPLETED",
            "total_duration_seconds": round(time.time() - t0, 2),
            "stages": stages,
        }
```

### Error Strategy

If any stage fails, the pipeline stops. Previously completed stages remain committed (each stage runs in auto-commit mode via psycopg2). The returned dict includes partial results with `"status": "FAILED"` and an `"error"` key.

```
Stage 1 passes → committed
Stage 2 fails  → Stage 1 results preserved, Stage 2-3 not run
```

This is acceptable because all generators are idempotent — re-running the pipeline will complete the remaining stages.

---

## 8. Repository Methods

### File

`services/feature-engineering-service/app/repository/repository.py`

### New Methods to Add

These methods provide database access for the generators. They follow the same psycopg2 pattern as the existing `compute_batch()`, `get_features()`, and `get_latest()` methods.

```python
def run_customer_profile(self, as_of_date: date) -> int:
    """Generator 1: Update customer_features with profile attributes.

    Args:
        as_of_date: Compute features as of this date.

    Returns:
        Number of rows updated.
    """
    sql = """
        UPDATE customer_features cf
        SET
            customer_tenure_days = (
                %(as_of_date)s::date - cc.activation_date::date
            ),
            customer_segment = cc.customer_type,
            age_years = EXTRACT(
                YEAR FROM AGE(%(as_of_date)s::date, cc.date_of_birth::date)
            ),
            onboarding_channel = cc.onboarding_channel
        FROM customers_clean cc
        WHERE cf.customer_id = cc.customer_id
          AND cf.as_of_date = %(as_of_date)s::date
    """
    with self._conn.cursor() as cur:
        cur.execute(sql, {"as_of_date": as_of_date})
        self._conn.commit()
        return cur.rowcount


def run_behaviour_features(self, as_of_date: date) -> dict:
    """Generator 2: Compute behaviour, engagement, and income features.

    Returns:
        Dict with row counts per feature query.
    """
    results = {}
    queries = {
        "inactivity_streak": "UPDATE customer_features SET inactivity_streak_days = days_since_last_txn WHERE as_of_date = %(d)s::date",
        "frequency_trend": """UPDATE customer_features SET txn_frequency_trend = CASE ... END WHERE as_of_date = %(d)s::date""",
        "engagement_score": """UPDATE customer_features SET engagement_score = ... WHERE as_of_date = %(d)s::date""",
        "salary_credit": """UPDATE customer_features cf SET has_salary_credit = EXISTS (...) WHERE cf.as_of_date = %(d)s::date""",
        "monthly_income": """UPDATE customer_features cf SET monthly_income_estimate = (...) WHERE cf.as_of_date = %(d)s::date""",
        "credit_debit_ratio": """UPDATE customer_features cf SET credit_to_debit_ratio_90d = (...) WHERE cf.as_of_date = %(d)s::date""",
    }
    params = {"d": as_of_date}
    with self._conn.cursor() as cur:
        for name, sql in queries.items():
            cur.execute(sql, params)
            results[name] = cur.rowcount
        self._conn.commit()
    return results


def run_clv_features(self, as_of_date: date) -> dict:
    """Generator 3: Compute CLV features.

    Returns:
        Dict with row counts per feature query.
    """
    # Two-step: compute ratio, then classify
    results = {}
    params = {"d": as_of_date}

    with self._conn.cursor() as cur:
        # Step 1: Compute revenue trend ratio
        cur.execute("""
            UPDATE customer_features
            SET revenue_trend_6m = CASE ... END
            WHERE as_of_date = %(d)s::date
        """, params)
        results["revenue_trend_ratio"] = cur.rowcount

        # Step 2: Classify into increasing/stable/declining
        cur.execute("""
            UPDATE customer_features
            SET revenue_trend_6m = CASE ... END
            WHERE as_of_date = %(d)s::date
              AND revenue_trend_6m IS NOT NULL
              AND revenue_trend_6m !~ '^[a-z]'
        """, params)
        results["revenue_trend_classified"] = cur.rowcount

        # Step 3: Predicted annual value
        cur.execute("""
            UPDATE customer_features
            SET predicted_annual_value = ROUND(...)
            WHERE as_of_date = %(d)s::date
        """, params)
        results["predicted_annual_value"] = cur.rowcount

        self._conn.commit()
    return results
```

### Connection Management

The repository uses a single psycopg2 connection passed at construction time. The connection is created by the FeatureService and shared across all generators. This avoids connection pool overhead for what is essentially a batch processing pipeline.

The connection string comes from `shared.config.settings.settings.database_target_url` (converted from asyncpg to psycopg2 format).

---

## 9. Error Handling & Edge Cases

### 9.1 Null Handling Strategy

| Scenario | Strategy |
|---|---|
| Missing source data (customer not in customers_clean) | Feature remains NULL. Generator skips via WHERE clause. |
| Division by zero | NULLIF on denominator. Feature evaluates to NULL. |
| Zero transactions for a customer | Count features = 0, monetary features = 0 or NULL depending on context. |
| Single transaction (can't compute stddev or avg_days_between) | Already handled in Phase 1 SQL. Generator 2 uses these as inputs — NULLs propagate safely. |
| Negative amounts | No guard. Assumed clean — ETL validation should prevent negative amounts. |
| Future transaction dates | No guard. Assumed clean — `transaction_date <= as_of_date` filter handles this. |

### 9.2 Idempotency

All generators are idempotent by design:
- Generator 1: Same values overwritten with same values (static customer attributes)
- Generator 2: Recalculated values overwrite previous values. Safe because inputs don't change for the same `as_of_date`.
- Generator 3: Two-step classification uses a regex guard (`!~ '^[a-z]'`) to skip already-classified rows.

Running the pipeline twice on the same `as_of_date` produces identical results.

### 9.3 Concurrency

Generators are NOT designed for concurrent execution. They run sequentially within a single database connection. If two instances of the pipeline run simultaneously on different `as_of_date` values, they operate on different rows (different `as_of_date` values) and won't conflict.

Two instances running on the same `as_of_date` will produce duplicate work but consistent results (idempotency).

### 9.4 Failure Recovery

If a generator fails mid-execution:
- psycopg2 rolls back the current transaction
- Previously committed stages remain (each stage commits separately)
- Re-running the pipeline will re-execute the failed stage(s)

---

## 10. Testing Strategy

### 10.1 Unit Tests (`tests/test_generators.py`)

Test each generator independently with hand-crafted fixture data.

**Generator 1 — Customer Profile:**
- [ ] All 4 features populated for customers present in customers_clean
- [ ] `customer_tenure_days` matches manual calculation from activation_date
- [ ] `age_years` NULL when date_of_birth is NULL
- [ ] `customer_segment` matches customer_type exactly
- [ ] Customer not in customers_clean → no rows updated (features remain NULL)
- [ ] Idempotency: running twice produces same values

**Generator 2 — Behaviour:**
- [ ] `inactivity_streak_days` equals `days_since_last_txn` for all customers
- [ ] `txn_frequency_trend` > 1.0 for accelerating, < 1.0 for declining, NULL for zero txns
- [ ] `engagement_score` between 0 and 100 for all customers
- [ ] Customer with 0 transactions → engagement_score = 0
- [ ] Customer with daily transactions, 5+ channels → engagement_score close to 100
- [ ] `has_salary_credit` TRUE for customer with 3 monthly CREDIT txns ≥ 2000
- [ ] `has_salary_credit` FALSE for customer with only small credits
- [ ] `monthly_income_estimate` = total_90d_credits / 3 (excluding micro-credits)
- [ ] `credit_to_debit_ratio_90d` NULL when no debits, 0 when no credits
- [ ] Division by zero: all ratios NULL-safe

**Generator 3 — CLV:**
- [ ] `revenue_trend_6m` is one of: "increasing", "stable", "declining", NULL
- [ ] 2x revenue increase → "increasing"
- [ ] Same revenue → "stable"
- [ ] 50% revenue drop → "declining"
- [ ] New customer (no previous period) → NULL
- [ ] `predicted_annual_value` ≤ `monthly_income_estimate × 12`
- [ ] 365+ days inactive → predicted_annual_value = 0
- [ ] Daily active → predicted_annual_value = monthly_income × 12
- [ ] Zero income → predicted_annual_value = 0

### 10.2 Integration Tests

- [ ] Full pipeline runs end-to-end without errors
- [ ] Pipeline returns correct stage durations and row counts
- [ ] Re-running pipeline produces idempotent results
- [ ] Pipeline fails gracefully on missing tables
- [ ] Phase 1 SQL still works after migration (new columns don't break INSERT)

### 10.3 Fixture Data

Use the existing fixture pattern from `tests/conftest.py`. Add:
- Customer with many transactions (daily, multiple channels)
- Customer with few transactions (monthly, single channel)
- Customer with zero transactions
- Customer with salary credits
- Customer not in customers_clean (orphan)
- Customer with NULL date_of_birth

---

## 11. Implementation Checklist

### Step 1: Database Migration (5 min)

Run these SQL statements against `etl_clean`:

```sql
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS customer_tenure_days INTEGER;
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS customer_segment VARCHAR(32);
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS age_years INTEGER;
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS onboarding_channel VARCHAR(32);
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS inactivity_streak_days INTEGER;
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS txn_frequency_trend FLOAT;
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS engagement_score FLOAT;
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS revenue_trend_6m VARCHAR(16);
ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS predicted_annual_value FLOAT;
```

### Step 2: Generator 1 — Customer Profile (30 min)

- [ ] Delete stub content in `features/customer/generator.py`
- [ ] Implement `CustomerProfileGenerator` class
- [ ] Add SQL UPDATE statement
- [ ] Handle NULL date_of_birth and activation_date
- [ ] Verify with manual query against test customer

### Step 3: Generator 2 — Behaviour (1 hr)

- [ ] Delete stub content in `features/behaviour/generator.py`
- [ ] Implement 6 feature SQL statements in `BehaviourGenerator.generate()`
- [ ] Engagement score: verify recency + frequency + diversity formula
- [ ] Salary credit: verify threshold and HAVING clause
- [ ] Credit/debit ratio: verify NULLIF guard
- [ ] Test with fixture data from conftest.py

### Step 4: Generator 3 — CLV (30 min)

- [ ] Delete stub content in `features/clv/generator.py`
- [ ] Implement 2-step revenue trend: ratio → classification
- [ ] Implement predicted_annual_value with retention factor
- [ ] Test boundary values (0, 365 days inactive)
- [ ] Test classification boundaries (0.8, 1.2)

### Step 5: Repository Methods (30 min)

- [ ] Add `run_customer_profile(as_of_date)` to `FeatureRepository`
- [ ] Add `run_behaviour_features(as_of_date)` to `FeatureRepository`
- [ ] Add `run_clv_features(as_of_date)` to `FeatureRepository`
- [ ] Each method: execute SQL, commit, return row count

### Step 6: Pipeline Orchestrator (30 min)

- [ ] Delete stub content in `pipelines/pipeline.py`
- [ ] Implement `FeaturePipeline` class
- [ ] Wire all generators in correct dependency order
- [ ] Add timing instrumentation per stage
- [ ] Return structured results dict
- [ ] Update `FeatureService.compute_batch()` to use `FeaturePipeline.run()` instead of just `FeatureRepository.compute_batch()`

### Step 7: Tests (1 hr)

- [ ] Write `tests/test_generators.py` with 15+ test cases
- [ ] Add fixture data for edge cases
- [ ] Run existing `tests/test_features.py` to verify no regressions
- [ ] Run: `pytest services/feature-engineering-service/tests/ -v`

### Step 8: Verification (Manual)

```bash
# 1. Compute features via gateway
curl -X POST http://localhost:8080/features/compute-batch \
  -H "Authorization: Bearer $(get_token)"

# 2. Check a customer has all features
curl http://localhost:8080/features/C0000001/latest \
  -H "Authorization: Bearer $(get_token)" | python -m json.tool

# 3. Verify specific values
# - customer_tenure_days should be positive integer
# - engagement_score should be between 0-100
# - customer_segment should match customer_type
# - has_salary_credit should be true/false
```
