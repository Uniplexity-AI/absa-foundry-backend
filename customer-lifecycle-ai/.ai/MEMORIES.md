# MEMORIES.md — ABSA Project Memory Bank

This file acts as the persistent, self-learning memory ledger for AI agents (GitHub Copilot Chat, DeepSeek, etc.) operating on the **ABSA Customer Lifecycle Platform**.

---

## 1. Agent Memory Guidelines

1. **Pre-Task Memory Lookup:** Before executing tasks, review section `2. High-Confidence System Rules` and section `3. Dynamic Learning Ledger`.
2. **Post-Task Log Entry:** Upon resolving bugs, fixing edge cases, or handling framework quirks across `.ai/`, `backend/`, or `frontend/`, append a structured record to `3. Dynamic Learning Ledger`.
3. **Promotion Protocol:** When an entry in Section 3 is validated 2+ times or marked **High Confidence**, move it into Section 2.

---

## 2. High-Confidence System Rules

* **Service Ports & Startup Sequence:**
  - `Gateway` (`:8080`): `gateway.main:create_app`
  - `Feature Engineering` (`:8002`): `services/feature-engineering-service`
  - `Customer State (L1)` (`:8003`): `services/customer-state-service`
  - `Prediction (L2)` (`:8004`): `services/prediction-service`
  - `Decision Intelligence (L3)` (`:8005`): `services/decision-intelligence-service`
  - *Rule:* Always execute `taskkill /F /IM python.exe` and sleep 2 seconds prior to re-binding Uvicorn processes in PowerShell.

* **Database & Repository Pattern:**
  - Async FastAPI endpoints MUST use `asyncpg`.
  - Sync ETL background jobs MUST use `psycopg2`.
  - Never write raw SQL directly inside route controllers; keep query logic encapsulated within `app/services/` repositories.

* **Vue 3 Setup & Pinia Standards:**
  - All Vue 3 components MUST use `<script setup>` syntax.
  - Pinia stores MUST follow the setup store syntax `defineStore('name', () => { ... })`.
  - API HTTP requests MUST utilize configured Axios clients with automatic JWT header propagation.

* **LLM Engine Boundaries (ADR-005):**
  - Deterministic decision engines and ML models calculate values, scores, and transitions.
  - LLMs are restricted strictly to narrative generation, executive summaries, and SHAP explainability text.

---

## 3. Dynamic Learning Ledger

### [2026-08-07] Prediction Batch & Ledger UI Gap
* **Context:** Frontend Portfolio page shows `--` for Churn % and CLV fields in table views.
* **Learned Rule:** The Layer 2 Prediction Service (`:8004`) must execute a prediction enrichment batch across customer IDs to populate churn scores into PostgreSQL before state tables render.
* **Confidence:** High

### [2026-08-07] PowerShell Service Process Binding
* **Context:** Port conflict errors when rapidly restarting backend microservices during iterative testing.
* **Learned Rule:** Uvicorn child processes do not immediately drop socket handles on Windows; enforce `Start-Sleep 2` after killing `python.exe` before calling `Start-Process`.
* **Confidence:** High

### [2026-08-07] YAML Rule Hot-Reloading
* **Context:** Rule changes made in `decision-intelligence-service` YAML files required full service restarts.
* **Learned Rule:** Use PyYAML with internal file watching/reload triggers in Layer 3 to refresh decision contexts without dropping open TCP connection pools.
* **Confidence:** Medium

### [2026-08-07] Service Startup From Own Directory
* **Context:** Feature/Prediction/Decision services failed with `ModuleNotFoundError: No module named 'app'` when started from project root.
* **Learned Rule:** Each microservice MUST be started from its own directory (`services/<name>/`) with `uvicorn main:app`, not from the project root via module path. Only the Gateway runs from `customer-lifecycle-ai/` root.
* **Confidence:** High

### [2026-08-07] Frontend Store API Shape Mismatch
* **Context:** Frontend stores expected different field names (snake_case) than what the backend APIs actually returned (camelCase + domain-specific shapes).
* **Learned Rule:** Always test the actual API response with `curl` before writing Pinia store mappings. Create `_mapCustomer()` normalizer functions to bridge backend shapes to frontend expectations.
* **Confidence:** High

