# Absa Bank Zambia — Frontend Functional Requirements
## Customer Lifecycle Prediction System · PoC Phase · July 20, 2026

---

## 1. Architecture & Technology Constraints

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
| **Screen** | 1920×1080 minimum — desktop only, no mobile required for PoC |

---

## 2. User Roles & Access Control

### 2.1 Role Matrix

| Role | Permissions |
|---|---|
| **Relationship Manager** | View own portfolio, drill into customers, see NBA recommendations, log actions |
| **Branch Manager** | View all branch customers, portfolio analytics, churn risk heatmap, team performance |
| **Data Scientist** | Model performance dashboards, champion/challenger, SHAP explanations, feature drift |
| **Operations** | ETL pipeline status, data quality scores, audit logs, system health |

### 2.2 Authentication Flow

- Login via LDAP username/password
- Session timeout: 30 minutes inactivity (configurable)
- Role determined by LDAP group membership
- No self-registration — accounts provisioned by IT

---

## 3. Screens — Relationship Manager

### 3.1 RM Dashboard (Landing Page)

Primary landing screen showing at-a-glance portfolio view.

#### FR-DASH-01: Summary Cards
- 4 KPI cards: Total Customers, At Risk count + %, Dormant count + %, Actions Due Today
- Each card clickable — filters the customer table below
- At Risk % colour-coded: green less-than 5%, amber 5-15%, red above 15%

#### FR-DASH-02: Priority Alerts
- Top 5 alerts ranked by severity: Health Score drop above 20 pts, state transition to At Risk/Dormant, significant CLV change
- Each alert links to customer detail screen
- Alerts persist until acknowledged (timestamp + RM ID for audit)

#### FR-DASH-03: Customer Table
- Columns: Customer Name, State (icon + label), Health Score (gauge bar), Churn Probability (%), CLV (ZMW), Recommended Action
- Default sort: Health Score ascending (worst first)
- Search: by customer name, account number, or customer ID
- Filter: by state (Active/At Risk/Dormant/Churned), branch, product type
- Pagination: 25 rows per page
- Click row navigates to Customer Detail (FR-CUST-01)

#### FR-DASH-04: Period Selector
- Dropdown: Current Snapshot vs historical dates (back to earliest feature snapshot)
- Default: Latest — shows most recent computed features

### 3.2 Customer Detail Screen

Full 360-degree view of a single customer with AI-powered insights.

#### FR-CUST-01: Customer Profile Card
- Display: customer name, account number, branch, segment, tenure, assigned RM
- Link to core banking system (external) for full KYC details

#### FR-CUST-02: AI Health Score Gauge
- Circular or horizontal gauge showing Health Score (0-100)
- Colour: green 70+, amber 40-69, red below 40
- Display component scores: Churn Risk, CLV Percentile, Behavioural Score
- Trend indicator: up/down change since last period (30 days)

#### FR-CUST-03: State Timeline
- Horizontal timeline showing customer state changes over time
- States: Active (green), At Risk (amber), Dormant (grey), Churned (red)
- Hover shows transition reason (e.g., 30d inactivity, balance drop)

#### FR-CUST-04: SHAP Explanation (PoC: feature importance)
- Bar chart showing top 5 features driving current prediction
- For PoC: feature values and contribution direction
- Full SHAP waterfall deferred to post-PoC

#### FR-CUST-05: NBA Recommendations
- Ranked list of 3-5 Next Best Actions
- Each shows: priority, action description, predicted impact (High/Medium/Low), effort, confidence %
- [Log Action] button opens small form: action type dropdown, notes field, auto timestamp
- Logged actions stored with: RM ID, customer ID, action taken, timestamp, NBA recommendation ID

#### FR-CUST-06: Action History
- Reverse-chronological list of all logged actions for this customer
- Filterable by action type, date range
- Shows: date, action description, outcome (if recorded)

### 3.3 RM Portfolio View

#### FR-PORT-01: Churn Risk Heatmap
- Grid: rows = customers, columns = weeks
- Cell colour = churn probability (green to red gradient)
- Click cell navigates to customer detail for that date

#### FR-PORT-02: State Distribution
- Active / At Risk / Dormant / Churned pie/donut chart
- Click segment filters customer table

#### FR-PORT-03: Health Score Distribution
- Histogram of Health Scores across portfolio
- Overlay: branch average, bank-wide average

---

## 4. Screens — Branch Manager

#### FR-BM-01: Branch KPIs
- Aggregate of RM dashboard metrics at branch level
- Total customers, At Risk %, Dormant %, Churn rate (monthly)
- Comparison vs previous month indicators
- Comparison vs other branches (anonymised ranking)

