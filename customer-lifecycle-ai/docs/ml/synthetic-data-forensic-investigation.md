# Synthetic Churn Model — Forensic Investigation Report

> **Date:** 2026-08-19
> **Model:** `churn_v1` (XGBoost + Platt calibration)
> **Question:** Are the current weaknesses (PSI 9.51, temporal OOF AUC 0.55, low
> precision) caused by the **synthetic data** or the **model**?
> **Method:** Code inspection + direct database queries against the synthetic
> feature store (`customer_features`, `customer_transactions_clean`).

---

## 1. Executive Summary

**The model and the ML pipeline are functioning correctly. The weaknesses are
caused by the synthetic data — specifically, the churn label is static and
behaviourally meaningless, and the training snapshots were computed from
inconsistent transaction generations.**

Three independent lines of evidence converge on this:

1. **The churn label is 100% static and behaviourally random.** The same 263
   customers are labelled `Closed` in every snapshot; their transaction, balance
   and engagement behaviour is statistically identical to `Active` customers.
2. **The 07-17 training snapshot is stale** — it was computed from a different
   (older, sparser) transaction generation than 07-22/07-27. This is the source
   of the PSI 9.51 "drift".
3. **The holdout is not out-of-sample at the customer level.** The identical
   4,998 customers (with identical static labels) appear in train and holdout, so
   the 0.81 holdout AUC is memorisation, not churn prediction. Time-series CV
   correctly exposes this (OOF AUC 0.55 ≈ random).

**Root-cause classification: `MULTIPLE PROBLEMS`** — primary: **LABEL GENERATION
PROBLEM** + **DATASET/SNAPSHOT-CONSTRUCTION PROBLEM**; secondary:
**VALIDATION METHODOLOGY PROBLEM**; minor: **PSI-magnitude artefact**.

---

## 2. Current Model Performance (baseline for reference)

| Metric | Value |
|--------|-------|
| Training samples / positives | 9,996 / 526 (5.26%) |
| Holdout samples / positives | 4,998 / 263 (5.26%) |
| Train AUC | 0.8552 |
| Holdout AUC | 0.8117 |
| 5-fold temporal OOF AUC | **0.5504** |
| Train/test gap | 0.0435 |
| Raw ECE / Brier / LogLoss | 0.4038 / 0.2115 / 0.6128 |
| Platt ECE (calibrated) | 0.0029 |
| Precision / Recall / F1 @ 0.5 | 0.1143 / 0.8365 / 0.2012 |

---

## 3. Dataset Investigation — Synthetic Data Generation

Inspected `scripts/generate_synthetic_feature_store_data.py` and the live DB.

### 3.1 Customer population

| Attribute | How it is generated |
|-----------|---------------------|
| Customers | 5,000, ids `CUST00001…CUST05000` |
| Date of birth | uniform 18–80 years old |
| Gender | `M`/`F`, 50/50 |
| Branch | random `BR001…BR025` |
| Tenure | `customer_since_date` = 30 days – 15 years before reference date |
| KYC tier | TIER_1/2/3 (55/35/10%) |
| Nationality | mostly ZM (62%) |

### 3.2 Transactions

| Attribute | How it is generated |
|-----------|---------------------|
| Count | 20–120 per customer |
| Dates | offsets from a single reference date (code says 0–180 days) |
| Amount | log-normal(4.2, 1.1), capped at 50,000 |
| Type | DEBIT 72% / CREDIT 28% |
| Channels | 6 channels, 2–4 "habitual" per customer |

### 3.3 ⚠️ Discrepancy between code and live data

The **code** generates a 0–180 day transaction window. The **live table** shows
`customer_transactions_clean` spanning **2024-01-01 … 2035-01-01** (~11 years),
with ~8,900 uniform transactions/month from 2024-01 to 2026-05, a partial
2026-06, and **42 future-dated rows in 2035-01**. The live data was therefore
produced by an **older/different generation process** than the current script —
the data in the DB is not what the current generator produces.

> **Confirmed synthetic-data limitation:** future-dated transactions (up to
> 2035) and a generation process that no longer matches the code.

---

## 4. Temporal Analysis — Why the "drift"

### 4.1 Snapshot overview

| Date | Rows | Churned | Distinct customers |
|------|------|---------|--------------------|
| 2026-07-17 | 4,998 | 263 (5.3%) | 4,998 |
| 2026-07-22 | 4,998 | 263 (5.3%) | 4,998 |
| 2026-07-27 | 4,998 | 263 (5.3%) | 4,998 |

### 4.2 Feature distributions per snapshot

| Feature | 07-17 | 07-22 | 07-27 |
|---------|-------|-------|-------|
| `avg_days_between_txn` mean | **72.89** | 23.02 | 23.15 |
| `avg_days_between_txn` std | 22.84 | 6.78 | 6.82 |
| `txn_count_90d` mean | **0.97** | 2.66 | 2.42 |
| `txn_count_180d` mean | **2.38** | 6.91 | 6.68 |
| `total_amount_90d` mean | **78,789** | 228,584 | 220,030 |
| `days_since_first_txn` mean | 863.5 | 868.5 | 873.5 |

