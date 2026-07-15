# Feature Engineering Design — Version 1.0

**Customer Lifecycle Prediction System**
**Date:** 2026-07-15
**Author:** Enterprise Data Architecture Team
**Based on:** BRS v1.0 (Proof of Concept) + Database Design Spec v2.0

---

## 1. Overview

### Purpose

This document defines every feature required by the Customer Lifecycle Prediction System. Each feature is specified with its **formula**, **source data**, **refresh frequency**, **data type**, and **missing value strategy** so that developers can implement the feature engineering pipelines without ambiguity.

### Relationship to BRS v1.0

The BRS v1.0 (Proof of Concept) defines customer lifecycle classification based on **days since last qualifying financial activity**. This document specifies:

- The core features that directly implement that classification
- Supporting features that enrich the classification for Relationship Managers
- Forward-looking features that will power ML models (Markov Chains, XGBoost, LightGBM) in later phases

### Feature Store Architecture

Features are organized into **8 groups** following the v2 Database Design Specification:

```
feature_group (logical grouping by domain)
  └── feature_definition (one feature per row)
       └── feature_value (current value per customer)
       └── feature_value_history (time-series)
       └── feature_lineage (provenance)
```

### Qualifying Financial Activity

Per the BRS, a "qualifying financial activity" is defined as any customer-initiated transaction. The following transaction types qualify:

| Transaction Type | Qualifies? | Rationale |
|-----------------|------------|-----------|
| CREDIT (customer deposit) | Yes | Customer-initiated deposit |
| DEBIT (purchase/payment) | Yes | Customer actively using account |
| TRANSFER (outgoing) | Yes | Customer moving money |
| FEE (bank charge) | No | Bank-initiated, not customer activity |
| INTEREST (interest credit) | No | Automated, not customer-initiated |
| REVERSAL | No | Correction, not new activity |

---

## 2. Feature Group: `customer_profile`

**Domain:** Customer demographics and profile attributes
**Owning Service:** `feature-engineering-service`
**Source Schema:** `customer_master`
**Default Refresh:** Daily

---

### F-CP-001: `age`

| Attribute | Value |
|-----------|-------|
| **Description** | Customer age in years, derived from date of birth |
| **Formula** | `FLOOR(DATE_PART('year', AGE(CURRENT_DATE, date_of_birth)))` |
| **Source** | `customer_master.customer.date_of_birth` |
| **Refresh Frequency** | Daily (changes only on birthday — recompute is cheap) |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Impute with median** of the customer's segment. If segment is also missing, impute with global median (typically 35–42 for retail banking). Mark as `age_imputed = TRUE` in feature metadata. |
| **POC Priority** | Medium — supports segmentation analysis |
| **Valid Range** | 18–120 |

---

### F-CP-002: `tenure_months`

| Attribute | Value |
|-----------|-------|
| **Description** | Number of months since the customer's first account was opened |
| **Formula** | `ROUND(DATE_PART('day', AGE(CURRENT_DATE, MIN(opened_date))) / 30.44)` across all customer accounts |
| **Source** | `accounts.account(opened_date)` WHERE `account.customer_id = ?` AND `account_status != 'CLOSED'` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0** if no open date is found (new customer with no account history). Mark as `tenure_estimated = TRUE`. |
| **POC Priority** | High — tenure correlates strongly with churn risk |

---

### F-CP-003: `customer_segment_current`

| Attribute | Value |
|-----------|-------|
| **Description** | Current customer segment classification |
| **Formula** | `SELECT segment_code FROM customer_master.customer_segment WHERE customer_id = ? AND effective_to IS NULL ORDER BY effective_from DESC LIMIT 1` |
| **Source** | `customer_master.customer_segment` |
| **Refresh Frequency** | Daily |
| **Data Type** | CATEGORICAL: `MASS_MARKET`, `MASS_AFFLUENT`, `AFFLUENT`, `HIGH_NET_WORTH`, `PRIVATE_BANKING`, `SME`, `CORPORATE` |
| **Missing Value Strategy** | **Default to `MASS_MARKET`** — the most common segment in retail banking. This is conservative and avoids over-prioritizing unknown customers. |
| **POC Priority** | High — used for prioritization and RM assignment |

---

### F-CP-004: `risk_category`

| Attribute | Value |
|-----------|-------|
| **Description** | Customer risk classification |
| **Formula** | `SELECT risk_category FROM customer_master.customer_risk_profile WHERE customer_id = ?` |
| **Source** | `customer_master.customer_risk_profile` |
| **Refresh Frequency** | Daily |
| **Data Type** | CATEGORICAL: `LOW`, `MEDIUM`, `HIGH`, `PEP` |
| **Missing Value Strategy** | **Default to `MEDIUM`** — the middle risk tier. This is conservative for compliance; unknown risk should not be treated as low risk. |
| **POC Priority** | Medium — supports compliance-aware recommendations |