### [2026-08-07] Gateway Route Registration
* **Context:** New gateway proxy routes must be explicitly registered in `gateway/main.py` via `app.include_router()` to appear in the OpenAPI spec.
* **Learned Rule:** After creating a new `gateway/routes/*.py` file, add both the import AND the `app.include_router()` call in `main.py`. The `--reload` flag handles the rest.
* **Confidence:** High

### [2026-08-07] Async vs Sync Database Drivers
* **Context:** Gateway ETL dashboard returned 500 because `asyncpg` was missing. The sync ETL pipeline used `psycopg2` which was already installed.
* **Learned Rule:** FastAPI endpoints using `Depends(get_target_session)` need the async driver. Install with `uv pip install asyncpg` before first gateway startup.
* **Confidence:** High

### [2026-08-19] Extraction spec per-spec mandatory-field override
* **Context:** Non-customer extraction specs (accounts, demographics, bridge) failed `run_etl.py` Phase 2 because `etl_config.yaml`'s global `validation.mandatory_fields` is customer-centric.
* **Learned Rule:** Extraction specs support a `validation:` block (merged by `run_etl.py`) to override `mandatory_fields` per dataset. `ValidationOverrideSpec` added to `ExtractionConfigSpec`. Other validators (Schema/Duplicate/BusinessRule) already skip missing columns gracefully — only `MandatoryFieldValidator` breaks.
* **Confidence:** High

### [2026-08-19] Pilot data config placeholder resolution
* **Context:** Source table names for real data needed one editable location instead of hardcoding across many spec files.
* **Learned Rule:** Specs use `${source_tables.<entity>}` placeholders resolved by `etl/config/pilot_data_config.py` (`PilotDataConfig.resolve`) in `ExtractionExecutor._load_spec` and `run_etl.py`'s transform/target/validation merge. Edit `pilot_data_config.yaml` only.
* **Confidence:** High

### [2026-08-19] Churn probability calibration (isotonic)
* **Context:** Raw XGBoost probabilities were overconfident (ECE ~0.40). The old "calibration deferred to D12" note was wrong.
* **Learned Rule:** Fit Platt + isotonic calibrators out-of-fold (`StratifiedKFold` + `cross_val_predict`), pick lowest holdout ECE, persist as joblib, apply in `churn_predictor._apply_calibrator`. Isotonic uses `.predict()`; Platt (`LogisticRegression`) uses `.predict_proba()`.
* **Confidence:** High

### [2026-08-19] Training leakage from metadata columns
* **Context:** `id`/`computed_at`/`created_at`/`updated_at` leaked into training, inflating AUC.
* **Learned Rule:** `NON_FEATURE_COLUMNS` in `scripts/train_models.py` must include all metadata columns. The fix took AUC 0.79 → 0.82.
* **Confidence:** High

### [2026-08-19] Tailscale IP removed → localhost/env config
* **Context:** Dev Tailscale IP `100.82.12.85` was hardcoded in decision-intelligence upstream URLs.
* **Learned Rule:** Upstream service URLs are env-configurable (`UPSTREAM_HOST`, `FEATURE_SERVICE_URL`, `STATE_SERVICE_URL`, `PREDICTION_SERVICE_URL`), defaulting to `localhost`. No hardcoded IPs in runtime code.
* **Confidence:** High

---

## 4. Pending Verification & Workspace Gotchas

- [ ] **Branch Manager Route:** `/dashboard/branch-manager` view needs Pinia store wiring once backend portfolio aggregation routes are finalized.
- [ ] **Synthetic Masking:** Customer names currently render as `"Customer 00001"`. Update mapper functions once real demographic schema seeds are imported.
- [ ] **Precision/Recall Metrics:** Models page shows `--` for F1/Precision/Recall because the prediction service model registry doesn't compute them yet.
- [ ] **ETL Startup Sequence:** Feature compute → State classify → Prediction batch must run in order after ETL pipeline loads raw data.
