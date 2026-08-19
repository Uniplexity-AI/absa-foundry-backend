# ABSA Foundry Backend — Pilot Deployment Guide (Windows Server)

> **Target environment:** Windows Server (no Docker for the pilot phase)
> **Version:** 1.0
> **Last updated:** 2026-08-19
> **Scope:** Configure, migrate, start, and verify all 5 backend services.

---

## 1. Architecture Overview

Five services + one gateway, all running as Uvicorn processes on a single Windows host.

| Service | Port | Purpose |
|---------|------|---------|
| API Gateway | `8080` | Auth, routing, rate limiting — proxies to all services |
| Feature Engineering | `8002` | Computes 21 customer features |
| Customer State (L1) | `8003` | Lifecycle classification + Markov matrix |
| Prediction (L2) | `8004` | Churn (XGBoost AUC 0.77) + health scores |
| Decision Intelligence (L3) | `8005` | NBA recommendations, 9 engines |

### Two databases

| Database | Role | Holds |
|----------|------|-------|
| `etl_validation` | **Source** (raw) | `iam.*` (auth), `public.raw_*` (raw data) |
| `etl_clean` | **Target** (clean) | `etl.*` (audit), `customers_clean`, `customer_states`, `customer_features` |

Both must exist on the PostgreSQL server before services start.

---

## 2. Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Windows Server | 2016+ | Any modern Windows |
| Python | 3.11+ (3.12 recommended) | On PATH |
| PostgreSQL | 16 | On the server or reachable over network |
| Redis | optional | Only if caching is enabled (default off) |
| `uv` | optional | Only needed if the `.venv` has no `pip` module |

> **Air-gapped note:** The platform is designed for an air-gapped network. All
> Python dependencies must be installable from a local wheelhouse/mirror if
> there is no internet access. See §7 (Troubleshooting).

---

## 3. Directory Layout

```
customer-lifecycle-ai/
├── .env                          # Environment configuration (create this)
├── start.ps1                     # DEV start script (do NOT use in pilot)
├── requirements.txt              # Master Python dependencies
├── run_etl.py                    # ETL pipeline entrypoint
├── gateway/                      # API Gateway (:8080)
├── services/
│   ├── feature-engineering-service/   (:8002)
│   ├── customer-state-service/        (:8003)
│   ├── prediction-service/            (:8004)
│   └── decision-intelligence-service/ (:8005)
├── database/
│   ├── iam/001_initial_schema.sql         # auth schema (source DB)
│   ├── migrations/001_etl_schema.sql      # ETL audit/validation (target DB)
│   ├── feature_store/001_customer_features.sql
│   └── state_engine/001_customer_states.sql
├── scripts/
│   ├── pilot_setup.ps1            # one-time: venv + deps + .env
│   ├── pilot_migrate.py           # DB migration runner
│   ├── pilot_start.ps1            # start all services (production)
│   └── pilot_stop.ps1             # stop all services
├── models/                        # ML model artifacts (deploy with code)
└── logs/pilot/                    # service logs (created at runtime)
```

---

## 4. Step-by-Step Setup

### Step 1 — Get the code onto the server

Copy the `customer-lifecycle-ai/` folder to the server. Ensure `models/` is
included — it contains the trained XGBoost churn model.

### Step 2 — Run the setup script

Open PowerShell and run:

```powershell
Set-Location "C:\path\to\customer-lifecycle-ai"
.\scripts\pilot_setup.ps1
```

This script:
1. Creates the `.venv` virtual environment
2. Installs all dependencies (`requirements.txt` + per-service files)
3. Creates `.env` from `.env.example` if missing
4. Rotates the placeholder `change-me-in-production` secrets

### Step 3 — Edit `.env`

Open `.env` and set **pilot-specific values**. Critical keys:

```dotenv
# PostgreSQL Source (raw data)
POSTGRES_HOST=<pilot-db-host>
POSTGRES_PORT=5432
POSTGRES_DB=etl_validation
POSTGRES_USER=<pilot-db-user>
POSTGRES_PASSWORD=<strong-password>

# PostgreSQL Target (clean data)
POSTGRES_TARGET_HOST=<pilot-db-host>
POSTGRES_TARGET_PORT=5432
POSTGRES_TARGET_DB=etl_clean
POSTGRES_TARGET_USER=<pilot-db-user>
POSTGRES_TARGET_PASSWORD=<strong-password>

# Security — MUST be unique per environment
GATEWAY_SECRET_KEY=<generated>
JWT_SECRET_KEY=<generated>
```

> The setup script already replaced `change-me-in-production` with a random
> value, but verify these two keys are set and different in every environment.

### Step 4 — Run migrations

This creates the two databases (if missing) and applies all schema SQL files:

```powershell
.\.venv\Scripts\python.exe scripts\pilot_migrate.py --create-databases
```

What it applies:

| SQL file | Database |
|----------|----------|
| `database/iam/001_initial_schema.sql` | `etl_validation` |
| `database/migrations/001_etl_schema.sql` | `etl_clean` |
| `database/feature_store/001_customer_features.sql` | `etl_clean` |
| `database/state_engine/001_customer_states.sql` | `etl_clean` |

