# Absa Bank Zambia — Frontend Functional Requirements v2.0
## Customer Lifecycle Prediction System · Enterprise Phase · August 6, 2026

> **Supersedes:** FRONTEND-REQUIREMENTS.md (PoC v1.0, July 20, 2026)
> **Status:** Draft for Frontend Dev Team Review
> **Backend Reference:** Decision Intelligence Service v2.0 TDD + Database Design Spec v2.1

---

## 1. What's New in v2.0

| # | Change | Rationale |
|---|--------|-----------|
| 1 | **Branch Manager Dashboard** — promoted from deferred | Layer 1-3 services now live; branch-level aggregation ready |
| 2 | **Data Scientist: Full Model Ops** — champion/challenger, feature drift, SHAP waterfall | Prediction Service operational; model registry exists |
| 3 | **NBA with LLM Explanations** — human-readable SHAP-derived reasoning | Decision Intelligence Service v1.0 LLM pipeline live |
| 4 | **Campaign Management** — full campaign lifecycle UI | `campaigns` schema exists in DB v2.1; Campaign Engine operational |
| 5 | **Customer Journey Visualizer** — multi-touchpoint journey mapping | v2.0 target: "Customer journey optimization across multiple interactions" |
| 6 | **Feedback Loop / Action Outcomes** — measure RM actions → retention lift | Closed-loop system required for RL (v1.1 roadmap) |
| 7 | **Priority Queue** — RM daily action queue ranked by Priority Score | Priority Engine operational; replaces ad-hoc table sorting |
| 8 | **PDF Export** — one-page RM meeting summary (promoted from deferred) | Operations requirement |
| 9 | **WebSocket Notifications** — real-time alerts via WS | System maturity; Redis pub/sub backend ready |
| 10 | **Full Audit Trail Viewer** — searchable, filterable, exportable | Regulatory compliance for Bank of Zambia |

---

## 2. Architecture & Technology Constraints (Unchanged)

| Constraint | Requirement |
|---|---|
| **Framework** | Vue 3 (Composition API) + TypeScript |
| **Build Tool** | Vite |
| **State Management** | Pinia |
| **Router** | Vue Router 4 |
| **UI Components** | Custom components or vendored PrimeVue (no npm CDN — bank air-gapped) |
| **Charts** | Chart.js via vue-chartjs (vendored) |
| **Deployment** | Internal bank network — no internet, no CDN, on-premise Ubuntu server, Nginx |
| **Backend API** | FastAPI Gateway (port 8080) — consumes 3-layer AI services |
| **Authentication** | Internal LDAP/Active Directory (no social logins) |
| **Browser** | Chromium-based only (bank-standard locked-down desktops) |
| **Screen** | 1920×1080 minimum — desktop only |

---

## 3. User Roles & Access Control (v2.0 Updated)

### 3.1 Role Matrix

| Role | v2.0 Permissions |
|---|---|
| **Relationship Manager** | View own portfolio, drill into customers, see NBA + LLM explanations, log actions, mark outcomes, view daily priority queue |
| **Branch Manager** | View all branch customers, portfolio analytics, churn risk heatmap, team performance, campaign performance, churn forecast |
| **Data Scientist** | Model performance dashboards, champion/challenger A/B, SHAP waterfall, feature drift, prediction logs, model registry, retraining triggers |
| **Operations** | ETL pipeline status, data quality scores, audit logs, system health, service status dashboard |
| **Admin** | User provisioning, role assignment, API key management, session management, full audit log access |

### 3.2 Authentication Flow (Unchanged)

- Login via LDAP username/password
- Session timeout: 30 minutes inactivity (configurable)
- Role determined by LDAP group membership
- No self-registration — accounts provisioned by IT
- JWT + refresh token rotation (15-min access, 7-day refresh)

---

## 4. Screens — Relationship Manager (v2.0 Enhanced)

### 4.1 RM Dashboard (Landing Page)

#### FR-V2-DASH-01: Summary Cards (Enhanced)
- 5 KPI cards: Total Customers, At Risk count + %, Dormant count + %, Actions Due Today, **Actions Completed This Week** (new)
- Each card clickable — filters the customer table below
- At Risk % colour-coded: green <5%, amber 5-15%, red >15%

