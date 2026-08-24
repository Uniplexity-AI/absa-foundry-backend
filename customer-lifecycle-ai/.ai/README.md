# AI Development Guide — Customer Lifecycle Prediction System

> **CRITICAL:** Read this file first before making ANY code changes.
> **ETL Status:** Production-hardened. Validation verified against ground truth (10/10 categories, 800/800 dirty rows). Run `python verify.py --verbose` after any ETL change.

---

## Before You Write Code

Read these documents **in order** before generating any implementation:

| # | Document / Graph | Purpose |
|---|------------------|---------|
| 1 | [project-context.md](./project-context.md) | What we're building and why |
| 2 | [current-sprint.md](./current-sprint.md) | What's in progress right now |
| 3 | [architecture.md](./architecture.md) | 3-Layer AI architecture and service boundaries |
| 4 | [coding-standards.md](./coding-standards.md) | How we write code |
| 5 | [skills/](./skills/) | Task-specific guidance (pick the relevant one) |
| 6 | [graphify-out/GRAPH_REPORT.md](../graphify-out/GRAPH_REPORT.md) | Codebase semantic graph (580+ files mapped) |

---

## Token Efficiency Protocol (Surgical Code Navigation)

To minimize context token usage and ensure surgical accuracy, AI agents must strictly follow this navigation protocol:

1. **Consult the semantic map first**: Instead of listing directories or grepping full files, read `graphify-out/GRAPH_REPORT.md` first. It breaks down the entire 427,000-word codebase into semantic communities. Use it to trace bridges (like `BaseModel` or `ConnectorConfig`) and locate the exact files matching your domain.
2. **Reuse pre-engineered templates**: Never ask the LLM to invent code patterns. Look at `.ai/skills/` first. It contains fully validated patterns for FastAPI routing, SQLAlchemy models, Pytest setups, and ML training pipelines.
3. **Perform targeted, partial file reads**: Never read entire large files. Request an outline, find the exact functions or classes of interest, and read only their specific lines using `start_line` and `end_line` ranges.
4. **Make surgically minimal edits**: Keep conversational history lean by performing highly focused, minimal line replacements. Rewriting whole files wastes thousands of output tokens and increases latency.

---

## Quick Rules (Always Follow)

1. **Never bypass the Service Layer.** All business logic lives in `app/services/`. Routes only delegate.
2. **Never create duplicate code.** Check `shared/` first — if it exists there, reuse it.
3. **Always use Repository Pattern.** Data access goes through `app/repository/`, never raw SQL in services.
4. **All configuration via environment variables.** Read from `app/config/settings.py`, never hardcode.
5. **Every Python file must have a module docstring and TODO comment.** No exceptions.
6. **Tests go in the proper subdirectory:** `unit/`, `integration/`, `performance/`, `security/`, or `fixtures/`.
7. **ETL changes must pass the fixture regression test:** `pytest tests/test_validation_ground_truth.py -v` before merging.
8. **Never change the fixture CSV** (`tests/fixtures/etl_validation_customers.csv`) — its value is that it never changes.

---

## Running Tests

```bash
# ETL fixture regression — runs pipeline once against known fixture, asserts all 10 categories
pytest tests/test_validation_ground_truth.py -v

# Ground-truth comparison (source vs target DB counts)
python verify.py --verbose

# ETL pipeline — dry run (validate only, no DB writes)
python run_etl.py --dry-run

# ETL pipeline — full run against fixture
python run_etl.py --force

# ETL pipeline — custom CSV
python run_etl.py --csv path/to/data.csv

# All tests (when Phase 2b API tests are added)
pytest tests/ -v
```

---

## Project Layout Quick Reference

```
customer-lifecycle-ai/
├── services/
│   ├── customer-state-service/       # Layer 1: Behaviour Intelligence (Markov)
│   ├── prediction-service/           # Layer 2: Prediction Intelligence (XGBoost/LightGBM)
│   ├── decision-intelligence-service/# Layer 3: Decision Intelligence (NBA)
│   ├── feature-engineering-service/  # Central Feature Store
│   ├── model-management-service/     # Champion/Challenger model registry
│   ├── model-management-service/     # Champion/Challenger model registry
│   ├── dashboard-service/            # Analytics data
│   └── orchestration-service/        # Workflow coordination
├── shared/                           # Reusable code — CHECK HERE FIRST
├── gateway/                          # API Gateway (auth, routing, rate limiting)
├── models/                           # ML model artifacts (champion/challenger)
├── infrastructure/                   # Docker, nginx, postgres, redis configs
└── research/                         # Jupyter notebooks for experimentation
```

---

## If Something Is Unclear

- `architecture.md` has the service responsibility boundaries
- `skills/` has task-specific patterns
- `standards/` has detailed conventions
- `ABSA-KNOWLEDGE-BASE.md` has the consolidated reference
- The `README.md` at the project root has the full overview

**Do not guess. Read the relevant document.**

---

## .ai Directory Structure

```
.ai/
├── README.md                 ← YOU ARE HERE
├── project-context.md        What we're building, who uses it, domain terms
├── current-sprint.md         Live sprint status, completed/remaining
├── architecture.md           3-Layer AI system, service boundaries
├── coding-standards.md       Python style, Pydantic, repository pattern
├── terminal-patterns.md      18+ pre-flight checks, PowerShell/uv/DB fixes
├── MEMORIES.md                Persistent agent memory bank — rules + learning ledger
├── ABSA-KNOWLEDGE-BASE.md    Consolidated reference (everything in one doc)
├── skills/
│   ├── add-api-endpoint.md   FastAPI route creation
│   ├── add-database-model.md DB schema/model creation
│   ├── add-feature.md        Feature engineering
│   ├── ml-model-training.md  XGBoost/LightGBM training
│   └── writing-tests.md      Pytest patterns
└── standards/
    └── conventions.md        Naming and structure conventions
```