**The 07-17 snapshot is on a completely different scale from 07-22/07-27.**
07-22 and 07-27 are nearly identical. This is not gradual drift — it is a
**step discontinuity** between two data generations.

### 4.3 Why the discontinuity occurs

The transaction table contains **zero transactions between 07-17 and 07-27**
(`txns ≤ 07-17` = `txns ≤ 07-22` = `txns ≤ 07-27` = 263,718). The three snapshots
are therefore *not* three views of a growing transaction history — the 07-17
snapshot was computed against a **different, sparser transaction generation**
(~12.8 txns/customer) than 07-22/07-27 (~38.7 txns/customer).

`avg_days_between_txn` is defined in `repository.py` as:

```
(as_of_date - MIN(transaction_date)) / (COUNT(*) - 1)
```

With `MIN` fixed (~863 days before the snapshots) but `COUNT` nearly tripling
between generations, the metric jumps from ~72.9 to ~23.0.

> **Confirmed bug (snapshot construction):** the 07-17 snapshot was not
> recomputed against the current transaction data, so training mixes two
> incompatible data generations.

---

## 5. PSI = 9.51 Investigation

### 5.1 Distribution of `avg_days_between_txn`

| Percentile | Train (07-17+22) | Holdout (07-27) |
|-----------|------------------|-----------------|
| P1 | 14.43 | 14.12 |
| P5 | 15.66 | 15.20 |
| P25 | 21.20 | 17.51 |
| P50 | **40.37** | **21.32** |
| P75 | **66.46** | **27.66** |
| P95 | **109.50** | **36.53** |
| P99 | **128.43** | **40.17** |

The train distribution is **bimodal** (a 07-17 mode at ~66–110 days mixed with a
07-22 mode at ~21 days); the holdout has only the ~21-day mode.

### 5.2 Manual PSI verification

| Feature | Reported PSI | Replicated PSI | Clean (shared-bin) PSI |
|---------|--------------|----------------|------------------------|
| `avg_days_between_txn` | 9.5106 | **9.5106 ✓** | 0.0519 |
| `txn_count_90d` | 5.8184 | **5.8184 ✓** | 0.0397 |
| `txn_count_180d` | 4.7813 | **4.7813 ✓** | 0.2171 |

### 5.3 Verdict on the PSI implementation

- The implementation **faithfully reproduces** the reported values — it is not
  "wrong" in a computational sense.
- **However**, it uses `eps = 1e-6` on *empty* bins. When a bin is populated in
  one distribution but empty in the other, the `(p_test − p_train)·ln(p_test/p_train)`
  term explodes. The **clean** PSI (using only bins shared by both distributions)
  is **0.05**, not 9.51 — a ~180× inflation.

> **Finding:** the PSI magnitude (9.51) is an **artefact of the eps-in-empty-bin
> treatment** on top of a **real** distribution shift caused by the stale 07-17
> snapshot. Both should be addressed: fix the snapshot, and switch the production
> PSI to shared-bin (or capped) calculation.

---

## 6. Label Generation Investigation — CRITICAL

The churn label is `rel_customer_status = 'Closed'` (configurable). Findings:

1. **100% static.** Every customer has the same label in all three snapshots:
   4,735 "never churned", 263 "always churned", 0 customers change.
2. **Behaviourally meaningless.** Churned vs Active customers are statistically
   identical on every feature:

| Feature (07-27) | Active | Closed | Dormant |
|-----------------|--------|--------|---------|
| days_since_last_txn | 101.9 | 107.6 | 99.5 |
| txn_count_90d | 2.4 | 2.2 | 2.4 |
| txn_count_180d | 6.7 | 6.4 | 6.8 |
| engagement_score | 13.8 | 12.8 | 14.2 |
| total_amount_90d | 220,113 | 212,656 | 222,150 |
| tenure_days | 906.6 | 930.4 | 913.7 |
| age_years | 38.4 | 37.9 | 39.6 |
| products_owned | 1.47 | 1.51 | 1.46 |

3. **Root cause:** the synthetic generator's `customers()` method has **no status
   field and no churn logic**. `status` is injected by a separate path (ETL from
   `raw_customers`) and is **independent of the transaction/engagement generation**.
   Churn is therefore **randomly assigned**, not behaviourally driven.

> **Confirmed bug (label generation):** churn is randomly assigned and uncorrelated
> with behaviour. The model *cannot* learn a meaningful churn pattern because none
> exists in the data.

---

## 7. Feature Leakage Investigation

The leakage exclusion list (`LEAKAGE_FEATURES`) correctly removes the label
(`rel_customer_status`) and recency/activity features used in the churn
definition. Review of the 64 training features found:

- All feature SQL enforces `transaction_date <= as_of_date` (point-in-time
  correct) — **no post-churn or future transaction leakage**.
- No feature is derived from the label or account-closure status.

> **Finding:** the leakage guard is sound. The 0.81 holdout AUC is **not** classic
> feature leakage — it is customer-memorisation (see §8).

---

## 8. OOF Validation Investigation — why 0.55 vs 0.81

