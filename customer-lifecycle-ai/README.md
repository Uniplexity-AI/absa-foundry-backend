# Customer Lifecycle Prediction System

An enterprise-grade AI platform for banking Customer Lifecycle Prediction, Churn Analysis, Customer Value Prediction, and Next Best Action (NBA) recommendations for Relationship Managers.

> **Phase:** Project Scaffolding — 3-Layer AI Architecture. No business logic implemented yet.

---

## Architecture: Three AI Layers

```mermaid
graph TD
    GW[API Gateway] --> DI[Data Ingestion Service]
    GW --> FE[Feature Engineering Service<br/>(Feature Store)]
    GW --> CS[Customer State Service<br/>Layer 1: Behaviour Intelligence]
    GW --> PS[Prediction Service<br/>Layer 2: Prediction Intelligence]
    GW --> DS[Decision Intelligence Service<br/>Layer 3: Decision Intelligence]
    GW --> MM[Model Management Service]
    GW --> DB[Dashboard Service]
    OS[Orchestration Service] --> DI
    OS --> FE
    OS --> CS
    OS --> PS
    OS --> DS

    CS -- customer state --> PS
    CS -- behavioural features --> FE

    PS -- health score<br/>churn prob<br/>CLV --> DS

    DS -- NBA recommendations --> DB

    DI --> PG[(PostgreSQL)]
    FE --> PG
    CS --> PG
    PS --> PG
    DS --> PG
    MM --> PG
    DB --> PG

    GW --> RD[(Redis)]
    subgraph Infrastructure
        NG[Nginx]
        PG
        RD
    end
```

### Layer 1 — Behaviour Intelligence (`customer-state-service`)

Markov Chain based customer state engine that tracks customer behavioral state transitions.

| Component | Description |
|-----------|-------------|
| Markov Engine | Transition matrix computation from customer journey data |
| HMM Engine (Future) | Hidden Markov Model for latent state discovery |
| Behaviour Profiler | Customer behavior pattern extraction and state classification |

**Outputs:** Customer state labels (Active, At Risk, Dormant, etc.), transition probabilities, behavioural features

### Layer 2 — Prediction Intelligence (`prediction-service`)

Unified prediction engine supporting multiple ML backends with champion/challenger model evaluation.

| Model | Framework | Purpose |
|-------|-----------|---------|
| Churn Model | XGBoost / LightGBM | Predict probability of customer churn |
| CLV Model | XGBoost / LightGBM | Estimate Customer Lifetime Value |
| Health Score | Fusion | Composite score from churn + CLV + behavioural state |

**Outputs:** Churn probability, CLV estimate, Customer Health Score

### Layer 3 — Decision Intelligence (`decision-intelligence-service`)

Rule engine and Next Best Action recommendation system for Relationship Managers.

| Component | Description |
|-----------|-------------|
| Rule Engine | Business rule evaluation and action triggering |
| NBA Generator | Next Best Action ranking and recommendation |
| RL Engine (Future) | Reinforcement learning for optimized treatment strategies |

**Outputs:** Ranked NBA recommendations, customer treatment strategies

---

## Tech Stack

| Component          | Technology                          |
| ------------------ | ----------------------------------- |
| Language           | Python 3.12+                        |
| Framework          | FastAPI                             |
| Database           | PostgreSQL 16                       |
| ORM                | SQLAlchemy 2.0+                     |
| Data Validation    | Pydantic v2                         |
| Migrations         | Alembic                             |
| Cache              | Redis 7                             |
| ML Libraries       | Scikit-Learn, XGBoost, LightGBM     |
| Containerization   | Docker, Docker Compose              |
| API Gateway        | FastAPI (custom gateway)            |
| Markov Models      | NumPy, SciPy                        |
| Deployment Target  | Ubuntu Server (single/small cluster)|

## Project Structure

