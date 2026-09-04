"""TEMP Phase B RBAC check — deleted after use."""
import json
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8080"
H = {"Content-Type": "application/json"}


def req(method, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=H)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa: BLE001
        return -1


def login(u):
    s, _ = None, None
    for _ in range(3):
        data = json.dumps({"username": u, "password": "Pilot@2025"}).encode()
        r = urllib.request.Request(BASE + "/auth/login", data=data, method="POST", headers=H)
        try:
            with urllib.request.urlopen(r, timeout=15) as resp:
                return json.loads(resp.read())["access_token"]
        except urllib.error.HTTPError as e:
            s = e.code
            time.sleep(1)
    return None


for _ in range(30):
    if req("GET", "/health") == 200:
        break
    time.sleep(1)

adm, rm, ds, ops = [login(u) for u in ("admin", "rm.demo", "ds.demo", "ops.demo")]
print("tokens:", bool(adm), bool(rm), bool(ds), bool(ops))

cases = [
    ("no-token    GET /api/v1/customers/portfolio",        None, "GET", "/api/v1/customers/portfolio"),
    ("admin       GET /api/v1/customers/portfolio",        adm,  "GET", "/api/v1/customers/portfolio"),
    ("rm          GET /api/v1/customers/portfolio",        rm,   "GET", "/api/v1/customers/portfolio"),
    ("ds          GET /api/v1/customers/portfolio (expect 403)", ds, "GET", "/api/v1/customers/portfolio"),
    ("rm          GET /api/v1/models (expect 403)",        rm,   "GET", "/api/v1/models"),
    ("ds          GET /api/v1/models",                     ds,   "GET", "/api/v1/models"),
    ("ops         GET /api/v1/monitoring/performance-history", ops, "GET", "/api/v1/monitoring/performance-history"),
    ("ops         GET /api/v1/customers/portfolio (expect 403)", ops, "GET", "/api/v1/customers/portfolio"),
    ("admin       GET /api/etl/configs",                   adm,  "GET", "/api/etl/configs"),
    ("admin       GET /admin/users",                        adm,  "GET", "/admin/users"),
    ("ds          GET /admin/users (expect 403)",          ds,   "GET", "/admin/users"),
]
for label, tok, m, p in cases:
    print(f"{req(m, p, token=tok):>4}  {label}")