#### FR-V2-DASH-02: Priority Queue (NEW)
- **Replaces** simple customer table sorting
- Ranked list of top 20 customers by Decision Intelligence Priority Score (0-100)
- Each row shows: Priority Rank, Customer Name, State, Health Score, Churn %, NBA Recommendation, Priority Score bar, **Estimated Revenue Impact (ZMW)** (new)
- Auto-refreshed after nightly batch; manual refresh available
- Priority formula displayed as tooltip: Business Value × Urgency × Acceptance Probability × Retention Impact

#### FR-V2-DASH-03: Priority Alerts (Enhanced)
- Top 5 alerts ranked by: Priority Score drop >15 pts, Health Score drop >20 pts, state transition to At Risk/Dormant/Churned, significant CLV change >25%
- Each alert links to customer detail
- Alerts persist until acknowledged (timestamp + RM ID)
- **NEW: Alert severity badges** — Critical (red), High (amber), Info (blue)

#### FR-V2-DASH-04: Customer Table (Enhanced)
- Columns: Priority Rank, Customer Name, State (icon + label), Health Score (gauge), Churn % (colored), CLV (ZMW), NBA (truncated), **Last Contact Date** (new), **Days Since Last Action** (new)
- Default sort: Priority Score descending
- Search: name, account number, customer ID, **NBA type** (new)
- Filter: state, branch, product type, **priority tier** (new: Critical/High/Medium/Low)
- Pagination: 25 rows/page
- Click row → Customer Detail

#### FR-V2-DASH-05: Period Selector
- Dropdown: Current Snapshot vs historical dates (back to earliest feature snapshot)
- Default: Latest

### 4.2 Customer Detail Screen (v2.0 Enhanced)

#### FR-V2-CUST-01: Customer Profile Card
- Customer name, account number, branch, segment, tenure, assigned RM
- **NEW: Customer Journey Stage** — lifecycle stage indicator (Onboarding / Engaged / Mature / Declining / At Risk)
- Link to core banking system (external)

#### FR-V2-CUST-02: AI Health Score Gauge
- Circular gauge: Health Score (0-100)
- Colour: green 70+, amber 40-69, red <40
- Component scores: Churn Risk, CLV Percentile, Behavioural Score
- Trend indicator: up/down arrow + Δ since last period (30 days)

#### FR-V2-CUST-03: State Timeline (Enhanced)
- Horizontal timeline: state changes over time
- States: Active (green), At Risk (amber), Dormant (grey), Churned (red)
- Hover: transition reason, trigger features, date
- **NEW: Markov next-state prediction overlay** — dotted line showing predicted next state with probability

#### FR-V2-CUST-04: SHAP Waterfall (PROMOTED from PoC deferred)
- Full SHAP waterfall chart showing feature contributions to current churn prediction
- Red bars: features pushing toward churn; Blue bars: features pushing away from churn
- Base value + cumulative contributions = final prediction
- **NEW: LLM-generated explanation** — natural language sentence below chart (e.g., "This customer's churn risk is elevated primarily due to 45 days of inactivity and a 32% drop in average transaction value, partially offset by strong product holdings.")

#### FR-V2-CUST-05: NBA Recommendations (Enhanced)
- Ranked list: 3-5 Next Best Actions
- Each shows: priority rank, action description, **LLM explanation** (1-2 sentences), predicted impact (High/Medium/Low), confidence %, estimated revenue impact (ZMW), estimated churn reduction (%), **recommended channel** (new: RM Call / Branch Visit / Digital / SMS), associated campaign name
- **NEW: Alternative Actions** — expandable section showing 2-3 alternative actions ranked below the top recommendation
- **[Log Action]** button opens form: action type dropdown, channel, notes, outcome dropdown (Contacted / Not Reachable / Declined / Accepted / Pending)
- Logged actions stored with: RM ID, customer ID, action taken, channel, timestamp, NBA recommendation ID, campaign ID

#### FR-V2-CUST-06: Action History (Enhanced)
- Reverse-chronological action log
- Filterable by: action type, date range, **outcome** (new)
- Columns: date, action, channel, outcome (colored badge), RM name, NBA reference
- **NEW: Outcome trend** — small inline chart showing action outcomes over time (Accepted/Declined/Pending ratio)