---

### F-CP-005: `customer_type`

| Attribute | Value |
|-----------|-------|
| **Description** | Customer type classification |
| **Formula** | `SELECT customer_type FROM customer_master.customer WHERE id = ?` |
| **Source** | `customer_master.customer` |
| **Refresh Frequency** | Daily |
| **Data Type** | CATEGORICAL: `INDIVIDUAL`, `JOINT`, `SME`, `CORPORATE` |
| **Missing Value Strategy** | **Default to `INDIVIDUAL`**. |
| **POC Priority** | Low — used for filtering (PoC may focus on INDIVIDUAL only) |

---

## 3. Feature Group: `transaction_behaviour`

**Domain:** Transaction patterns and financial activity
**Owning Service:** `feature-engineering-service`
**Source Schema:** `clean`, `transactions`
**Default Refresh:** Daily

---

### F-TB-001: `days_since_last_activity` ⭐ PRIMARY

| Attribute | Value |
|-----------|-------|
| **Description** | Number of days since the customer's last qualifying financial activity. This is the **primary feature for BRS v1.0 lifecycle classification**. |
| **Formula** | `DATE_PART('day', AGE(CURRENT_DATE, MAX(transaction_date))) FROM clean.clean_transaction WHERE customer_id = ? AND transaction_type IN ('CREDIT', 'DEBIT', 'TRANSFER')` |
| **Source** | `clean.clean_transaction(transaction_date, transaction_type, customer_id)` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 9999** — a sentinel value meaning "no transaction history." These customers are classified as DORMANT (≥365 days). If a customer has accounts but zero transactions, treat as DORMANT. |
| **POC Priority** | **CRITICAL** — This feature directly drives the BRS lifecycle classification |
| **Configurable Thresholds** | The thresholds that map this feature to states are stored in `configuration.customer_state_definition`, NOT hard-coded. Defaults: ACTIVE (<60), EARLY_WARNING (60–89), INACTIVE (90–179), PRE_DORMANT (180–364), DORMANT (≥365). |

---

### F-TB-002: `txn_count_30d`

| Attribute | Value |
|-----------|-------|
| **Description** | Total number of qualifying transactions in the last 30 days |
| **Formula** | `COUNT(*) FROM clean.clean_transaction WHERE customer_id = ? AND transaction_type IN ('CREDIT','DEBIT','TRANSFER') AND transaction_date >= CURRENT_DATE - INTERVAL '30 days'` |
| **Source** | `clean.clean_transaction` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** No transactions in the window means zero activity. |
| **POC Priority** | High — provides granularity beyond the binary "active/inactive" |

---

### F-TB-003: `txn_count_90d`

| Attribute | Value |
|-----------|-------|
| **Description** | Total qualifying transactions in the last 90 days |
| **Formula** | Same as F-TB-002 with 90-day window |
| **Source** | `clean.clean_transaction` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** |
| **POC Priority** | Medium — trend analysis |

---

### F-TB-004: `txn_count_180d`

| Attribute | Value |
|-----------|-------|
| **Description** | Total qualifying transactions in the last 180 days |
| **Formula** | Same as F-TB-002 with 180-day window |
| **Source** | `clean.clean_transaction` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** |
| **POC Priority** | Medium — trend analysis |

---

### F-TB-005: `txn_count_365d`

| Attribute | Value |
|-----------|-------|
| **Description** | Total qualifying transactions in the last 365 days |
| **Formula** | Same as F-TB-002 with 365-day window |
| **Source** | `clean.clean_transaction` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** |
| **POC Priority** | Medium |

---

### F-TB-006: `avg_txn_amount_30d`

| Attribute | Value |
|-----------|-------|
| **Description** | Average transaction amount over the last 30 days |
| **Formula** | `AVG(amount) FROM clean.clean_transaction WHERE customer_id = ? AND transaction_date >= CURRENT_DATE - INTERVAL '30 days'` |
| **Source** | `clean.clean_transaction(amount)` |
| **Refresh Frequency** | Daily |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to 0.0.** If there are no transactions, average is zero. |
| **POC Priority** | Medium — indicates transaction value trends |

---

### F-TB-007: `avg_txn_amount_90d`

| Attribute | Value |
|-----------|-------|
| **Description** | Average transaction amount over the last 90 days |
| **Formula** | Same as F-TB-006 with 90-day window |
| **Source** | `clean.clean_transaction(amount)` |
| **Refresh Frequency** | Daily |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to 0.0.** |
| **POC Priority** | Medium |

---

### F-TB-008: `txn_volatility_90d`

