# Architecture Strategy — PoC vs Target

## Branch Strategy

| Branch | Purpose |
|---|---|
| `architecture-target-full` | **Reference design** — full 8-microservice architecture with all connectors, engines, and middleware. Never modified; used as the source of truth for post-PoC enterprise rollout. |
| `poc-90day` | **Lean PoC** — stripped subset focused on the data pipeline, feature engineering, and minimal 3-layer AI services. Currently checked out. |
| `mukoma` / `main` | Original development branch(es). |

## What Was Removed from PoC (all recoverable)

| Module | Reason | How to Restore |
|---|---|---|
| `services/customer-state-service/app/engines/hmm/` | Hidden Markov Model — marked "future" | `git checkout architecture-target-full -- services/customer-state-service/app/engines/hmm/` |
| `services/decision-intelligence-service/app/reinforcement_learning/` | RL engine — marked "future" | `git checkout architecture-target-full -- services/decision-intelligence-service/app/reinforcement_learning/` |
| `etl/connectors/streaming/` | Kafka/Debezium stubs — not implemented | `git checkout architecture-target-full -- etl/connectors/streaming/` |
| `etl/connectors/api/` | REST/SOAP connectors — not needed for CSV-based PoC | `git checkout architecture-target-full -- etl/connectors/api/` |
| `docker-compose.yml` `orchestration-service` | Service not yet implemented | Uncomment in compose file, restore from `architecture-target-full` |

## What's Active on PoC

- **ETL Engine** — production-hardened, all 10 validation categories verified
- **Feature Engineering Service** — next deliverable (Month 1 "Data Foundation")
- **Layer 1**: Customer State Service (minimal Markov, no HMM)
- **Layer 2**: Prediction Service (minimal XGBoost/LightGBM, no champion/challenger)
- **Layer 3**: Decision Intelligence Service (rule engine only, no RL)
- **Dashboard Service** — functional, not polished
- **PostgreSQL + Redis** — infrastructure

## Verification

```bash
# Confirm reference branch is an exact snapshot (no divergence from original state)
git diff mukoma architecture-target-full   # should show no differences

# ETL regression (must pass before any merge)
pytest tests/test_validation_ground_truth.py -v

# Restore any removed module
git checkout architecture-target-full -- path/to/module/
```
