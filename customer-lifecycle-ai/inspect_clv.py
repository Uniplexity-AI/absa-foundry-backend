import joblib, numpy as np

model = joblib.load("models/customer-lifetime-value-prediction/lightgbm_clv_model.pkl")
print("Model type:", type(model).__name__)
print("Feature count:", len(model.feature_name_))
print("Feature names:", model.feature_name_[:20])

# Check model's training target stats if available
booster = getattr(model, "booster_", None)
if booster:
    params = booster.dump_model()
    print("Objective:", params.get("objective"))
    print("Num trees:", params.get("num_tree_per_iteration"))
