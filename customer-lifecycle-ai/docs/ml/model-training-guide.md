# Model Training Guide — Churn Prediction

> **Service:** prediction-service
> **Training script:** `scripts/train_models.py`
> **Model output:** `models/champion/churn/xgboost_churn_v1.json`
> **Registry:** `models/registry.json`
> **Last updated:** 2026-08-19

---

## 1. Quick Start

```powershell
Set-Location "c:\path\to\customer-lifecycle-ai"
.\.venv\Scripts\python.exe scripts\train_models.py
```

What happens:
1. Loads features from `customer_features` (training dates)
2. Excludes leakage + dead features (including `id`, `computed_at` metadata)
3. Trains XGBoost with class weighting
4. Evaluates on a holdout date
5. Fits a probability calibrator (Platt + isotonic) out-of-fold
6. Saves the model + calibrator + generates plots + writes health/drift/hallucination metrics
7. Updates `models/registry.json`

---

## 2. Configuration — Where It Lives & What It Does

### 2.1 Shared config (`shared/config/settings.py`)

All training config is env-overridable via `.env` (pydantic-settings).

| Env var | Default | What it does |
|---------|---------|-------------|
| `TRAINING_DATES` | `2026-07-17,2026-07-22` | Comma-separated `as_of_date` values used for training |
| `TRAINING_HOLDOUT_DATE` | `2026-07-27` | Holdout `as_of_date` for evaluation |
| `LABEL_CHURN_COLUMN` | `rel_customer_status` | Column that defines churn |
| `LABEL_CHURN_POSITIVE_VALUE` | `Closed` | Value meaning "churned" (→ label 1) |
| `TABLE_CUSTOMER_FEATURES` | `customer_features` | Feature table name |
| `COL_CUSTOMER_ID` / `COL_AS_OF_DATE` | `customer_id` / `as_of_date` | Identifier columns (excluded from training) |

> These let you retrain on real ABSA data **without code changes** — point the
> table/column names at the real schema and set new training dates.

### 2.2 Leakage guard (`scripts/train_models.py`, `_get_leakage_features`)

Features that encode recency/target information are auto-excluded from
training to prevent data leakage. The label column is added dynamically.

### 2.3 Dead-feature scan (automatic)

Before training, the script scans all numeric columns and auto-excludes any
that are `ALL_ZERO` or 100% NULL — these carry no signal.

### 2.4 Hyperparameters (edit in `train_churn_model()`, `XGBClassifier(...)`)

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `max_depth` | 4 | Tree depth — lower = less overfit |
| `learning_rate` | 0.05 | Step size |
| `n_estimators` | 50 | Number of trees |
| `min_child_weight` | 2 | Min leaf weight — higher = more regularized |
| `reg_lambda` | 1.0 | L2 regularization on leaf weights |
| `subsample` | 0.8 | Row sampling per tree |
| `colsample_bytree` | 0.8 | Column sampling per tree (reduces overfit) |
| `scale_pos_weight` | auto | Class-imbalance balancing |

---

## 3. Outputs

### 3.1 Model artifacts

| Path | Content |
|------|---------|
| `models/champion/churn/xgboost_churn_v1.json` | Trained XGBoost model |
| `models/champion/churn/churn_calibrator_isotonic.joblib` | Fitted probability calibrator |
| `models/registry.json` | Model metadata, metrics, calibration, training features |

### 3.2 Plots (saved to `models/champion/churn/plots/`)

| File | What it shows |
|------|---------------|
| `roc_curve.png` | ROC curve with AUC |
| `calibration.png` | Reliability diagram (raw predicted vs actual) |
| `calibration_comparison.png` | Raw vs Platt vs Isotonic reliability curves |
| `feature_importance.png` | Top-10 feature importances |

### 3.3 Metrics written to `registry.json`

```json
"metrics": {
  "auc": 0.8117,
  "brier": 0.2115,
  "ece": 0.2724,
  "log_loss": 0.6128
}
```

The `calibrator` field carries the post-calibration comparison:

```json
"calibrator": {
  "method": "isotonic",
  "ece_raw": 0.4038,
  "ece_platt": 0.0228,
  "ece_isotonic": 0.0172,
  "ece_after": 0.0172,
  "brier_after": ...,
  "log_loss_after": ...
}
```

---

## 4. Health, Drift & Hallucination Diagnostics

The training script now computes three diagnostic groups, stored under
`diagnostics` in `registry.json`:

### 4.1 Health (`diagnostics.health`)

| Field | Meaning | Red flag |
|-------|---------|----------|
| `model_health.overfit_gap` | train AUC − test AUC | > 0.03 = overfitting |
| `model_health.overfit_flag` | bool | `true` → reduce `max_depth`/`n_estimators` |
| `data_health.test_missing_ratio` | fraction of NaN in holdout | > 0.05 = data problem |
| `data_health.test_samples` | holdout size | too small → unreliable metrics |

### 4.2 Drift (`diagnostics.drift`)

Population Stability Index (PSI) between training and holdout feature
distributions. Interpretation:

| PSI | Level | Action |
|-----|-------|--------|
| < 0.10 | low | OK |
| 0.10 – 0.25 | moderate | Investigate feature drift |
| > 0.25 | high | Retrain / review features |

`top_drifted_features` lists the 10 most-drifted features.

### 4.3 Hallucination (`diagnostics.hallucination`)

`overconfidence_ratio` = fraction of high-confidence (≥ 0.9) predictions that
are wrong. This proxies "model hallucination" — being confidently incorrect.

| Ratio | Meaning |
|-------|---------|
| 0.00 – 0.10 | healthy |
| 0.10 – 0.30 | needs calibration |
| > 0.30 | model is overconfident — investigate |

---

## 5. Probability Calibration

The XGBoost model has strong ranking (AUC 0.81) but raw probabilities are
uncalibrated (weighted ECE ~0.40). The training script now fits a calibrator
and the prediction service applies it at inference time.

### 5.1 How it works (leakage-free)

1. Train the base XGBoost model on training dates
2. Generate **out-of-fold** predictions on the training set via
   `StratifiedKFold(5) + cross_val_predict` (the calibrator fitting data)
3. Fit two calibrators:
   - **Platt scaling** — `LogisticRegression(C=999999)` on OOF probabilities
   - **Isotonic regression** — `IsotonicRegression(out_of_bounds="clip")`
4. Apply both to the holdout set, compute ECE with the weighted formula
5. Save the calibrator with the **lowest holdout ECE**

### 5.2 Method selection

| | Platt | Isotonic |
|--|-------|----------|
| Parametric | Monotonic sigmoid | Non-parametric step function |
| Dataset size | Small (<1k) | Large (>1k) |
| Overfit risk | Low | Higher on sparse data |

Our calibration set (~10k OOF samples) favours isotonic.

### 5.3 Results (current model)

| Method | ECE |
|--------|-----|
| Uncalibrated | 0.4038 |
| Platt | 0.0228 |
| **Isotonic** ✅ | **0.0172** |

### 5.4 Inference wiring

The prediction service (`app/models/churn_predictor.py`) loads the
calibrator from the registry and applies it via `_apply_calibrator()`,
which handles both `LogisticRegression` (`predict_proba`) and
`IsotonicRegression` (`predict`). `churn_probability` is now a calibrated
probability, not a raw ranking score.

---

## 6. How to Tune

| Goal | Change |
|------|--------|
| Improve AUC | Increase `max_depth` (4→5), `n_estimators` (50→100), but watch overfit gap |
| Reduce overfitting | Lower `max_depth`, raise `min_child_weight`/`reg_lambda`, reduce `colsample_bytree` |
| Fix class imbalance | `scale_pos_weight` is auto-computed; adjust manually if needed |
| Fix drift | Revisit training dates — ensure training window represents recent data |
| Fix overconfidence | Calibration is now automatic — check `calibrator.ece_after` |

**Workflow:**
1. Run training → check `diagnostics`
2. If `overfit_flag` → reduce complexity → re-run
3. If `drift_level` is high → update `TRAINING_DATES` → re-run
4. Compare `metrics.auc` against the ≥ 0.80 target
5. Verify `calibrator.ece_after` < 0.05 (calibrated)

---

## 7. Related Scripts

| Script | Purpose |
|--------|---------|
| `scripts/feature_importance.py` | Standalone feature importance report (top-N) |
| `services/decision-intelligence-service/scripts/train_ranking_model.py` | LightGBM NBA ranking model (Phase 2) |

---

## 8. Feature Config Reference

Feature computation is separate from model training. See
[`docs/ml/feature-catalog.md`](./feature-catalog.md) for the 21 features and
their env toggles (`FE_ENABLE_PHASE2_DERIVED`, `FE_ENABLE_PHASE2B_RATIO`).
