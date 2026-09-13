# Churn Model Training Report

- **Trained at:** 2026-09-11
- **Training dates:** 2026-07-17, 2026-07-22
- **Holdout date:** 2026-07-27
- **Features:** 57 training (9 leakage excluded, 14 dead excluded)

## Data

- Training samples: 8000 (370 positive)
- Holdout samples: 1000 (58 positive)

## Metrics (raw probabilities)

| Metric | Value |
|--------|-------|
| AUC | 1.0 |
| 5-fold OOF CV AUC | 0.9999992915589246 |
| Brier | 0.0016 |
| LogLoss (test) | 0.0414 |
| LogLoss (train) | 0.0418 |
| Accuracy (optimal threshold) | 1.0 |
| ECE (raw) | 0.0407 |
| Optimal threshold (Youden's J) | 0.9509361386299133 |

## Classification (optimal threshold)

- Precision: 1.0
- Recall: 1.0
- F1: 1.0

| | Predicted 0 | Predicted 1 |
|---|---|---|
| Actual 0 | 942 | 0 |
| Actual 1 | 0 | 58 |

## Calibration

- Method: isotonic
- ECE raw: 0.0406
- ECE Platt: 0.0002
- ECE isotonic: 0.0
- ECE after: 0.0
- Brier after: 0.0
- LogLoss after: 0.0

## Diagnostics

- Overfit gap: 0.0 (flag=False)
- Drift max PSI: 2.4761 (high)
- Overconfidence ratio: 0.0

## Top features

1. `txn_count_30d` — 0.40470001101493835
2. `behav_frequency_score` — 0.3075999915599823
3. `behav_active_days_90d` — 0.24400000274181366
4. `amount_growth_ratio` — 0.03629999980330467
5. `txn_count_90d` — 0.0032999999821186066
6. `behav_txn_count_7d` — 0.003000000026077032
7. `avg_days_between_txn` — 0.000699999975040555
8. `txn_count_180d` — 0.00039999998989515007
9. `total_amount_180d` — 0.0
10. `fin_income_growth` — 0.0

## Plots

- `roc_curve.png` (roc_curve)
- `calibration.png` (calibration)
- `feature_importance.png` (feature_importance)
- `learning_curve.png` (learning_curve)
- `loss_curve.png` (loss_curve)
- `accuracy_threshold.png` (accuracy_threshold)
- `confusion_matrix.png` (confusion_matrix)
- `prediction_distribution.png` (prediction_distribution)
- `threshold_analysis.png` (threshold_analysis)
- `calibration_comparison.png` (calibration_comparison)

## Hyperparameters

- `max_depth` = 4
- `learning_rate` = 0.05
- `n_estimators` = 50
- `min_child_weight` = 2
- `reg_lambda` = 1.0
- `subsample` = 0.8
- `colsample_bytree` = 0.8
- `scale_pos_weight` = 20.62162162162162

