# Feature Catalog — customer_features

> **Service:** feature-engineering-service
> **Config:** `app/config/settings.py` (`FeatureConfig`, env-prefixed `FE_`)
> **Updated:** 2026-08-19

The feature set is computed point-in-time from `customer_transactions_clean`.
All queries enforce `transaction_date <= as_of_date` (no data leakage).

---

## Feature Groups & Toggles

| Group | SQL | Env toggle | Default | Description |
|-------|-----|-----------|---------|-------------|
| Phase 1 (raw aggregates) | `FEATURE_SQL` | always on | — | Core recency/frequency/monetary features |
| Phase 2 (derived) | `PHASE2_SQL` | `FE_ENABLE_PHASE2_DERIVED` | `true` | Credit/debit split, trend, salary, income |
| Phase 2b (ratio) | `PHASE2B_SQL` | `FE_ENABLE_PHASE2B_RATIO` | `true` | Credit-to-debit ratio (needs Phase 2) |

Example: disable derived features without a code change
```powershell
$env:FE_ENABLE_PHASE2_DERIVED = "false"
$env:FE_ENABLE_PHASE2B_RATIO   = "false"
```

---

## The 21 Features

### Phase 1 — Raw aggregates (15)

| # | Column | Category | Notes |
|---|--------|----------|-------|
| 1 | `days_since_last_txn` | Recency | days since most recent txn |
| 2 | `days_since_first_txn` | Tenure | days since first txn |
| 3 | `txn_count_30d` | Frequency | txns in last 30d |
| 4 | `txn_count_90d` | Frequency | txns in last 90d |
| 5 | `txn_count_180d` | Frequency | txns in last 180d |
| 6 | `avg_days_between_txn` | Frequency | avg gap between txns |
| 7 | `total_amount_90d` | Monetary | sum in last 90d |
| 8 | `avg_amount_90d` | Monetary | mean in last 90d |
| 9 | `total_amount_180d` | Monetary | sum in last 180d |
| 10 | `amount_growth_ratio` | Growth | 90d vs 180d growth |
| 11 | `distinct_channels_90d` | Diversity | unique channels in 90d |
| 12 | `distinct_txn_types_90d` | Diversity | unique txn types in 90d |
| 13 | `dominant_channel` | Channel | most frequent channel in 90d |
| 14 | `amount_stddev_90d` | Volatility | stddev of amount in 90d |
| 15 | `customer_tenure_days` | Tenure | (derived at read time) |

### Phase 2 — Derived (5)

| # | Column | Description |
|---|--------|-------------|
| 16 | `txn_count_365d` | txns in last 365d |
| 17 | `credit_sum_30d` | total credit in 90d window |
| 18 | `debit_sum_30d` | total debit in 90d window |
| 19 | `balance_trend_90d` | RISING / STABLE |
| 20 | `has_salary_credit` | 3+ monthly credit deposits |

### Phase 2b — Ratio (1)

| # | Column | Description |
|---|--------|-------------|
| 21 | `credit_to_debit_ratio_90d` | credit / debit ratio |

---

## Configurable Thresholds (already env-driven)

| Env var | Default | Used for |
|---------|---------|----------|
| `FE_ENGAGEMENT_RECENCY_WEIGHT` | 40.0 | Engagement score |
| `FE_ENGAGEMENT_FREQUENCY_WEIGHT` | 35.0 | Engagement score |
| `FE_ENGAGEMENT_DIVERSITY_WEIGHT` | 25.0 | Engagement score |
| `FE_RISK_DORMANT_DAYS` | 90 | Dormant risk flag |
| `FE_RISK_HIGH_VALUE_THRESHOLD` | 10000.0 | High-value customer flag |
| `FE_FINANCIAL_SALARY_MIN_AMOUNT` | 500.0 | Salary detection |
| `FE_CHANNEL_MOBILE` / `_ATM` / `_BRANCH` / `_ONLINE` / `_INTERNET` | see code | Channel taxonomy mapping |

> **Note:** Fully per-feature toggling (e.g. disable just `amount_stddev_90d`)
> would require refactoring `FEATURE_SQL` into composable blocks. The current
> design exposes toggles at the **group** level (Phase 1 / 2 / 2b). If you need
> per-feature flags, that is the next increment.
