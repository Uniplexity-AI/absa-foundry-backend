# Churn Model Training Report

- **Trained at:** 2026-08-19
- **Training dates:** 2026-07-17, 2026-07-22
- **Holdout date:** 2026-07-27
- **Features:** 64 training (9 leakage excluded, 5 dead excluded)

## Data

- Training samples: 7996 (406 positive)
- Holdout samples: 1000 (60 positive)

## Metrics (raw probabilities)

| Metric | Value |
|--------|-------|
| AUC | 0.4737 |
| 5-fold OOF CV AUC | 0.4622735710067044 |
| Brier | 0.2125 |
| LogLoss (test) | 0.614 |
| LogLoss (train) | 0.5819 |
| Accuracy (optimal threshold) | 0.9 |
| ECE (raw) | 0.3437 |
| Optimal threshold (Youden's J) | 0.5585224032402039 |

## Classification (optimal threshold)

- Precision: 0.1154
- Recall: 0.1
- F1: 0.1071

| | Predicted 0 | Predicted 1 |
|---|---|---|
| Actual 0 | 894 | 46 |
| Actual 1 | 54 | 6 |

## Calibration

- Method: isotonic
- ECE raw: 0.3799
- ECE Platt: 0.0101
- ECE isotonic: 0.0095
- ECE after: 0.0095
- Brier after: 0.0565
- LogLoss after: 0.2279

## Diagnostics

- Overfit gap: 0.4177 (flag=True)
- Drift max PSI: 0.3515 (high)
- Overconfidence ratio: 0.0

## Top features

1. `distinct_channels_90d` — 0.034699998795986176
2. `risk_high_value_txn_ratio_90d` — 0.03139999881386757
3. `temp_payday_activity_ratio_90d` — 0.03060000017285347
4. `fin_median_txn_amount_90d` — 0.029899999499320984
5. `behav_frequency_score` — 0.02930000051856041
6. `amount_stddev_90d` — 0.02889999933540821
7. `risk_txn_volatility_90d` — 0.02850000001490116
8. `debit_sum_30d` — 0.02669999934732914
9. `eng_login_count_7d` — 0.026499999687075615
10. `temp_weekday_txn_ratio_90d` — 0.02590000070631504

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
- `scale_pos_weight` = 18.694581280788178

