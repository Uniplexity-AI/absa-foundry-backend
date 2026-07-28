# Customer Feature Store Architecture v1.0

## Authoritative Design — Contract Between Data Engineering and AI Engineering

> **Version:** 1.0  
> **Date:** 2026-07-27  
> **Status:** Implemented  
> **Target:** 60 features across 7 domains  
> **Current:** 56 implemented (Phase 1 + Phase 2) + 4 deferred (accounts/loans/timestamp dependencies)

---

## Table of Contents

1. [Mission & Principles](#1-mission--principles)
2. [Architecture Boundaries](#2-architecture-boundaries)
3. [Feature Domains](#3-feature-domains)
4. [Domain 1 — Customer Profile](#4-domain-1--customer-profile)
5. [Domain 2 — Behaviour](#5-domain-2--behaviour)
6. [Domain 3 — Financial](#6-domain-3--financial)
7. [Domain 4 — Channel](#7-domain-4--channel)
8. [Domain 5 — Relationship](#8-domain-5--relationship)
9. [Domain 6 — Risk](#9-domain-6--risk)
10. [Domain 7 — Temporal](#10-domain-7--temporal)
11. [Feature Metadata Catalog](#11-feature-metadata-catalog)
12. [Computation Pipeline](#12-computation-pipeline)
13. [Data Contracts](#13-data-contracts)
14. [Implementation Plan](#14-implementation-plan)
15. [SQL Reference](#15-sql-reference)

---

## 1. Mission & Principles

### Mission

The Customer Feature Store is the centralized repository of **observable customer behaviour** derived from banking data. It stores only features that can be computed directly from historical data available at or before the `as_of_date`.

It **must not** contain:

- Markov states
- Churn predictions
- CLV predictions
- NBA recommendations
- Survival probabilities
- Any ML model outputs

Those belong to downstream AI services.

### Architectural Rules

**Rule 1 — Explainability.** Every feature must be explainable by its name alone. A business analyst should understand what it measures without consulting documentation.

```
Good: txn_count_30d, total_credit_90d, mobile_ratio_90d
Bad:  customer_score, feature_42, cluster_label
```

**Rule 2 — Reproducibility.** Running the pipeline on the same snapshot must produce identical results. No randomness. No external API calls. No non-deterministic functions. No `RAND()`, no `NOW()` in computation logic, no UUID generation.

**Rule 3 — Point-in-Time Correctness.** Every feature is computed using only data available at or before `as_of_date`. No future information. This prevents data leakage in downstream ML training. A churn model trained on features that accidentally included future transactions would report unrealistic accuracy.

**Rule 4 — No ML Predictions.** The Feature Store contains observations. Models create predictions. The boundary is absolute and unidirectional: if a value is the output of `model.predict()`, it does not belong here.

**Rule 5 — Domain Ownership.** Each feature belongs to exactly one domain. No feature appears in two domains. Each domain has a single generator responsible for its computation. This prevents conflicting definitions of the same feature from different teams.

---

## 2. Architecture Boundaries

```
              Source Banking Systems
┌──────────────────────────────────────────────────┐
│ Customers  │ Transactions │ Accounts │ Cards     │
│ Loans      │ Channels     │ CRM      │ (future)  │
└──────────────────────────────────────────────────┘
                     │
                     ▼
              ETL Engine (run_etl.py)
              Validates, transforms, loads clean tables
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│            CUSTOMER FEATURE STORE                │
│                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Profile  │ │Behaviour │ │    Financial     │ │
│  │ (8 feat) │ │(15 feat) │ │   (12 feat)      │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────┐│ │
│  │ Channel  │ │Relation. │ │  Risk    │ │Temp.││ │
│  │ (8 feat) │ │(5 feat)  │ │(6 feat)  │ │(6)  ││ │
│  └──────────┘ └──────────┘ └──────────┘ └─────┘│ │
│                                                  │
│  Table: customer_features (etl_clean)            │
│  PK: (customer_id, as_of_date)                   │
│  One row per customer per snapshot date          │
│  60 columns: 7 domains, unified schema           │
└──────────────────────────────────────────────────┘
                     │
                     │  READ-ONLY contract
                     │  NO write-back path
                     ▼
┌──────────────────────────────────────────────────┐
│             Downstream AI Services               │
│                                                  │
│  Customer State Service    (Markov chain)        │
│  Churn Prediction          (XGBoost/LightGBM)    │
│  CLV Estimation            (XGBoost/LightGBM)    │
│  Customer Segmentation     (Clustering)          │
│  Decision Intelligence     (NBA Engine)          │
│  RM Dashboard API          (Vue Frontend)        │
│                                                  │
│  Each service stores its own outputs:            │
│  - customer_states.{state, transition_prob}      │
│  - predictions.{churn_prob, clv, health_score}   │
│  - decisions.{nba_rankings, recommended_actions} │
└──────────────────────────────────────────────────┘
```

**Critical rule:** There is no arrow from AI services back into the Feature Store. Models read features. They do not write features. If a model output is useful as an input to another model, that dependency must be explicit in the orchestration layer, not baked into the feature store schema.

---

## 3. Feature Domains

| # | Domain | Abbreviation | Features | v1 Status |
|---|---|---|---|---|
| 1 | Customer Profile | `prof` | 8 | 6 done, 2 deferred (kyc_tier, nationality) |
| 2 | Behaviour | `behav` | 16 | 16 done |
| 3 | Financial | `fin` | 12 | 12 done |
| 4 | Channel | `chan` | 8 | 8 done |
| 5 | Relationship | `rel` | 5 | 1 done, 4 deferred (accounts/loans) |
| 6 | Risk | `risk` | 6 | 5 done, 1 deferred (no 30d txn data) |
| 7 | Temporal | `temp` | 6 | 3 done, 3 deferred (timestamp needed) |
| **Total** | | | **61** | **51 active, 10 deferred** |

### Naming Convention

All features follow the pattern: `{domain_abbrev}_{descriptor}_{window}`

| Element | Rule | Example |
|---|---|---|
| Domain prefix | 3-5 letter abbreviation | `behav_`, `fin_`, `chan_` |
| Descriptor | Descriptive, no abbreviations | `txn_count`, `total_credit`, `mobile_ratio` |
| Window | Suffix indicating time window | `_30d`, `_90d`, `_365d` |

Legacy Phase 1 features use names without domain prefixes (e.g., `txn_count_30d` instead of `behav_txn_count_30d`). These will be aliased for backward compatibility. New Phase 2 features use the new convention.

### Feature Metadata Schema

Every feature in the catalog is documented with:

| Attribute | Description |
|---|---|
| **Feature Name** | Unique identifier following naming convention |
| **Domain** | One of the 7 domains |
| **Data Type** | INTEGER, FLOAT, BOOLEAN, VARCHAR |
| **Source Tables** | Tables queried to compute this feature |
| **Computation** | Brief formula description |
| **Refresh Frequency** | Daily (computed per as_of_date) |
| **Point-in-Time Safe** | Yes (always) |
| **Downstream Consumers** | Which AI services use this feature |
| **Status** | Implemented or Planned |

---

## 4. Domain 1 — Customer Profile

**Ownership:** `features/profile/generator.py`  
**Source Tables:** `customers_clean`  
**Nature:** Slowly-changing attributes. Computed once per `as_of_date`, same value for all snapshots of a given customer.

### Features (8 total)

| # | Feature | Type | Source | Computation | Status |
|---|---|---|---|---|---|
| 1 | `prof_customer_type` | VARCHAR(32) | customers_clean | Direct copy of customer_type | ✅ |
| 2 | `prof_tenure_days` | INTEGER | customers_clean | as_of_date - activation_date | ✅ |
| 3 | `prof_age_years` | INTEGER | customers_clean | EXTRACT(YEAR FROM AGE(as_of_date, date_of_birth)) | ✅ |
| 4 | `prof_onboarding_channel` | VARCHAR(32) | customers_clean | Direct copy | ✅ |
| 5 | `prof_age_band` | VARCHAR(16) | customers_clean | Bucket: <18, 18-25, 26-35, 36-50, 51-65, 65+ | 🆕 |
| 6 | `prof_kyc_tier` | VARCHAR(16) | customers_clean | Direct copy if available in source | 🆕 |
| 7 | `prof_primary_branch` | VARCHAR(16) | customers_clean | Direct copy of branch_code | 🆕 |
| 8 | `prof_nationality` | VARCHAR(64) | customers_clean | Direct copy if available in source | 🆕 |

### SQL

```sql
UPDATE customer_features cf
SET
    prof_customer_type       = cc.customer_type,
    prof_tenure_days         = (%(d)s::date - cc.activation_date::date),
    prof_age_years           = EXTRACT(YEAR FROM AGE(%(d)s::date, cc.date_of_birth::date)),
    prof_onboarding_channel  = cc.onboarding_channel,
    prof_age_band            = CASE
        WHEN EXTRACT(YEAR FROM AGE(%(d)s::date, cc.date_of_birth::date)) < 18 THEN '<18'
        WHEN EXTRACT(YEAR FROM AGE(%(d)s::date, cc.date_of_birth::date)) BETWEEN 18 AND 25 THEN '18-25'
        WHEN EXTRACT(YEAR FROM AGE(%(d)s::date, cc.date_of_birth::date)) BETWEEN 26 AND 35 THEN '26-35'
        WHEN EXTRACT(YEAR FROM AGE(%(d)s::date, cc.date_of_birth::date)) BETWEEN 36 AND 50 THEN '36-50'
        WHEN EXTRACT(YEAR FROM AGE(%(d)s::date, cc.date_of_birth::date)) BETWEEN 51 AND 65 THEN '51-65'
        WHEN EXTRACT(YEAR FROM AGE(%(d)s::date, cc.date_of_birth::date)) >= 65 THEN '65+'
    END,
    prof_primary_branch      = cc.branch_code
FROM customers_clean cc
WHERE cf.customer_id = cc.customer_id
  AND cf.as_of_date = %(d)s::date;
```

### Edge Cases

| Scenario | Behaviour |
|---|---|
| `date_of_birth` NULL | `prof_age_years` = NULL, `prof_age_band` = NULL |
| `activation_date` NULL | `prof_tenure_days` = NULL |
| `customer_type` not in known set | Passed through as-is (no validation) |
| Customer not in customers_clean | Row skipped via INNER JOIN. Features remain NULL from Phase 1. |
| Generator re-run on same as_of_date | Idempotent — same values overwritten |

---

## 5. Domain 2 — Behaviour

**Ownership:** `features/behaviour/generator.py`  
**Source Tables:** `customer_transactions_clean`, `customer_features` (reads Phase 1 aggregates)  
**Nature:** The heart of lifecycle prediction. Transaction patterns, engagement metrics, activity levels.

### Features (15 total)

| # | Feature | Type | Source | Computation | Status |
|---|---|---|---|---|---|
| 1 | `behav_days_since_last_txn` | INTEGER | txn_clean | as_of_date - MAX(transaction_date) | ✅ |
| 2 | `behav_days_since_first_txn` | INTEGER | txn_clean | as_of_date - MIN(transaction_date) | ✅ |
| 3 | `behav_txn_count_7d` | INTEGER | txn_clean | COUNT WHERE date > as_of_date - 7d | 🆕 |
| 4 | `behav_txn_count_30d` | INTEGER | txn_clean | COUNT WHERE date > as_of_date - 30d | ✅ |
| 5 | `behav_txn_count_90d` | INTEGER | txn_clean | COUNT WHERE date > as_of_date - 90d | ✅ |
| 6 | `behav_txn_count_180d` | INTEGER | txn_clean | COUNT WHERE date > as_of_date - 180d | ✅ |
| 7 | `behav_txn_count_365d` | INTEGER | txn_clean | COUNT WHERE date > as_of_date - 365d | ✅ |
| 8 | `behav_avg_days_between_txn` | FLOAT | txn_clean | tenure_days / (total_count - 1) | ✅ |
| 9 | `behav_txn_frequency_trend` | FLOAT | features | (count_30d / 30) / (count_90d / 90) | ✅ |
| 10 | `behav_active_days_90d` | INTEGER | txn_clean | COUNT(DISTINCT transaction_date) in 90d | 🆕 |
| 11 | `behav_inactive_days_90d` | INTEGER | features | 90 - active_days_90d | 🆕 |
| 12 | `behav_engagement_score` | FLOAT | features | Composite 0-100: recency(40) + frequency(35) + diversity(25) | ✅ |
| 13 | `behav_recency_score` | FLOAT | features | Component of engagement: 40 - min(40, days_since_last_txn/90 * 40) | 🆕 |
| 14 | `behav_frequency_score` | FLOAT | features | Component of engagement: min(35, txn_count_30d/30 * 35) | 🆕 |
| 15 | `behav_diversity_score` | FLOAT | features | Component of engagement: channel_diversity + type_diversity | 🆕 |
| 16 | `behav_activity_consistency` | FLOAT | features | active_days_90d / 90. Range 0-1 | 🆕 |

### Engagement Score Formula

The engagement score is a composite 0-100 metric combining three dimensions:

**Component 1 — Recency (0-40 points):**
```
recency_score = 40 - MIN(40, (days_since_last_txn / 90.0) × 40)
```
- 0 days since last transaction → 40 points (transacted today)
- 45 days → 20 points
- 90+ days → 0 points

**Component 2 — Frequency (0-35 points):**
```
frequency_score = MIN(35, (txn_count_30d / 30.0) × 35)
```
- 30+ transactions in 30 days → 35 points (daily user)
- 15 transactions → 17.5 points
- 0 transactions → 0 points

**Component 3 — Diversity (0-25 points):**
```
channel_diversity = MIN(12.5, (distinct_channels_90d / 5.0) × 12.5)
type_diversity    = MIN(12.5, (distinct_txn_types_90d / 5.0) × 12.5)
diversity_score   = channel_diversity + type_diversity
```
- 5+ distinct channels → 12.5 points
- 5+ distinct transaction types → 12.5 points

**Total:** `engagement_score = recency_score + frequency_score + diversity_score`

### SQL

```sql
UPDATE customer_features
SET
    behav_txn_count_7d = (
        SELECT COUNT(*) FROM customer_transactions_clean t
        WHERE t.customer_id = customer_features.customer_id
          AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '7 days')
          AND t.transaction_date::date <= customer_features.as_of_date
    ),
    behav_active_days_90d = (
        SELECT COUNT(DISTINCT transaction_date::date)
        FROM customer_transactions_clean t
        WHERE t.customer_id = customer_features.customer_id
          AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= customer_features.as_of_date
    ),
    behav_inactive_days_90d = 90 - COALESCE((
        SELECT COUNT(DISTINCT transaction_date::date)
        FROM customer_transactions_clean t
        WHERE t.customer_id = customer_features.customer_id
          AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= customer_features.as_of_date
    ), 0),
    behav_activity_consistency = ROUND(
        COALESCE((
            SELECT COUNT(DISTINCT transaction_date::date)::float / 90.0
            FROM customer_transactions_clean t
            WHERE t.customer_id = customer_features.customer_id
              AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '90 days')
              AND t.transaction_date::date <= customer_features.as_of_date
        ), 0), 2
    ),
    -- Component scores + composite engagement
    behav_recency_score = LEAST(40, GREATEST(0,
        40.0 - LEAST(40.0, (COALESCE(behav_days_since_last_txn, 90)::float / 90.0) * 40.0)
    )),
    behav_frequency_score = LEAST(35, GREATEST(0,
        (COALESCE(behav_txn_count_30d, 0)::float / 30.0) * 35.0
    )),
    behav_diversity_score = LEAST(25, GREATEST(0,
        (COALESCE(distinct_channels_90d, 0)::float / 5.0) * 12.5
        + (COALESCE(distinct_txn_types_90d, 0)::float / 5.0) * 12.5
    )),
    behav_engagement_score = ROUND(
        LEAST(40, GREATEST(0,
            40.0 - LEAST(40.0, (COALESCE(behav_days_since_last_txn, 90)::float / 90.0) * 40.0)
        ))
        + LEAST(35, GREATEST(0, (COALESCE(behav_txn_count_30d, 0)::float / 30.0) * 35.0))
        + LEAST(25, GREATEST(0,
            (COALESCE(distinct_channels_90d, 0)::float / 5.0) * 12.5
            + (COALESCE(distinct_txn_types_90d, 0)::float / 5.0) * 12.5
        )), 0
    )
WHERE as_of_date = %(d)s::date;
```

### Edge Cases

| Scenario | Behaviour |
|---|---|
| Zero transactions for customer | All counts = 0, engagement = 0, scores = 0 |
| One transaction only | `avg_days_between_txn` = NULL (division by zero guarded) |
| All COALESCE fallbacks triggered | Defaults: days_since_last_txn→90, counts→0 |
| Scores out of range | Clamped via LEAST/GREATEST to [0, max] |
| Re-run on same as_of_date | Idempotent — same inputs produce same outputs |

---

## 6. Domain 3 — Financial

**Ownership:** `features/financial/generator.py`  
**Source Tables:** `customer_transactions_clean`, `customer_features`  
**Nature:** Money movement — credits, debits, amounts, income estimation, spending patterns.

### Features (12 total)

| # | Feature | Type | Source | Computation | Status |
|---|---|---|---|---|---|
| 1 | `fin_total_credit_30d` | FLOAT | txn_clean | SUM(amount WHERE CREDIT, 30d) | ✅ |
| 2 | `fin_total_debit_30d` | FLOAT | txn_clean | SUM(amount WHERE DEBIT, 30d) | ✅ |
| 3 | `fin_total_credit_90d` | FLOAT | txn_clean | SUM(amount WHERE CREDIT, 90d) | 🆕 |
| 4 | `fin_total_debit_90d` | FLOAT | txn_clean | SUM(amount WHERE DEBIT, 90d) | 🆕 |
| 5 | `fin_avg_txn_amount_90d` | FLOAT | txn_clean | AVG(amount, 90d) | ✅ |
| 6 | `fin_median_txn_amount_90d` | FLOAT | txn_clean | PERCENTILE_CONT(0.5), 90d | 🆕 |
| 7 | `fin_txn_amount_stddev_90d` | FLOAT | txn_clean | STDDEV(amount, 90d) | ✅ |
| 8 | `fin_salary_estimate` | FLOAT | txn_clean | SUM(CREDIT >= 500, 90d) / 3 | ✅ |
| 9 | `fin_salary_consistency` | FLOAT | txn_clean | STDDEV(monthly_credit_sums) / AVG(monthly_credit_sums) | 🆕 |
| 10 | `fin_income_growth` | FLOAT | features | credit_90d / (credit_180d - credit_90d) | 🆕 |
| 11 | `fin_cashflow_ratio` | FLOAT | txn_clean | total_credit_90d / total_debit_90d | ✅ |
| 12 | `fin_has_salary_credit` | BOOLEAN | txn_clean | COUNT(CREDIT >= 2000, 90d) >= 2 | ✅ |

### Salary Detection

Salary is detected by looking for recurring large CREDIT transactions. The logic uses two criteria:

1. **Amount threshold:** CREDIT transaction amount >= 2,000 ZMW (configurable)
2. **Recurrence:** At least 2 such credits within 90 days

This is a heuristic — it cannot distinguish between a salary deposit and a large one-off transfer. It works well for customers with regular monthly salary deposits from an employer but may produce false positives for business owners who receive irregular large payments.

### Income Estimation

Monthly income is estimated by summing all qualifying CREDIT transactions (amount >= 500 ZMW, excluding micro-credits like refunds or interest) over 90 days and dividing by 3. The 500 ZMW threshold filters out noise.

### Salary Consistency

Lower values indicate more regular income (typical of salaried employees). Higher values suggest irregular income (typical of self-employed or commission-based earners).

```
monthly_sums = GROUP BY DATE_TRUNC('month', transaction_date)
consistency  = STDDEV(monthly_sums) / AVG(monthly_sums)
```

### SQL

```sql
UPDATE customer_features cf
SET
    fin_total_credit_90d = (
        SELECT COALESCE(SUM(amount), 0) FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
          AND t.transaction_type = 'CREDIT'
    ),
    fin_total_debit_90d = (
        SELECT COALESCE(SUM(amount), 0) FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
          AND t.transaction_type = 'DEBIT'
    ),
    fin_median_txn_amount_90d = (
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ),
    fin_salary_consistency = (
        SELECT CASE
            WHEN AVG(monthly) > 0
            THEN ROUND(STDDEV(monthly)::float / NULLIF(AVG(monthly), 0), 2)
            ELSE NULL
        END
        FROM (
            SELECT DATE_TRUNC('month', transaction_date) AS month,
                   SUM(amount) AS monthly
            FROM customer_transactions_clean t
            WHERE t.customer_id = cf.customer_id
              AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
              AND t.transaction_date::date <= cf.as_of_date
              AND t.transaction_type = 'CREDIT'
              AND t.amount >= 500
            GROUP BY DATE_TRUNC('month', transaction_date)
        ) monthly_sums
    ),
    fin_income_growth = CASE
        WHEN fin_total_credit_90d IS NULL OR total_amount_180d IS NULL THEN NULL
        WHEN total_amount_180d - fin_total_credit_90d <= 0 THEN NULL
        ELSE ROUND(
            fin_total_credit_90d /
            NULLIF(total_amount_180d - fin_total_credit_90d, 0), 2
        )
    END,
    fin_cashflow_ratio = CASE
        WHEN fin_total_debit_90d = 0 THEN NULL
        ELSE ROUND(fin_total_credit_90d / NULLIF(fin_total_debit_90d, 0), 2)
    END,
    fin_has_salary_credit = EXISTS (
        SELECT 1 FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
          AND t.transaction_type = 'CREDIT'
          AND t.amount >= 2000
        HAVING COUNT(*) >= 2
    )
WHERE cf.as_of_date = %(d)s::date;
```

---

## 7. Domain 4 — Channel

**Ownership:** `features/channel/generator.py`  
**Source Tables:** `customer_transactions_clean`  
**Nature:** How the customer interacts with the bank — digital adoption, channel preferences, switching behaviour.

### Features (8 total)

| # | Feature | Type | Source | Computation | Status |
|---|---|---|---|---|---|
| 1 | `chan_distinct_channels_90d` | INTEGER | txn_clean | COUNT(DISTINCT channel, 90d) | ✅ |
| 2 | `chan_dominant_channel` | VARCHAR(32) | txn_clean | Mode of channel by count in 90d | ✅ |
| 3 | `chan_distinct_txn_types_90d` | INTEGER | txn_clean | COUNT(DISTINCT transaction_type, 90d) | ✅ |
| 4 | `chan_mobile_ratio_90d` | FLOAT | txn_clean | COUNT(MOBILE, 90d) / COUNT(*, 90d) | 🆕 |
| 5 | `chan_atm_ratio_90d` | FLOAT | txn_clean | COUNT(ATM, 90d) / COUNT(*, 90d) | 🆕 |
| 6 | `chan_branch_ratio_90d` | FLOAT | txn_clean | COUNT(BRANCH, 90d) / COUNT(*, 90d) | 🆕 |
| 7 | `chan_digital_adoption_score` | FLOAT | txn_clean | (mobile + online + ussd ratios) × 100, range 0-100 | 🆕 |
| 8 | `chan_channel_entropy` | FLOAT | txn_clean | Normalized Shannon entropy of channel distribution, range 0-1 | 🆕 |

### Digital Adoption Score

Measures how much a customer uses digital channels versus physical channels. Higher scores indicate digitally-savvy customers who are good candidates for app-based campaigns.

```
digital_adoption = (mobile_ratio + online_ratio + ussd_ratio) × 100
```

A customer who ONLY uses mobile → 100. A customer who ONLY visits a branch → 0.

### Channel Entropy

Normalized Shannon entropy measuring how evenly distributed a customer's transactions are across channels. A value near 1.0 means the customer uses all channels equally. A value near 0 means the customer uses only one channel.

This becomes useful for campaign targeting: customers with high channel entropy are channel-agnostic and may respond to any channel. Customers with low entropy have a strong preference and should be contacted through their preferred channel.

### SQL

```sql
UPDATE customer_features cf
SET
    chan_mobile_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE channel = 'MOBILE')::float /
               NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    chan_atm_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE channel = 'ATM')::float /
               NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    chan_branch_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE channel = 'BRANCH')::float /
               NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    chan_digital_adoption_score = ROUND(
        COALESCE(chan_mobile_ratio_90d, 0) * 100
        + COALESCE((
            SELECT COUNT(*) FILTER (WHERE channel IN ('ONLINE', 'INTERNET'))::float /
                   NULLIF(COUNT(*), 0) * 100
            FROM customer_transactions_clean t
            WHERE t.customer_id = cf.customer_id
              AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
              AND t.transaction_date::date <= cf.as_of_date
        ), 0), 0
    ),
    chan_channel_entropy = (
        SELECT ROUND(
            -1.0 * SUM(
                (cnt::float / NULLIF(total, 0)) *
                LN(NULLIF(cnt::float / NULLIF(total, 0), 0))
            ) / NULLIF(LN(GREATEST(ch_count, 1)), 0), 2
        )
        FROM (
            SELECT COUNT(*) AS cnt,
                   SUM(COUNT(*)) OVER () AS total,
                   COUNT(DISTINCT channel) OVER () AS ch_count
            FROM customer_transactions_clean t
            WHERE t.customer_id = cf.customer_id
              AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
              AND t.transaction_date::date <= cf.as_of_date
            GROUP BY channel
        ) channel_stats
    )
WHERE cf.as_of_date = %(d)s::date;
```

---

## 8. Domain 5 — Relationship

**Ownership:** `features/relationship/generator.py`  
**Source Tables:** `customers_clean`, future: accounts, cards, loans tables  
**Nature:** How the customer relates to the bank — products held, account status, cross-sell potential.

### Features (5 total)

| # | Feature | Type | Source | Computation | Status |
|---|---|---|---|---|---|
| 1 | `rel_accounts_active` | INTEGER | accounts table (future) | COUNT WHERE status = Active | 🆕 |
| 2 | `rel_has_loan` | BOOLEAN | loans table (future) | EXISTS active loan product | 🆕 |
| 3 | `rel_has_savings` | BOOLEAN | accounts table (future) | EXISTS savings account | 🆕 |
| 4 | `rel_customer_status` | VARCHAR(16) | customers_clean | Direct copy of status | 🆕 |
| 5 | `rel_products_owned` | INTEGER | multiple (future) | COUNT(DISTINCT product_type) | 🆕 |

### v1 Scope Note

Most Relationship features depend on account, card, and loan data that may not yet be available in clean tables. The generator computes what's available and leaves NULL for unavailable columns. As new source tables are onboarded through the ETL pipeline, features activate automatically — no generator code changes required.

### Immediately Computable

`rel_customer_status` is available today from `customers_clean.status`:

```sql
UPDATE customer_features cf
SET rel_customer_status = cc.status
FROM customers_clean cc
WHERE cf.customer_id = cc.customer_id
  AND cf.as_of_date = %(d)s::date;
```

---

## 9. Domain 6 — Risk

**Ownership:** `features/risk/generator.py`  
**Source Tables:** `customer_transactions_clean`  
**Nature:** Observable risk indicators — descriptive, NOT predictive. These are flags a compliance officer could verify by looking at the raw transaction data.

### Features (6 total)

| # | Feature | Type | Source | Computation | Status |
|---|---|---|---|---|---|
| 1 | `risk_high_value_txn_ratio_90d` | FLOAT | txn_clean | COUNT(amount > 10000) / COUNT(*), 90d | 🆕 |
| 2 | `risk_txn_volatility_90d` | FLOAT | txn_clean | STDDEV(amount) / AVG(amount), 90d | 🆕 |
| 3 | `risk_reversal_ratio_90d` | FLOAT | txn_clean | COUNT(REVERSAL) / COUNT(*), 90d | 🆕 |
| 4 | `risk_cash_heavy_ratio_90d` | FLOAT | txn_clean | (ATM + BRANCH count) / total count, 90d | 🆕 |
| 5 | `risk_unusual_channel_flag` | BOOLEAN | txn_clean | Channel in 30d not used in prior 180d (excluding 30d) | 🆕 |
| 6 | `risk_dormant_indicator` | BOOLEAN | features | days_since_last_txn > 90 AND status != Closed | 🆕 |

### Design Rationale

These are deliberately **observational**, not predictive. A high `risk_high_value_txn_ratio` does not mean the customer is laundering money — it means they have a high proportion of large transactions, which is a fact a compliance officer can verify. The interpretation (suspicious or not) belongs to the downstream risk model or human reviewer.

### SQL

```sql
UPDATE customer_features cf
SET
    risk_high_value_txn_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE amount > 10000)::float / NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    risk_txn_volatility_90d = CASE
        WHEN behav_txn_count_90d > 0 AND fin_avg_txn_amount_90d > 0
        THEN ROUND(COALESCE(fin_txn_amount_stddev_90d, 0) / NULLIF(fin_avg_txn_amount_90d, 0), 2)
        ELSE NULL
    END,
    risk_reversal_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE transaction_type = 'REVERSAL')::float / NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    risk_cash_heavy_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE channel IN ('ATM', 'BRANCH'))::float / NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    risk_unusual_channel_flag = EXISTS (
        SELECT 1 FROM customer_transactions_clean t30
        WHERE t30.customer_id = cf.customer_id
          AND t30.transaction_date::date > (cf.as_of_date - INTERVAL '30 days')
          AND t30.transaction_date::date <= cf.as_of_date
          AND t30.channel NOT IN (
              SELECT DISTINCT channel FROM customer_transactions_clean t180
              WHERE t180.customer_id = cf.customer_id
                AND t180.transaction_date::date > (cf.as_of_date - INTERVAL '180 days')
                AND t180.transaction_date::date <= (cf.as_of_date - INTERVAL '30 days')
          )
    ),
    risk_dormant_indicator = (
        COALESCE(behav_days_since_last_txn, 999) > 90
        AND COALESCE(rel_customer_status, 'Active') != 'Closed'
    )
WHERE cf.as_of_date = %(d)s::date;
```

### Edge Cases

| Scenario | Behaviour |
|---|---|
| New customer (no prior 180d history) | `risk_unusual_channel_flag` = FALSE (every channel is new, none is unusual) |
| `transaction_type` doesn't include REVERSAL | `risk_reversal_ratio_90d` = 0 |
| Customer with no transactions | All ratios = 0, `risk_dormant_indicator` = TRUE |
| Closed account | `risk_dormant_indicator` = FALSE (account closure is expected dormancy) |

---

## 10. Domain 7 — Temporal

**Ownership:** `features/temporal/generator.py`  
**Source Tables:** `customer_transactions_clean`  
**Nature:** Time-based behavioural patterns — when the customer transacts, not just how much.

### Features (6 total)

| # | Feature | Type | Source | Computation | Status |
|---|---|---|---|---|---|
| 1 | `temp_weekend_txn_ratio_90d` | FLOAT | txn_clean | COUNT(DOW 0,6) / COUNT(*), 90d | 🆕 |
| 2 | `temp_weekday_txn_ratio_90d` | FLOAT | txn_clean | COUNT(DOW 1-5) / COUNT(*), 90d | 🆕 |
| 3 | `temp_morning_activity_ratio_90d` | FLOAT | txn_clean | COUNT(HOUR 6-11) / COUNT(*), 90d | 🆕 |
| 4 | `temp_afternoon_activity_ratio_90d` | FLOAT | txn_clean | COUNT(HOUR 12-17) / COUNT(*), 90d | 🆕 |
| 5 | `temp_evening_activity_ratio_90d` | FLOAT | txn_clean | COUNT(HOUR 18-23) / COUNT(*), 90d | 🆕 |
| 6 | `temp_payday_activity_ratio_90d` | FLOAT | txn_clean | COUNT(DAY 25-31 or 1-5) / COUNT(*), 90d | 🆕 |

### Why Temporal Features Matter

Temporal patterns are surprisingly strong predictors of lifecycle changes. A customer who suddenly starts transacting on weekends after months of weekday-only activity may have changed jobs. A customer whose payday activity disappears may have lost their primary income source. These signals are invisible to aggregate count/amount features.

### Payday Pattern

Payday is defined as transactions occurring between the 25th and 5th of the month — the typical salary payment window in Zambia. A high payday ratio indicates a customer whose financial life revolves around a monthly salary cycle. A low ratio suggests irregular income.

### SQL

```sql
UPDATE customer_features cf
SET
    temp_weekend_txn_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE EXTRACT(DOW FROM transaction_date) IN (0, 6))::float
               / NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    temp_weekday_txn_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE EXTRACT(DOW FROM transaction_date) BETWEEN 1 AND 5)::float
               / NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    temp_morning_activity_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE EXTRACT(HOUR FROM transaction_date) BETWEEN 6 AND 11)::float
               / NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    temp_afternoon_activity_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE EXTRACT(HOUR FROM transaction_date) BETWEEN 12 AND 17)::float
               / NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    temp_evening_activity_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (WHERE EXTRACT(HOUR FROM transaction_date) BETWEEN 18 AND 23)::float
               / NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2),
    temp_payday_activity_ratio_90d = ROUND(COALESCE((
        SELECT COUNT(*) FILTER (
            WHERE EXTRACT(DAY FROM transaction_date) BETWEEN 25 AND 31
               OR EXTRACT(DAY FROM transaction_date) BETWEEN 1 AND 5
        )::float / NULLIF(COUNT(*), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = cf.customer_id
          AND t.transaction_date::date > (cf.as_of_date - INTERVAL '90 days')
          AND t.transaction_date::date <= cf.as_of_date
    ), 0), 2)
WHERE cf.as_of_date = %(d)s::date;
```

### Limitation

Time-of-day features (`morning`, `afternoon`, `evening`) depend on `transaction_date` containing a time component (TIMESTAMP, not DATE). If the column is DATE-only, `EXTRACT(HOUR FROM ...)` returns 0 for all rows, making morning_ratio = 1.0 and all others = 0.0. This is a known limitation of the v1 data source. These features will activate automatically when timestamp-precision transaction data is available.

---

## 11. Feature Metadata Catalog

### Complete Feature List (60 features across 7 domains)

#### Profile Domain (8)

| Feature | Type | Source | Downstream | Status |
|---|---|---|---|---|
| `prof_customer_type` | VARCHAR(32) | customers_clean | State, Churn, CLV, NBA | ✅ |
| `prof_tenure_days` | INTEGER | customers_clean | State, Churn, CLV | ✅ |
| `prof_age_years` | INTEGER | customers_clean | Churn, CLV | ✅ |
| `prof_onboarding_channel` | VARCHAR(32) | customers_clean | NBA, Segmentation | ✅ |
| `prof_age_band` | VARCHAR(16) | customers_clean | Segmentation, NBA | 🆕 |
| `prof_kyc_tier` | VARCHAR(16) | customers_clean | Risk | 🆕 |
| `prof_primary_branch` | VARCHAR(16) | customers_clean | State, Segmentation | 🆕 |
| `prof_nationality` | VARCHAR(64) | customers_clean | Segmentation | 🆕 |

#### Behaviour Domain (15)

| Feature | Type | Source | Downstream | Status |
|---|---|---|---|---|
| `behav_days_since_last_txn` | INTEGER | txn_clean | State, Churn, CLV, NBA | ✅ |
| `behav_days_since_first_txn` | INTEGER | txn_clean | CLV | ✅ |
| `behav_txn_count_7d` | INTEGER | txn_clean | State, Churn | 🆕 |
| `behav_txn_count_30d` | INTEGER | txn_clean | State, Churn, NBA | ✅ |
| `behav_txn_count_90d` | INTEGER | txn_clean | State, Churn, CLV | ✅ |
| `behav_txn_count_180d` | INTEGER | txn_clean | CLV, Segmentation | ✅ |
| `behav_txn_count_365d` | INTEGER | txn_clean | CLV | ✅ |
| `behav_avg_days_between_txn` | FLOAT | txn_clean | State, Churn | ✅ |
| `behav_txn_frequency_trend` | FLOAT | features | State, Churn | ✅ |
| `behav_active_days_90d` | INTEGER | txn_clean | State, Churn | 🆕 |
| `behav_inactive_days_90d` | INTEGER | features | State, Churn | 🆕 |
| `behav_engagement_score` | FLOAT | features | State, NBA | ✅ |
| `behav_recency_score` | FLOAT | features | State | 🆕 |
| `behav_frequency_score` | FLOAT | features | State | 🆕 |
| `behav_diversity_score` | FLOAT | features | State | 🆕 |
| `behav_activity_consistency` | FLOAT | features | State, Segmentation | 🆕 |

#### Financial Domain (12)

| Feature | Type | Source | Downstream | Status |
|---|---|---|---|---|
| `fin_total_credit_30d` | FLOAT | txn_clean | CLV, NBA | ✅ |
| `fin_total_debit_30d` | FLOAT | txn_clean | Churn | ✅ |
| `fin_total_credit_90d` | FLOAT | txn_clean | CLV, NBA | 🆕 |
| `fin_total_debit_90d` | FLOAT | txn_clean | Churn | 🆕 |
| `fin_avg_txn_amount_90d` | FLOAT | txn_clean | CLV, Segmentation | ✅ |
| `fin_median_txn_amount_90d` | FLOAT | txn_clean | Segmentation | 🆕 |
| `fin_txn_amount_stddev_90d` | FLOAT | txn_clean | Risk, Churn | ✅ |
| `fin_salary_estimate` | FLOAT | txn_clean | CLV, NBA | ✅ |
| `fin_salary_consistency` | FLOAT | txn_clean | CLV, Risk | 🆕 |
| `fin_income_growth` | FLOAT | features | CLV, State | 🆕 |
| `fin_cashflow_ratio` | FLOAT | txn_clean | Churn, Risk | ✅ |
| `fin_has_salary_credit` | BOOLEAN | txn_clean | CLV, NBA | ✅ |

#### Channel Domain (8)

| Feature | Type | Source | Downstream | Status |
|---|---|---|---|---|
| `chan_distinct_channels_90d` | INTEGER | txn_clean | State, Segmentation | ✅ |
| `chan_dominant_channel` | VARCHAR(32) | txn_clean | NBA, Segmentation | ✅ |
| `chan_distinct_txn_types_90d` | INTEGER | txn_clean | Segmentation | ✅ |
| `chan_mobile_ratio_90d` | FLOAT | txn_clean | NBA, Segmentation | 🆕 |
| `chan_atm_ratio_90d` | FLOAT | txn_clean | Risk | 🆕 |
| `chan_branch_ratio_90d` | FLOAT | txn_clean | Risk | 🆕 |
| `chan_digital_adoption_score` | FLOAT | txn_clean | NBA, Segmentation | 🆕 |
| `chan_channel_entropy` | FLOAT | txn_clean | Segmentation | 🆕 |

#### Relationship Domain (5)

| Feature | Type | Source | Downstream | Status |
|---|---|---|---|---|
| `rel_accounts_active` | INTEGER | accounts (future) | Segmentation, NBA | 🆕 |
| `rel_has_loan` | BOOLEAN | loans (future) | NBA, Risk | 🆕 |
| `rel_has_savings` | BOOLEAN | accounts (future) | NBA | 🆕 |
| `rel_customer_status` | VARCHAR(16) | customers_clean | State, Churn | 🆕 |
| `rel_products_owned` | INTEGER | multiple (future) | Segmentation, NBA | 🆕 |

#### Risk Domain (6)

| Feature | Type | Source | Downstream | Status |
|---|---|---|---|---|
| `risk_high_value_txn_ratio_90d` | FLOAT | txn_clean | Risk, Segmentation | 🆕 |
| `risk_txn_volatility_90d` | FLOAT | txn_clean | Risk, Churn | 🆕 |
| `risk_reversal_ratio_90d` | FLOAT | txn_clean | Risk | 🆕 |
| `risk_cash_heavy_ratio_90d` | FLOAT | txn_clean | Risk | 🆕 |
| `risk_unusual_channel_flag` | BOOLEAN | txn_clean | Risk | 🆕 |
| `risk_dormant_indicator` | BOOLEAN | features | State, Churn | 🆕 |

#### Temporal Domain (6)

| Feature | Type | Source | Downstream | Status |
|---|---|---|---|---|
| `temp_weekend_txn_ratio_90d` | FLOAT | txn_clean | State, Segmentation | 🆕 |
| `temp_weekday_txn_ratio_90d` | FLOAT | txn_clean | State, Segmentation | 🆕 |
| `temp_morning_activity_ratio_90d` | FLOAT | txn_clean | Segmentation | 🆕 |
| `temp_afternoon_activity_ratio_90d` | FLOAT | txn_clean | Segmentation | 🆕 |
| `temp_evening_activity_ratio_90d` | FLOAT | txn_clean | Segmentation | 🆕 |
| `temp_payday_activity_ratio_90d` | FLOAT | txn_clean | State, Churn, CLV | 🆕 |

---

## 12. Computation Pipeline

### Execution DAG

```
Stage 0: Phase 1 SQL (existing — FEATURE_SQL + PHASE2_SQL)
  Reads: customer_transactions_clean
  Writes: 21 base features (transaction aggregates, credit/debit splits)
  Time: 2-5 seconds
  Dependency: none (runs first)

Stage 1: Profile Generator
  Reads: customers_clean
  Writes: 8 profile features
  Time: <1 second
  Depends on: Stage 0 (needs customer_features rows to UPDATE)

Stage 2: Behaviour Generator
  Reads: customer_transactions_clean, customer_features (Phase 1 output)
  Writes: 15 behaviour features
  Time: 5-10 seconds
  Depends on: Stage 0, Stage 1

Stage 3: Financial Generator
  Reads: customer_transactions_clean, customer_features (Phase 1 output)
  Writes: 12 financial features
  Time: 3-5 seconds
  Depends on: Stage 0

Stage 4: Channel Generator
  Reads: customer_transactions_clean
  Writes: 8 channel features
  Time: 2-3 seconds
  Depends on: Stage 0

Stage 5: Relationship Generator
  Reads: customers_clean
  Writes: 5 relationship features
  Time: <1 second
  Depends on: Stage 0, Stage 1

Stage 6: Risk Generator
  Reads: customer_transactions_clean, customer_features (Stage 2 + Stage 5)
  Writes: 6 risk features
  Time: 3-5 seconds
  Depends on: Stage 0, Stage 2, Stage 5

Stage 7: Temporal Generator
  Reads: customer_transactions_clean
  Writes: 6 temporal features
  Time: 3-5 seconds
  Depends on: Stage 0
```

**Total pipeline time:** ~4 seconds for 5,000 customers with ~209,000 transactions (measured).

### Parallelism Opportunity

Stages 2, 3, 4, 6, and 7 have no interdependencies after Stage 0 completes. They can run in parallel, reducing total pipeline time to ~2-3 seconds. The current implementation runs sequentially for simplicity and debugging clarity. Parallel execution is a future optimization tracked in the backlog.

### Pipeline Class

```python
class FeaturePipeline:
    """Orchestrates all 7 domain generators in dependency order."""

    def __init__(self, conn: psycopg2.extensions.connection):
        self._repo = FeatureRepository(conn)
        self._stages = {
            "profile":      CustomerProfileGenerator(conn),
            "behaviour":    BehaviourGenerator(conn),
            "financial":    FinancialGenerator(conn),
            "channel":      ChannelGenerator(conn),
            "relationship": RelationshipGenerator(conn),
            "risk":         RiskGenerator(conn),
            "temporal":     TemporalGenerator(conn),
        }

    def run(self, as_of_date: date | None = None) -> dict:
        """Execute all stages. Returns timing + row counts per stage."""
        effective_date = as_of_date or date.today()
        t0 = time.time()
        results = {}

        # Stage 0: Phase 1 transaction aggregates (existing)
        results["phase1"] = self._repo.compute_batch(effective_date)

        # Stages 1-7: Domain generators
        for name, gen in self._stages.items():
            t_start = time.time()
            row_counts = gen.generate(effective_date)
            results[name] = {
                **row_counts,
                "duration_seconds": round(time.time() - t_start, 2),
            }

        return {
            "as_of_date": effective_date.isoformat(),
            "status": "COMPLETED",
            "total_duration_seconds": round(time.time() - t0, 2),
            "stages": results,
        }
```

### Failure Strategy

Each stage commits independently via psycopg2. If Stage 5 fails:
- Stages 0-4 results are committed and valid
- Stages 5-7 are not executed
- Re-running the pipeline skips Stages 0-4 (idempotent) and completes Stages 5-7

All generators are idempotent by design — running the same stage twice on the same `as_of_date` produces identical results.

---

## 13. Data Contracts

### Input Contract

The Feature Store requires these tables to exist in `etl_clean`:

| Table | Required For | Critical Columns |
|---|---|---|
| `customers_clean` | Profile, Relationship | customer_id, activation_date, customer_type, date_of_birth, onboarding_channel, branch_code, status |
| `customer_transactions_clean` | Behaviour, Financial, Channel, Risk, Temporal | customer_id, transaction_date, transaction_type, channel, amount |
| `accounts_clean` (future) | Relationship | customer_id, account_type, status |
| `loans_clean` (future) | Relationship | customer_id, loan_type, status |

If a table is not available, its dependent features remain NULL. The pipeline does not fail — it computes what it can and skips what it cannot.

### Output Contract

The Feature Store produces one row per `(customer_id, as_of_date)` in `customer_features`. All 60 columns are present after migration. Columns without data (source table not integrated, or computation not possible) are NULL.

**Schema guarantees:**
- Columns are added, never removed or renamed
- Legacy names are aliased (e.g., `txn_count_30d` → `behav_txn_count_30d`)
- New columns default to NULL for existing rows
- The `(customer_id, as_of_date)` unique constraint is enforced

**Data guarantees:**
- Point-in-time correctness: all features use only data at or before `as_of_date`
- Idempotency: running the pipeline twice produces identical rows
- NULL = "not computable" (missing source data)
- 0 = "computable, and the answer is zero"

### Consumer Contract (for AI Services)

Every downstream service:

1. **Reads** features via `GET /features/{customer_id}/latest` or `GET /features/{customer_id}?as_of_date=YYYY-MM-DD`
2. **Never writes** to `customer_features`
3. **Stores outputs** (states, predictions, recommendations) in their own tables/schemas
4. **References** `as_of_date` when logging predictions for audit trail

A downstream service that violates this contract (writes to customer_features) will break idempotency and point-in-time correctness for all other consumers. This is prevented by database permissions — the service account used by AI services has SELECT-only on `customer_features`.

---

## 14. Implementation Plan — ✅ Complete

All 6 steps completed. The full 7-domain pipeline runs in ~4 seconds.

| Step | Description | Status |
|---|---|---|
| 1 | Database migration (44 columns across 7 domains) | ✅ |
| 2 | Generator implementation (7 generators, FROM-subquery pattern) | ✅ |
| 3 | Pipeline orchestrator (`pipeline.py` — 7 stages) | ✅ |
| 4 | Backward compatibility (legacy columns + Pydantic schema) | ✅ |
| 5 | Testing (20 generator tests + integration) | ✅ |
| 6 | Verification (end-to-end pipeline run confirmed) | ✅ |

---

## 15. SQL Reference

### Complete Migration Script

Already executed. See `scripts/migrate_features_phase2.py` and `scripts/add_phase2_columns.py`.

### Domain Generator SQL

See individual domain sections:
- [Section 4](#4-domain-1--customer-profile) — Profile SQL
- [Section 5](#5-domain-2--behaviour) — Behaviour SQL
- [Section 6](#6-domain-3--financial) — Financial SQL
- [Section 7](#7-domain-4--channel) — Channel SQL
- [Section 8](#8-domain-5--relationship) — Relationship SQL
- [Section 9](#9-domain-6--risk) — Risk SQL
- [Section 10](#10-domain-7--temporal) — Temporal SQL

### Existing Phase 1 SQL

Not modified. See `services/feature-engineering-service/app/repository/repository.py`:
- `FEATURE_SQL` — 14 transaction aggregate features
- `PHASE2_SQL` — 7 derived features (365d counts, credit/debit splits)
