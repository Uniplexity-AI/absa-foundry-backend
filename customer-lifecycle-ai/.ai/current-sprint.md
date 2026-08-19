# Current Sprint — ABSA Customer Lifecycle Platform

**Status:** Pilot Deployment Preparation — Real-Data Onboarding
**Date:** 2026-08-19
**Branch:** `poc-90day`

---

## Active Phase: Pilot Data Onboarding

Backend prepared for Windows Server pilot with real customer data. Churn model
trained + calibrated (AUC 0.8117, isotonic ECE 0.0172). Extraction specs + a single
pilot data config drive real-table mapping. Remaining: obtain transaction +
balance history and confirm source table names in `pilot_data_config.yaml`.

## Completed This Sprint (2026-08-11 → 08-19)

### Model Training & Calibration
- [x] XGBoost churn retrained — leakage fixed (`id`/`computed_at` excluded), AUC 0.7672 → 0.8117
- [x] Probability calibration — Platt + isotonic (out-of-fold), isotonic ECE 0.0172
- [x] Calibrator wired into prediction service (`churn_predictor.py`)
- [x] Diagnostics: health (overfit gap), drift (PSI), hallucination (overconfidence)

### Pilot Deployment Tooling
- [x] `scripts/pilot_setup.ps1`, `pilot_start.ps1`, `pilot_stop.ps1`, `pilot_migrate.py`
- [x] No `--reload`, no blanket `taskkill`; PID-tracked; logs to `logs/pilot/`
- [x] Tailscale IP removed — upstream URLs env-configurable (`UPSTREAM_HOST`, `*_SERVICE_URL`)
- [x] Ports/thresholds/feature toggles env-configurable (`CS_`, `FE_`, `PRED_`)

### Real-Data ETL Onboarding
- [x] 5 extraction specs: `customer_master`, `customer_account_map`, `accounts`, `customer_demographics`, `employment_income`
- [x] Per-spec `validation.mandatory_fields` override (non-customer specs)
- [x] `etl/config/pilot_data_config.yaml` — single editable source of truth (tables, churn label, join keys)
- [x] `${source_tables.*}` placeholder resolution in spec loader

### Documentation
- [x] `docs/deployment/PILOT-DATA-ONBOARDING-GUIDE.md` — datasets, table names, full .env reference
- [x] `docs/deployment/REAL-DATA-MAPPING.md` — 17 bank tables → backend model mapping + gap analysis
- [x] `docs/deployment/PILOT-DEPLOYMENT-GUIDE.md` — Windows Server runbook
- [x] `docs/ml/model-training-guide.md` — calibration section + updated metrics

## Backend Services

| Port | Service | Status |
|------|---------|--------|
| `:8080` | API Gateway | pilot-ready |
| `:8002` | Feature Engineering | 21 features |
| `:8003` | Customer State | thresholds env-configurable |
| `:8004` | Prediction Service | XGBoost AUC 0.81 + isotonic calibrator |
| `:8005` | Decision Intelligence | upstream URLs env-configurable |

## Frontend (6 pages wired)

| Page | Route | Data |
|------|-------|------|
| Dashboard Home | `/dashboard/home` | Live KPIs + 500-row ledger |
| Portfolio | `/dashboard/portfolio` | Live KPIs |
| Customer Detail | `/dashboard/customer/:id` | State, health, churn, timeline, markov |
| Model Performance | `/dashboard/models` | AUC-ROC 76.7%, 2 models |
| ETL Pipeline | `/dashboard/etl-pipeline` | Health cards, quality chart, run table |
| ETL Run History | `/dashboard/etl-run-history` | Paginated audit trail |

## Known Gaps / Blockers
- [ ] Transaction history dataset not yet provided (core churn feature source)
- [ ] Balance history dataset not yet provided (`balances_clean` + GROWING state)
- [ ] Real source table names + join keys not yet confirmed in `pilot_data_config.yaml`
- [ ] Clean-table DDL alignment (feature engine expects `activation_date`, `status`, `customer_type`, …)
- [ ] `demographics_clean` PK conflict between Tables 7 & 9 (merge into one spec or add upsert)
- [ ] Customer ID format decision (`C01######` vs `CUST#####`)
- [ ] Branch Manager Dashboard not yet wired
- [ ] Customer names are synthetic — replaced by real data on pilot
