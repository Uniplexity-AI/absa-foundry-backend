# Feature Importance Analysis

> **Script:** `scripts/feature_importance.py`  
> **Runs against:** Trained XGBoost model (`models/champion/churn/xgboost_churn_v1.json`) + `models/registry.json`  
> **Output:** Ranked feature importance, category breakdown, leakage audit, key insights

---

## Quick Start

```bash
# Default: top 20 features
python scripts/feature_importance.py

# Top 10 only (for slides)
python scripts/feature_importance.py --top 10

# Different model
python scripts/feature_importance.py --model models/challenger/churn/xgboost_churn_v2.json
```

---

## Output Sections

### 1. Header

```
Model: churn_v1  |  AUC: 0.7672  |  Trained: 2026-07-29
Training features: 65  |  Leakage excluded: 9  |  Dead excluded: 6
```

Shows model identity, performance, and how many features were excluded for leakage (intentional) vs dead (auto-detected).

### 2. Ranked Table

```
Rank  Feature                             Importance    Cumul  Category
  1   behav_frequency_score                 0.0457    4.6%  Transaction Frequency
  2   eng_login_count_30d                   0.0410    8.7%  Digital Engagement
```

Features are ranked by XGBoost `feature_importances_` (gain-based). The Cumul column shows how much total importance is captured by the top N features.

**Interpretation:**
- Importance values are relative — they sum to 1.0 across all features
- A feature at 4.6% means it accounts for 4.6% of all decision splits
- No single feature dominating → healthy model
- If one feature were >20% → likely leakage or overfitting

### 3. Category Breakdown

```
Monetary Value       ██████████████████████████ 26.0%
Product Holdings     █████████████ 13.3%
Channel & Digital    ████████████ 11.9%
```

Groups features into business-facing categories. This answers "what kind of signal drives churn?" — useful for stakeholder presentations.

**Category definitions:**

| Category | What it captures |
|----------|-----------------|
| Monetary Value | Transaction amounts, averages, growth ratios |
| Product Holdings | Number of accounts, cards, loans, product types |
| Channel & Digital | ATM/mobile/branch usage, digital adoption |
| Transaction Frequency | Count of transactions in various windows |
| Temporal Patterns | Day-of-week, payday cycles |
| Customer Demographics | Age, tenure, first transaction date |
| Financial Health | Credit/debit totals, salary consistency, income |
| Risk Indicators | Volatility, reversals, high-value transactions |
| Digital Engagement | Login counts, session duration, platform preference |

### 4. Leakage Audit

```
Leakage Audit: 9 features excluded from training
  ✗ days_since_last_txn
  ✗ engagement_score
  ✗ rel_customer_status
  ...
✅ All 9 leakage features confirmed excluded.
```

Confirms that features which would cause target leakage are NOT present in the model. If any leakage feature appeared here, the model would have been trained with leaked information — the defensive cross-check in `ChurnPredictor.__init__()` prevents that at inference time, and this audit confirms it at training time.

### 5. Dead Features

```
Dead Features: 6 auto-excluded (ALL_ZERO or 100% NULL)
  ⚠ behav_txn_count_7d
  ⚠ temp_morning_activity_ratio_90d
  ...
```

Lists features that were auto-excluded by the pre-flight quality check because they were ALL_ZERO or 100% NULL across the training data. These don't pollute the model.

### 6. Key Insights

```
1. Strongest signal: Monetary Value (26.0%)
2. Top 3 features account for 12.2% of importance
3. 30 features capture 80% of total importance
4. AUC=0.767 is in the expected range for an honest model
```

Distilled takeaways for non-technical stakeholders.

---

## Integration

The feature importance is also logged during training (`scripts/train_models.py` step 5). This script provides a richer standalone report that can be run:

- **After each training run** — to document what changed
- **Before stakeholder demos** — to explain model behavior
- **When onboarding new data** — to verify importance hasn't shifted unexpectedly

---

## Expected Ranges

| Metric | Healthy Range | Warning Signal |
|--------|-------------|----------------|
| Top feature importance | 2-8% | >15% (single feature dominating) |
| Features to reach 80% | 20-40 | <10 (too few drivers) or >50 (noisy) |
| AUC | 0.65-0.85 | >0.90 (possible leakage) |
| Leakage features in model | 0 | Any (critical failure) |
