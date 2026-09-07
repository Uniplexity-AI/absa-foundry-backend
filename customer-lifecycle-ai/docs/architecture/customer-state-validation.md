# Customer State Validation

> **Script:** `scripts/validate_states.py`  
> **Runs against:** `customer_states` + `customer_features` in `etl_clean`  
> **Output:** State distribution, activity checks, transitions, anomalies, verdict

---

## Quick Start

```bash
python scripts/validate_states.py
```

Runs against `2026-07-27` by default. The report covers all 3 PoC dates for state distribution and transitions.

---

## Output Sections

### 1. State Distribution

```
2026-07-17: ACTIVE: 135 (3%), AT_RISK: 2512 (50%), CHURNED: 287 (6%), DORMANT: 2064 (41%)
2026-07-22: AT_RISK: 2472 (49%), CHURNED: 288 (6%), DORMANT: 2238 (45%)
2026-07-27: AT_RISK: 2291 (46%), CHURNED: 290 (6%), DORMANT: 2417 (48%)
```

Shows how many customers are in each state across dates. The steady shift AT_RISK → DORMANT is expected — as the as_of_date moves forward, more customers pass the 90-day inactivity threshold.

### 2. High-Value Customer Check

Validates that high-value customers (>R500K) are classified correctly. In the current data, 149 high-value customers are AT_RISK and 7 are CHURNED — none are misclassified as ACTIVE (which would be suspicious).

### 3. Activity Checks by State

For each state, validates that transaction activity matches expectations:

| State | Expected | Actual | Verdict |
|-------|----------|--------|---------|
| DORMANT | Zero or very low transactions | 86% zero txns, 14% 1-3 txns | ✅ |
| AT_RISK | Moderate activity | avg 4.6 txns, 56d since last | ✅ |
| ACTIVE | Frequent recent transactions | **0 customers** | ⚠ Stale data |
| CHURNED | Account closed or 365d+ inactive | 290 total | ✅ |

**No ACTIVE customers** — this is a data artifact, not an engine bug. The synthetic transaction data ends 2026-06-19, which is 38 days before the as_of_date. Since ACTIVE requires <30 days since last transaction, no customer qualifies. With real data that has continuous transactions, the ACTIVE population would be substantial.

### 4. State Transitions

```
AT_RISK = AT_RISK    2291  (stable)
AT_RISK ↓ DORMANT     181  (deteriorating)
DORMANT = DORMANT    2236  (stable)
DORMANT ↓ CHURNED       2  (deteriorating)
CHURNED = CHURNED     288  (stable)
```

Shows how customers moved between states from the previous date. The = symbol means stayed in same state, ↓ means deteriorated (worse state), ↑ means improved. Churn is absorbing — once CHURNED, always CHURNED.

### 5. Health Score by State

```
AT_RISK   : avg_health= 41.2
DORMANT   : avg_health= 38.3
CHURNED   : avg_health= 36.5
```

Validates that the health score gradient is correct: AT_RISK > DORMANT > CHURNED. This confirms the health score formula produces sensible ordering.

### 6. Anomaly Detection

| Check | Finding |
|-------|---------|
| DORMANT with >5 txns | 5 customers (0.2%) — minor boundary cases |
| ACTIVE with zero txns | 0 — correct |
| CHURNED non-Closed | 27 customers — behavioral churn (365d+ inactive, account still open) |

### 7. Boundary Validation

```
AT_RISK within 10 days of DORMANT (80-89d):   17 customers
DORMANT just past threshold (90-100d):        338 customers
```

Shows customers near classification boundaries. 338 customers just crossed into DORMANT — this is the group most likely to be recoverable with intervention.

### 8. Validation Verdict

```
✓ DORMANT with >5 txns < 2%: 0.2%
✓ CHURNED: Closed + behavioral: 263 Closed + 27 behavioral (>365d)
✓ Health: AT_RISK > DORMANT > CHURNED: 41.2 > 38.3 > 36.5
3/3 checks passed
✅ State engine is classifying correctly.
```

---

## Classification Rules

The state engine uses 4-priority rules (see `customer-state-service.md` §3):

| Priority | Rule | State |
|----------|------|-------|
| 1 | `rel_customer_status == "Closed"` | **CHURNED** |
| 2 | `days_since_last_txn > 365` | **CHURNED** (behavioral) |
| 3 | `days_since_last_txn > 90` | **DORMANT** |
| 4 | `days_since_last_txn > 30` | **AT_RISK** |
| — | Otherwise | **ACTIVE** |

---

## Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| Stale data (38-day gap) | No ACTIVE customers | Will resolve with real-time transaction data |
| 5 DORMANT with >5 txns | Minor boundary misclassification | Acceptable (0.2% error rate) |
| Boundary sensitivity | 17 customers within 10 days of threshold flip | Expected — real data will have smoother distribution |
| Single classification dimension | State based only on recency | Production should add engagement + value dimensions |

---

## When to Run

- After every feature engineering pipeline run
- After state engine configuration changes
- Before stakeholder demos
- When investigating unexpected health scores
