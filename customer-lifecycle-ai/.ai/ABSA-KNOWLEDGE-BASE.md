# ABSA Customer Lifecycle Platform — AI Knowledge Base

**Generated:** 2026-08-07  
**Source:** `.ai/` directories from backend + frontend

---

## 1. Project Overview

### What We're Building

An enterprise-grade AI platform deployed inside ABSA Bank Zambia's internal infrastructure:

1. **Predicts customer lifecycles** — Where is each customer in their journey? (Active → At Risk → Dormant → Churned)
2. **Predicts churn** — Which customers are likely to leave? (XGBoost, AUC 0.77)
3. **Predicts customer value** — Customer Lifetime Value (CLV percentile)
4. **Recommends Next Best Action (NBA)** — What should the RM do? (YAML-configured Decision Engine)

### Who Uses This

| Role | Backend | Frontend Views |
|------|---------|----------------|
| Relationship Managers | Customer Intel + Decision | Customer detail, NBA recommendations |
| Branch Managers | Churn Intel + Forecast | Portfolio overview, branch performance |
| Data Scientists | Model registry | Model management, ETL run history |
| Administrators | Gateway auth | User management, system config |

### Domain Terminology

| Term | Definition |
|------|------------|
| **Customer State** | Discrete label: Active, At Risk, Dormant, Churned (Markov chain) |
| **Health Score** | Composite 0-100 score from churn risk + CLV + behaviour |
| **NBA** | Next Best Action — ranked recommendation for RM |
| **NBO** | Next Best Offer — product recommendation |
| **CLV** | Customer Lifetime Value — predicted total future revenue |
| **Churn Probability** | Likelihood customer will leave within 90 days |
| **Transition Matrix** | Markov 4×4 matrix of state transition probabilities |
| **SHAP** | Feature importance values for explainability |

---

## 2. Current Sprint Status (2026-08-07)

**Status:** Demo-Ready — Backend + Frontend Wired End-to-End

### Backend Services (all 5 running)

| Port | Service | Key Detail |
|------|---------|------------|
| `:8080` | API Gateway | 15 routes, JWT auth, httpx proxies |
| `:8002` | Feature Engineering | 22 features, 4,998 customers |
| `:8003` | Customer State (L1) | 4,998 classified, Markov matrix |
| `:8004` | Prediction (L2) | Churn AUC 0.77, health scores |
| `:8005` | Decision Intelligence (L3) | 9 engines, YAML-configured, 34/34 tests |

### Frontend (6 pages wired)

| Page | Route | Backend APIs |
|------|-------|-------------|
| Dashboard Home | `/dashboard/home` | `/customers/portfolio` + `/customers` |
| Portfolio | `/dashboard/portfolio` | `/customers/portfolio` |
| Customer Detail | `/dashboard/customer/:id` | `/customers/{id}`, `/timeline`, `/predictions/{id}/churn`, `/health`, `/markov-matrix` |
| Model Performance | `/dashboard/models` | `/models` |
| ETL Pipeline | `/dashboard/etl-pipeline` | `/etl/runs` |
| ETL Run History | `/dashboard/etl-run-history` | `/etl/runs` |

### Pinia Stores

| Store | API Endpoints | Pages |
|-------|-------------|-------|
| `customerStore.js` | `/customers/portfolio`, `/customers`, `/{id}`, `/{id}/timeline` | DashboardHome, Portfolio, CustomerDetail |
| `predictionStore.js` | `/predictions/{id}/churn`, `/health`, `/markov-matrix` | CustomerDetail |
| `modelsStore.js` | `/models` | Models |
| `etlStore.js` | `/etl/runs` | EtlPipeline, ETLRunHistory |

### Known Gaps
- [ ] Branch Manager Dashboard not yet wired
- [ ] Customer names are synthetic "Customer 00001"
- [ ] Account number/tenure/RM show `...` placeholder
- [ ] Churn % and CLV show `--` in ledger table (needs prediction enrichment batch)

---

## 3. Architecture

### 3-Layer AI System

```
┌─────────────────────────────────────────────────────────────┐
│                   API Gateway (:8080)                        │
│         Auth / RBAC / Rate Limit / API Key / Logging         │
└──────┬──────────┬──────────┬──────────┬─────────────────────┘
       │          │          │          │
 ┌─────▼────┐ ┌──▼─────┐ ┌─▼───────┐ ┌─▼──────────┐
 │ Layer 1  │ │Layer 2 │ │Layer 3  │ │ Supporting  │
 │ Customer │ │Predict.│ │Decision │ │ Services    │
 │ State    │ │Service │ │Intel.   │ │             │
 │ (:8003)  │ │(:8004) │ │(:8005)  │ │ (:8002)     │
 │          │ │        │ │         │ │ Features    │
 │ Markov   │ │XGBoost │ │9 engines│ │ ETL         │
 │ Chain    │ │Churn   │ │YAML cfg │ │ PostgreSQL  │
 └──────────┘ └────────┘ └─────────┘ └─────────────┘
```

