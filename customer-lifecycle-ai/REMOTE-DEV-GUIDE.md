# Remote Dev Connection Guide

**Host Machine:** `100.82.12.85` (Tailscale)  
**Prerequisite:** All devs must be on the Uniplexity Tailscale network.

---

## Quick Test

```bash
curl http://100.82.12.85:8080/health
```

Should return: `{"status":"healthy","service":"gateway"}`

---

## API Endpoints (via Gateway :8080)

| Endpoint | Description |
|----------|-------------|
| `http://100.82.12.85:8080/api/v1/customers/portfolio?as_of_date=2026-07-27` | Portfolio KPIs |
| `http://100.82.12.85:8080/api/v1/customers?as_of_date=2026-07-27&limit=10` | Customer list |
| `http://100.82.12.85:8080/api/v1/customers/CUST00001?as_of_date=2026-07-27` | Customer detail |
| `http://100.82.12.85:8080/api/v1/customers/CUST00001/timeline` | State timeline |
| `http://100.82.12.85:8080/api/v1/predictions/CUST00001/churn?as_of_date=2026-07-27` | Churn probability |
| `http://100.82.12.85:8080/api/v1/predictions/CUST00001/health?as_of_date=2026-07-27` | Health score |
| `http://100.82.12.85:8080/api/v1/predictions/markov-matrix?as_of_date=2026-07-27` | Markov matrix |
| `http://100.82.12.85:8080/api/v1/models` | Model registry |
| `http://100.82.12.85:8080/api/etl/runs?limit=5` | ETL dashboard |
| `http://100.82.12.85:8080/docs` | Swagger UI |

## Frontend Config

In `src/services/api.js`, remote devs should set:

```js
const RAW_API_URL = 'http://100.82.12.85:8080'
```

Or set the env var: `VITE_API_BASE_URL=http://100.82.12.85:8080`

## Direct Service Access

| Service | URL |
|---------|-----|
| Gateway | `http://100.82.12.85:8080` |
| Feature Engineering | `http://100.82.12.85:8002` |
| Customer State (L1) | `http://100.82.12.85:8003` |
| Prediction (L2) | `http://100.82.12.85:8004` |
| Decision Intelligence (L3) | `http://100.82.12.85:8005` |

## Full Docs

- Frontend: `absa-foundry-frontend/docs/FRONTEND-REQUIREMENTS-V3.md`
- Backend: `absa-foundry-backend/customer-lifecycle-ai/.ai/ABSA-KNOWLEDGE-BASE.md`
- Architecture: `absa-foundry-backend/customer-lifecycle-ai/docs/architecture/decision-intelligence-platform-v3.md`
