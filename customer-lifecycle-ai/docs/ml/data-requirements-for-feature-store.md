# Data Requirements — Customer Feature Store

**To:** Data Science / Data Engineering Team  
**From:** Feature Engineering (AI/ML)  
**Date:** 2026-07-27  
**Priority:** P1 items block 4 features; P2 blocks 6 more

---

## Context

The Customer Feature Store computes 56 observable features across 7 domains from `etl_clean` tables. 10 additional features are blocked by data gaps — 4 can be unblocked with schema changes to existing tables, and 6 require new source tables or fresh data.

---

## Priority 1 — Schema Changes (4 features unblocked)

### P1.1: Migrate `transaction_date` from DATE → TIMESTAMP

**Table:** `customer_transactions_clean`  
**Current type:** `DATE`  
**Required type:** `TIMESTAMP` (or `TIMESTAMPTZ`)  

**Why:** 3 temporal features need hour-of-day:

| Feature | Query Fragment |
|---------|---------------|
| `temp_morning_activity_ratio_90d` | `EXTRACT(HOUR FROM transaction_date) BETWEEN 6 AND 11` |
| `temp_afternoon_activity_ratio_90d` | `EXTRACT(HOUR FROM transaction_date) BETWEEN 12 AND 17` |
| `temp_evening_activity_ratio_90d` | `EXTRACT(HOUR FROM transaction_date) BETWEEN 18 AND 23` |

PostgreSQL throws `unit "hour" not supported for type date` — these fail today.

**Migration approach (non-breaking):**
```sql
ALTER TABLE customer_transactions_clean 
  ALTER COLUMN transaction_date TYPE TIMESTAMP 
  USING transaction_date::timestamp;
```
This preserves all existing date values (casts to midnight). No data loss.

**Acceptable alternative:** Add a new column `transaction_timestamp TIMESTAMP` populated during ETL, and keep `transaction_date` as-is. If you go this route, let us know the column name — we'll update the generator SQL.

---

### P1.2: Add `nationality` and `kyc_tier` to `customers_clean`

**Table:** `customers_clean`  
**New columns needed:**

| Column | Type | Nullable | Source |
|--------|------|----------|--------|
| `kyc_tier` | `VARCHAR(16)` | YES | Raw customer CSV — KYC verification level |
| `nationality` | `VARCHAR(64)` | YES | Raw customer CSV — customer nationality |

**Why:** These are direct copies into the feature store:

| Feature | Source |
|---------|--------|
| `prof_kyc_tier` | `customers_clean.kyc_tier` |
| `prof_nationality` | `customers_clean.nationality` |

**Migration:**
```sql
ALTER TABLE customers_clean ADD COLUMN IF NOT EXISTS kyc_tier VARCHAR(16);
ALTER TABLE customers_clean ADD COLUMN IF NOT EXISTS nationality VARCHAR(64);
```

If these columns already exist in the raw source data but are dropped during ETL, update the ETL field mapping to include them. No generator code changes needed — the SQL already reads `cc.branch_code` and can read these identically.

---

## Priority 2 — Fresh Data + New Tables (6 features unblocked)

### P2.1: Transaction data within 30 days of target date

**Issue:** The most recent transaction in `customer_transactions_clean` is more than 30 days before `2026-07-27`. The 30-day window is empty.

**Why:** 1 risk feature needs a 30-day comparison window:

| Feature | Logic |
|---------|-------|
| `risk_unusual_channel_flag` | Channel used in last 30 days that was NOT used in prior 150 days |

**Request:** Run the ETL pipeline with source data that includes transaction dates up to and including the target `as_of_date`. This feature self-activates — the SQL is ready, just needs data in the window.

---

### P2.2: New Table — `accounts_clean`

**Required columns:**

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `customer_id` | `VARCHAR(64)` | YES | FK to customers_clean |
| `account_type` | `VARCHAR(32)` | YES | e.g., 'SAVINGS', 'CURRENT', 'FIXED_DEPOSIT' |
| `status` | `VARCHAR(16)` | YES | e.g., 'Active', 'Dormant', 'Closed' |
| `opened_date` | `DATE` | NO | Account opening date |
| `loaded_at` | `TIMESTAMPTZ` | YES | ETL batch timestamp |
| `batch_id` | `VARCHAR(64)` | YES | ETL batch identifier |

**Why:** 3 relationship features:

| Feature | SQL |
|---------|-----|
| `rel_accounts_active` | `COUNT(*) WHERE status = 'Active'` |
| `rel_has_savings` | `EXISTS (SELECT 1 WHERE account_type = 'SAVINGS')` |
| `rel_products_owned` | `COUNT(DISTINCT account_type)` |