### Decision Intelligence Platform (v3.0)

6 engines sharing a common DecisionContext:

| Engine | Question | Capabilities |
|--------|----------|-------------|
| **Churn Intelligence** | Why are customers leaving? | Root cause, segment analysis, branch performance |
| **Customer Intelligence** | What's happening to this customer? | Health trajectory, lifecycle stage, alerts |
| **Decision Engine** | What should the bank do? | NBA, routing, strategy, approval workflow |
| **Recommendation Engine** | What product to offer? | NBO, cross-sell, upsell, campaign mapping |
| **Forecast Engine** | What will happen? | Churn forecast, revenue at risk, RM workload |
| **Insight Engine** | What does this mean? | LLM explanations, executive summaries (Phase 3) |

### Frontend Component Tree

```
App.vue
└── DashboardLayout
    ├── Sidebar (2 groups: CUSTOMER LIFECYCLE + AI & DATA)
    ├── TopBar (search, period selector, user menu)
    └── <router-view>
        ├── DashboardHome       → /dashboard/home
        ├── PortfolioOverview   → /dashboard/portfolio
        ├── CustomerDetail      → /dashboard/customer/:id
        ├── BranchManager       → /dashboard/branch-manager (not wired)
        ├── Models              → /dashboard/models
        ├── EtlPipeline         → /dashboard/etl-pipeline
        └── ETLRunHistory       → /dashboard/etl-run-history
```

### Sidebar Structure

```
CUSTOMER LIFECYCLE
  ▣  Dashboard
  ▨  Portfolio
  ⌂  Branch Manager

AI & DATA
  ◫  Model Performance
  ⛭  ETL Pipeline
  ◷  Run History

──
  ⏻  Logout
```

---

## 4. Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend Language** | Python 3.12 (in `.venv`) |
| **API** | FastAPI + Pydantic v2 |
| **ML** | XGBoost (churn AUC 0.77), LightGBM (ranking MAE 0.0015), SHAP |
| **Database** | PostgreSQL 16 + psycopg2 (sync) + asyncpg (async) |
| **Cache** | Redis |
| **HTTP** | httpx (upstream proxy) |
| **Config** | PyYAML (all rules/strategies/catalogs) |
| **Package Manager** | uv pip install |
| **Frontend** | Vue 3 (Composition API) + Vite + Pinia + Tailwind CSS |
| **HTTP Client** | Axios with JWT interceptor |

---

## 5. Coding Standards

### Python

- Python 3.12+ syntax (`str | None`, not `Optional[str]`)
- Type hints on ALL function signatures
- Pydantic v2 for all schemas
- Google-style docstrings
- Repository pattern for data access (no raw SQL in services)
- All business logic in `app/services/`, routes only delegate
- Check `shared/` first before creating new code

### Vue 3

- `<script setup>` composition API
- Component order: Imports → Props/Emits → Composables → State → Computed → Methods → Lifecycle → Watchers
- PascalCase multi-word components
- Pinia stores with `defineStore('name', () => { ... })` setup syntax

---

## 6. Key Commands

### Start All Backend Services

```powershell
$root = "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai"
$py = "$root\.venv\Scripts\python.exe"
$env:PYTHONPATH = $root

taskkill /F /IM python.exe 2>$null; Start-Sleep 2

# Gateway :8080
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","gateway.main:create_app","--factory","--host","0.0.0.0","--port","8080","--reload" -WorkingDirectory $root

# Feature :8002
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8002","--reload" -WorkingDirectory "$root\services\feature-engineering-service"

# State :8003
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8003","--reload" -WorkingDirectory "$root\services\customer-state-service"

# Prediction :8004
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8004","--reload" -WorkingDirectory "$root\services\prediction-service"

# Decision :8005
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8005","--reload" -WorkingDirectory "$root\services\decision-intelligence-service"
```

### Verify All Services

```powershell
netstat -ano | findstr "LISTENING" | findstr "8002 8003 8004 8005 8080"
```

### Key API Calls

```powershell
# Portfolio
curl "http://localhost:8080/api/v1/customers/portfolio?as_of_date=2026-07-27"

# Customer detail
curl "http://localhost:8080/api/v1/customers/CUST00042?as_of_date=2026-07-27"

# Churn probability
curl "http://localhost:8080/api/v1/predictions/CUST00042/churn?as_of_date=2026-07-27"

# Health score
curl "http://localhost:8080/api/v1/predictions/CUST00042/health?as_of_date=2026-07-27"

# Model registry
curl "http://localhost:8080/api/v1/models"

# ETL dashboard
curl "http://localhost:8080/api/etl/runs?limit=3"
```

### Start Frontend

