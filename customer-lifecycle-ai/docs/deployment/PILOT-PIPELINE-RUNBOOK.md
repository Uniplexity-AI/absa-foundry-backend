# Pilot — Full Pipeline Runbook (schema → synthetic data → features → states → models → services)

> **Version:** 2026-09-04 · **Purpose:** reproduce the working ABSA pilot (synthetic data,
> populated dashboards) on the pilot machine, and explain each pipeline layer so a pilot
> operator has no surprises. Companion docs: `PILOT-SYNTHETIC-MIGRATION-GUIDE.md`,
> `PILOT-DEPLOYMENT-GUIDE.md`, `docs/auth/pilot-demo-access.md`, `docs/pilot-service.md`.

---

## 1. The pipeline at a glance

```
migrate ──► seed_iam ──► generate_synthetic ──► customer_id_mapping ──► feature pipeline ──► seed_states ──► (train) ──► services
  (DDL)      (users)     (clean tables)          (identity join)       (customer_features)   (customer_states)  (models)    (gateway etc.)
```

| Layer | Populates | Script |
|---|---|---|
| 0 · Schema | `iam.*` (source), all `etl_clean` tables | `scripts/pilot_migrate.py` |
| 1 · Users | 4 demo users + service API keys | `scripts/seed_iam.py` |
| 2 · Raw clean data | `customers_clean`, `customer_transactions_clean`, accounts/loans/cards/engagement/demographics | `scripts/generate_synthetic_feature_store_data.py --load` |
| 3 · ID mapping | `customer_id_mapping` (identity join) | auto-built by `scripts/run_full_pipeline_all_dates.py` |
| 4 · Feature store | `customer_features` (~64 features × as-of date) | `scripts/run_full_pipeline_all_dates.py` (Phase-1 SQL `compute_batch` + 7 domain generators) |
| 5 · State engine | `customer_states`, `state_transitions` | `scripts/seed_states.py --as-of-date <d>` |
| 6 · Models (optional) | `models/champion/churn/…` + `models/registry.json` | `scripts/train_models.py` |
| 7 · Runtime | gateway 8080 + feature/state/prediction/decision (8002–8005) | `scripts/pilot_start.ps1` **or** pywin32 service |

**ETL note:** `run_etl.py` (repo root) is the **CSV onboarding** path (validates + loads real
CSV files into `etl_clean` with an audit trail). It is **not** required for the synthetic demo —
the generator (`generate_synthetic_feature_store_data.py`) writes the clean layer directly.
Use `run_etl.py` only when a stakeholder provides real CSVs.

---

## 2. One-command bootstrap (recommended)

Requires `.env` set for the source DB and `postgres` running. From `customer-lifecycle-ai`:

```powershell
$db = "postgresql://postgres:<PILOT_DB_PASSWORD>@127.0.0.1:5432/etl_clean"
powershell -ExecutionPolicy Bypass -File scripts\pilot_bootstrap.ps1 -DatabaseUrl $db
```

What it runs (each step is logged, non-zero exit is a warning not a halt):

1. `scripts\pilot_stop.ps1`
2. `scripts\pilot_reset_clean.py` (truncates all downstream `etl_clean` tables, CASCADE)
3. `scripts\pilot_migrate.py`
4. `scripts\seed_iam.py`
5. generator `--load --customers 5000 --as-of-date 2026-07-27 --seed 42 --database-url $db`
6. `scripts\run_full_pipeline_all_dates.py 2026-07-17 2026-07-22 2026-07-27`
7. `scripts\seed_states.py --as-of-date <each date>`
8. `scripts\train_models.py`
9. `scripts\pilot_start.ps1` (+ 15s wait)

Useful switches: `-SkipReset -SkipLoad -SkipFeatures -SkipTrain -SkipStart`,
`-Customers N`, `-AsOfDate`, `-Dates '2026-07-27'`.

> If you run services as the pywin32 service instead of `pilot_start.ps1`, add `-SkipStart`,
> then after bootstrap run `python scripts\pilot_service.py start`.

---

## 3. Manual step-by-step (if you prefer to run each layer yourself)