#### FR-V2-CUST-07: Customer Journey Map (NEW)
- Visual Sankey or flow diagram of customer's product holdings and interaction touchpoints
- Nodes: Products held (Savings, Current, Loan, Card, Insurance, etc.)
- Edges: Interaction channels used (Branch, Digital, ATM, RM Call)
- Timeline scrubber to view journey evolution over months

---

## 5. Screens — Branch Manager (PROMOTED from Deferred)

### 5.1 Branch Manager Dashboard

#### FR-V2-BM-01: Branch KPIs
- Aggregate KPI cards: Total Customers, At Risk %, Dormant %, Churn Rate (monthly), **Avg Portfolio Health Score** (new), **Actions Completion Rate** (new)
- Δ indicators vs previous month (green up / red down)
- Peer branch comparison (anonymised ranking: "Your branch: 3rd of 12")

#### FR-V2-BM-02: Team Performance Table
- Columns: RM Name, Customers Assigned, At Risk %, Actions Logged (month), **Actions Completed** (new), **Completion Rate %** (new), Avg Health Score, **Avg Days to Contact** (new)
- Sort by any column
- Click RM → filtered view of their portfolio
- **NEW: Performance trend sparkline** per RM (last 6 weeks)

#### FR-V2-BM-03: Churn Forecast (Enhanced)
- Projected churn count: next 30/60/90 days
- Breakdown by segment (Premium, Mass Market, SME)
- **NEW: Confidence bands** on forecast chart
- **NEW: "What-if" slider** — simulate impact of 10%/25%/50% intervention rate on projected churn

#### FR-V2-BM-04: Churn Risk Heatmap (Enhanced)
- Grid: rows = top 50 at-risk customers, columns = weeks
- Cell colour: churn probability gradient (green→red)
- Click cell → customer detail
- **NEW: Segment filter** — Premium / Mass Market / SME tabs

#### FR-V2-BM-05: Campaign Performance (NEW)
- Active campaigns table: Campaign Name, Target Segment, Customers Targeted, Responses, Conversion Rate, Revenue Generated
- Campaign detail drill-down: response timeline, segment breakdown, top-performing RMs
- Compare campaigns side-by-side

---

## 6. Screens — Data Scientist (PROMOTED + Enhanced)

### 6.1 Model Operations Dashboard

#### FR-V2-DS-01: Model Metrics (Enhanced)
- AUC-ROC, Precision, Recall, F1, Log Loss for champion model
- Time-series chart: 30/60/90 day trends
- Threshold alert lines (configurable per metric)
- **NEW: Segment-level metrics** — performance broken down by customer segment

#### FR-V2-DS-02: Champion vs Challenger (PROMOTED)
- Side-by-side comparison cards: Model Name, Version, Traffic Split %, Win Rate, Statistical Significance (p-value)
- Metric comparison table: AUC-ROC, Precision, Recall, F1 — champion vs challenger
- **[Promote Challenger]** button with confirmation dialog
- Traffic split slider (0-100%) for A/B test configuration

#### FR-V2-DS-03: Feature Drift Monitor (Enhanced)
- Table: Feature Name, Training Distribution (histogram thumbnail), Current Distribution (histogram thumbnail), PSI Score, Drift Status (OK/Warning/Critical)
- Threshold: PSI >0.1 warning, >0.25 critical (configurable)
- **NEW: Drift timeline** — per-feature PSI trend over last 30 days
- **NEW: Automated alert** — email/Slack when drift exceeds threshold (configurable)

#### FR-V2-DS-04: Prediction Log Browser (Enhanced)
- Searchable table: Timestamp, Customer ID, Prediction Type (Churn/CLV/Health), Probability, SHAP Top 3 Features, Model Version
- Filter by: date range, prediction type, model version, **segment** (new)
- Export to CSV
- **NEW: Click row → full SHAP waterfall + LLM explanation for that prediction**

#### FR-V2-DS-05: Model Registry (NEW)
- Table: Model Name, Version, Type (XGBoost/LightGBM), Status (Champion/Challenger/Archived), Deployed Date, Training Date, Training Rows, AUC-ROC
- **[Register New Model]** workflow: upload model artifact → validate → deploy as challenger
- Model lineage: version tree showing training data, hyperparameters, features used

---

## 7. Screens — Operations (Enhanced)