```powershell
cd "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-frontend"
npm run dev
# → http://localhost:3000
```

### Installing Packages

```powershell
cd "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai"
.\.venv\Scripts\Activate.ps1
uv pip install <package-name>
```

---

## 7. Gateway API Routes

| Prefix | Purpose | Backend Service |
|--------|---------|----------------|
| `/auth/*` | Login, refresh, logout | Gateway internal |
| `/admin/*` | User/role management | Gateway internal |
| `/api/v1/customers/*` | Portfolio, list, detail, timeline | State Service (:8003) |
| `/api/v1/predictions/*` | Churn, health, markov-matrix | Prediction (:8004) + State (:8003) |
| `/api/v1/models` | Model registry | Prediction (:8004) |
| `/api/etl/*` | ETL runs, dashboard | PostgreSQL etl_clean |
| `/features/*` | Feature compute, snapshots | Feature (:8002) |

---

## 8. Key Architecture Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| ADR-001 | 6 engines, one platform, shared foundation | DecisionContext built once, consumed by all |
| ADR-002 | Churn Intelligence is portfolio-level | Per-customer churn is Prediction Service (L2) |
| ADR-003 | Decision routing by stakeholder | Not every decision needs human intervention |
| ADR-004 | Forecast separate from predictions | Enables scenario modeling |
| ADR-005 | LLM explains, never decides | Deterministic engines produce decisions |
| ADR-006 | YAML for all rules/catalogs/strategies | Audit-friendly, hot-reloadable |
| ADR-007 | Decision Memory for closed-loop | Every decision → execution → outcome tracked |

---

## 11. .ai Directory Structure

### Backend `.ai/` (customer-lifecycle-ai)

```
.ai/
├── README.md                 # AI agent entry point — read this first
├── project-context.md        # What we're building, who uses it, domain terms
├── current-sprint.md         # Live sprint status, completed/remaining tasks
├── architecture.md           # 3-Layer AI system design, service boundaries
├── coding-standards.md       # Python style, Pydantic, repository pattern
├── terminal-patterns.md      # 18+ pre-flight checks, PowerShell/uv/DB patterns
├── MEMORIES.md                # Persistent agent memory bank — rules + learning ledger
├── ABSA-KNOWLEDGE-BASE.md    # THIS FILE — consolidated reference
├── skills/
│   ├── add-api-endpoint.md   # FastAPI route creation guide
│   ├── add-database-model.md # DB schema/model creation guide
│   ├── add-feature.md        # Feature engineering guide
│   ├── ml-model-training.md  # XGBoost/LightGBM training guide
│   └── writing-tests.md      # Pytest patterns and conventions
└── standards/
    └── conventions.md        # Internal naming and structure conventions
```

### Frontend `.ai/` (absa-foundry-frontend)

```
.ai/
├── README.md                 # AI agent entry point
├── project-context.md        # What we're building, tech stack, domain terms
├── current-sprint.md         # Live sprint status, store→API mapping
├── architecture.md           # Component tree, routing, data flow, Pinia stores
├── coding-standards.md       # Vue 3 conventions, naming, component structure
└── skills/
    ├── absa-brand-colour.md  # ABSA colour guidelines
    └── rm-dashboard-colour-mapping.md  # Dashboard colour scheme

### Backend
```
customer-lifecycle-ai/
├── gateway/           API Gateway (routes, middleware, services)
├── services/
│   ├── customer-state-service/       Layer 1: Markov chain
│   ├── prediction-service/           Layer 2: XGBoost churn
│   ├── decision-intelligence-service/ Layer 3: 9 engines
│   └── feature-engineering-service/  Feature store
├── shared/            Shared config, database, auth models
├── etl/               ETL extraction, repositories
├── docs/architecture/ decision-intelligence-platform-v3.md
└── .ai/               AI knowledge base
```

### Frontend
```
absa-foundry-frontend/
├── src/
│   ├── views/         Page components
│   ├── stores/        Pinia stores (customerStore, predictionStore, etc.)
│   ├── services/      API clients (api.js, etlApi.js)
│   ├── components/    Reusable (absa/, layouts/, ui/)
│   └── router/        Vue Router config
└── .ai/               AI knowledge base
```

---

## 10. Demo Flow (5 minutes)

| Step | Page | Talking Point |
|------|------|---------------|
| 1 | `/dashboard/home` | "4,998 customers, 46% at risk, 48% dormant — real ML pipeline" |
| 2 | Click At Risk KPI | "Filters to 2,291 customers needing attention" |
| 3 | Click a row | "Health score, churn %, state timeline from Markov chain" |
| 4 | `/dashboard/models` | "Champion churn model: AUC 76.7%, 2 registered models" |
| 5 | `/dashboard/etl-pipeline` | "14 pipeline runs, 100% quality, 15K rows, full audit trail" |
