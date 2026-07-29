# Model Monitoring & Drift Detection

> **Script:** `scripts/model_monitor.py`  
> **Runs against:** `customer_states` + `customer_features` across dates  
> **Output:** Health distribution, state trends, feature completeness, PSI drift, alerts

---

## Quick Start

```bash
# Default: all 3 PoC dates
python scripts/model_monitor.py

# Specific dates
python scripts/model_monitor.py --dates 2026-07-17,2026-07-27
```

---

## Monitored Metrics

### 1. Health Score Distribution

```
Date            Min    P25 Median    P75    Max   Mean    Std
2026-07-27   17.5  36.7  38.9  41.8  62.4  39.5  6.2
```

Tracks the distribution of health scores across dates. A shift in mean or spread signals changing customer behavior or model drift.

**PSI (Population Stability Index):** Measures distribution shift vs the baseline date. 

| PSI Value | Label | Action |
|-----------|-------|--------|
| < 0.10 | STABLE | No action |
| 0.10 – 0.25 | MODERATE | Monitor |
| > 0.25 | SIGNIFICANT | Investigate |

**Current finding:** Health scores only available for 2026-07-27. Backfill `POST /predict/batch` for 07-17 and 07-22 to enable trend analysis.

### 2. Health Score Trend

```
Date          Count    Mean  Median Healthy%  AtRisk% Critical%
2026-07-27     4998    39.5    38.9     0.0%    37.6%     62.4%
```

Tracks the proportion of customers in each health category over time. A rising Critical% signals deteriorating portfolio health.

**Current finding:** 62.4% Critical, 37.6% At Risk, 0% Healthy — driven by stale data (missing frequency component) and uncalibrated probabilities.

### 3. State Distribution

```
Date           ACTIVE  AT_RISK  DORMANT  CHURNED
2026-07-17      2.7%   50.3%   41.3%    5.7%
2026-07-22      0.0%   49.5%   44.8%    5.8%
2026-07-27      0.0%   45.8%   48.4%    5.8%
```

Tracks the proportion of customers in each lifecycle state. The steady AT_RISK → DORMANT shift over 10 days is expected (aging data). Churn rate is stable at 5.7-5.8%.

### 4. Feature Completeness

```
Feature                               07-17   07-22   07-27     Trend
txn_count_90d                          0.0%    0.0%    0.0%  → STABLE
total_amount_90d                      38.2%   41.5%   44.8%   ↑ WORSE
amount_growth_ratio                   52.7%   55.3%   57.7%   ↑ WORSE
```

Tracks the percentage of NULL values per feature across dates. **↑ WORSE** means missing data is increasing — these features may become unusable if the trend continues.

**Current findings:**
- `total_amount_90d`: 38% → 45% missing — as the as_of_date moves forward, more customers fall outside the 90d window
- `amount_growth_ratio`: 53% → 58% missing — same root cause
- `credit_sum_30d`, `monthly_income_estimate`: 0% missing — Phase 2 fix working

### 5. Feature Drift (PSI)

```
Feature                                  PSI  Status
txn_count_90d                         3.0928  SIGNIFICANT ⚠
total_amount_90d                      1.9748  SIGNIFICANT ⚠
engagement_score                      0.1422  MODERATE ⚠
days_since_last_txn                   0.0243  STABLE
age_years                             0.0000  STABLE
```

Measures how much each feature's distribution has shifted from the baseline date. 

**Current findings:**
- `txn_count_90d` PSI=3.09 — expected. Same customers on different dates have different 90d windows, so transaction counts naturally shift
- `age_years` PSI=0.00 — correct. Age is static and should never drift
- `days_since_last_txn` PSI=0.02 — stable. The recency pattern is consistent across the portfolio

### 6. Health Score Distribution

```
2026-07-27: total=4998
  Critical (<40)    :  3118 ( 62.4%)
  At Risk (40-69)   :  1880 ( 37.6%)
  Healthy (70+)     :     0 (  0.0%)
```

Visual breakdown of health score categories.

### 7. Monitoring Summary

The script automatically generates alerts for:
- **HEALTH DRIFT:** PSI > 0.10 on health scores vs baseline
- **HEALTH DECLINE:** Mean health score dropping across dates
- **MISSING HEALTH:** >5% of predictions missing on latest date

---

## Drift Detection Methodology

### Population Stability Index (PSI)

```
PSI = Σ (Actual% - Expected%) × ln(Actual% / Expected%)
```

- Bins the feature distribution into 10 equal-width buckets
- Compares current distribution to baseline (first date)
- Symmetric — same value regardless of direction
- Handles zero bins by clipping to 0.0001

### Feature Completeness Trend

```
Trend = ↑ WORSE if latest missing% > earliest + 5%
      = ↓ BETTER if latest missing% < earliest - 5%
      = → STABLE otherwise
```

---

## Integration

The monitoring report should run:

| When | Purpose |
|------|---------|
| After each `POST /predict/batch` | Verify backfill succeeded |
| After feature engineering runs | Check feature completeness |
| Before stakeholder demos | Surface any drift concerns |
| Weekly (production) | Track long-term trends |

### Production Extension

For production, add:
- **Alert thresholds:** Auto-notify when PSI > 0.25 or missing% increases by >10%
- **Historical baseline:** Compare against a fixed "golden" baseline date, not just the first date
- **Churn probability monitoring:** Once `churn_prob` is stored in `customer_states`, track its distribution
- **SHAP value drift:** Track which features are driving predictions over time