The `TimeSeriesSplit(5)` implementation is **correct**: it folds manually
(`sklearn.base.clone`), past→train / future→validate. The low OOF AUC is genuine.

**Explanation of the 0.81 vs 0.55 gap:**

- The holdout (07-27) contains the **same 4,998 customers** as training (07-22),
  with the **same static labels**. The model memorises "these specific customers
  are churned" and transfers it to 07-27 → inflated 0.81.
- `TimeSeriesSplit` splits on row index. Its validation folds contain customers
  whose features came from the **stale 07-17 generation**, which the model has
  no way to reconcile with the fresh 07-22 features → honest ≈0.55 (random).

> **Confirmed validation problem:** the holdout is not out-of-sample at the
> customer level. A valid evaluation must use **disjoint customer populations**
> across train/holdout (or true temporal separation with fresh data).

---

## 9. Synthetic Data Realism Assessment

| Relationship | Status |
|--------------|--------|
| Frequency ↔ amount | ✅ plausible (log-normal) |
| Frequency ↔ engagement | ⚠️ independent random streams |
| Tenure ↔ products | ⚠️ independent random streams |
| **Inactivity ↔ churn** | ❌ **no relationship — churn is random** |
| Product usage ↔ churn | ❌ no relationship |
| **Temporal realism** | ❌ uniform 30-month spread, no recent-activity pattern |
| **Future-dated rows** | ❌ 42 rows dated 2035-01-01 |

**Conclusion:** the synthetic data is structurally plausible but contains **no
causal churn signal** and **no meaningful temporal structure** in the training
window.

---

## 10. Controlled Experiments — status

- **Multi-seed (5 seeds):** **not run** — unnecessary. The root cause (random
  static labels) means any seed would reproduce ≈0.5–0.55 temporal OOF. Seed
  variance is not the issue.
- **Controlled churn experiment:** **recommended, not run.** Building a synthetic
  dataset where churn is *caused by* falling frequency/engagement/inactivity, then
  training XGBoost, is the correct way to prove the pipeline learns when signal
  exists. This is a **synthetic-data improvement**, not a model change.

---

## 11. Root-Cause Classification

```
MULTIPLE PROBLEMS
├── PRIMARY 1 — LABEL GENERATION PROBLEM
│     Churn is randomly assigned & static → no learnable signal.
├── PRIMARY 2 — DATASET / SNAPSHOT-CONSTRUCTION PROBLEM
│     07-17 snapshot stale (different transaction generation) → spurious drift.
├── SECONDARY — VALIDATION METHODOLOGY PROBLEM
│     Holdout shares customers with train → memorisation inflates AUC.
└── MINOR — PSI-magnitude artefact
      eps-in-empty-bin inflates PSI ~180× (9.51 vs 0.05 shared-bin).
```

**Not problems:** the XGBoost model, the feature-engineering point-in-time logic,
and the leakage guard all work correctly.

---

## 12. Recommendations (prioritised)

### BUG FIXES (before trusting any synthetic metric)

1. **Recompute all snapshots against one consistent transaction generation.**
   Regenerate transactions once, then compute 07-17/22/27 features from that same
   table.
2. **Make the holdout out-of-sample by customer.** Split customers into disjoint
   train/holdout populations (or use genuinely fresh temporal data), so
   memorisation cannot inflate AUC.
3. **Fix PSI to shared-bin (or capped) calculation** so drift magnitude is
   interpretable.

### SYNTHETIC DATA IMPROVEMENTS (to make the synthetic stage meaningful)

4. **Make churn behaviourally driven.** Assign `Closed` probability as a function
   of declining frequency, rising inactivity, falling engagement and product
   usage — with a clear causal structure.
5. **Regenerate a realistic temporal window** (e.g. transactions concentrated
   near the snapshot dates, no future-dated rows).

### VALIDATION IMPROVEMENTS

6. **Keep time-series CV** (it correctly exposed the problem) and add a
   **group-by-customer** split to prevent entity leakage.

### MODEL IMPROVEMENTS — deferred

7. Do **not** tune the model yet. The performance numbers are not meaningful
   until the data/label/validation issues are fixed. Re-run the model comparison
   (n_estimators, max_depth, regularisation) only on corrected data.

---

## 13. ABSA Pilot Readiness Assessment

> **Verdict: `READY WITH CONDITIONS`**

The **pipeline** (feature engineering, leakage control, training, calibration,
model registry, prediction service, drift detection, threshold methodology) is
**functioning correctly** and is fit to receive real data. The synthetic stage
has done its job of validating this machinery.

However, **no predictive-performance conclusion can be drawn from the synthetic
numbers** (AUC 0.81 is memorisation; the true signal is ~random). Before relying
on *any* synthetic metric, fix the three bug classes above. Real ABSA data —
with genuine, behaviourally-correlated churn labels and real temporal structure —
should establish the actual predictive performance.

**Answer to "modify synthetic data, model, validation, or proceed to real data?":**
fix the synthetic **label + snapshot construction**, fix the **validation split**,
then proceed to real ABSA data. Do **not** invest further in model tuning against
synthetic data.