#### FR-V2-OPS-01: ETL Run History (Enhanced)
- Table: Run ID, Batch ID, Duration, Rows Received/Valid/Loaded/Rejected, Quality Score, Status
- Status icons: Completed ✓, Failed ✗, Running ⟳
- Click row → detailed audit record with step-by-step timing breakdown
- **NEW: Run comparison** — select two runs and diff the results

#### FR-V2-OPS-02: Data Quality Dashboard (Enhanced)
- Time-series chart: quality_score over recent runs
- Threshold line at 90% (configurable)
- Breakdown: rejection reasons by run (stacked bar chart)
- **NEW: Schema drift alerts** — new/removed columns detected in source data

#### FR-V2-OPS-03: System Health (Enhanced)
- Service status cards: PostgreSQL, Redis, Feature Service (8002), State Service (8003), Prediction Service (8004), Decision Intel (8005), API Gateway (8080)
- Per service: Uptime %, last heartbeat, response time (ms), error rate (last hour)
- Green/Amber/Red status
- **NEW: Dependency graph** — visual showing which services depend on which

#### FR-V2-OPS-04: Full Audit Trail (NEW)
- Searchable, filterable, sortable table of all auditable actions
- Columns: Timestamp, User ID, Role, Action Type, Customer ID, Details (JSON expandable), IP Address
- Filter by: date range, user, role, action type, customer
- Export to CSV/PDF
- Retention policy indicator: "Records available from [date] to [date]"

---

## 8. Common UI Components (v2.0 Enhanced)

#### FR-V2-COM-01: Navigation
- Persistent left sidebar with role-based menu items:
  - **RM:** Dashboard, Priority Queue, My Customers, Portfolio
  - **Branch Manager:** Dashboard, Team Performance, Campaigns, Portfolio Analytics
  - **Data Scientist:** Model Ops, Feature Drift, Prediction Logs, Model Registry
  - **Operations:** ETL Pipeline, Data Quality, System Health, Audit Trail
  - **Admin:** User Management, API Keys, Sessions, Audit Trail
- Breadcrumb trail on every screen
- User avatar (initials) + name + role in top-right corner with logout dropdown

#### FR-V2-COM-02: Global Search
- Search bar (Ctrl+K shortcut): customer name, account number, customer ID
- Results dropdown: name, state icon, health score, branch, priority score
- Selecting → Customer Detail

#### FR-V2-COM-03: Notifications (Enhanced)
- Bell icon with unread count badge
- Dropdown: recent alerts with severity badge
- **NEW: WebSocket real-time** — alerts appear without page refresh
- Click → navigate to relevant screen
- "Mark all read" button

#### FR-V2-COM-04: Export
- Any table → CSV export
- Customer Detail → **PDF export** (one-page RM meeting summary) — PROMOTED
- PDF includes: customer profile, health score gauge, top NBA, SHAP summary, action history (last 5)

#### FR-V2-COM-05: Audit Logging (Enhanced)
- Every frontend action that modifies data writes to audit log
- Fields: timestamp, user ID, role, action type, customer ID, details, IP, session ID
- **NEW: Frontend action categories**: VIEW, CREATE, UPDATE, DELETE, EXPORT, LOGIN, LOGOUT

#### FR-V2-COM-06: Dark Mode (NEW)
- Toggle in user menu: Light / Dark / System
- Persisted to localStorage
- All charts, gauges, tables respect theme

---

## 9. API Contract — Frontend to Backend (v2.0)

### 9.1 Authentication

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| A1 | `/auth/login` | POST | Public | LDAP login → JWT + refresh token |
| A2 | `/auth/refresh` | POST | Authenticated | Rotate access token |
| A3 | `/auth/logout` | POST | Authenticated | Blacklist token, revoke refresh |
| A4 | `/auth/me` | GET | Authenticated | Current user profile + roles |

### 9.2 Customers & Features

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| C1 | `/api/customers` | GET | RM, BM | List RM's customers with latest features, state, health score, priority score |
| C2 | `/api/customers/{customer_id}` | GET | RM, BM, DS | Full customer 360: profile + latest features + state + predictions + NBA |
| C3 | `/api/customers/{customer_id}/history` | GET | RM, BM, DS | Feature snapshots over time (date range) |
| C4 | `/api/customers/{customer_id}/timeline` | GET | RM, BM, DS | State transition timeline with trigger reasons |
| C5 | `/api/customers/{customer_id}/journey` | GET | RM, BM | Customer journey: touchpoints, channels, product events |

