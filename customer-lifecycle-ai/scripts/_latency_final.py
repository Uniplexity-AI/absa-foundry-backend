"""Final latency check after 127.0.0.1 + cache fixes (measure via 127.0.0.1)."""
import json
import time
import urllib.error
import urllib.request

HOST = "127.0.0.1"


def get(url, timeout=90):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = json.loads(r.read().decode())
        return body, round(time.perf_counter() - t0, 3), None
    except urllib.error.HTTPError as e:
        return None, round(time.perf_counter() - t0, 3), f"HTTP {e.code}"
    except Exception as e:
        return None, round(time.perf_counter() - t0, 3), str(e)


print(f"=== services health via {HOST} ===")
for port in (8002, 8003, 8004, 8005, 8080):
    _, s, e = get(f"http://{HOST}:{port}/health")
    print(f"  :{port} health: {s}s  {e or 'OK'}")

print("\n=== prediction (8004) churn, cold + warm ===")
_, s1, e1 = get(f"http://{HOST}:8004/predict/CUST00021/churn?as_of_date=2026-07-27")
print(f"  churn cold: {s1}s  {e1 or 'OK'}")
_, s2, e2 = get(f"http://{HOST}:8004/predict/CUST00021/churn?as_of_date=2026-07-27")
print(f"  churn warm: {s2}s  {e2 or 'OK'}")

print("\n=== decision-intel (8005) decision, cold + warm ===")
_, s3, e3 = get(f"http://{HOST}:8005/decisions/CUST00021?as_of_date=2026-07-27&strategy=BALANCED")
print(f"  decision cold: {s3}s  {e3 or 'OK'}")
_, s4, e4 = get(f"http://{HOST}:8005/decisions/CUST00022?as_of_date=2026-07-27&strategy=BALANCED")
print(f"  decision warm: {s4}s  {e4 or 'OK'}")

print("\n=== gateway (8080) proxy ===")
_, s5, e5 = get(f"http://{HOST}:8080/api/v1/churn-intel/drivers?as_of_date=2026-07-27")
print(f"  gateway churn-intel/drivers: {s5}s  {e5 or 'OK'}")
