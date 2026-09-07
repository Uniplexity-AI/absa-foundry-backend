# Data Request: Churned Customers Dataset
## Customer Lifecycle Prediction System — Model Validation

---

| **Document Control** | |
|---|---|
| **Request Reference** | ABSA-CLP-DR-001 |
| **Requesting Team** | Uniplexity AI — Customer Lifecycle AI |
| **Requesting Project** | Customer Lifecycle Prediction System PoC |
| **Date of Request** | 6 August 2026 |
| **Priority** | High — required for model validation milestone (Month 2) |
| **Data Classification** | Confidential — Customer PII |
| **Approval Route** | Data Governance Committee → Chief Data Officer |

---

## 1. Purpose

This document requests a structured extract of **churned and active customer data** from Absa Bank Zambia's core banking system(s). The data will be used exclusively for:

1. **Training validation** — verifying that the churn prediction model correctly identifies customers who subsequently churned
2. **Classification accuracy testing** — measuring precision, recall, and false-positive rates of the Customer State Service
3. **Feature engineering calibration** — validating that the 56 engineered features produce meaningful signal for churn vs. active customers
4. **End-to-end system testing** — verifying that the full pipeline (ETL → Features → State → Prediction → NBA) produces correct outputs against known ground truth

**The data will NOT be used for production inference, credit scoring, or any purpose other than model validation within the PoC environment.**

---

## 2. Data Environment

| Constraint | Detail |
|---|---|
| **Storage location** | On-premise Absa PoC server (Ubuntu, 500 GB SSD) |
| **Network access** | Air-gapped — no internet connectivity |
| **Data retention** | Duration of PoC only (90 days); destroyed on project completion |
| **Access control** | Restricted to 3 authorized data scientists via PostgreSQL role-based access |
| **Compliance** | All data remains within Bank of Zambia jurisdiction |

---

## 3. Requested Cohorts

### 3.1 Churned Customers (Target Group)

| Parameter | Specification |
|---|---|
| **Definition of "churned"** | Customer whose last account was closed OR whose last transaction/activity was ≥365 days ago as of extract date |
| **Sample size** | 500 customers |
| **Time window** | Customers who churned between **1 January 2025 and 30 June 2026** |
| **Selection method** | Random sample from all churned customers meeting the definition, stratified by segment (Mass Market / Mass Affluent / Affluent / SME) if possible |

### 3.2 Active Customers (Control Group)

| Parameter | Specification |
|---|---|
| **Definition of "active"** | Customer with at least one transaction in the last 30 days AND no accounts in CLOSED or DORMANT status |
| **Sample size** | 500 customers |
| **Selection method** | Random sample from all active customers, stratified by segment to match the churned cohort distribution |

---

## 4. Data Fields Required

### 4.1 Customer Profile (1 row per customer)

| # | Field Name | Data Type | Required | Description |
|---|-----------|-----------|----------|-------------|
| 1 | `customer_id` | VARCHAR(64) | **Yes** | Unique customer identifier (may be masked/anonymized) |
| 2 | `date_of_birth` | DATE | **Yes** | Or age at extract date if PII concern |
| 3 | `gender` | VARCHAR(16) | No | MALE / FEMALE |
| 4 | `branch_code` | VARCHAR(16) | **Yes** | Branch where customer is domiciled |
| 5 | `activation_date` | DATE | **Yes** | Date customer relationship began (first account opened) |
| 6 | `kyc_tier` | VARCHAR(16) | No | TIER_1 / TIER_2 / TIER_3 |
| 7 | `nationality` | VARCHAR(32) | No | |
| 8 | `employment_status` | VARCHAR(32) | No | EMPLOYED / SELF_EMPLOYED / UNEMPLOYED / RETIRED |
| 9 | `monthly_income` | DECIMAL(15,2) | No | Declared monthly income in ZMW |
| 10 | `education_level` | VARCHAR(32) | No | |
| 11 | `marital_status` | VARCHAR(16) | No | |
| 12 | `customer_segment` | VARCHAR(32) | **Yes** | MASS_MARKET / MASS_AFFLUENT / AFFLUENT / SME / CORPORATE |
| 13 | `churn_date` | DATE | **Yes** (churned only) | Date customer churned (account closed or last activity +365d) |
| 14 | `churn_reason` | VARCHAR(64) | **Yes** (churned only) | ACCOUNT_CLOSED / DORMANT_365D / TRANSFERRED_OUT / DECEASED / OTHER |
| 15 | `churn_reason_detail` | VARCHAR(256) | No | Free-text reason if available (e.g., "Moved to competitor", "Fee dissatisfaction") |

