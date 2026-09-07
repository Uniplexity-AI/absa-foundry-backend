# Project Context — Customer Lifecycle Prediction System

## What We're Building

An enterprise-grade AI platform deployed inside a bank's internal infrastructure that:

1. **Predicts customer lifecycles** — Where is each customer in their journey?
2. **Predicts churn** — Which customers are likely to leave?
3. **Predicts customer value** — What is the Customer Lifetime Value (CLV)?
4. **Recommends Next Best Action (NBA)** — What should the Relationship Manager do next?

## Who Uses This

| Role | Use Case |
|------|----------|
| Relationship Managers | Dashboard with NBA recommendations for their customers |
| Branch Managers | Portfolio-level churn and value analytics |
| Data Scientists | Model training, evaluation, and champion/challenger testing |
| Operations | System monitoring and pipeline orchestration |

## Domain Terminology

| Term | Definition |
|------|------------|
| **Customer State** | Discrete behavioural label (Active, At Risk, Dormant, Churned) derived from Markov chain |
| **Health Score** | Composite 0–100 score combining churn probability, CLV, and behavioural state |
| **NBA** | Next Best Action — a ranked recommendation for the Relationship Manager |
| **Champion Model** | The currently deployed production model |
| **Challenger Model** | A new model being evaluated against the champion |
| **Transition Matrix** | Markov chain matrix of state transition probabilities |
| **CLV** | Customer Lifetime Value — predicted total future revenue |
| **Dynamic Extractor** | Pre-ETL engine that unifies multi-table source data via YAML-driven SQL generation |
| **Extraction Spec** | YAML file defining source tables, JOINs, field mappings, filters, and validation rules |
| **DLQ** | Dead-Letter Queue (`audit.rejected_records`) — stores structurally-invalid records with diagnostics |
| **Watermark** | Timestamp tracking the last successful incremental extraction for delta loads |

## Business Constraints

- **GDPR / Data Privacy:** Customer data must be anonymized in non-production environments
- **Audit Trail:** Every prediction and NBA recommendation must be logged
- **Explainability:** All model predictions must have SHAP explanations for compliance
- **Internal Deployment:** Pilot runs on bank-owned Windows Server (no Docker) — services are Uvicorn processes
- **No Internet Access:** Services run in an air-gapped network; all dependencies vendored

## Technical Constraints

- **Python 3.12+** only
- **FastAPI** for all services (no Django, no Flask)
- **PostgreSQL 16** as the single database
- **No Docker in pilot** — PowerShell scripts (`scripts/pilot_*.ps1`) start/stop Uvicorn processes
- **No cloud-native services** — everything runs on bare metal/VMs
- **Redis** is optional but recommended for caching

## Python Environment

- **Virtual environment:** `customer-lifecycle-ai/.venv` (CPython 3.12.0)
- **Package manager:** `uv pip install` (NOT `pip install`)
- **uv-managed Python:** `C:\Users\ADMIN\AppData\Roaming\uv\python\cpython-3.11.13\` — LOCKED, do not use for package installs
- **Activate venv:** `.\.venv\Scripts\Activate.ps1`
- **Service startup:** `uvicorn services.<name>.main:app --host 0.0.0.0 --port <port>`
- **⚠️ NEVER use `curl` in PowerShell — use `Invoke-RestMethod`**
- **⚠️ NEVER `pip install` into uv-managed Python — use `.venv` + `uv pip install`**

### Service Port Map

| Service | Port | Health Check |
|---------|------|-------------|
| Feature Engineering | 8002 | `Invoke-RestMethod http://localhost:8002/health` |
| Customer State (L1) | 8003 | `Invoke-RestMethod http://localhost:8003/health` |
| Prediction (L2) | 8004 | `Invoke-RestMethod http://localhost:8004/health` |
| Decision Intel (L3) | 8005 | `Invoke-RestMethod http://localhost:8005/health` |
| API Gateway | 8080 | `Invoke-RestMethod http://localhost:8080/health` |
