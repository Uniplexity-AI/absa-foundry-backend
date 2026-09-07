# Decision & Insight Intelligence Platform v3.0 — Architecture Design Document

**Customer Lifecycle Prediction System**  
**Date:** 2026-08-07  
**Status:** Design Phase — Platform Architecture  
**Supersedes:** Decision Intelligence Service v1.0 TDD · v2.0 / v2.1 Drafts  
**Reference:** Database Design Spec v2.1 · Prediction Service (L2 Live) · Customer State Service (L1 Live)

---

## 1. Mission Statement

> The Decision & Insight Intelligence Platform is the bank's central intelligence layer. It answers *Why? What? Who? When? What next? What if?* — serving Executive Management, Marketing, Retail Banking, Relationship Managers, and Business Banking with a single, consistent source of AI-powered truth.

**This is NOT just a Next Best Action engine.** It is the platform that transforms predictions into decisions, insights, forecasts, and explanations — distributed to the right stakeholder, in the right format, at the right time.

---

## 2. The Problem We're Actually Solving

Absa didn't ask for "product recommendations." They asked broader questions:

| Question | Stakeholder | Engine |
|----------|-------------|--------|
| *Why are customers leaving?* | Executive, Marketing | Churn Intelligence |
| *Which customers are most likely to leave?* | Retail, RM | Customer Intelligence |
| *Which branch is losing customers?* | Executive, Retail | Churn Intelligence |
| *Which segment is deteriorating?* | Executive, Marketing | Customer Intelligence |
| *What interventions should we perform?* | Retail, Marketing | Decision Engine |
| *Which intervention has the highest ROI?* | Executive, Marketing | Recommendation + Forecast |
| *How many customers will churn next quarter?* | Executive | Forecast Engine |
| *Which campaigns should Marketing launch?* | Marketing | Recommendation Engine |
| *Which customers require RM attention?* | Retail, RM | Decision Engine |
| *Which customers can be retained digitally?* | Marketing, Retail | Decision Engine |

---

## 3. Platform Architecture

```
                              CUSTOMER 360°
                           (Feature Store + Predictions + State)
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DECISION & INSIGHT INTELLIGENCE PLATFORM                  │
│                                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │    CHURN     │ │  CUSTOMER    │ │   DECISION   │ │ RECOMMENDATION│       │
│  │ INTELLIGENCE │ │ INTELLIGENCE │ │   ENGINE     │ │   ENGINE      │       │
│  │              │ │              │ │              │ │               │       │
│  │ "Why are     │ │ "What is     │ │ "What should │ │ "What product │       │
│  │  customers   │ │  happening   │ │  the bank    │ │  should we    │       │
│  │  leaving?"   │ │  to this     │ │  do?"        │ │  offer?"      │       │
│  │              │ │  customer?"  │ │              │ │               │       │
│  │ Root Cause   │ │ Health       │ │ NBA +        │ │ NBO +         │       │
│  │ Portfolio    │ │ Trajectory   │ │ Workflows +  │ │ Cross-sell +  │       │
│  │ Aggregation  │ │ Alerts       │ │ Approvals    │ │ Upsell        │       │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬────────┘       │
│         │                │                │                │                │
│  ┌──────┴────────────────┴────────────────┴────────────────┴────────┐       │
│  │                     SHARED FOUNDATION                             │       │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐│       │
│  │  │ DECISION CONTEXT │  │ POLICY & RULES   │  │ DECISION MEMORY  ││       │
│  │  │     BUILDER      │  │   (YAML Config)  │  │  (Audit + Loop)  ││       │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘│       │
│  └──────────────────────────────────────────────────────────────────┘       │
│                                     │                                       │
│  ┌──────────────────────────────────┴──────────────────────────────────┐   │
│  │                      INSIGHT & EXPLANATION LAYER                     │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │   │
│  │  │    FORECAST      │  │   EXPLANATION    │  │    INSIGHT       │   │   │
│  │  │     ENGINE       │  │     ENGINE       │  │     ENGINE       │   │   │
│  │  │                  │  │                  │  │                  │   │   │
│  │  │ "What will       │  │ "Explain this    │  │ "What does this  │   │   │
│  │  │  happen?"        │  │  decision"       │  │  mean for us?"   │   │   │
│  │  │                  │  │                  │  │                  │   │   │
│  │  │ Portfolio churn  │  │ LLM Gateway →    │  │ Executive        │   │   │
│  │  │ Revenue at risk  │  │ Reason Codes →   │  │ summaries        │   │   │
│  │  │ RM workload      │  │ Natural Language │  │ Trend narratives │   │   │
│  │  │ Campaign sizing  │  │ Talking Points   │  │ Risk briefings   │   │   │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
└─────────────────────────────────────┼───────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
          ▼                           ▼                           ▼
   ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
   │  EXECUTIVE  │           │  MARKETING  │           │RETAIL + RM  │
   │  MANAGEMENT │           │             │           │+ BUSINESS   │
   │             │           │ "Which      │           │             │
   │ "What is    │           │  campaign?" │           │ "Which      │
   │  happening?"│           │             │           │  customers?"│
   └──────┬──────┘           └──────┬──────┘           └──────┬──────┘
          │                         │                         │
          ▼                         ▼                         ▼
   Portfolio              Campaign                    RM Work Queue
   Dashboards             Recommendations             Customer Alerts
   Forecasts              Segment Insights            Action Plans
   Risk Reports           ROI Estimates               Digital Retention
```