> **Raw data seeding** is a separate step. The migrations create schemas only.
> Load raw data with `scripts/csv_importer.py`, or point extraction specs at
> real ABSA tables (§6).

### Step 5 — Start the services

```powershell
.\scripts\pilot_start.ps1
```

Services start in the background. Logs go to `logs\pilot\`.

### Step 6 — Verify health

```powershell
Invoke-RestMethod http://localhost:8080/health   # gateway
Invoke-RestMethod http://localhost:8002/health   # feature
Invoke-RestMethod http://localhost:8003/health   # state
Invoke-RestMethod http://localhost:8004/health   # prediction
Invoke-RestMethod http://localhost:8005/health   # decision
```

All five should return a healthy status.

### Step 7 — Stop the services

```powershell
.\scripts\pilot_stop.ps1
```

This stops **only** the PIDs recorded by `pilot_start.ps1` — it will not kill
unrelated Python processes.

---

## 5. Manual Start Commands (Reference)

If you need to start a single service manually (e.g. for debugging):

```powershell
$env:PYTHONPATH = "C:\path\to\customer-lifecycle-ai"

# Gateway (:8080) — the ONLY service run from project root
Set-Location "C:\path\to\customer-lifecycle-ai"
.\.venv\Scripts\python.exe -m uvicorn gateway.main:create_app --factory --host 0.0.0.0 --port 8080

# Feature Engineering (:8002)
Set-Location "C:\path\to\customer-lifecycle-ai\services\feature-engineering-service"
..\..\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8002

# Customer State (:8003)
Set-Location "C:\path\to\customer-lifecycle-ai\services\customer-state-service"
..\..\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8003

# Prediction (:8004)
Set-Location "C:\path\to\customer-lifecycle-ai\services\prediction-service"
..\..\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8004

# Decision Intelligence (:8005)
Set-Location "C:\path\to\customer-lifecycle-ai\services\decision-intelligence-service"
..\..\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8005
```

> **Do NOT use `--reload`** in production — it's a development feature that
> watches files and restarts on changes.

---

## 6. Raw Data & ETL

### Loading synthetic data (PoC)

```powershell
.\.venv\Scripts\python.exe scripts\csv_importer.py
.\.venv\Scripts\python.exe scripts\generate_synthetic_feature_store_data.py
```

### Pointing at real ABSA data

Extraction specs live in `etl/config/extraction_specs/*.yaml`. Write a new
spec targeting the real tables, then either:

```powershell
.\.venv\Scripts\python.exe run_etl.py --extraction-spec etl/config/extraction_specs/<name>.yaml
```

Or trigger it from the UI (ETL Manager → Trigger Manual Run).

---

## 7. Security Checklist (Before Go-Live)

- [ ] `GATEWAY_SECRET_KEY` and `JWT_SECRET_KEY` are unique and strong
- [ ] `POSTGRES_PASSWORD` rotated from the dev default (`wamulehi`)
- [ ] No `--reload` flags (pilot_start.ps1 already excludes them)
- [ ] No `taskkill /F /IM python.exe` (dev script only — do not use)
- [ ] No hardcoded IPs — check `services/decision-intelligence-service/main.py` for the dev Tailscale IP `100.82.12.85` and replace with env config
- [ ] PostgreSQL firewalled to the app host only
- [ ] Frontend `VITE_API_BASE_URL` points to the pilot gateway
- [ ] HTTPS via reverse proxy (IIS/nginx) if exposed outside the internal network

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'app'` | Service started from wrong directory | Start from the service's own directory (see §5) |
| `.venv` has no `pip` module | uv-managed venv | Use `uv pip install -r requirements.txt` |
| `psycopg2`/`asyncpg` import error | Missing DB drivers | `uv pip install psycopg2-binary asyncpg` |
| `relation "etl.etl_audit" does not exist` | Migrations not run against `etl_clean` | Run `pilot_migrate.py --create-databases` |
| Port already in use | Previous run not stopped | Run `pilot_stop.ps1`, then `pilot_start.ps1` |
| Auth 401 on all routes | JWT secret mismatch | Ensure `JWT_SECRET_KEY` matches between gateway and frontend |
| ETL trigger produces no output | Log file location | Check `logs/etl_trigger_*.log` |
| Services start but `/health` fails | Service crashed at boot | Check `logs\pilot\<name>.err.log` |

---

## 9. Operational Commands Quick Reference

```powershell
# One-time setup
.\scripts\pilot_setup.ps1
.\.venv\Scripts\python.exe scripts\pilot_migrate.py --create-databases

# Start / stop
.\scripts\pilot_start.ps1
.\scripts\pilot_stop.ps1

# Health check all 5 services
@(8080,8002,8003,8004,8005) | ForEach-Object {
    try { $r = Invoke-RestMethod "http://localhost:$_/health" -TimeoutSec 5; ":$($_ ) OK" }
    catch { ":$($_ ) DOWN" }
}
```