| Attribute | Value |
|-----------|-------|
| **Description** | Standard deviation of transaction amounts over 90 days — indicates spending consistency |
| **Formula** | `STDDEV(amount) FROM clean.clean_transaction WHERE customer_id = ? AND transaction_date >= CURRENT_DATE - INTERVAL '90 days'` |
| **Source** | `clean.clean_transaction(amount)` |
| **Refresh Frequency** | Daily |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to 0.0** if fewer than 3 transactions (insufficient data for meaningful stddev). |
| **POC Priority** | Low — ML feature for later phases |

---

### F-TB-009: `credit_sum_30d`

| Attribute | Value |
|-----------|-------|
| **Description** | Total credits (deposits) in the last 30 days |
| **Formula** | `SUM(amount) FROM clean.clean_transaction WHERE customer_id = ? AND transaction_type = 'CREDIT' AND transaction_date >= CURRENT_DATE - INTERVAL '30 days'` |
| **Source** | `clean.clean_transaction` |
| **Refresh Frequency** | Daily |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to 0.0.** |
| **POC Priority** | High — indicates income/deposit activity |

---

### F-TB-010: `debit_sum_30d`

| Attribute | Value |
|-----------|-------|
| **Description** | Total debits (spending) in the last 30 days |
| **Formula** | `SUM(amount) FROM clean.clean_transaction WHERE customer_id = ? AND transaction_type = 'DEBIT' AND transaction_date >= CURRENT_DATE - INTERVAL '30 days'` |
| **Source** | `clean.clean_transaction` |
| **Refresh Frequency** | Daily |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to 0.0.** |
| **POC Priority** | High — indicates spending activity |

---

### F-TB-011: `credit_to_debit_ratio_90d`

| Attribute | Value |
|-----------|-------|
| **Description** | Ratio of total credits to total debits over 90 days. >1 means net saving, <1 means net spending. |
| **Formula** | `SUM(CASE WHEN type='CREDIT' THEN amount ELSE 0 END) / NULLIF(SUM(CASE WHEN type='DEBIT' THEN amount ELSE 0 END), 0)` |
| **Source** | `clean.clean_transaction` |
| **Refresh Frequency** | Daily |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to 1.0** if no debits (neutral ratio). Default to 9999 sentinel if no transactions at all. |
| **POC Priority** | Medium — financial health indicator |

---

### F-TB-012: `monthly_income_estimate`

| Attribute | Value |
|-----------|-------|
| **Description** | Estimated monthly income based on recurring credits |
| **Formula** | Identify recurring credit transactions (same approximate amount, same description, monthly pattern). `AVG(monthly_credit_sum)` over 3–6 months. |
| **Source** | `clean.clean_transaction` — credits with `transaction_type = 'CREDIT'` AND recurring pattern detection |
| **Refresh Frequency** | Weekly |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to NULL.** If no recurring pattern is detected, income cannot be estimated. Do not impute — NULL means "unknown." |
| **POC Priority** | Medium — used for CLV estimation in later phases |

---

### F-TB-013: `balance_trend_90d`

| Attribute | Value |
|-----------|-------|
| **Description** | Trend direction of account balance over 90 days (increasing, stable, decreasing) |
| **Formula** | Linear regression slope of `closing_balance` over 90 days from `account_balance_snapshot`. Categorize: `INCREASING` (slope > threshold), `STABLE` (\|slope\| ≤ threshold), `DECREASING` (slope < -threshold). |
| **Source** | `accounts.account_balance_snapshot(closing_balance, snapshot_date)` |
| **Refresh Frequency** | Daily |
| **Data Type** | CATEGORICAL: `INCREASING`, `STABLE`, `DECREASING` |
| **Missing Value Strategy** | **Default to `STABLE`** if fewer than 30 days of balance snapshots. |
| **POC Priority** | High — a decreasing balance trend is a strong churn precursor |

---

### F-TB-014: `has_salary_credit`

| Attribute | Value |
|-----------|-------|
| **Description** | Whether the customer receives a salary credit (binary indicator) |
| **Formula** | `EXISTS (SELECT 1 FROM clean.clean_transaction WHERE customer_id = ? AND transaction_type = 'CREDIT' AND category = 'SALARY' AND transaction_date >= CURRENT_DATE - INTERVAL '45 days')` |
| **Source** | `clean.clean_transaction` with `category` or `description` matching salary patterns |
| **Refresh Frequency** | Daily |
| **Data Type** | BOOLEAN |
| **Missing Value Strategy** | **Default to FALSE.** Salary credits are assumed absent until detected. |
| **POC Priority** | High — salaried customers have different churn patterns |

---

## 4. Feature Group: `loan_behaviour`

**Domain:** Loan repayment and delinquency behavior
**Owning Service:** `feature-engineering-service`
**Source Schema:** `loans`
**Default Refresh:** Daily

---

### F-LB-001: `active_loan_count`

