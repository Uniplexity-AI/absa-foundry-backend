# Feature Engineering — Implementation Status

**Service:** `feature-engineering-service` (port 8002)
**Database:** `etl_clean` (target DB)
**Source Tables:** `customer_transactions_clean` (209K rows, 5,000 unique customers)
**Last Updated:** 2026-07-22

---

## 1. What's Built

### 1.1 Service Architecture

```
feature-engineering-service/
├── main.py                    # FastAPI app, port 8002, loads .env
├── app/
│   ├── api/routes.py          # 3 endpoints
│   ├── services/service.py    # Business logic (thin — delegates to repo)
│   ├── repository/repository.py  # 2-phase SQL computation + fetch
│   └── schemas/schemas.py     # FeatureSnapshot (21 fields) + responses
```

### 1.2 API Endpoints

| Method | Route | Purpose | Status |
|---|---|---|---|
| `POST` | `/features/compute-batch?as_of_date=YYYY-MM-DD` | Compute features for all 5,000 active customers | ✅ Working |
| `GET` | `/features/{customer_id}?as_of_date=YYYY-MM-DD` | Get one customer's features for a specific date | ✅ Working |
| `GET` | `/features/{customer_id}/latest` | Get the most recent feature snapshot | ✅ Working |
| `GET` | `/health` | Health check | ✅ Working |

### 1.3 Features Computed (21 total)

#### Phase 1 — Raw Aggregates (15 features)
Computed in a single `INSERT ... SELECT ... GROUP BY` query from `customer_transactions_clean`.

| # | Feature | Type | Window | Description |
|---|---|---|---|---|
| 1 | `days_since_last_txn` | INT | — | Days since most recent qualifying transaction |
| 2 | `days_since_first_txn` | INT | — | Days since first-ever transaction |
| 3 | `txn_count_30d` | INT | 30 days | Count of qualifying transactions |
| 4 | `txn_count_90d` | INT | 90 days | Count of qualifying transactions |
| 5 | `txn_count_180d` | INT | 180 days | Count of qualifying transactions |
| 6 | `avg_days_between_txn` | FLOAT | — | Average days between transactions (NULL if <2 txns) |
| 7 | `total_amount_90d` | NUMERIC | 90 days | Sum of all transaction amounts |
| 8 | `avg_amount_90d` | NUMERIC | 90 days | Average transaction amount |
| 9 | `total_amount_180d` | NUMERIC | 180 days | Sum of all transaction amounts |
| 10 | `amount_growth_ratio` | FLOAT | 90d vs 180d | Growth ratio (90d amount / (180d - 90d) amount) |
| 11 | `distinct_channels_90d` | INT | 90 days | Count of unique channels used |
| 12 | `distinct_txn_types_90d` | INT | 90 days | Count of unique transaction types |
| 13 | `dominant_channel` | TEXT | 90 days | Most-used channel (window function, ties by recency) |
| 14 | `amount_stddev_90d` | NUMERIC | 90 days | Standard deviation of transaction amounts |
| 15 | `computed_at` | TIMESTAMPTZ | — | When the features were computed |

#### Phase 2 — Derived Features (7 features, minus 1 for duplicate count)
Computed in a second `UPDATE` pass on already-aggregated data. Runs after Phase 1.

| # | Feature | Type | Source | Description |
|---|---|---|---|---|
| 16 | `txn_count_365d` | INT | Subquery | Full year transaction count |
| 17 | `credit_sum_30d` | NUMERIC | Subquery | Total deposits last 30 days (WHERE type=CREDIT) |
| 18 | `debit_sum_30d` | NUMERIC | Subquery | Total spending last 30 days (WHERE type=DEBIT) |
| 19 | `credit_to_debit_ratio_90d` | FLOAT | Derived | credit_sum_30d / debit_sum_30d |
| 20 | `balance_trend_90d` | TEXT | Derived | 'RISING' / 'FALLING' / 'STABLE' — 30d vs 60-90d activity |
| 21 | `has_salary_credit` | BOOLEAN | Subquery | TRUE if 3+ monthly CREDIT deposits in 90 days |
| 22 | `monthly_income_estimate` | NUMERIC | Subquery | Average monthly CREDIT over 90 days |

Total: **21 unique features** (txn_count_* counted as distinct windows).

### 1.4 Database Table