---

### P2.3: New Table — `loans_clean`

**Required columns:**

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `customer_id` | `VARCHAR(64)` | YES | FK to customers_clean |
| `loan_type` | `VARCHAR(32)` | YES | e.g., 'PERSONAL', 'MORTGAGE', 'BUSINESS' |
| `status` | `VARCHAR(16)` | YES | e.g., 'Active', 'Closed', 'Defaulted' |
| `origination_date` | `DATE` | NO | Loan start date |
| `loaded_at` | `TIMESTAMPTZ` | YES | ETL batch timestamp |
| `batch_id` | `VARCHAR(64)` | YES | ETL batch identifier |

**Why:** 1 relationship feature:

| Feature | SQL |
|---------|-----|
| `rel_has_loan` | `EXISTS (SELECT 1 WHERE status = 'Active')` |

---

## Data Contract Summary

| # | Request | Table | Change Type | Features |
|---|---------|-------|-------------|----------|
| P1.1 | DATE → TIMESTAMP | `customer_transactions_clean` | ALTER COLUMN | 3 temporal |
| P1.2 | Add `kyc_tier`, `nationality` | `customers_clean` | ADD COLUMN + ETL mapping | 2 profile |
| P2.1 | Transactions within 30 days | `customer_transactions_clean` | Fresh ETL run | 1 risk |
| P2.2 | New table | `accounts_clean` | CREATE TABLE + ETL pipeline | 3 relationship |
| P2.3 | New table | `loans_clean` | CREATE TABLE + ETL pipeline | 1 relationship |

---

## Priority 3 — Additional Source Tables (future phases)

These tables unlock new feature domains beyond the current 7-domain architecture. They are not blockers for v1 completion but will significantly improve downstream model accuracy for churn prediction, CLV estimation, and segmentation.

---

### P3.1: New Table — `cards_clean`

**Why:** Cards are the most common secondary banking product. Card activation, usage, and expiry are strong churn signals — a customer who stopped using their card is likely disengaging from the bank entirely.

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `customer_id` | `VARCHAR(64)` | YES | FK to customers_clean |
| `card_type` | `VARCHAR(32)` | YES | 'DEBIT', 'CREDIT', 'PREPAID' |
| `status` | `VARCHAR(16)` | YES | 'Active', 'Blocked', 'Expired', 'Cancelled', 'Pending_Activation' |
| `issued_date` | `DATE` | NO | Card issuance date |
| `expiry_date` | `DATE` | NO | Card expiry date — upcoming expiry = retention opportunity |
| `activated_date` | `DATE` | NO | When card was first used (NULL = never activated) |
| `loaded_at` | `TIMESTAMPTZ` | YES | ETL batch timestamp |
| `batch_id` | `VARCHAR(64)` | YES | ETL batch identifier |

**Would enable (3-5 new features):**

| Feature | Type | Description |
|---------|------|-------------|
| `rel_has_card` | BOOLEAN | Has at least one active card |
| `rel_card_count` | INTEGER | Number of cards held |
| `rel_has_unactivated_card` | BOOLEAN | Issued but never activated — cross-sell failure signal |
| `rel_card_expiring_30d` | BOOLEAN | Card expiring within 30 days — retention trigger |
| `rel_card_types` | INTEGER | COUNT(DISTINCT card_type) — product diversity |

**Sample SQL (ready to implement):**
```sql
SELECT customer_id,
       COUNT(*) AS card_count,
       COUNT(*) FILTER (WHERE status = 'Active') AS active_cards,
       COUNT(*) FILTER (WHERE expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 30) AS expiring_30d,
       COUNT(*) FILTER (WHERE activated_date IS NULL) AS unactivated
FROM cards_clean
GROUP BY customer_id;
```

---

### P3.2: New Table — `digital_engagement_clean`

**Why:** Transaction channels tell you *where* money moves. Login data tells you *how often* customers engage — two different signals. A customer might have zero transactions but log in daily to check their balance. Another might have many transactions but never log in (auto-debits). These patterns predict churn differently.

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `customer_id` | `VARCHAR(64)` | YES | FK to customers_clean |
| `login_date` | `DATE` | YES | Date of login/session |
| `platform` | `VARCHAR(32)` | YES | 'MOBILE_APP', 'WEB', 'USSD' |
| `session_duration_seconds` | `INTEGER` | NO | Session length — engagement depth proxy |
| `actions_count` | `INTEGER` | NO | Number of clicks/actions in session |
| `loaded_at` | `TIMESTAMPTZ` | YES | ETL batch timestamp |
| `batch_id` | `VARCHAR(64)` | YES | ETL batch identifier |

