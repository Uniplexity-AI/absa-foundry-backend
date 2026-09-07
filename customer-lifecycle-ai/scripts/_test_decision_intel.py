"""Quick smoke test for the Decision Intelligence service (port 8005)."""
import json
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8005"


def get(path, timeout=60):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
            body = json.loads(r.read().decode())
        return body, round(time.perf_counter() - t0, 2), None
    except urllib.error.HTTPError as e:
        return None, round(time.perf_counter() - t0, 2), f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        return None, round(time.perf_counter() - t0, 2), str(e)


def post(path, timeout=60):
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(f"{BASE}{path}", method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode())
        return body, round(time.perf_counter() - t0, 2), None
    except urllib.error.HTTPError as e:
        return None, round(time.perf_counter() - t0, 2), f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        return None, round(time.perf_counter() - t0, 2), str(e)


tests = [
    ("GET /health", get, "/health"),
    ("GET /decisions/strategies/list", get, "/decisions/strategies/list"),
    ("GET /decisions/CUST00021", get, "/decisions/CUST00021?as_of_date=2026-07-27&strategy=BALANCED"),
    ("POST /decisions/compute (5)", post, "/decisions/compute?as_of_date=2026-07-27&strategy=BALANCED&max_customers=5"),
    ("GET /customer-intel/CUST00021", get, "/customer-intel/CUST00021?as_of_date=2026-07-27"),
    ("GET /customer-intel/alerts/CUST00021", get, "/customer-intel/alerts/CUST00021?as_of_date=2026-07-27"),
    ("GET /recommendations/CUST00021", get, "/recommendations/CUST00021?as_of_date=2026-07-27"),
    ("GET /insights/reason-codes/CUST00021", get, "/insights/reason-codes/CUST00021?as_of_date=2026-07-27"),
    ("GET /churn-intel/drivers", get, "/churn-intel/drivers?as_of_date=2026-07-27"),
    ("GET /forecasts/churn", get, "/forecasts/churn?as_of_date=2026-07-27&horizon_days=90"),
]

for name, fn, path in tests:
    data, secs, err = fn(path)
    status = "OK" if err is None else f"ERR ({err})"
    print(f"\n=== {name} ===  [{secs}s] {status}")
    if data is not None:
        print(json.dumps(data, indent=2, default=str)[:1600])
    print("=" * 70, flush=True)