> **PII note:** Customer names are NOT required. If `customer_id` must be masked, ensure consistent masking across ALL tables (same customer maps to same masked ID across all 6 data domains).

---

### 4.2 Transactions (multiple rows per customer)

**Time window:** 12 months of history ending at the later of (a) the customer's churn date, or (b) 30 June 2026 for active customers.

| # | Field Name | Data Type | Required | Description |
|---|-----------|-----------|----------|-------------|
| 1 | `customer_id` | VARCHAR(64) | **Yes** | FK to Customer Profile |
| 2 | `account_id` | VARCHAR(64) | **Yes** | |
| 3 | `transaction_id` | VARCHAR(64) | **Yes** | Unique per transaction |
| 4 | `transaction_date` | TIMESTAMP | **Yes** | Date and time of transaction |
| 5 | `transaction_type` | VARCHAR(16) | **Yes** | CREDIT / DEBIT / TRANSFER / FEE / INTEREST / REVERSAL |
| 6 | `channel` | VARCHAR(16) | No | ATM / POS / MOBILE / BRANCH / ONLINE / USSD |
| 7 | `currency` | CHAR(3) | No | Default ZMW |
| 8 | `amount` | DECIMAL(15,2) | **Yes** | Transaction amount |

> **Volume estimate:** ~500 customers × ~20 transactions/month × 12 months ≈ 120,000 rows

---

### 4.3 Accounts (multiple rows per customer)

| # | Field Name | Data Type | Required | Description |
|---|-----------|-----------|----------|-------------|
| 1 | `customer_id` | VARCHAR(64) | **Yes** | FK to Customer Profile |
| 2 | `account_id` | VARCHAR(64) | **Yes** | |
| 3 | `account_type` | VARCHAR(32) | **Yes** | SAVINGS / CURRENT / FIXED_DEPOSIT / LOAN |
| 4 | `status` | VARCHAR(16) | **Yes** | ACTIVE / INACTIVE / DORMANT / CLOSED |
| 5 | `opened_date` | DATE | **Yes** | |
| 6 | `closed_date` | DATE | No | Date account was closed (if applicable) |

> **Volume estimate:** ~500 customers × ~2 accounts each ≈ 1,000 rows

---

### 4.4 Loans (multiple rows per customer with loan products)

| # | Field Name | Data Type | Required | Description |
|---|-----------|-----------|----------|-------------|
| 1 | `customer_id` | VARCHAR(64) | **Yes** | FK to Customer Profile |
| 2 | `loan_id` | VARCHAR(64) | **Yes** | |
| 3 | `loan_type` | VARCHAR(32) | **Yes** | PERSONAL / MORTGAGE / AUTO / BUSINESS / OVERDRAFT |
| 4 | `status` | VARCHAR(16) | **Yes** | ACTIVE / PAID_OFF / DEFAULTED / WRITTEN_OFF |
| 5 | `origination_date` | DATE | **Yes** | |
| 6 | `closure_date` | DATE | No | |

> **Volume estimate:** ~500 customers × ~0.3 loans each ≈ 150 rows

---

### 4.5 Cards (multiple rows per customer with card products)

| # | Field Name | Data Type | Required | Description |
|---|-----------|-----------|----------|-------------|
| 1 | `customer_id` | VARCHAR(64) | **Yes** | FK to Customer Profile |
| 2 | `card_id` | VARCHAR(64) | **Yes** | |
| 3 | `card_type` | VARCHAR(16) | **Yes** | DEBIT / CREDIT / PREPAID |
| 4 | `status` | VARCHAR(16) | **Yes** | ACTIVE / INACTIVE / BLOCKED / EXPIRED |
| 5 | `issued_date` | DATE | **Yes** | |
| 6 | `expiry_date` | DATE | No | |

> **Volume estimate:** ~500 customers × ~1 card each ≈ 500 rows

---

### 4.6 Digital Engagement (multiple rows per customer)

**Time window:** 12 months of history (same window as transactions).

| # | Field Name | Data Type | Required | Description |
|---|-----------|-----------|----------|-------------|
| 1 | `customer_id` | VARCHAR(64) | **Yes** | FK to Customer Profile |
| 2 | `login_date` | TIMESTAMP | **Yes** | Date and time of login/session |
| 3 | `platform` | VARCHAR(16) | No | MOBILE / WEB / USSD |
| 4 | `session_duration_seconds` | INTEGER | No | Session length in seconds |
| 5 | `actions_count` | INTEGER | No | Number of actions performed in session |

