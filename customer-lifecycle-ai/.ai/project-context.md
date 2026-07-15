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

## Business Constraints

- **GDPR / Data Privacy:** Customer data must be anonymized in non-production environments
- **Audit Trail:** Every prediction and NBA recommendation must be logged
- **Explainability:** All model predictions must have SHAP explanations for compliance
- **Internal Deployment:** Runs on bank-owned Ubuntu servers, NOT in public cloud
- **No Internet Access:** Services run in an air-gapped network; all dependencies vendored

## Technical Constraints

- **Python 3.12+** only
- **FastAPI** for all services (no Django, no Flask)
- **PostgreSQL 16** as the single database
- **Docker Compose** for orchestration (no Kubernetes)
- **No cloud-native services** — everything runs on bare metal/VMs
- **Redis** is optional but recommended for caching