### 9.3 Predictions & Explainability

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| P1 | `/api/customers/{customer_id}/predictions` | GET | RM, BM, DS | Latest churn prob, CLV, health score with component breakdown |
| P2 | `/api/customers/{customer_id}/predictions/history` | GET | DS | Prediction history over time for a customer |
| P3 | `/api/customers/{customer_id}/shap` | GET | RM, BM, DS | SHAP waterfall values + LLM explanation for latest prediction |
| P4 | `/api/customers/{customer_id}/markov/predict` | GET | RM, BM, DS | Markov next-state prediction with probabilities |

### 9.4 Decision Intelligence (NBA)

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| D1 | `/api/customers/{customer_id}/nba` | GET | RM, BM | Ranked NBA recommendations with LLM explanations |
| D2 | `/api/customers/{customer_id}/nba/alternatives` | GET | RM, BM | Alternative actions (ranked 2-4 below top recommendation) |
| D3 | `/api/customers/{customer_id}/priority` | GET | RM, BM | Priority score breakdown: Value × Urgency × Acceptance × Retention Impact |

### 9.5 Actions & Feedback Loop

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| F1 | `/api/customers/{customer_id}/actions` | GET | RM, BM | Action history (paginated, filterable by type/date/outcome) |
| F2 | `/api/customers/{customer_id}/actions` | POST | RM | Log new action taken by RM |
| F3 | `/api/customers/{customer_id}/actions/{action_id}/outcome` | PATCH | RM | Update action outcome (Contacted / Not Reachable / Accepted / Declined) |
| F4 | `/api/rm/{rm_id}/actions/summary` | GET | RM, BM | Action summary stats: total, completed, pending, completion rate |

### 9.6 Priority Queue

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| Q1 | `/api/rm/{rm_id}/queue` | GET | RM | Daily priority queue: top N customers ranked by Priority Score |
| Q2 | `/api/rm/{rm_id}/queue/stats` | GET | RM | Queue stats: critical/high/medium/low counts |

### 9.7 Alerts & Notifications

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| N1 | `/api/alerts` | GET | RM, BM | Unacknowledged alerts for current user |
| N2 | `/api/alerts/{alert_id}/acknowledge` | PATCH | RM, BM | Acknowledge an alert (timestamp + user ID) |
| N3 | `/ws/notifications` | WS | Authenticated | Real-time notification stream (state changes, health drops, NBA expiry) |

### 9.8 Branch Manager

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| B1 | `/api/branch/{branch_code}/portfolio` | GET | BM | Branch-level portfolio aggregation |
| B2 | `/api/branch/{branch_code}/kpis` | GET | BM | Branch KPIs with month-over-month deltas |
| B3 | `/api/branch/{branch_code}/team` | GET | BM | RM team performance table |
| B4 | `/api/branch/{branch_code}/churn-forecast` | GET | BM | Projected churn: 30/60/90 days with confidence bands |
| B5 | `/api/branch/{branch_code}/heatmap` | GET | BM | Churn risk heatmap data (customers × weeks) |

### 9.9 Campaigns

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| G1 | `/api/campaigns` | GET | BM, DS | List active campaigns with performance metrics |
| G2 | `/api/campaigns/{campaign_id}` | GET | BM, DS | Campaign detail: response timeline, segment breakdown, RM performance |
| G3 | `/api/campaigns/{campaign_id}/compare` | GET | BM, DS | Side-by-side campaign comparison data |

### 9.10 Model Operations (Data Scientist)

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| M1 | `/api/models/performance` | GET | DS | Champion model metrics (AUC-ROC, Precision, Recall, F1) |
| M2 | `/api/models/performance/trend` | GET | DS | Metric time-series: last 30/60/90 days |
| M3 | `/api/models/performance/by-segment` | GET | DS | Model metrics broken down by customer segment |
| M4 | `/api/models/champion-challenger` | GET | DS | Side-by-side comparison: traffic split, win rate, significance |
| M5 | `/api/models/registry` | GET | DS | Model registry: all versions, statuses, dates, metrics |
| M6 | `/api/models/registry` | POST | DS | Register new model version |
| M7 | `/api/models/registry/{model_id}/promote` | POST | DS | Promote challenger → champion |