**Would enable (3-4 new features):**

| Feature | Type | Description |
|---------|------|-------------|
| `eng_login_count_7d` | INTEGER | Login frequency — daily engagement |
| `eng_login_count_30d` | INTEGER | Monthly engagement |
| `eng_digital_platform_preference` | VARCHAR(32) | Dominant platform (APP vs WEB vs USSD) |
| `eng_avg_session_duration_30d` | FLOAT | Average session length — depth of engagement |

**Sample SQL (ready to implement):**
```sql
UPDATE customer_features cf
SET
    eng_login_count_30d = agg.login_count,
    eng_digital_platform_preference = agg.dominant_platform,
    eng_avg_session_duration_30d = agg.avg_duration
FROM (
    SELECT customer_id,
           COUNT(*) AS login_count,
           MODE() WITHIN GROUP (ORDER BY platform) AS dominant_platform,
           AVG(session_duration_seconds) AS avg_duration
    FROM digital_engagement_clean
    WHERE login_date > (%(d)s::date - INTERVAL '30 days')
      AND login_date <= %(d)s::date
    GROUP BY customer_id
) agg
WHERE cf.customer_id = agg.customer_id
  AND cf.as_of_date = %(d)s::date;
```

---

### P3.3: New Table — `demographics_clean`

**Why:** Employment status and declared income enable salary cross-referencing (does observed credit match declared income?), employer cohort analysis (which companies see high churn?), and education-based segmentation. If this data already lives in `customers_clean`, prefer adding columns there instead of creating a separate table.

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `customer_id` | `VARCHAR(64)` | YES | FK to customers_clean |
| `employment_status` | `VARCHAR(32)` | NO | 'Employed', 'Self_Employed', 'Unemployed', 'Retired', 'Student' |
| `employer_name` | `VARCHAR(128)` | NO | Employer — enables employer cohort churn analysis |
| `monthly_income_declared` | `FLOAT` | NO | Self-declared at onboarding — cross-ref with observed credits |
| `education_level` | `VARCHAR(32)` | NO | 'Primary', 'Secondary', 'Tertiary', 'Postgraduate' |
| `marital_status` | `VARCHAR(16)` | NO | 'Single', 'Married', 'Divorced', 'Widowed' |
| `loaded_at` | `TIMESTAMPTZ` | YES | ETL batch timestamp |
| `batch_id` | `VARCHAR(64)` | YES | ETL batch identifier |

**Would enable (3-4 new features):**

| Feature | Type | Description |
|---------|------|-------------|
| `prof_employment_status` | VARCHAR(32) | Direct copy |
| `prof_education_level` | VARCHAR(32) | Direct copy |
| `prof_declared_vs_observed_income_ratio` | FLOAT | `monthly_income_declared / (fin_total_credit_90d / 3)` — income discrepancy = risk |
| `prof_employer_cohort` | VARCHAR(128) | Employer name for cohort analysis |

**Note:** If `employment_status`, `education_level`, and `employer_name` already exist in the raw customer source but were dropped during ETL, add them to `customers_clean` instead of creating this table. The feature store can read from either.

---

## Complete Data Contract Summary

| # | Request | Table | Type | Features |
|---|---------|-------|------|----------|
| P1.1 | DATE → TIMESTAMP | `customer_transactions_clean` | Schema change | 3 |
| P1.2 | Add `kyc_tier`, `nationality` | `customers_clean` | Schema change | 2 |
| P2.1 | Transactions within 30 days | `customer_transactions_clean` | Fresh data | 1 |
| P2.2 | New table | `accounts_clean` | New pipeline | 3 |
| P2.3 | New table | `loans_clean` | New pipeline | 1 |
| P3.1 | New table | `cards_clean` | New pipeline | 5 |
| P3.2 | New table | `digital_engagement_clean` | New pipeline | 4 |
| P3.3 | New table or columns | `demographics_clean` / `customers_clean` | New pipeline or schema | 4 |
| **Total** | | | | **23 new features** |

## Verification

After delivering each item, features auto-activate. Verify with:

```bash
cd customer-lifecycle-ai
python _run_generators.py
```

Expected: all 10 previously-NULL features show non-NULL counts in the verification output.

---

## Questions?

Contact the Feature Engineering team (owner of `services/feature-engineering-service/`). Generator code is in `app/features/*/generator.py` — all SQL is already written and ready.