#### FR-BM-02: Team Performance
- Table: RM Name, Customers Assigned, At Risk %, Actions Logged (month), Avg Health Score
- Identifies RMs with high-risk portfolios needing support

#### FR-BM-03: Churn Forecast
- Projected churn count for next 30/60/90 days
- Breakdown by segment (Premium, Mass Market, SME)

---

## 5. Screens — Data Scientist

#### FR-DS-01: Model Metrics
- AUC-ROC, Precision, Recall, F1 for champion model
- Time-series chart of metrics over last 30 days
- Alert if any metric drops below threshold

#### FR-DS-02: Champion vs Challenger (Post-PoC)
- Side-by-side comparison: traffic split %, win rate, significance test
- Deferred but UI slot designed

#### FR-DS-03: Feature Drift Monitor
- Table: Feature Name, Training Distribution, Current Distribution, Drift Score
- Alert if drift exceeds threshold (PSI above 0.25)

#### FR-DS-04: Prediction Log Browser
- Searchable table: timestamp, customer ID, prediction type, probability, SHAP top features, model version
- Export to CSV

---

## 6. Screens — Operations

#### FR-OPS-01: ETL Run History
- Table from etl.etl_audit: Run ID, Batch ID, Duration, Rows Received/Valid/Loaded/Rejected, Quality Score, Status
- Status icons: Completed, Failed, Running
- Click row navigates to detailed audit record

#### FR-OPS-02: Data Quality Dashboard
- Time-series chart of quality_score over recent runs
- Alert threshold line at configured minimum (90%)
- Breakdown of rejection reasons by run

#### FR-OPS-03: System Health
- Service status: PostgreSQL, Redis, Feature Service, API Gateway
- Uptime %, last heartbeat, response time (ms)
- Green/Amber/Red status per service

---

## 7. Common UI Components

#### FR-COM-01: Navigation
- Persistent left sidebar: Dashboard, My Customers, Portfolio, Models (DS only), Operations (Ops only)
- Breadcrumb trail on every screen
- User name + role in top-right corner

#### FR-COM-02: Search
- Global search bar: customer name, account number, customer ID
- Results dropdown with: name, state icon, health score, branch
- Selecting navigates to Customer Detail

#### FR-COM-03: Notifications
- Bell icon with unread count badge
- Dropdown lists recent alerts: state changes, health score drops, NBA expiry
- Click navigates to relevant screen

#### FR-COM-04: Export
- Any table view exportable as CSV
- Customer detail exportable as PDF (one-page RM meeting summary)

#### FR-COM-05: Audit Logging
- Every frontend action that modifies data must write to audit log
- Fields: timestamp, user ID, role, action type, customer ID, details

---

## 8. API Contract (Frontend to Backend)

| Endpoint | Method | Source Service | Purpose |
|---|---|---|---|
| /api/customers/{rm_id} | GET | Gateway to Feature Service | List RM customers with latest features |
| /api/customers/{customer_id} | GET | Gateway to Feature + State + Prediction | Full customer detail |
| /api/customers/{customer_id}/history | GET | Gateway to Feature Service | Feature snapshots over time |
| /api/customers/{customer_id}/nba | GET | Gateway to Decision Intel | NBA recommendations |
| /api/customers/{customer_id}/actions | GET/POST | Gateway to Decision Intel | Action history / log new action |
| /api/branch/{branch_id}/portfolio | GET | Gateway to Aggregated | Branch-level analytics |
| /api/models/performance | GET | Gateway to Model Mgmt | Champion model metrics |
| /api/etl/runs | GET | Gateway to ETL Audit | Pipeline run history |
| /api/auth/login | POST | Gateway | LDAP authentication |
| /api/alerts/{user_id} | GET/PATCH | Gateway | Priority alerts / acknowledge |

---

## 9. PoC Scope Boundaries

### Included in PoC
- RM Dashboard (FR-DASH-01 to 04)
- Customer Detail with Health Score + NBA (FR-CUST-01 to 06)
- State Timeline (FR-CUST-03)
- Feature importance (FR-CUST-04 — simplified, no full SHAP waterfall)
- Action Logging (FR-CUST-05)
- Operations: ETL Run History (FR-OPS-01)
- Export CSV (FR-COM-04)
- LDAP login

### Deferred to Post-PoC
- Branch Manager Dashboard (FR-BM-01 to 03)
- Data Scientist: Champion/Challenger, Feature Drift (FR-DS-02, FR-DS-03)
- Full SHAP waterfall explanations
- PDF export
- Mobile/responsive layout
- Real-time WebSocket notifications