### 9.11 Feature Drift

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| R1 | `/api/models/drift` | GET | DS | Feature drift table: PSI scores, distributions, status |
| R2 | `/api/models/drift/{feature_name}/trend` | GET | DS | Single feature PSI trend over time |

### 9.12 Prediction Logs

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| L1 | `/api/predictions/logs` | GET | DS | Searchable prediction log browser (paginated, filterable) |
| L2 | `/api/predictions/logs/export` | GET | DS | Export prediction logs as CSV |

### 9.13 ETL Operations

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| E1 | `/api/etl/runs` | GET | Ops | Paginated ETL run history with dashboard KPIs |
| E2 | `/api/etl/runs/{run_id}` | GET | Ops | Detailed run audit: step timings, row counts, errors |
| E3 | `/api/etl/runs/compare` | GET | Ops | Diff two ETL runs |
| E4 | `/api/etl/quality/trend` | GET | Ops | Data quality score time-series |
| E5 | `/api/etl/quality/rejections` | GET | Ops | Rejection reason breakdown by run |

### 9.14 System Health

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| H1 | `/api/system/health` | GET | Ops, Admin | All service statuses: uptime, heartbeat, response time, error rate |
| H2 | `/api/system/health/{service_name}` | GET | Ops, Admin | Single service detailed health |

### 9.15 Audit Trail

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| U1 | `/api/audit/logs` | GET | Admin, Ops | Full audit trail (paginated, filterable, searchable) |
| U2 | `/api/audit/logs/export` | GET | Admin, Ops | Export audit logs as CSV |

### 9.16 Admin

| # | Endpoint | Method | Role | Purpose |
|---|----------|--------|------|---------|
| X1 | `/admin/users` | GET/POST | Admin | List / create users |
| X2 | `/admin/users/{user_id}/roles` | PATCH | Admin | Update user roles |
| X3 | `/admin/api-keys` | GET/POST | Admin | List / create API keys for service-to-service auth |
| X4 | `/admin/api-keys/{key_id}/revoke` | POST | Admin | Revoke an API key |
| X5 | `/admin/sessions` | GET | Admin | Active user sessions |

---

## 10. WebSocket Protocol (NEW in v2.0)

### 10.1 Connection

```
ws://{host}:8080/ws/notifications
Headers: Authorization: Bearer {jwt}
```

### 10.2 Server → Client Messages

```json
{
  "type": "alert",
  "severity": "critical|high|info",
  "title": "Health Score Drop",
  "message": "Customer John Doe health score dropped from 72 to 48",
  "customer_id": "CUST00123",
  "timestamp": "2026-08-06T14:30:00Z",
  "alert_id": "ALT-0042"
}
```

### 10.3 Message Types

| Type | Trigger | Navigation Target |
|------|---------|-------------------|
| `state_change` | Customer transitions to At Risk/Dormant/Churned | Customer Detail |
| `health_drop` | Health Score drops >20 points in one period | Customer Detail |
| `nba_expiry` | NBA recommendation expires without action | Customer Detail → NBA tab |
| `batch_complete` | Nightly batch prediction completes | Dashboard |
| `model_drift` | Feature drift exceeds threshold (DS only) | Feature Drift Monitor |
| `etl_failure` | ETL pipeline run fails (Ops only) | ETL Run History |

---

## 11. v2.0 Scope Boundaries

### Included in v2.0
- ALL v1.0 PoC features (already built)
- Branch Manager Dashboard (promoted from deferred)
- Data Scientist: Full Model Ops (promoted from deferred)
- SHAP waterfall + LLM explanations
- Priority Queue with Priority Score
- Campaign Management basic views
- Customer Journey visualizer (Sankey/flow)
- Action outcome tracking (feedback loop)
- PDF export for customer summary
- WebSocket real-time notifications
- Full audit trail viewer
- Dark mode
- All 74 API endpoints documented above

### Deferred to v2.1+
- Reinforcement Learning feedback UI (adaptive action selection)
- Multi-armed bandit experiment configuration UI
- Real-time streaming dashboard (Kafka-backed)
- Mobile/responsive layout
- RBAC fine-grained permission editor UI
- Custom dashboard builder (drag-and-drop widgets)
- Voice-to-text action logging
- Offline/PWA full support

---

## 12. Frontend State Management (Pinia Stores — v2.0)