> **Volume estimate:** ~500 customers × ~8 logins/month × 12 months ≈ 48,000 rows

---

## 5. Delivery Format

| Requirement | Specification |
|---|---|
| **Format** | CSV (UTF-8, comma-delimited, header row) |
| **Delivery** | 6 separate files (one per domain above) OR 1 denormalized file |
| **Delivery method** | Secure file transfer to PoC server OR encrypted USB (per IT Security policy) |
| **Naming convention** | `absa_churn_[domain]_20260806.csv` (e.g., `absa_churn_customers_20260806.csv`) |
| **Null representation** | Empty field or `NULL` |

---

## 6. Justification — Why This Data Is Needed

| Testing Objective | Data Required | Without This Data |
|---|---|---|
| **Churn classification accuracy** | Customers with known churn dates | Cannot measure precision/recall of the state engine — only have synthetic data |
| **Early-warning signal detection** | 12 months of transaction history before churn | Cannot verify that declining activity precedes churn in real customer data |
| **Feature calibration** | Profile + transaction + engagement data | 56 engineered features validated on synthetic data only — real distributions may differ |
| **False-positive rate** | Active customer control group | Cannot measure how many active customers are incorrectly flagged as at-risk |
| **Segment-specific performance** | Segment field in customer profile | Cannot verify model works equally well across Mass Market vs Affluent vs SME |
| **NBA relevance** | Product holdings + churn reason | Cannot validate that recommended actions match real churn drivers |

---

## 7. Data Governance Commitments

| Commitment | Detail |
|---|---|
| **Purpose limitation** | Data used exclusively for PoC model validation; not for production decisions |
| **Storage limitation** | Data retained for PoC duration only (90 days from receipt); destroyed thereafter |
| **Access limitation** | Maximum 3 authorized personnel with PostgreSQL role-based access |
| **No onward sharing** | Data will not leave the PoC server; no copies to cloud, email, or external systems |
| **Auditability** | All access logged via ETL audit trail (`etl.etl_audit`) |
| **Destruction certificate** | Will provide written confirmation of data destruction upon PoC completion |
| **Compliance** | Fully compliant with Bank of Zambia data localization requirements — all processing on-premise, air-gapped |

---

## 8. Approvals

| Role | Name | Signature | Date |
|---|---|---|---|
| **Requestor** (Uniplexity AI Lead) | ___________ | ___________ | ___/___/2026 |
| **Data Owner** (Head of Retail Banking) | ___________ | ___________ | ___/___/2026 |
| **Data Governance** (Chief Data Officer) | ___________ | ___________ | ___/___/2026 |
| **InfoSec** (CISO or delegate) | ___________ | ___________ | ___/___/2026 |
| **PoC Sponsor** (Executive Sponsor) | ___________ | ___________ | ___/___/2026 |

---

## Appendix A: Quick-Reference Field Checklist

```
☐ customer_id            ☐ transaction_date       ☐ account_type
☐ date_of_birth          ☐ transaction_type       ☐ account_status
☐ gender                 ☐ channel                ☐ account_opened_date
☐ branch_code            ☐ currency               ☐ account_closed_date
☐ activation_date        ☐ amount                 ☐ loan_id
☐ kyc_tier                                       ☐ loan_type
☐ nationality            ☐ login_date             ☐ loan_status
☐ employment_status      ☐ platform               ☐ loan_origination_date
☐ monthly_income         ☐ session_duration       ☐ loan_closure_date
☐ education_level        ☐ actions_count          ☐ card_id
☐ marital_status                                 ☐ card_type
☐ customer_segment       ☐ account_id             ☐ card_status
☐ churn_date ★                                   ☐ card_issued_date
☐ churn_reason ★                                 ☐ card_expiry_date
☐ churn_reason_detail
```

> ★ = Most critical fields for churn validation

---

## Appendix B: Estimated Data Volume

| Domain | Rows (approx.) | Columns | Est. File Size (CSV) |
|---|---|---|---|
| Customer Profile | 1,000 | 15 | ~150 KB |
| Transactions | 120,000 | 8 | ~8 MB |
| Accounts | 1,000 | 6 | ~60 KB |
| Loans | 150 | 6 | ~10 KB |
| Cards | 500 | 6 | ~30 KB |
| Digital Engagement | 48,000 | 5 | ~2 MB |
| **TOTAL** | **~170,650** | | **~10 MB** |