| Attribute | Value |
|-----------|-------|
| **Description** | Number of currently active loans |
| **Formula** | `COUNT(*) FROM loans.loan WHERE customer_id = ? AND loan_status = 'ACTIVE'` |
| **Source** | `loans.loan` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** No loan records means no active loans. |
| **POC Priority** | High — loan holders have different engagement patterns |

---

### F-LB-002: `max_delinquency_days`

| Attribute | Value |
|-----------|-------|
| **Description** | Maximum delinquency days across all active loans |
| **Formula** | `MAX(delinquency_days) FROM loans.loan WHERE customer_id = ? AND loan_status = 'ACTIVE'` |
| **Source** | `loans.loan(delinquency_days)` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** No loans = no delinquency. |
| **POC Priority** | High — delinquency is a strong churn indicator |

---

### F-LB-003: `total_outstanding_loan_balance`

| Attribute | Value |
|-----------|-------|
| **Description** | Sum of outstanding balances across all active loans |
| **Formula** | `SUM(outstanding_balance) FROM loans.loan WHERE customer_id = ? AND loan_status = 'ACTIVE'` |
| **Source** | `loans.loan` |
| **Refresh Frequency** | Daily |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to 0.0.** |
| **POC Priority** | Medium |

---

### F-LB-004: `loan_repayment_ratio`

| Attribute | Value |
|-----------|-------|
| **Description** | Ratio of total amount paid to total amount due across all loans over 90 days |
| **Formula** | `SUM(lr.amount_paid) / NULLIF(SUM(lr.amount_due), 0) FROM loans.loan_repayment lr JOIN loans.loan l ON lr.loan_id = l.id WHERE l.customer_id = ? AND lr.due_date >= CURRENT_DATE - INTERVAL '90 days'` |
| **Source** | `loans.loan_repayment(amount_paid, amount_due)`, `loans.loan` |
| **Refresh Frequency** | Daily |
| **Data Type** | FLOAT (0.0–1.0+) |
| **Missing Value Strategy** | **Default to 1.0** if no repayments due. Default to 0.0 if due but none paid. |
| **POC Priority** | Medium |

---

### F-LB-005: `has_defaulted_loan`

| Attribute | Value |
|-----------|-------|
| **Description** | Whether the customer has ever defaulted on a loan (binary) |
| **Formula** | `EXISTS (SELECT 1 FROM loans.loan WHERE customer_id = ? AND loan_status IN ('DEFAULTED','WRITTEN_OFF'))` |
| **Source** | `loans.loan(loan_status)` |
| **Refresh Frequency** | Daily |
| **Data Type** | BOOLEAN |
| **Missing Value Strategy** | **Default to FALSE.** No records = no defaults. |
| **POC Priority** | High — default history is a strong predictor |

---

## 5. Feature Group: `card_usage`

**Domain:** Credit and debit card activity
**Owning Service:** `feature-engineering-service`
**Source Schema:** `cards`
**Default Refresh:** Daily

---

### F-CU-001: `active_card_count`

| Attribute | Value |
|-----------|-------|
| **Description** | Number of active cards (debit + credit) |
| **Formula** | `COUNT(*) FROM cards.card WHERE customer_id = ? AND card_status = 'ACTIVE'` |
| **Source** | `cards.card` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** |
| **POC Priority** | Medium |

---

### F-CU-002: `card_utilization_pct`

| Attribute | Value |
|-----------|-------|
| **Description** | Credit card utilization percentage (current balance / credit limit) |
| **Formula** | `(SUM(current_balance) / NULLIF(SUM(credit_limit), 0)) * 100 FROM cards.card WHERE customer_id = ? AND card_type = 'CREDIT' AND card_status = 'ACTIVE'` |
| **Source** | `cards.card`, `accounts.account(current_balance)` |
| **Refresh Frequency** | Daily |
| **Data Type** | FLOAT (0–100+) |
| **Missing Value Strategy** | **Default to 0.0** if no credit cards. Default to NULL if cards exist but limit is unknown. |
| **POC Priority** | Medium — high utilization correlates with financial stress |

---

### F-CU-003: `online_txn_ratio_90d`

| Attribute | Value |
|-----------|-------|
| **Description** | Ratio of online card transactions to total card transactions over 90 days |
| **Formula** | `COUNT(CASE WHEN ct.is_online THEN 1 END) * 1.0 / NULLIF(COUNT(*), 0) FROM cards.card_transaction ct JOIN cards.card c ON ct.card_id = c.id WHERE c.customer_id = ? AND ct.transaction_date >= CURRENT_DATE - INTERVAL '90 days'` |
| **Source** | `cards.card_transaction(is_online)` |
| **Refresh Frequency** | Daily |
| **Data Type** | FLOAT (0.0–1.0) |
| **Missing Value Strategy** | **Default to 0.0** if no card transactions. |
| **POC Priority** | Low — digital adoption indicator |

