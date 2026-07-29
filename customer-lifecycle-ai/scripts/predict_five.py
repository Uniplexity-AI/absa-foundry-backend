"""Query predictions for 5 sample customers."""
import urllib.request, json

BASE = "http://localhost:8004"
ids = ["CUST00001", "CUST00050", "CUST00100", "CUST00263", "CUST00500"]
date = "2026-07-27"

print(f"{'Customer':<12s} {'State':>8s}  {'Churn':>6s}  {'CLV':>6s}  {'Health':>7s}  {'Behav':>6s}")
print("-" * 60)

for cid in ids:
    try:
        r = urllib.request.urlopen(f"{BASE}/predict/{cid}?as_of_date={date}")
        p = json.loads(r.read())
        print(
            f"{p['customer_id']:<12s} {p['state'] or 'N/A':>8s}  "
            f"{p['churn_probability']:6.3f}  {p['clv_percentile']:6.3f}  "
            f"{p['health_score']:6.1f}  {p['component_scores']['behaviour_sub']:6.1f}"
        )
    except Exception as e:
        print(f"{cid:<12s} {'ERROR':>8s}  {e}")