```powershell
$proj = "C:\path\to\absa-foundry-backend\customer-lifecycle-ai"
$py = "$proj\.venv\Scripts\python.exe"
$db = "postgresql://postgres:<PILOT_DB_PASSWORD>@127.0.0.1:5432/etl_clean"
Set-Location $proj

# 0) Stop anything running
powershell -ExecutionPolicy Bypass -File scripts\pilot_stop.ps1

# 1) Schema + users
& $py scripts\pilot_migrate.py
& $py scripts\seed_iam.py

# 2) Synthetic clean data (ONCE — anchors 07-27; dates are point-in-time views of it)
& $py scripts\generate_synthetic_feature_store_data.py --load --customers 5000 --as-of-date 2026-07-27 --seed 42 --database-url $db

# 3) Feature store for the demo snapshots
& $py scripts\run_full_pipeline_all_dates.py 2026-07-17 2026-07-22 2026-07-27

# 4) State engine
& $py scripts\seed_states.py --as-of-date 2026-07-17
& $py scripts\seed_states.py --as-of-date 2026-07-22
& $py scripts\seed_states.py --as-of-date 2026-07-27

# 5) (Optional) models page: train + write registry (GET /api/v1/models reads registry.json)
& $py scripts\train_models.py

# 6) Start services
powershell -ExecutionPolicy Bypass -File scripts\pilot_start.ps1
```

---

## 4. Verification (do all of these)

```powershell
# 4.1 Health
Invoke-RestMethod http://127.0.0.1:8080/health      # gateway
foreach ($p in 8002,8003,8004,8005) { try { Invoke-RestMethod "http://127.0.0.1:$p/health" | Out-Null; "$p OK" } catch { "$p DOWN" } }

# 4.2 Row counts (source of truth)
psql -h 127.0.0.1 -U postgres -d etl_clean -c "SELECT 'customers' t,count(*) FROM customers_clean UNION ALL SELECT 'transactions',count(*) FROM customer_transactions_clean UNION ALL SELECT 'features',count(*) FROM customer_features UNION ALL SELECT 'states',count(*) FROM customer_states;"
# Expect: customers 5,000 · transactions ~348k · features 3×5,000 · states 3×5,000

# 4.3 Auth (JWT now enforced)
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/auth/login -ContentType application/json -Body '{"username":"admin","password":"Pilot@2025"}'
Invoke-RestMethod -Uri http://127.0.0.1:8080/auth/me -Headers @{ Authorization = "Bearer $($r.access_token)" }

# 4.4 Dashboard data (needs features + states; as ADMIN)
$h = @{ Authorization = "Bearer $($r.access_token)" }
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/customers/portfolio?as_of_date=2026-07-27" -Headers $h
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/predictions/markov-matrix" -Headers $h
```

---

## 5. Dashboard shows 0 customers? (the #1 gotcha)

The generator only fills the **clean** tables. If `customer_features` / `customer_states` are
empty (or the ID mapping is empty), the portfolio reads nothing. Fix = run layers 3–5 above.
Check the empty layers first:

```powershell
psql -h 127.0.0.1 -U postgres -d etl_clean -c "SELECT count(*) FROM customer_features; SELECT count(*) FROM customer_states; SELECT count(*) FROM customer_id_mapping;"
```

---

## 6. Troubleshooting quick reference

| Symptom | Cause | Fix |
|---|---|---|
| `InvalidForeignKey ... customers_clean` during migrate | stale clean schema from an old generator | `pilot_reset_clean.py` + drop clean tables if needed (see migration guide §6), re-migrate |
| Dashboards 0 customers | `customer_features`/`customer_states` empty | run feature pipeline + `seed_states.py` (bootstrap steps 3–4) |
| `401` on `/api/*` | JWT enforced | login → `Authorization: Bearer …` (see §4.3) |
| `GET /api/v1/models` 500 | models registry empty (no `models/registry.json`) | run `train_models.py` (or restore a champion artifact) |
| generator loads to wrong DB | default `DATABASE_URL` = `etl_validation` | always pass `--database-url …/etl_clean` |
| feature pipeline fails per date | feature SQL expects consistent txn history | re-run after a clean load (never generator alone over stale data) |
| demo login invalid | users not seeded | `seed_iam.py` (password `Pilot@2025`) |

---

## 7. Repeat / rollback

- **Re-seed everything:** `pilot_bootstrap.ps1` (destructive to `etl_clean` — reproducible with `--seed 42`).
- **Re-load data only:** `pilot_reset_clean.py` then generator + feature pipeline + states.
- **Services only:** `pilot_stop.ps1` / `pilot_start.ps1`, or the pywin32 service (`scripts/pilot_service.py`, see `docs/pilot-service.md`).