---

## 6. Feature Group: `digital_engagement`

**Domain:** Digital banking activity and channel adoption
**Owning Service:** `feature-engineering-service`
**Source Schema:** `channels`
**Default Refresh:** Daily

---

### F-DE-001: `login_freq_7d`

| Attribute | Value |
|-----------|-------|
| **Description** | Number of successful digital banking logins in the last 7 days |
| **Formula** | `COUNT(*) FROM channels.digital_activity WHERE customer_id = ? AND activity_type = 'LOGIN' AND is_successful = TRUE AND activity_date >= CURRENT_DATE - INTERVAL '7 days'` |
| **Source** | `channels.digital_activity` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** No login records = no digital engagement. |
| **POC Priority** | **CRITICAL** — digital login is a qualifying activity indicator and strong engagement signal |

---

### F-DE-002: `login_freq_30d`

| Attribute | Value |
|-----------|-------|
| **Description** | Successful logins in the last 30 days |
| **Formula** | Same as F-DE-001 with 30-day window |
| **Source** | `channels.digital_activity` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** |
| **POC Priority** | High |

---

### F-DE-003: `days_since_last_login`

| Attribute | Value |
|-----------|-------|
| **Description** | Days since the customer's last successful digital banking login |
| **Formula** | `DATE_PART('day', AGE(CURRENT_DATE, MAX(activity_date))) FROM channels.digital_activity WHERE customer_id = ? AND activity_type = 'LOGIN' AND is_successful = TRUE` |
| **Source** | `channels.digital_activity` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 9999** sentinel — customer has never logged into digital banking. |
| **POC Priority** | High — digital disengagement often precedes financial disengagement |

---

### F-DE-004: `digital_adoption_score`

| Attribute | Value |
|-----------|-------|
| **Description** | Composite score (0–100) measuring the customer's adoption of digital channels |
| **Formula** | Weighted sum: `(mobile_app_usage × 0.4) + (online_banking_usage × 0.3) + (digital_payments_usage × 0.2) + (paperless_preference × 0.1)`. Each component is a 0–100 sub-score from `channel_preference` and `digital_activity` patterns. |
| **Source** | `channels.channel_preference`, `channels.digital_activity` |
| **Refresh Frequency** | Weekly |
| **Data Type** | FLOAT (0–100) |
| **Missing Value Strategy** | **Default to 0.0** — no digital activity means zero adoption. |
| **POC Priority** | Medium — digitally adopted customers are stickier |

---

### F-DE-005: `primary_channel`

| Attribute | Value |
|-----------|-------|
| **Description** | Customer's primary banking channel |
| **Formula** | `SELECT channel FROM channels.channel_preference WHERE customer_id = ? AND is_primary = TRUE LIMIT 1` |
| **Source** | `channels.channel_preference` |
| **Refresh Frequency** | Weekly |
| **Data Type** | CATEGORICAL: `BRANCH`, `MOBILE`, `INTERNET`, `ATM`, `CALL_CENTER` |
| **Missing Value Strategy** | **Default to `BRANCH`** — the traditional default channel. |
| **POC Priority** | Medium |

---

### F-DE-006: `has_mobile_app`

| Attribute | Value |
|-----------|-------|
| **Description** | Whether the customer has used the mobile app (binary) |
| **Formula** | `EXISTS (SELECT 1 FROM channels.digital_activity WHERE customer_id = ? AND channel = 'MOBILE_APP')` |
| **Source** | `channels.digital_activity` |
| **Refresh Frequency** | Daily |
| **Data Type** | BOOLEAN |
| **Missing Value Strategy** | **Default to FALSE.** |
| **POC Priority** | Medium |

---

## 7. Feature Group: `relationship_depth`

**Domain:** Product holdings and relationship breadth
**Owning Service:** `feature-engineering-service`
**Source Schema:** `customer_master`, `products`, `accounts`
**Default Refresh:** Weekly

---

### F-RD-001: `product_count`

| Attribute | Value |
|-----------|-------|
| **Description** | Number of distinct active products held by the customer |
| **Formula** | `COUNT(DISTINCT product_id) FROM products.customer_product_holding WHERE customer_id = ? AND holding_status = 'ACTIVE'` |
| **Source** | `products.customer_product_holding` |
| **Refresh Frequency** | Weekly |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 1** (assuming at least a basic account). |
| **POC Priority** | High — more products = deeper relationship = lower churn |

---

### F-RD-002: `product_diversity_score`

| Attribute | Value |
|-----------|-------|
| **Description** | Diversity of product categories held (0–1) — higher means broader relationship |
| **Formula** | `COUNT(DISTINCT p.product_type) / (SELECT COUNT(DISTINCT product_type) FROM products.product)` — ratio of product types held to total available types |
| **Source** | `products.customer_product_holding` JOIN `products.product` |
| **Refresh Frequency** | Weekly |
| **Data Type** | FLOAT (0.0–1.0) |
| **Missing Value Strategy** | **Default to 0.0.** |
| **POC Priority** | Medium |