---

## 4. The Six Engines

### Engine 1 — Churn Intelligence

**Answers:** *"Why are customers leaving?"*

This is NOT per-customer churn probability (that's the Prediction Service). This is portfolio-level intelligence.

| Capability | Description |
|------------|-------------|
| **Root Cause Analysis** | Aggregate SHAP feature importance across all at-risk customers to identify top churn drivers |
| **Segment Deterioration** | Which segments are deteriorating fastest? Mass Market vs Affluent vs SME |
| **Branch Performance** | Which branches have the highest churn rates? Month-over-month trends |
| **Driver Attribution** | "Salary cessation drives 31% of churn. Reduced transaction frequency drives 24%." |
| **Competitor Signal Detection** | Patterns that suggest competitor movement (large withdrawals, salary redirects) |

**Example output:**

```
Top Churn Drivers — Q3 2026
═══════════════════════════════
Salary ceased                  31% ████████████████████████████████
Reduced transaction frequency  24% ████████████████████████
High inactivity                18% ██████████████████
Low product ownership          11% ███████████
Poor digital engagement         9% █████████
Age-related                     4% ████
Other                           3% ███
```

**LLM executive summary:**

> *"Premier Banking churn increased 2.3pp this quarter, driven primarily by salary credit disruptions (31% of cases) and declining transaction activity (24%). The highest concentration of risk is in customers aged 30–45 who maintain large balances but have stopped using digital channels. We recommend immediate RM outreach for the top 250 at-risk Premier customers and a targeted digital re-engagement campaign for the broader affected segment."*

---

### Engine 2 — Customer Intelligence

**Answers:** *"What is happening to this customer?"*

This is the 360° customer health narrative — not raw features, but interpreted trajectory.

| Capability | Description |
|------------|-------------|
| **Health Trajectory** | Is this customer improving, stable, or deteriorating? Over what timeframe? |
| **Lifecycle Stage** | Onboarding / Engaged / Mature / Declining / At Risk — with transition probabilities |
| **Behavioural Alerts** | Salary missing? Transaction volume dropping? Digital engagement declining? |
| **Peer Comparison** | How does this customer compare to their segment peers? |
| **Predicted Trajectory** | If no intervention, where will this customer be in 30/60/90 days? |

**Example output:**

```
CUSTOMER INTELLIGENCE: CUST0042
═══════════════════════════════
Health Score: 35/100 ↓ (was 52, 30 days ago)
State: AT_RISK (transitioned from ACTIVE, 14 days ago)
Segment: Mass Affluent | Tenure: 48 months

Key Signals:
⚠ Salary deposit missed (last: 22 days ago, previously weekly)
⚠ Transaction volume ↓ 62% vs 90-day average
⚠ Digital logins ↓ from daily to 2×/week
✓ High savings balance maintained (ZMW 85,000)
✓ 3 active products (Savings, Current, Insurance)

90-Day Projection (no intervention):
→ DORMANT: 62% probability
→ CHURNED: 18% probability
→ AT_RISK: 17% probability
→ ACTIVE:  3% probability
```

---

### Engine 3 — Decision Engine

**Answers:** *"What should the bank do?"*

This is the NBA engine from v2.1 — but now it routes decisions to the right stakeholder, not just RMs.

| Capability | Description |
|------------|-------------|
| **Action Routing** | Digital retention? RM call? Marketing campaign? Branch visit? Based on customer value + risk + channel preference |
| **NBA + NBO Fusion** | Combines Next Best Action (retention/service) with Next Best Offer (product) |
| **Approval Workflow** | Auto-execute low-risk actions. Require approval for high-value/FEE_WAIVER/CORPORATE |
| **Channel Selection** | Digital (SMS/email/app) vs Human (RM call/branch visit) based on customer preference + urgency |
| **Escalation Logic** | Health score <20 → Regional Manager. CLV >90th percentile + churn >0.7 → RM within 24h |

**Routing Matrix:**

| Customer Profile | Decision | Channel | Stakeholder |
|-----------------|----------|---------|-------------|
| Premier + High CLV + High Churn | Retention Call within 48h | RM Direct | Relationship Manager |
| Mass Market + Moderate Churn + Mobile User | Digital Savings Campaign | SMS / App | Marketing (automated) |
| SME + Revenue Declining | Overdraft Review + RM Meeting | Branch Visit | Business Banking RM |
| Mass Affluent + Salary Missing | Salary Account Retention Offer | RM Call | Retail RM |
| Young Professional + Low Products + High Mobile | Digital Onboarding Campaign | App Notification | Marketing (automated) |
| All segments + Low Risk + Healthy | No Action / Monitor | — | System (passive) |

---

### Engine 4 — Recommendation Engine

**Answers:** *"What product should we offer?"*

This is the Next Best Offer (NBO) engine — distinct from the Decision Engine's action routing.

| Capability | Description |
|------------|-------------|
| **Product Propensity** | Score every product for every customer: Loan, Card, Mortgage, Insurance, Investment, FX |
| **Cross-Sell Logic** | "Customer has Savings + Salary → offer Credit Card" |
| **Upsell Logic** | "Customer has Basic Savings → offer Premium Savings" |
| **Campaign Mapping** | "Recommendation: Offer Personal Loan → Campaign: PL_AUG_2026" |
| **Eligibility-Aware** | Never recommend a product the customer already holds or doesn't qualify for |

**Example:**

```
PRODUCT RECOMMENDATIONS: CUST0042
════════════════════════════════
  Personal Loan           0.87  ← Top recommendation
  Credit Card             0.72
  Investment Product      0.58
  Mortgage                N/A  (customer already holds)
  Insurance               N/A  (customer already holds)
```

---

### Engine 5 — Forecast Engine

**Answers:** *"What will happen?"*

This is the executive-facing engine. Aggregates individual predictions into portfolio-level forecasts.

| Capability | Description |
|------------|-------------|
| **Churn Forecast** | Expected churn count: next month, next quarter, next 6 months |
| **Revenue at Risk** | Total CLV of customers projected to churn (ZMW) |
| **RM Workload Forecast** | How many customers will require RM intervention next week/month? |
| **Campaign Sizing** | How many customers match each campaign's target profile? |
| **Segment Projections** | Churn forecast broken down by Mass Market / Affluent / SME / Corporate |
| **Intervention Impact** | "If we execute retention calls for top 500 at-risk customers, projected churn reduction: 120 customers (24%)" |

**Example:**

```
FORECAST: Q4 2026
══════════════════
Expected Churn:          680 customers
Revenue at Risk:         ZMW 12.4 Million
RM Workload (next 30d):  1,240 intervention candidates
Campaign Reach:          3,200 customers (Digital Retention)

By Segment:
  Mass Market:   420 customers (ZMW 4.2M at risk)
  Mass Affluent: 180 customers (ZMW 5.1M at risk)
  Affluent:       55 customers (ZMW 2.3M at risk)
  SME:            25 customers (ZMW 0.8M at risk)

Intervention Scenario:
  If 500 retention calls → projected 120 saves → ZMW 2.8M preserved
```

---

### Engine 6 — Insight & Explanation Engine

**Answers:** *"What does this mean? Explain it to me."*

This is the LLM-powered layer that explains outputs from all other engines.

| Capability | Description |
|------------|-------------|
| **Executive Summaries** | Natural language briefings on portfolio health |
| **Decision Explanations** | Why was this NBA/NBO selected for this customer? |
| **Trend Narratives** | "Premier Banking churn increased because…" |
| **RM Talking Points** | "Here's what to say when you call this customer" |
| **Regulatory Explanations** | Full audit trail in human-readable form |
| **Ad-Hoc Queries** | "Explain why Branch 014 is underperforming" |

**Architecture:**

```
Any Engine Output
      │
      ▼
┌─────────────────┐
│ REASON CODE      │  ← Structured, deterministic codes
│ GENERATOR        │    Independent of LLM
│ (SHAP + Rules)   │
└───────┬─────────┘
        │
        ▼
┌─────────────────┐
│ LLM GATEWAY      │  ← Abstraction layer
│ - Prompt Builder │    Model switching
│ - Retry Handler  │    Response caching
│ - Cache Layer    │    Output validation
│ - Model Router   │    Future: cloud LLM support
└───────┬─────────┘
        │
        ▼
┌─────────────────┐
│ OLLAMA           │  ← Local inference
│ (Qwen2.5 7B)     │    CPU-only, ~8 GB RAM
└─────────────────┘
```

**⚠️ The LLM is an ADVISOR — never a decision-maker.** It explains what the deterministic engines already produced. It never overrides business rules, ranking models, or eligibility checks.


## 5. Shared Foundation

All six engines share three foundation modules:

### Decision Context Builder

Assembles the complete `DecisionContext` from upstream services (State, Prediction, Features). Built ONCE per customer, shared across all engines.

### Policy & Rules Engine (YAML)

All business rules, eligibility checks, action catalogs, reason codes, and strategy configurations are YAML-defined and version-controlled. No hardcoded banking logic.

### Decision Memory

Every decision, execution, outcome, and forecast is persisted. Powers the closed feedback loop:

```
Decision → Execution → Outcome → Decision Memory → Feature Store → Retraining
```


## 6. Stakeholder Outputs

| Stakeholder | Consumes From | Format | Frequency |
|-------------|--------------|--------|-----------|
| **Executive Management** | Churn Intel + Forecast + Insight | Portfolio dashboards, executive briefings, risk reports | Weekly / Monthly |
| **Marketing** | Churn Intel + Recommendation + Forecast | Campaign recommendations, segment insights, ROI estimates | Weekly / On-demand |
| **Retail Banking** | Customer Intel + Decision | Customer alerts, intervention lists, health dashboards | Daily |
| **Relationship Managers** | Customer Intel + Decision + Recommendation | RM work queue, NBA/NBO, talking points, customer 360° | Daily / Real-time |
| **Business Banking** | Customer Intel + Decision + Recommendation | SME health dashboards, overdraft reviews, RM meeting prep | Weekly / On-demand |


## 7. Internal Module Structure

```
services/decision-intelligence-platform/
│
├── foundation/                       # Shared by all engines
│   ├── context_builder.py           # DecisionContext assembly
│   ├── policy_engine.py             # YAML business rules
│   ├── eligibility_engine.py        # YAML eligibility rules
│   └── decision_memory.py           # Audit + feedback loop
│
├── engines/
│   ├── churn_intelligence/
│   │   ├── root_cause.py            # Aggregate SHAP → portfolio drivers
│   │   ├── segment_analyzer.py      # Segment-level deterioration
│   │   └── branch_analyzer.py       # Branch-level churn metrics
│   │
│   ├── customer_intelligence/
│   │   ├── health_trajectory.py     # Health trend + trajectory
│   │   ├── lifecycle_stage.py       # Onboarding → Engaged → Declining
│   │   ├── behavioural_alerts.py    # Signal detection
│   │   └── peer_comparison.py       # Segment benchmarking
│   │
│   ├── decision_engine/
│   │   ├── action_generator.py      # 25 actions, 5 categories
│   │   ├── ranking_engine.py        # LightGBM → Top-N
│   │   ├── strategy_layer.py        # Retention First / Revenue First / etc.
│   │   ├── optimization_engine.py   # Multi-objective scoring
│   │   ├── routing_engine.py        # RM vs Digital vs Marketing
│   │   └── approval_workflow.py     # Auto vs Human approval
│   │
│   ├── recommendation_engine/
│   │   ├── product_propensity.py    # Score per product
│   │   ├── cross_sell_logic.py      # Rule-based cross-sell
│   │   ├── upsell_logic.py          # Rule-based upsell
│   │   └── campaign_mapper.py       # NBO → Campaign
│   │
│   ├── forecast_engine/
│   │   ├── churn_forecast.py        # Aggregate → quarterly/monthly
│   │   ├── revenue_at_risk.py       # CLV × churn probability
│   │   ├── workload_forecast.py     # RM capacity planning
│   │   └── campaign_sizing.py       # Target audience sizing
│   │
│   └── insight_engine/
│       ├── reason_code_generator.py # SHAP → structured codes
│       ├── llm_gateway.py           # Ollama abstraction
│       ├── executive_summarizer.py  # Portfolio → narrative
│       ├── trend_narrator.py        # Time-series → natural language
│       └── adhoc_explainer.py       # "Why is Branch 014 underperforming?"
│
├── api/
│   ├── routes/
│   │   ├── churn_intelligence.py
│   │   ├── customer_intelligence.py
│   │   ├── decisions.py
│   │   ├── recommendations.py
│   │   ├── forecasts.py
│   │   └── insights.py
│   └── dependencies.py
│
├── schemas/
│   └── schemas.py                   # All Pydantic v2 models
│
├── repository/
│   └── repository.py                # decisions.* schema CRUD
│
├── upstream/
│   └── client.py                    # httpx → 8002/8003/8004
│
├── config/
│   ├── policies/banking_rules.yaml
│   ├── eligibility/eligibility_rules.yaml
│   ├── candidates/action_catalog.yaml
│   ├── products/product_catalog.yaml
│   ├── explainability/reason_codes.yaml
│   └── strategies/strategy_config.yaml
│
├── prompts/
│   ├── explain_decision.txt
│   ├── executive_summary.txt
│   ├── trend_narrative.txt
│   └── adhoc_query.txt
│
└── tests/
    ├── test_churn_intelligence.py
    ├── test_customer_intelligence.py
    ├── test_decision_engine.py
    ├── test_recommendation_engine.py
    ├── test_forecast_engine.py
    └── test_pipeline.py
```


## 8. Decision Context (Shared Across All Engines)

```python
class DecisionContext(BaseModel):
    """The single object built once and shared across all 6 engines."""

    # === Identity ===
    customer_id: str
    as_of_date: date

    # === From State Service (L1) ===
    customer_state: Literal["ACTIVE", "AT_RISK", "DORMANT", "CHURNED"]
    state_duration_days: int
    state_probability: float
    previous_state: str | None = None

    # === From Prediction Service (L2) ===
    health_score: float
    churn_probability: float
    clv_percentile: float
    component_scores: dict

    # === From Feature Store ===
    segment: str
    age: int
    income_band: str | None = None
    tenure_months: int
    branch_code: str
    preferred_channel: str | None = None
    engagement_score: float | None = None
    days_since_last_txn: int | None = None
    total_amount_90d: float | None = None
    products: dict
    shap_values: dict | None = None

    # === Relationship ===
    rm_id: str | None = None

    # === Eligibility ===
    aml_flag: bool = False
    kyc_expired: bool = False
    marketing_opt_out: bool = False
    credit_risk_rating: str | None = None
    loan_in_arrears: bool = False

    # === History ===
    last_action_date: date | None = None
    contact_frequency_30d: int = 0
    previous_offers: list[dict] = []
```


## 9. API Contract

### Churn Intelligence

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/churn-intel/drivers?as_of_date=&segment=&branch=` | Top churn drivers with SHAP aggregation |
| `GET` | `/churn-intel/segments?as_of_date=` | Segment deterioration rankings |
| `GET` | `/churn-intel/branches?as_of_date=` | Branch churn performance |
| `GET` | `/churn-intel/summary?as_of_date=` | LLM executive summary |

### Customer Intelligence

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/customer-intel/{id}?as_of_date=` | Full 360° customer intelligence |
| `GET` | `/customer-intel/{id}/trajectory` | 90-day projected trajectory |
| `GET` | `/customer-intel/{id}/alerts` | Active behavioural alerts |
| `GET` | `/customer-intel/{id}/peers` | Segment peer comparison |

### Decision Engine

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/decisions/compute?as_of_date=&strategy=BALANCED` | Batch decision computation |
| `GET` | `/decisions/{id}?as_of_date=` | Full decision package |
| `GET` | `/decisions/queue?rm_id=&limit=20` | RM priority work queue |
| `POST` | `/decisions/{id}/execute` | Log RM action |
| `PATCH` | `/decisions/{id}/outcome` | Record outcome |
| `PATCH` | `/decisions/{id}/approve` | Human approval |

### Recommendation Engine

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/recommendations/{id}?as_of_date=` | Product recommendations for customer |
| `GET` | `/recommendations/campaigns?segment=&limit=1000` | Campaign target lists |

### Forecast Engine

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/forecasts/churn?horizon=90d&segment=` | Churn forecast |
| `GET` | `/forecasts/revenue-at-risk?horizon=90d` | Revenue at risk (ZMW) |
| `GET` | `/forecasts/workload?horizon=30d` | RM workload projection |
| `GET` | `/forecasts/campaign-sizing?campaign=` | Campaign audience sizing |
| `GET` | `/forecasts/scenario?intervention=retention_calls&coverage=500` | What-if scenario |

### Insight Engine

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/insights/executive-summary?period=Q3` | LLM executive briefing |
| `GET` | `/insights/trend?metric=churn&segment=Premier` | Natural language trend narrative |
| `POST` | `/insights/explain` | Ad-hoc query: "Why is Branch 014 underperforming?" |

### Platform

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/strategies` | List active strategies |
| `PATCH` | `/strategies/activate` | Switch strategy |
| `GET` | `/health` | Platform health + upstream status |
| `POST` | `/rules/reload` | Reload YAML configs |


## 10. Database Schema — `decisions` Schema

```sql
-- Churn Intelligence
CREATE TABLE decisions.churn_drivers (
    id BIGSERIAL PRIMARY KEY,
    as_of_date DATE NOT NULL,
    segment VARCHAR(32),
    branch_code VARCHAR(16),
    driver_rank INT,
    driver_name VARCHAR(128),
    driver_contribution_pct NUMERIC(5,2),
    affected_customer_count INT,
    computed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Customer Intelligence
CREATE TABLE decisions.customer_intelligence (
    id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    as_of_date DATE NOT NULL,
    health_trajectory VARCHAR(16),  -- IMPROVING, STABLE, DECLINING, CRITICAL
    lifecycle_stage VARCHAR(32),
    active_alerts JSONB DEFAULT '[]',
    projected_state_30d VARCHAR(16),
    projected_state_90d VARCHAR(16),
    peer_percentile_health NUMERIC(5,2),
    peer_percentile_engagement NUMERIC(5,2),
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (customer_id, as_of_date)
);

-- Decisions (NBA)
CREATE TABLE decisions.recommendation (
    decision_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    as_of_date DATE NOT NULL,
    status VARCHAR(32) DEFAULT 'GENERATED',
    top_actions JSONB NOT NULL DEFAULT '[]',
    routing VARCHAR(32),  -- RM, DIGITAL, MARKETING, BRANCH
    priority_score NUMERIC(5,2),
    estimated_revenue_zmw NUMERIC(12,2),
    reason_codes JSONB DEFAULT '[]',
    explanation JSONB DEFAULT '{}',
    decision_confidence JSONB DEFAULT '{}',
    approval_required BOOLEAN DEFAULT false,
    strategy VARCHAR(32) DEFAULT 'BALANCED',
    computed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Recommendations (NBO)
CREATE TABLE decisions.product_recommendation (
    id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    as_of_date DATE NOT NULL,
    product VARCHAR(64) NOT NULL,
    propensity_score NUMERIC(5,4),
    is_eligible BOOLEAN,
    campaign VARCHAR(64),
    computed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Forecasts
CREATE TABLE decisions.forecast (
    id BIGSERIAL PRIMARY KEY,
    forecast_date DATE NOT NULL,
    horizon_days INT NOT NULL,
    metric VARCHAR(64),  -- CHURN, REVENUE_AT_RISK, WORKLOAD, CAMPAIGN_SIZE
    segment VARCHAR(32),
    predicted_value NUMERIC(15,2),
    confidence_lower NUMERIC(15,2),
    confidence_upper NUMERIC(15,2),
    computed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Execution & Feedback (shared)
CREATE TABLE decisions.recommendation_execution (
    id BIGSERIAL PRIMARY KEY,
    decision_id VARCHAR(64) REFERENCES decisions.recommendation(decision_id),
    customer_id VARCHAR(64) NOT NULL,
    rm_id VARCHAR(64),
    action_taken VARCHAR(64),
    channel_used VARCHAR(32),
    status VARCHAR(32) DEFAULT 'PENDING',
    notes TEXT,
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE decisions.recommendation_feedback (
    id BIGSERIAL PRIMARY KEY,
    decision_id VARCHAR(64) REFERENCES decisions.recommendation(decision_id),
    customer_id VARCHAR(64) NOT NULL,
    outcome VARCHAR(32) NOT NULL,
    actual_revenue_zmw NUMERIC(12,2),
    product_adopted VARCHAR(64),
    retained_after_30d BOOLEAN,
    retained_after_90d BOOLEAN,
    feedback_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```


## 11. Phase 1 Implementation Plan

**Phase 1 delivers:**

| Engine | Capabilities |
|--------|-------------|
| **Foundation** | Decision Context Builder, Policy Engine, Eligibility Engine, Decision Memory |
| **Decision Engine** | Action Generation, Heuristic Ranking, Strategy Layer, Routing, Approval Workflow |
| **Customer Intelligence** | Health Trajectory, Lifecycle Stage, Behavioural Alerts |
| **Recommendation Engine** | Product Propensity (heuristic), Cross-sell Logic, Campaign Mapping |
| **Churn Intelligence** | Root Cause Analysis (aggregate SHAP), Segment Deterioration |
| **Forecast Engine** | Churn Forecast, Revenue at Risk |
| **Insight Engine** | Reason Code Generator (LLM Gateway + Explanation deferred to Phase 3) |

**Phase 1 defers:**
- LightGBM ranking model (Phase 2 — heuristic scoring for now)
- LLM Gateway + Ollama explanations (Phase 3)
- Peer comparison (Phase 3)
- What-if scenario simulation (Phase 4)
- Feedback loop back to Feature Store (Phase 4)
- Campaign integration (Phase 4)


## 12. Technology Stack

| Component | Technology | Status |
|-----------|-----------|--------|
| Language | Python 3.12 | ✅ In .venv |
| API | FastAPI | ✅ Installed |
| ML | LightGBM, XGBoost, SHAP | ✅ Installed |
| Rule Engine | Custom YAML-based | 🔨 To build |
| LLM Runtime | Ollama (Qwen2.5 7B) | 🔨 To configure |
| Database | PostgreSQL (etl_clean) | ✅ Running |
| Cache | Redis | ✅ Installed |
| HTTP Client | httpx (upstream + Ollama) | ✅ Installed |
| Config | PyYAML | 🔨 To install |


## 13. Architecture Decision Record

| # | Decision | Rationale |
|---|----------|-----------|
| ADR-001 | Six engines, one platform, shared foundation | Avoids code duplication. Decision Context built once, consumed by all engines |
| ADR-002 | Churn Intelligence is portfolio-level, not per-customer | Per-customer churn is Prediction Service (L2). This engine answers "why" at scale |
| ADR-003 | Decision routing by stakeholder, not just RM | Not every decision needs human intervention. Route to Digital/Marketing/RM based on value + urgency |
| ADR-004 | Forecast Engine separate from individual predictions | Aggregation logic is different from per-customer scoring. Enables scenario modeling |
| ADR-005 | LLM explains engine outputs, never makes decisions | Deterministic engines produce the decision. LLM converts to natural language |
| ADR-006 | YAML for all rules, catalogs, strategies, codes | Non-technical stakeholders can review. Audit-friendly. Hot-reloadable |
| ADR-007 | Decision Memory for closed-loop learning | Without feedback, models never improve. Every decision → execution → outcome tracked |
| ADR-008 | Single DecisionContext shared across engines | No engine queries upstream services individually. Testable with mocked context |


## 14. Future Phases

| Phase | Capabilities |
|-------|-------------|
| **Phase 1** | Foundation + Decision Engine + Customer Intel + Recommendation (heuristic) + Churn Intel (aggregation) + Forecast (basic) |
| **Phase 2** | LightGBM Ranking + Optimization Engine + Simulation Engine + Advanced Forecast (confidence bands) |
| **Phase 3** | LLM Gateway + Reason Codes + Natural Language Explanations + Executive Summaries + Ad-Hoc Queries |
| **Phase 4** | Feedback Loop → Feature Store + Campaign Integration + Full Approval Workflow + Peer Comparison |
| **v4.0** | Reinforcement Learning ranking + Real-time streaming (Kafka) + Multi-arm bandit optimization + Autonomous decisions with human-in-the-loop |