```
customer-lifecycle-ai/
├── services/                                    # Independent microservices
│   ├── data-ingestion-service/                  # ETL & data acquisition
│   ├── feature-engineering-service/             # Central Feature Store
│   │   └── app/features/                        # Domain feature generators
│   │       ├── customer/                        # Customer profile features
│   │       ├── transactions/                    # Transactional features
│   │       ├── products/                        # Product holding features
│   │       ├── loans/                           # Loan-related features
│   │       ├── cards/                           # Card usage features
│   │       ├── digital/                         # Digital banking features
│   │       ├── behaviour/                       # Behavioural features
│   │       └── clv/                             # CLV-related features
│   ├── customer-state-service/                  # Layer 1: Behaviour Intelligence
│   │   └── app/engines/
│   │       ├── markov/                          # Markov Chain engine
│   │       └── hmm/                             # Hidden Markov Model (future)
│   ├── prediction-service/                      # Layer 2: Prediction Intelligence
│   │   └── app/
│   │       ├── models/xgboost/                  # XGBoost churn & CLV models
│   │       ├── models/lightgbm/                 # LightGBM churn & CLV models
│   │       ├── training/                        # Model training pipelines
│   │       ├── evaluation/                      # Model evaluation & metrics
│   │       └── explainability/shap/             # SHAP-based explanations
│   ├── decision-intelligence-service/           # Layer 3: Decision Intelligence
│   │   └── app/
│   │       ├── rule_engine/                     # Business rule engine
│   │       ├── nba/                             # Next Best Action generator
│   │       └── reinforcement_learning/          # RL (future)
│   ├── model-management-service/                # Model registry & lifecycle
│   │   └── app/
│   │       ├── registry/                        # Model registry
│   │       ├── versioning/                      # Version tracking
│   │       ├── champion_challenger/             # A/B model evaluation
│   │       ├── training/                        # Training orchestration
│   │       ├── evaluation/                      # Performance metrics
│   │       ├── monitoring/                      # Drift monitoring
│   │       └── metadata/                        # Model metadata
│   ├── dashboard-service/                       # Analytics & dashboard data
│   └── orchestration-service/                   # Workflow orchestration
├── shared/                                      # Shared libraries & utilities
│   ├── auth/                                    # Authentication & authorization
│   ├── config/                                  # Shared configuration
│   ├── database/                                # Database base, session, postgres
│   ├── logging/                                 # Structured logging
│   ├── exceptions/                              # Exception hierarchy
│   ├── utils/                                   # Common utilities
│   ├── ml/                                      # Shared ML components
│   ├── schemas/                                 # Shared Pydantic schemas
│   ├── security/                                # Security utilities
│   ├── constants/                               # Project-wide constants
│   └── validators/                              # Data validators
├── gateway/                           # API Gateway
│   ├── app/                           # Gateway application
│   ├── routes/                        # Proxy & health routes
│   ├── middleware/                     # Auth, rate-limit, logging, CORS
│   └── config/                        # Gateway configuration
├── infrastructure/                    # Deployment infrastructure
│   ├── nginx/                         # Reverse proxy config
│   ├── monitoring/                    # Prometheus/Grafana (future)
│   ├── postgres/                      # DB initialization scripts
│   ├── redis/                         # Redis config
│   ├── docker/                        # Production Docker configs
│   ├── backup/                        # Backup procedures
│   └── security/                      # Infrastructure security
├── models/                            # Central ML model registry
│   ├── champion/                      # Active champion models
│   │   ├── customer_state/
│   │   ├── churn_prediction/
│   │   ├── clv_prediction/
│   │   ├── health_score/
│   │   └── nba/
│   ├── challenger/                    # Models under evaluation
│   ├── archive/                       # Archived previous models
│   ├── feature_metadata/              # Feature definitions & drift stats
│   ├── training_history/              # Training logs & lineage
│   └── registry.json
├── datasets/                          # Data storage
│   ├── raw/                           # Raw ingested data
│   ├── processed/                     # Processed/feature data
│   ├── external/                      # External data sources
│   └── synthetic/                     # Synthetic test data
├── research/                          # Jupyter notebooks & experimentation
│   ├── 01_data_exploration/
│   ├── 02_feature_engineering/
│   ├── 03_behaviour_modeling/
│   ├── 04_markov_chain/
│   ├── 05_xgboost/
│   ├── 06_lightgbm/
│   ├── 07_model_comparison/
│   ├── 08_clv_prediction/
│   ├── 09_decision_engine/
│   └── 10_business_value/
├── scripts/                           # Utility scripts
├── docs/                              # Documentation
│   ├── architecture/
│   ├── api/
│   ├── database/
│   ├── deployment/
│   ├── ml/
│   ├── business/
│   ├── security/
│   └── operations/
├── docker/                            # Docker configs (production)
├── .env.example                       # Environment variables template
├── docker-compose.yml                 # Local development orchestration
└── README.md                          # This file
```