---

### F-RD-003: `cross_sell_opportunity_count`

| Attribute | Value |
|-----------|-------|
| **Description** | Number of products the customer does NOT hold but is eligible for |
| **Formula** | Count of active products in the catalog where `product_type` matches the customer's segment eligibility but the customer does not hold the product |
| **Source** | `products.product`, `products.customer_product_holding`, `customer_master.customer_segment` |
| **Refresh Frequency** | Weekly |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** |
| **POC Priority** | High — directly feeds NBA cross-sell recommendations |

---

### F-RD-004: `relationship_duration_days`

| Attribute | Value |
|-----------|-------|
| **Description** | Days since the customer's first product was acquired |
| **Formula** | `DATE_PART('day', AGE(CURRENT_DATE, MIN(acquired_date))) FROM products.customer_product_holding WHERE customer_id = ?` |
| **Source** | `products.customer_product_holding(acquired_date)` |
| **Refresh Frequency** | Weekly |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** |
| **POC Priority** | High — relationship duration is a strong retention predictor |

---

### F-RD-005: `has_investment_product`

| Attribute | Value |
|-----------|-------|
| **Description** | Whether the customer holds any investment product (binary) |
| **Formula** | `EXISTS (SELECT 1 FROM products.customer_product_holding cph JOIN products.product p ON cph.product_id = p.id WHERE cph.customer_id = ? AND p.product_type = 'INVESTMENT' AND cph.holding_status = 'ACTIVE')` |
| **Source** | `products.*` |
| **Refresh Frequency** | Weekly |
| **Data Type** | BOOLEAN |
| **Missing Value Strategy** | **Default to FALSE.** |
| **POC Priority** | Medium — investment holders are significantly stickier |

---

## 8. Feature Group: `behavioural_state`

**Domain:** Customer lifecycle state and behavioural patterns
**Owning Service:** `customer-state-service` (reads) / `feature-engineering-service` (writes)
**Source Schema:** `customer_behaviour`, feature store
**Default Refresh:** Daily

---

### F-BS-001: `current_lifecycle_state` ⭐ PRIMARY

| Attribute | Value |
|-----------|-------|
| **Description** | Current customer lifecycle state based on days since last qualifying activity. This is the output of the BRS classification, stored as a feature for downstream consumption. |
| **Formula** | Apply configurable thresholds from `customer_state_definition` to `days_since_last_activity` (F-TB-001): ACTIVE (< min_days_for_early_warning), EARLY_WARNING (between thresholds), INACTIVE, PRE_DORMANT, DORMANT (≥ max_days_for_pre_dormant). |
| **Source** | `feature_store.feature_value` (F-TB-001), `configuration.customer_state_definition` |
| **Refresh Frequency** | Daily (recomputed after F-TB-001 refresh) |
| **Data Type** | CATEGORICAL: `ACTIVE`, `EARLY_WARNING`, `INACTIVE`, `PRE_DORMANT`, `DORMANT` |
| **Missing Value Strategy** | **Default to `DORMANT`** if `days_since_last_activity` is missing or equals the 9999 sentinel. Conservative — assume the worst when data is absent. |
| **POC Priority** | **CRITICAL** — This is the primary output of the PoC |

---

### F-BS-002: `days_in_current_state`

| Attribute | Value |
|-----------|-------|
| **Description** | Number of consecutive days the customer has been in their current state |
| **Formula** | `DATE_PART('day', AGE(CURRENT_DATE, MIN(transition_date))) FROM customer_behaviour.customer_state_history WHERE customer_id = ? AND to_state_id = (SELECT id FROM customer_state WHERE customer_id = ?)` |
| **Source** | `customer_behaviour.customer_state_history`, `customer_behaviour.customer_state` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** New customer or no state history. |
| **POC Priority** | High — recent changes are more actionable than long-standing states |

---

### F-BS-003: `state_transition_count_365d`

| Attribute | Value |
|-----------|-------|
| **Description** | Number of state transitions in the last 365 days — high count indicates unstable behavior |
| **Formula** | `COUNT(*) FROM customer_behaviour.customer_state_history WHERE customer_id = ? AND transition_date >= CURRENT_DATE - INTERVAL '365 days'` |
| **Source** | `customer_behaviour.customer_state_history` |
| **Refresh Frequency** | Daily |
| **Data Type** | INTEGER |
| **Missing Value Strategy** | **Default to 0.** |
| **POC Priority** | Medium — behavioral volatility indicator |

---

### F-BS-004: `previous_state`

