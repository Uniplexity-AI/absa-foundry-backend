import joblib, numpy as np

model = joblib.load("models/customer-lifetime-value-prediction/lightgbm_clv_model.pkl")

# Check what features it uses (are there any amount-like features?)
feats = model.feature_name_
print("All features:", feats)

# Check feature importance - what drives predictions
import pandas as pd
importance = pd.Series(model.feature_importances_, index=feats).sort_values(ascending=False)
print("\nTop 10 feature importances:")
print(importance.head(10))

# Can we check training data range from the trees?
booster = model.booster_
print("\nTree count:", booster.num_trees())