```sql
customer_features (
    customer_id           TEXT NOT NULL,
    as_of_date            DATE NOT NULL,
    -- Phase 1
    days_since_last_txn   INT,
    days_since_first_txn  INT,
    txn_count_30d         INT,
    txn_count_90d         INT,
    txn_count_180d        INT,
    avg_days_between_txn  FLOAT,
    total_amount_90d      NUMERIC,
    avg_amount_90d        NUMERIC,
    total_amount_180d     NUMERIC,
    amount_growth_ratio   FLOAT,
    distinct_channels_90d INT,
    distinct_txn_types_90d INT,
    dominant_channel      TEXT,
    amount_stddev_90d     NUMERIC,
    computed_at           TIMESTAMPTZ DEFAULT NOW(),
    -- Phase 2
    txn_count_365d        INT,
    credit_sum_30d        NUMERIC,
    debit_sum_30d         NUMERIC,
    credit_to_debit_ratio_90d FLOAT,
    balance_trend_90d     TEXT,
    has_salary_credit     BOOLEAN,
    monthly_income_estimate NUMERIC,
    PRIMARY KEY (customer_id, as_of_date)
);
```

### 1.5 Key Design Decisions

| Decision | Rationale |
|---|---|
| **Point-in-time (`<= as_of_date`)** | Prevents data leakage in ML training. Every feature is computed as if we're standing at `as_of_date` with no future knowledge. |
| **Two-phase compute** | Phase 1 (heavy aggregation) runs once. Phase 2 (lightweight derived features) runs as UPDATEs on pre-aggregated data. |
| **`ON CONFLICT DO UPDATE`** | Re-running for the same date updates existing rows — idempotent. |
| **`dominant_channel` optimization** | Originally a correlated subquery (per-customer, slow). Optimized to `ROW_NUMBER() OVER (...)` window function. |
| **Sync psycopg2** | Matches the ETL pattern. No async overhead needed for batch computation. |
| **Separate service (port 8002)** | Can scale independently from the gateway. Accessed via API key auth planned for Phase 3. |

---

## 2. Data Provenance

```
raw_customers (etl_validation, 15,200 rows)
        │
        ▼  run_etl.py --source-table raw_customers
customers_clean (etl_clean, 15,200 rows)
        │
        │
raw_transactions / customer_transactions (etl_validation, 209K+ rows)
        │
        ▼  run_etl.py --source-table customer_transactions
customer_transactions_clean (etl_clean, 209K rows, 5,000 unique customers)
        │
        ▼  POST /features/compute-batch
customer_features (etl_clean, 5,000 rows per as_of_date)
```

---

## 3. Current Run Stats

| Metric | Value |
|---|---|
| Customers with transactions | 5,000 |
| Customers with features | 5,000 |
| Transactions processed | 209,000 |
| Phase 1 duration | ~230 seconds (3.8 min) |
| Phase 2 duration | TBD (after psycopg2 fix) |
| Rows per as_of_date | 5,000 |

---

## 4. What's Left

### Phase 3 — Customer Profile Features (2-3 hours)

Pull demographic/profile data from `raw_customers` / `customers_clean` and merge with transaction features.

| Feature | Source | Type |
|---|---|---|
| `age` | `raw_customers.date_of_birth` | INT |
| `tenure_months` | `raw_customers.activation_date` | INT |
| `customer_type` | `raw_customers.customer_type` | CATEGORICAL (Retail/SME/Premium/Corporate) |
| `gender` | `raw_customers.gender` | CATEGORICAL (M/F) |
| `onboarding_channel` | `raw_customers.onboarding_channel` | CATEGORICAL (Branch/App/USSD/Web/ATM/Agent) |
| `status` | `raw_customers.status` | CATEGORICAL (Active/Dormant/Closed/Suspended) |

Implementation: JOIN `customer_features` with `customers_clean` on `customer_id`, either as a Phase 3 UPDATE or a third SQL block. These are simple lookups — no aggregation needed.

### Phase 4 — Gateway Wiring (30 minutes)

Add proxy routes on `:8080` so the frontend can access features through the auth gateway:

```python
# gateway/routes/feature_routes.py
@router.get("/features/{customer_id}/latest")
async def get_customer_features(customer_id: str, user = Depends(get_current_user)):
    # Forward to feature service on :8002
```

### Phase 5 — Scheduler (1 hour)

Daily cron-style batch recomputation. Run Phase 1 + Phase 2 for `as_of_date = today()` every morning.

### Phase 6 — Feature Drift Monitoring (2 hours)

Track: null rate per feature, distribution shifts, freshness (days since last compute). Alerts when `days_since_last_txn` distribution shifts significantly.

### Phase 7 — Extended Domains (from design doc)

Per `docs/ml/feature-engineering-design-v1.md`:

| Group | Features | Priority |
|---|---|---|
| `loan_behaviour` | 6 features (active_loan_count, total_exposure, days_past_due, ...) | HIGH |
| `card_usage` | 5 features (card_txn_count_30d, utilization_pct, ...) | MEDIUM |
| `digital_engagement` | 8 features (mobile_logins_30d, ussd_sessions, has_app, ...) | MEDIUM |
| `relationship_depth` | 6 features (total_products, cross_sell_score, channel_diversity) | LOW |
| `behavioural_state` | 4 features (current_state, days_in_state, transition_probability) | Depends on Markov engine |
| `clv_drivers` | TBD (revenue_12m, margin_12m, predicted_clv) | Depends on prediction service |

