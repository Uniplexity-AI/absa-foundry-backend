# Churn Model — Performance Review & Actions

> **Date:** 2026-08-19
> **Model:** `churn_v1` (XGBoost + calibration)
> **Scope:** Review of the training run + implementation of the remediation actions.

---

## 1. Executive Summary

The model ranks well out-of-sample (holdout AUC **0.8117**) but shows **severe
temporal instability**: time-series cross-validation AUC is only **0.5504**,
and feature drift reaches **PSI 9.51** (`avg_days_between_txn`). Calibration is
excellent (Platt **ECE 0.0029**). Three remediation actions were implemented;
the remaining items are feature-engineering investigations and monitoring wiring.

| Dimension | Metric | Assessment |
|-----------|--------|------------|
| Discrimination | Holdout AUC = 0.8117 | Passes PoC target |
| Generalization | Train AUC 0.8552, gap 0.0435 | Controlled (under 0.05) |
| **Cross-validation** | **5-fold time-series OOF AUC = 0.5504** | ⚠️ Severe temporal gap vs holdout |
| Calibration | Platt ECE = 0.0029 | Production-ready |
| Operating point | Precision 0.114 @ threshold 0.5 | High false-positive rate |
| Drift | PSI 9.51 → **freeze_scoring = True** | Blocking |

---

## 2. Actions Implemented (this iteration)

### 2.1 Time-series cross-validation
`_calibrate_probabilities()` now uses `TimeSeriesSplit(5)` instead of random
`StratifiedKFold`. Because `cross_val_predict()` rejects `TimeSeriesSplit`, the
out-of-fold loop is done manually (`sklearn.base.clone(model)` per fold).

**Effect:** OOF CV AUC dropped from **0.6796 → 0.5504** — the honest temporal
estimate. This confirms the model does **not** generalise across the 5-day gap.

### 2.2 F1-optimal decision threshold
Added `_find_f1_optimal_threshold()` (threshold that maximises F1) alongside the
existing Youden's-J threshold.

| Threshold | Raw | Precision | Recall | F1 |
|-----------|-----|-----------|--------|-----|
| Youden's J | 0.4998 | 0.1143 | 0.8365 | 0.2012 |
| **F1-optimal** | **0.5683** | **0.3793** | **0.2928** | **0.3305** |

The F1-optimal point cuts false positives from **1,704 → 126** (at the cost of
recall 0.84 → 0.29) — the recommended operating point for high-cost retention.

### 2.3 Drift monitoring freeze flag
`_compute_drift()` now returns `freeze_scoring: bool` (true when any feature
`PSI > 0.25`). Current run: `max_psi = 9.5106` → **`freeze_scoring = True`**.

---

## 3. Critical Findings

### 3.1 Calibrator switched to Platt
With time-series OOF, Platt (ECE 0.0029) now beats isotonic (ECE 0.0246).
The registry points to `champion/churn/churn_calibrator_platt.joblib`
(`LogisticRegression`). The prediction service loads it correctly.

### 3.2 ⚠️ Threshold scale mismatch (must fix before pilot)
`ChurnPredictor.predict()` returns the **calibrated** probability, which now
lives in the **0.05–0.07** range (true churn rates), not 0.5–0.7.

| Raw score | Calibrated |
|-----------|------------|
| 0.4998 | 0.0568 |
| 0.5683 | 0.0588 |
| 0.8000 | 0.0664 |

`PRED_CHURN_THRESHOLD=0.5` was derived on **raw** scores. On calibrated outputs a
0.5 cutoff classifies **everyone as non-churner**. The threshold must be set on
the calibrated scale:

- ~**0.057** for the Youden point, or
- ~**0.059** for the F1-optimal point.

**Action:** update `PRED_CHURN_THRESHOLD` (or re-derive the classification on
calibrated probabilities) before go-live.

---

## 4. Remaining Recommendations (not yet implemented)

1. **Winsorization / quantile binning of drifting features**
   (`avg_days_between_txn`, `txn_count_90d`, `txn_count_180d`) — cap extreme
   values or bin into 5–10 ordinal buckets to stabilise PSI.
2. **Null-imputation audit** — verify how `NULL`/new-customer rows are imputed
   (0 vs −1 vs median) for `avg_days_between_txn`; the PSI 9.51 jump is not
   plausible from a genuine 5-day shift.
3. **Production drift alerting** — wire `diagnostics.drift.freeze_scoring` into a
   monitoring rule: any feature PSI > 0.25 → alert + pause automated scoring.
4. **Re-examine churn label** — the 0.55 time-series AUC vs 0.81 holdout gap
   suggests the account-closure label may be quasi-deterministic across the
   5-day window; consider a longer holdout gap or a behaviour-based label.

---

## 5. Artifacts

- Model: `models/champion/churn/xgboost_churn_v1.json`
- Calibrator: `models/champion/churn/churn_calibrator_platt.joblib`
- Report: `models/champion/churn/plots/training_report.pdf` (12 pages, plots embedded)
- Registry: `models/registry.json` (new `cv_auc`, `f1_optimal_threshold`,
  `classification_f1_threshold`, `drift.freeze_scoring`)
