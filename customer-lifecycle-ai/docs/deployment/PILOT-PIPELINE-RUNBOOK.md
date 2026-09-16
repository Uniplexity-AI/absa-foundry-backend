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
| 6 · Models (optional) | `models/champion/churn/…`, `models/value_*_v1.pkl`, `models/registry.json`, `etl_clean.model_registry` | `scripts/train_models.py` → `scripts/train_value_model.py` → `scripts/register_value_models.py` |
| 7 · Runtime | gateway 8080 + feature/state/prediction/decision/model-management (8002–8006) | `scripts/pilot_start.ps1` **or** pywin32 service |
| 8 · Value scores | `customer_states.erosion_probability`, `predicted_future_value` | `POST /api/v1/predictions/value-batch?as_of_date=<d>` (needs layer 7 up) |

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
& $py scripts\train_models.py                       # churn champion -> models[] (type: churn)
& $py scripts\train_value_model.py                  # CLV family -> models/value_*_v1.pkl + metrics JSON
& $py scripts\register_value_models.py              # CLV entries -> models[] + etl_clean.model_registry

# 6) Start services
powershell -ExecutionPolicy Bypass -File scripts\pilot_start.ps1
```

---

## 4. Verification (do all of these)

```powershell
# 4.1 Health (6 services)
Invoke-RestMethod http://127.0.0.1:8080/health      # gateway
foreach ($p in 8002,8003,8004,8005,8006) { try { Invoke-RestMethod "http://127.0.0.1:$p/health" | Out-Null; "$p OK" } catch { "$p DOWN" } }

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

# 4.5 Models page
#   GET /api/v1/models  -> registry document (served from models/registry.json)
#   GET /api/v1/models/features, /audit, /champion -> proxied to Model Management (:8006)
(Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/models" -Headers $h).models | Select-Object model_id,type,status
# Expect 3 entries: churn_v1 (churn) + value_erosion_v1 / value_forecast_v1 (clv)
(Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/models/champion" -Headers $h).optimal_threshold
# Expect 0.9509 (the trained churn threshold — NOT the 0.5 service mock)
(Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/models/challengers" -Headers $h)
# Expect the 2 APPROVED CLV artifacts

# 4.6 Ollama narration (ADR-005: narration only, never a decision)
#   The action itself is deterministic (ActionGenerator -> RankingEngine -> RoutingEngine);
#   Ollama only writes the RM-facing narrative around the already-chosen action.
Invoke-RestMethod -Uri "http://localhost:11434/api/tags"        # Ollama up + model pulled
$c = "CUST0000239"
$d = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/insights/llm-explain/$c`?as_of_date=2026-07-27" `
     -Headers $h -TimeoutSec 300
$d.llm_available; $d.model; $d.top_action          # True | qwen2.5-coder:7b | FEE_WAIVER
$d.llm_explanation
# Expect 200 and a written narrative. ALLOW ~60-120s — the 7B model runs on CPU.
# Tunables (repo-root .env): LLM_MODEL, LLM_MAX_TOKENS, LLM_TIMEOUT_SECONDS,
#   LLM_GATEWAY_TIMEOUT_SECONDS. gemma3:1b is already pulled and is far faster.
#   In the UI this is the "AI Explanation" card on the customer page (button-triggered,
#   never on page load, because of the CPU latency).
```

### 4.7 MLOps governance flow (Models page, :8006)

The Models page controls now do real work — "Request Retrain" runs the actual trainer.

```powershell
# Retrain: queues a background job that runs scripts/train_models.py (~20s)
$job = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/v1/models/training" `
       -Headers $h -ContentType application/json -Body '{"feature_ids":[],"dataset_version":"2026-07-27"}'
$job.job_id

# ...wait for the row to reach TRAINED, then walk the governance chain:
$chall = (Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/models/compare" -Headers $h).challenger
$chall.status; $chall.evaluation_metrics.auc
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/v1/models/$($chall.id)/validate" -Headers $h
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/v1/models/$($chall.id)/approve"  -Headers $h
# Invoke-RestMethod -Method Post .../$($chall.id)/promote ...   # retires the current champion

# Calibration simulator — uses the champion's real confusion matrix
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/v1/models/simulate-calibration" `
     -Headers $h -ContentType application/json -Body '{"threshold":0.6}'
```

> `compare` pairs models **within the same family only**, so the approved CLV artifacts are
> never presented as churn challengers. `/approve` accepts `VALIDATED` (nomination is implicit),
> matching the three buttons the UI shows: Validate → Approve → Promote.

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
| `GET /api/v1/models` 502 `Model Management Service unavailable` | the 6th service (:8006) is not running | `pilot_start.ps1` (it starts 6 services) or `pilot_service.py start`; verify `http://127.0.0.1:8006/health` |
| Models page shows no champion / 0 models | `models/registry.json` not written yet | run `train_models.py` (writes `models[]` + champion block) |
| CLV family missing from `models[]` / Model Comparison | `train_value_model.py` + `register_value_models.py` not run | run both (bootstrap does this in the train step) |
| Value/erosion views empty, or `MODEL_NOT_LOADED` from `value-batch` | value scores never computed (layer 8), or the pickles aren't found | run `value-batch` per date (bootstrap does this after services start); pickles must be at `<repo>/models/value_*_v1.pkl` |
| `/api/v1/insights/llm-explain/*` → `llm_available: false` | Ollama not running or the model isn't pulled | `ollama serve` + `ollama pull qwen2.5-coder:7b` (see §4.6) |
| `/api/v1/insights/llm-explain/*` → 504 | CPU narration exceeds the proxy timeout | raise `LLM_GATEWAY_TIMEOUT_SECONDS` / `LLM_TIMEOUT_SECONDS`, or set `LLM_MODEL=gemma3:1b` |
| narration returns “LLM generation failed” | Ollama up but the model errored / OOM | check `ollama ps` + the decision-service log; try a smaller model |
| Retrain stays `TRAINING` forever | trainer subprocess failed | check `logs/pilot/modelmgmt.err.log`; the row records `evaluation_metrics.error` when it fails |
| Calibration slider errors | champion has no `confusion_matrix` in `evaluation_metrics` | re-run `register_value_models.py` (it copies the matrix from `registry.json`) |
| generator loads to wrong DB | default `DATABASE_URL` = `etl_validation` | always pass `--database-url …/etl_clean` |
| feature pipeline fails per date | feature SQL expects consistent txn history | re-run after a clean load (never generator alone over stale data) |
| demo login invalid | users not seeded | `seed_iam.py` (password `Pilot@2025`) |

---

## 7. Repeat / rollback

- **Re-seed everything:** `pilot_bootstrap.ps1` (destructive to `etl_clean` — reproducible with `--seed 42`).
- **Re-load data only:** `pilot_reset_clean.py` then generator + feature pipeline + states.
- **Services only:** `pilot_stop.ps1` / `pilot_start.ps1`, or the pywin32 service (`scripts/pilot_service.py`, see `docs/pilot-service.md`).
