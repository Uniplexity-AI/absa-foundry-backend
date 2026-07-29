"""Quick validation of prediction service API."""
import urllib.request
import json
import sys

BASE = "http://localhost:8004"

def get(path):
    r = urllib.request.urlopen(f"{BASE}{path}")
    return json.loads(r.read())

# Health
h = get("/health")
print(f"Health: {h}")

# Models
m = get("/predict/models")
print(f"Models: {len(m['models'])} registered")
for mod in m["models"]:
    print(f"  {mod['model_id']} ({mod['type']}): {mod['status']}")

# Single customer prediction
try:
    p = get("/predict/CUST00001?as_of_date=2026-07-27")
    print(f"\nCustomer: {p['customer_id']}")
    print(f"  State: {p['state']}")
    print(f"  Churn probability: {p['churn_probability']:.4f}")
    print(f"  CLV percentile: {p['clv_percentile']:.4f}")
    print(f"  Health score: {p['health_score']:.1f}")
    print(f"  Components: {p['component_scores']}")
    print(f"  Models: {p['model_versions']}")
except urllib.error.HTTPError as e:
    print(f"Customer prediction failed: {e.code} {e.reason}")
    print(e.read().decode())

# Batch
print("\nRunning batch prediction...")
try:
    req = urllib.request.Request(
        f"{BASE}/predict/batch?as_of_date=2026-07-27",
        method="POST",
    )
    r = urllib.request.urlopen(req)
    b = json.loads(r.read())
    print(f"Batch: {b['customers_scored']} scored, {b['chunks_processed']} chunks")
    print(f"  Health scores backfilled: {b['health_scores_backfilled']}")
    print(f"  Duration: {b['duration_seconds']}s")
    print(f"  Status: {b['status']}")
except urllib.error.HTTPError as e:
    print(f"Batch failed: {e.code} {e.reason}")
    print(e.read().decode()[:500])

print("\nAll validations complete.")
