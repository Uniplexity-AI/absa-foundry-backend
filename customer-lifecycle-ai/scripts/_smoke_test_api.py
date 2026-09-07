"""Smoke test — hit Customer State Service API."""
import requests, json

base = 'http://localhost:8003'

# Health
print('=== Health ===')
r = requests.get(base + '/health')
print(r.json())

# Portfolio
print('\n=== Portfolio 2026-07-27 ===')
r = requests.get(base + '/states/portfolio?as_of_date=2026-07-27')
d = r.json()
print('Status:', r.status_code)
print('Total:', d['total_customers'])
for state, info in d['by_state'].items():
    print(f'  {state:10s} {info["count"]:5d}  {info["pct"]}%')

# Latest portfolio
print('\n=== Portfolio 2026-07-22 ===')
r = requests.get(base + '/states/portfolio?as_of_date=2026-07-22')
d = r.json()
for state, info in d['by_state'].items():
    print(f'  {state:10s} {info["count"]:5d}  {info["pct"]}%')

# Try a customer
print('\n=== Customer Lookups ===')
for cid in ['CUST00001', 'C01CUST00001']:
    r = requests.get(base + '/states/' + cid + '?as_of_date=2026-07-27')
    if r.status_code == 200:
        d = r.json()
        print(f'{cid}: state={d["state"]}, health_score={d["health_score"]}')
    else:
        print(f'{cid}: {r.status_code} — {r.json().get("detail", "")[:80]}')

print('\n=== DONE ===')
