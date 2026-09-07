"""Profile the prediction service hot path: load_features vs model predict."""
import os
import sys
import time

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
sys.path.insert(0, os.path.join(_PROJ, "services", "prediction-service"))

from datetime import date
from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJ, ".env"))

from app.repository.repository import PredictionRepository
from app.models.churn_predictor import ChurnPredictor

repo = PredictionRepository()
d = date(2026, 7, 27)

# 1. Time load_features
t = time.perf_counter()
features = repo.load_features(d)
print(f"load_features: {time.perf_counter()-t:.3f}s  ({len(features)} rows)")

# 2. Time load_clv_percentiles
t = time.perf_counter()
clv = repo.load_clv_percentiles(d)
print(f"load_clv_percentiles: {time.perf_counter()-t:.3f}s  ({len(clv)} ids)")

# 3. Load model (like service startup)
t = time.perf_counter()
predictor = ChurnPredictor()
print(f"ChurnPredictor __init__ (model load): {time.perf_counter()-t:.3f}s")

# 4. Find one customer row + predict (single)
row = next(r for r in features if r["customer_id"] == "CUST00021")
t = time.perf_counter()
p = predictor.predict(row)
print(f"predict (single): {time.perf_counter()-t:.3f}s  -> {p}")

# 5. Repeat predict (warm)
t = time.perf_counter()
for _ in range(10):
    predictor.predict(row)
print(f"predict x10 warm: {time.perf_counter()-t:.3f}s")

# 6. Linear scan over features list (what get_churn does)
t = time.perf_counter()
for _ in range(100):
    for r in features:
        if r["customer_id"] == "CUST00021":
            break
print(f"linear scan x100: {time.perf_counter()-t:.3f}s")