These require additional source tables (`raw_loans`, `raw_cards`, etc.) not yet available in `etl_validation`.

---

## 5. Design Addition: Why Customer Profile Features Matter

The 6 features in Phase 3 aren't just demographic checkboxes — each one fundamentally changes how the model interprets transaction behavior.

### `age`

Banks segment customers by life stage because **needs and churn triggers are fundamentally different**:

| Age | Typical behavior | Churn risk |
|---|---|---|
| 18-25 | Student accounts, low balances, high digital usage | High — graduating, moving cities, first job elsewhere |
| 26-35 | Salary accounts, growing balances, taking loans (mortgage, car) | Medium — settling down, harder to switch |
| 36-50 | Peak earning, multiple products (loan + card + investment) | Low — deeply embedded, high switching cost |
| 51-65 | Pre-retirement, paying off debt, saving for retirement | Low — stable |
| 66+ | Pension accounts, reduced activity, branch-dependent | Medium — vulnerable to RM changes |

A 22-year-old with 500 days of inactivity is very different from a 55-year-old with 500 days. The model needs age to contextualize the behavior.

---

### `tenure_months`

**New customers churn differently than old ones:**

- **0-3 months:** Onboarding drop-off — signed up but never really started. 40%+ churn in some banks
- **3-12 months:** Still exploring — might leave for a competitor offering a better loan rate
- **1-3 years:** Stabilizing — has direct deposit, maybe a loan. Churn drops significantly
- **3+ years:** Embedded — multiple products, hard to leave. Churn driven by service failures, not price

Without tenure, the model flags a 2-month-old customer with 60 days of inactivity the same as an 8-year customer — but the 2-month customer is just warming up while the 8-year one is genuinely disengaging.

---

### `customer_type`

Each segment has **completely different churn dynamics:**

| Type | What drives them | How they leave |
|---|---|---|
| **Retail** | Convenience, fees, branch proximity | Walk into competitor branch, close account |
| **SME** | Loan terms, RM quality, cash management tools | Move entire business banking package |
| **Premium** | Personal service, investment products, lifestyle benefits | Private banker poaches them |
| **Corporate** | Credit facilities, treasury services, multi-country support | Formal RFP process — slow but total loss |

A Retail customer with $50 in fees might leave. An SME with the same fees doesn't care — they care about their $200K credit line being renewed. You can't treat them the same.

---

### `onboarding_channel`

**How a customer joined predicts how they'll behave and leave:**

| Channel | Profile | Risk |
|---|---|---|
| **Branch** | Older, relationship-driven, less digital | Low churn but high cost to serve |
| **App** | Young, tech-savvy, self-service | High — they'll switch to the app with better UX |
| **USSD** | Feature-phone users, rural, low-income | Medium — loyal if service is reliable |
| **Web** | Middle-income, research-oriented, compares banks | High — they're shopping around |
| **ATM** | Walk-in, convenience-driven | Medium |

If App-onboarded customers go dormant, the fix is digital (push notifications, in-app offers). If Branch-onboarded customers go dormant, the fix is human (RM call). Same symptom, different treatment.

---

### `gender`

Used for **demographic segmentation and product targeting** — not for individual decisions:

- Women's banking products (e.g., ABSA SHE account) have different churn patterns
- Joint account holders behave differently from individual account holders
- Regulatory reporting often requires gender-disaggregated metrics (financial inclusion KPIs)

The model doesn't discriminate by gender, but it must know if male and female customers respond differently to the same NBA (e.g., credit card offer vs. savings product offer).

---

### `status`

Captures whether the account is **Active, Dormant, Closed, or Suspended**. A customer flagged "Dormant" by the core banking system but still generating transactions needs a different response than one flagged "Active" with zero transactions. The source system's own classification is a powerful signal — when it disagrees with the computed features, that discrepancy itself is a churn indicator.

---

## 6. Known Issues

| # | Issue | Impact | Fix |
|---|---|---|---|
| 1 | `credit_to_debit_ratio_90d` references `debit_sum_30d` but should use 90d windows | Minor — ratio covers wrong window | Update SQL to use 90d subqueries |
| 2 | Phase 2 `balance_trend_90d` formula is a simplified heuristic, not a proper trend | Medium — acceptable for PoC | Replace with linear regression in Phase 6 |
| 3 | Phase 2 subqueries re-scan `customer_transactions_clean` per row | Performance — may be slow on large datasets | Add indexes on `(customer_id, transaction_date, transaction_type)` |
| 4 | No `customer_transactions_clean` index on `(customer_id, transaction_date)` | Phase 1 runs at 21 customers/sec | Add composite index for 10x speedup |