| Store | Responsibility | Key State |
|-------|---------------|-----------|
| `useAuthStore` | Authentication + session | user, roles, token, refreshToken, isAuthenticated |
| `useCustomerStore` | Customer data | customers, selectedCustomer, filters, pagination |
| `usePredictionStore` | Predictions + SHAP | predictions, shapValues, llmExplanation, healthScore |
| `useNBAStore` | NBA recommendations | recommendations, alternatives, priorityScores |
| `useActionStore` | Action logging + outcomes | actions, outcomes, actionStats |
| `useQueueStore` | Priority queue | queue, queueStats |
| `useAlertStore` | Alerts + WebSocket | alerts, unreadCount, wsConnection |
| `useBranchStore` | Branch manager data | branchKPIs, teamPerformance, churnForecast, heatmap |
| `useModelStore` | Model operations | modelMetrics, championChallenger, modelRegistry, driftData |
| `useCampaignStore` | Campaign management | campaigns, campaignDetail |
| `useETLStore` | ETL operations | etlRuns, qualityTrend, rejectionBreakdown |
| `useSystemStore` | System health | serviceStatuses, dependencyGraph |
| `useAuditStore` | Audit trail | auditLogs, filters |
| `useUIStore` | UI preferences | theme (light/dark), sidebarCollapsed, notifications |

---

## 13. API Response Envelope (Standard)

All v2.0 API responses follow a consistent envelope:

```json
{
  "data": { ... },
  "meta": {
    "page": 1,
    "limit": 25,
    "total": 249,
    "pages": 10
  },
  "errors": null,
  "timestamp": "2026-08-06T14:30:00Z"
}
```

Error responses:

```json
{
  "data": null,
  "meta": null,
  "errors": [
    {
      "code": "CUSTOMER_NOT_FOUND",
      "detail": "No customer with ID 'CUST99999'",
      "path": "/api/customers/CUST99999"
    }
  ],
  "timestamp": "2026-08-06T14:30:00Z"
}
```

---

## Appendix A: Endpoint Summary Matrix

| Category | Endpoint Count | New in v2.0 |
|----------|---------------|-------------|
| Authentication | 4 | 1 (`/auth/me`) |
| Customers & Features | 5 | 2 (journey, timeline) |
| Predictions & Explainability | 4 | 3 (SHAP, Markov, history) |
| Decision Intelligence (NBA) | 3 | 2 (alternatives, priority) |
| Actions & Feedback | 4 | 3 (outcome, summary) |
| Priority Queue | 2 | 2 |
| Alerts & Notifications | 3 | 1 (WebSocket) |
| Branch Manager | 5 | 5 (all promoted) |
| Campaigns | 3 | 3 |
| Model Operations | 7 | 7 (all promoted + new) |
| Feature Drift | 2 | 2 |
| Prediction Logs | 2 | 2 |
| ETL Operations | 5 | 3 (detail, compare, rejections) |
| System Health | 2 | 2 |
| Audit Trail | 2 | 2 |
| Admin | 5 | 5 |
| **TOTAL** | **58** | **37 new/changed** |

---

## Appendix B: Backend Service Mapping

| Frontend Domain | Backend Service(s) | Port | Status |
|-----------------|-------------------|------|--------|
| Auth | API Gateway (auth routes) | 8080 | ✅ Live |
| Customers / Features | Feature Engineering Service | 8002 | ✅ Live |
| State / Timeline / Markov | Customer State Service (Layer 1) | 8003 | ✅ Live |
| Predictions / SHAP / Health Score | Prediction Service (Layer 2) | 8004 | 🔨 In Build |
| NBA / Priority / LLM Explanations | Decision Intelligence Service (Layer 3) | 8005 | 🔨 Scaffolded |
| Campaigns | Campaign Engine (Decision Intel sub-module) | 8005 | 🔨 Scaffolded |
| ETL / Data Quality | ETL Engine | — | ✅ Live |
| Model Registry / Drift | Model Management Service | — | 🔨 In Build |
| Audit Trail | Gateway (middleware) + ETL audit tables | 8080 | ✅ Live |
| WebSocket Notifications | Gateway (WS endpoint) + Redis pub/sub | 8080 | 🔨 To Build |
| System Health | Gateway health + per-service /health | 8080 | ✅ Live |