## Each Microservice Structure

```
<service-name>/
├── app/
│   ├── __init__.py
│   ├── api/                 # Route definitions & dependencies
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── dependencies.py
│   ├── services/            # Business logic layer
│   │   ├── __init__.py
│   │   └── service.py
│   ├── repository/          # Data access / Repository pattern
│   │   ├── __init__.py
│   │   └── repository.py
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   └── models.py
│   ├── schemas/             # Pydantic v2 schemas
│   │   ├── __init__.py
│   │   └── schemas.py
│   └── config/              # Service configuration
│       ├── __init__.py
│       ├── settings.py
│       └── logging.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   ├── performance/
│   ├── security/
│   └── fixtures/
├── Dockerfile
├── requirements.txt
└── main.py
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- PostgreSQL 16 (if running outside Docker)

### Local Development

1. **Clone and navigate:**
   ```bash
   cd customer-lifecycle-ai
   ```

2. **Copy environment variables:**
   ```bash
   cp .env.example .env
   ```

3. **Start all services:**
   ```bash
   docker-compose up -d
   ```

4. **Verify services:**
   ```bash
   docker-compose ps
   ```

5. **Stop all services:**
   ```bash
   docker-compose down
   ```

### Service Ports

| Service                     | Port | Layer  |
| --------------------------- | ---- | ------ |
| API Gateway                 | 8080 | —      |
| Data Ingestion Service      | 8001 | —      |
| Feature Engineering Service | 8002 | —      |
| Customer State Service      | 8003 | 1      |
| Prediction Service          | 8004 | 2      |
| Decision Intelligence Svc   | 8005 | 3      |
| Model Management Service    | 8006 | —      |
| Dashboard Service           | 8007 | —      |
| Orchestration Service       | 8008 | —      |

## Design Principles

- **3-Layer AI Architecture** — Behaviour → Prediction → Decision pipeline
- **Clean Architecture** — Separation of concerns with distinct layers
- **SOLID Principles** — Single responsibility, dependency inversion
- **Domain-Driven Design** — Bounded contexts around banking domains
- **Microservices** — Independently deployable, loosely coupled services
- **Repository Pattern** — Abstracted data access behind interfaces
- **Champion/Challenger** — Safe model deployment with A/B evaluation
- **Environment-Based Config** — All configuration via environment variables
- **Multi-Model Support** — XGBoost and LightGBM with configurable model selection
- **SHAP Explainability** — Model predictions are interpretable for banking compliance

## Roadmap

- [x] Project scaffolding & folder structure
- [x] Docker Compose local development setup
- [x] Shared module skeleton
- [x] 3-Layer AI architecture with champion/challenger
- [ ] Implement database models & Alembic migrations
- [ ] Implement API endpoints for each service
- [ ] Implement Markov Chain customer state engine
- [ ] Implement XGBoost & LightGBM prediction models
- [ ] Implement SHAP explainability
- [ ] Implement rule engine & NBA generator
- [ ] Implement champion/challenger model evaluation
- [ ] Implement API Gateway routing & auth
- [ ] Add monitoring & observability
- [ ] CI/CD pipelines
- [ ] Production hardening & security audit

## Deployment Target

This solution is designed for deployment on **one or a small number of Ubuntu servers** using Docker Compose. It does NOT use Kubernetes, Helm, or Terraform.

## Security Considerations

This platform is designed for deployment inside a bank's internal infrastructure. The following must be addressed before production:

- All secrets managed via a secrets manager (HashiCorp Vault, Azure Key Vault, etc.)
- Network segmentation and firewall rules
- TLS/SSL for all inter-service communication
- Audit logging for all data access
- Data encryption at rest and in transit
- Role-Based Access Control (RBAC)
- Regular security scanning and penetration testing

## License

Proprietary — All rights reserved.
