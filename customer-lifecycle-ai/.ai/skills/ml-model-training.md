# Skill: Implementing an ML Model Training Pipeline

Applies to: `prediction-service/app/training/`

## Steps

1. **Create Data Loader** — `training/data_loader.py`
   - Query features from Feature Store (via repository, not raw SQL)
   - Handle train/validation/test split
   - Return structured dataset with feature matrix + labels

2. **Create Model Implementation** — `models/xgboost/churn_model.py` or `models/lightgbm/churn_model.py`
   - Implement `train()`, `predict()`, `save()`, `load()` methods
   - Accept hyperparameters as dict
   - Return model metadata (training date, metrics, feature list)

3. **Create Trainer** — `training/trainer.py`
   - Orchestrate: load data → train → evaluate → save
   - Log all metrics to model registry
   - Create challenger entry in `model-management-service`

4. **Create Evaluator** — `evaluation/evaluator.py`
   - Compute AUC-ROC, precision-recall, F1, calibration
   - Generate comparison report vs champion
   - Trigger champion/challenger promotion if thresholds met

5. **Add SHAP Explainability** — `explainability/shap/explainer.py`
   - Compute SHAP values for feature importance
   - Store explanations alongside predictions
   - Never skip — banking compliance requires this

## Rules

- Both XGBoost and LightGBM must be supported (configurable via `PREDICTION_MODEL_TYPE`)
- Models saved to `models/champion/` or `models/challenger/` based on status
- Every training run logged to `models/training_history/`
- Feature metadata stored in `models/feature_metadata/`
- Never hardcode hyperparameters — use config or hyperparameter search