| Attribute | Value |
|-----------|-------|
| **Description** | The customer's lifecycle state from the previous classification cycle |
| **Formula** | `SELECT to_state_id FROM customer_behaviour.customer_state_history WHERE customer_id = ? ORDER BY transition_date DESC LIMIT 1 OFFSET 1` |
| **Source** | `customer_behaviour.customer_state_history` |
| **Refresh Frequency** | Daily |
| **Data Type** | CATEGORICAL (same as F-BS-001) |
| **Missing Value Strategy** | **Default to NULL** — no previous state means this is the first classification. |
| **POC Priority** | High — state transitions (improving vs. deteriorating) are key for RM action |

---

### F-BS-005: `state_change_direction`

| Attribute | Value |
|-----------|-------|
| **Description** | Direction of the most recent state change |
| **Formula** | Compare `current_lifecycle_state` to `previous_state`. `IMPROVING` (Dormant→Pre-Dormant, Pre-Dormant→Inactive, etc.), `DETERIORATING` (Active→Early Warning, Early Warning→Inactive, etc.), `STABLE` (no change). |
| **Source** | Derived from F-BS-001 and F-BS-004 |
| **Refresh Frequency** | Daily |
| **Data Type** | CATEGORICAL: `IMPROVING`, `STABLE`, `DETERIORATING`, `NEW` |
| **Missing Value Strategy** | **Default to `NEW`** if no previous state exists (first classification). |
| **POC Priority** | **CRITICAL** — directly drives RM prioritization |

---

### F-BS-006: `has_returned_from_dormant`

| Attribute | Value |
|-----------|-------|
| **Description** | Whether the customer has ever returned from DORMANT to a better state (binary) |
| **Formula** | `EXISTS (SELECT 1 FROM customer_behaviour.customer_state_history WHERE customer_id = ? AND from_state_id IN (SELECT id FROM customer_state_definition WHERE state_code = 'DORMANT') AND to_state_id IN (SELECT id FROM customer_state_definition WHERE state_code != 'DORMANT'))` |
| **Source** | `customer_behaviour.customer_state_history` |
| **Refresh Frequency** | Daily |
| **Data Type** | BOOLEAN |
| **Missing Value Strategy** | **Default to FALSE.** |
| **POC Priority** | Medium — previously reactivated customers may churn again |

---

## 9. Feature Group: `clv_drivers`

**Domain:** Customer Lifetime Value estimation inputs
**Owning Service:** `feature-engineering-service`
**Source Schema:** Multiple (transactions, accounts, products)
**Default Refresh:** Monthly

---

### F-CLV-001: `revenue_12m`

| Attribute | Value |
|-----------|-------|
| **Description** | Total revenue generated by this customer in the last 12 months (interest income + fees) |
| **Formula** | `SUM(amount) FROM clean.clean_transaction WHERE customer_id = ? AND transaction_type IN ('FEE','INTEREST') AND transaction_date >= CURRENT_DATE - INTERVAL '12 months'` + estimated net interest margin from account balances |
| **Source** | `clean.clean_transaction`, `accounts.account_balance_snapshot` |
| **Refresh Frequency** | Monthly |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to 0.0.** |
| **POC Priority** | Medium — for CLV estimation and prioritization |

---

### F-CLV-002: `avg_monthly_balance_12m`

| Attribute | Value |
|-----------|-------|
| **Description** | Average monthly closing balance across all accounts over 12 months |
| **Formula** | `AVG(closing_balance) FROM accounts.account_balance_snapshot WHERE account_id IN (SELECT id FROM accounts.account WHERE customer_id = ?) AND snapshot_date >= CURRENT_DATE - INTERVAL '12 months'` |
| **Source** | `accounts.account_balance_snapshot` |
| **Refresh Frequency** | Monthly |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to 0.0** if no balance snapshots. |
| **POC Priority** | Medium |

---

### F-CLV-003: `cost_to_serve_estimate`

| Attribute | Value |
|-----------|-------|
| **Description** | Estimated annual cost to serve this customer (branch visits, call center, transaction processing) |
| **Formula** | Sum of: `branch_visit_count × branch_cost_per_visit` + `call_center_call_count × call_cost_per_call` + `transaction_count × txn_processing_cost`. Cost parameters from `configuration.system_setting`. |
| **Source** | `channels.digital_activity`, `clean.clean_transaction`, `configuration.system_setting` |
| **Refresh Frequency** | Monthly |
| **Data Type** | FLOAT |
| **Missing Value Strategy** | **Default to average cost-to-serve** for the customer's segment. |
| **POC Priority** | Low — for profitability analysis in later phases |

---

### F-CLV-004: `nps_proxy_score`

| Attribute | Value |
|-----------|-------|
| **Description** | Proxy Net Promoter Score based on behavioral indicators (since actual NPS survey data may not be available) |
| **Formula** | Composite: `(digital_adoption_score × 0.3) + (complaint_absence × 0.3) + (product_diversity × 0.2) + (tenure_normalized × 0.2)`. Scaled 0–100. |
| **Source** | Multiple feature groups |
| **Refresh Frequency** | Monthly |
| **Data Type** | FLOAT (0–100) |
| **Missing Value Strategy** | **Default to 50** — neutral score. |
| **POC Priority** | Low — behavioral proxy for satisfaction |

---

## 10. Feature Summary Matrix

### Feature Count by Group

| Feature Group | Feature Count | POC-Critical | POC-High | POC-Medium | POC-Low |
|---------------|---------------|--------------|----------|------------|----------|
| `customer_profile` | 5 | 0 | 2 | 2 | 1 |
| `transaction_behaviour` | 14 | **2** | 4 | 5 | 3 |
| `loan_behaviour` | 5 | 0 | 2 | 2 | 1 |
| `card_usage` | 3 | 0 | 0 | 2 | 1 |
| `digital_engagement` | 6 | **1** | 2 | 3 | 0 |
| `relationship_depth` | 5 | 0 | 3 | 2 | 0 |
| `behavioural_state` | 6 | **2** | 2 | 2 | 0 |
| `clv_drivers` | 4 | 0 | 0 | 2 | 2 |
| **TOTAL** | **48** | **5** | **15** | **20** | **8** |

### POC-Critical Features (Must Implement First)

| ID | Feature | Group | Drives |
|----|---------|-------|--------|
| F-TB-001 | `days_since_last_activity` | transaction_behaviour | BRS lifecycle classification |
| F-TB-002 | `txn_count_30d` | transaction_behaviour | Activity granularity |
| F-DE-001 | `login_freq_7d` | digital_engagement | Digital engagement signal |
| F-BS-001 | `current_lifecycle_state` | behavioural_state | Primary PoC output |
| F-BS-005 | `state_change_direction` | behavioural_state | RM prioritization |

---

## 11. Feature Refresh Schedule

Features are refreshed on different schedules to balance freshness with computational cost:

| Schedule | Feature Groups | Timing |
|----------|---------------|--------|
| **Daily (01:00 UTC)** | `transaction_behaviour`, `digital_engagement`, `loan_behaviour`, `card_usage`, `behavioural_state` | After nightly ETL completes |
| **Weekly (Sunday 03:00 UTC)** | `customer_profile`, `relationship_depth` | After weekend batch window |
| **Monthly (1st, 04:00 UTC)** | `clv_drivers` | After month-end close |

### Pipeline Dependency Order

```
1. Raw → Staging → Clean (ETL)
2. customer_profile, transaction_behaviour, digital_engagement (daily features)
3. loan_behaviour, card_usage (daily features, depend on #2 for customer linkage)
4. behavioural_state (depends on transaction_behaviour + digital_engagement)
5. relationship_depth (weekly, depends on #2 for current product data)
6. clv_drivers (monthly, depends on all above)
```

---

## 12. Missing Value Strategy — Design Principles

| Strategy | When to Use | Example |
|----------|-------------|---------|
| **Default to 0** | Count features — no data means zero activity | `txn_count_30d` → 0 |
| **Default to sentinel (9999)** | Features where "unknown" is meaningfully different from any valid value | `days_since_last_activity` → 9999 |
| **Default to NULL** | Features where imputation would be misleading; downstream models handle NULL | `monthly_income_estimate` → NULL |
| **Default to median/mean** | Continuous features where a reasonable population estimate exists | `age` → segment median |
| **Default to most-common category** | Categorical features where the mode is a safe assumption | `customer_segment_current` → MASS_MARKET |
| **Default to conservative value** | Risk-sensitive features where assuming the worst is safer | `risk_category` → MEDIUM (not LOW) |
| **Mark as imputed** | Any imputed value should have a companion `_imputed` flag | `age_imputed = TRUE` |

---

## 13. Configuration-Driven Thresholds

The BRS specifies that lifecycle thresholds must be **configurable, not hard-coded**. The `customer_state_definition` table stores these values:

| State | `min_days` | `max_days` | `state_code` | `priority` |
|-------|-----------|-----------|-------------|------------|
| ACTIVE | 0 | 59 | ACTIVE | 5 |
| EARLY_WARNING | 60 | 89 | EARLY_WARNING | 4 |
| INACTIVE | 90 | 179 | INACTIVE | 3 |
| PRE_DORMANT | 180 | 364 | PRE_DORMANT | 2 |
| DORMANT | 365 | 999999 | DORMANT | 1 |

This means a bank can change "Active" from <60 days to <45 days without any code changes — just update the `min_days`/`max_days` values in the configuration table.

---

*End of Feature Engineering Design v1.0*
