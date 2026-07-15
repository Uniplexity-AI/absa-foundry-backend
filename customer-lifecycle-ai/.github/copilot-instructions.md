# GitHub Copilot Instructions — Customer Lifecycle Prediction System

## Before Generating Any Code

Read these files in order before writing any implementation:

1. `.ai/project-context.md` — What we're building and the banking constraints
2. `.ai/current-sprint.md` — What's in progress right now (Phase 2: Database & APIs)
3. `.ai/architecture.md` — 3-Layer AI architecture and service boundaries
4. `.ai/coding-standards.md` — How code must be structured

For task-specific guidance, also read the relevant skill file in `.ai/skills/`.

## Mandatory Rules

- **Never bypass the Service Layer.** Business logic lives in `app/services/service.py`. Routes only delegate.
- **Never create duplicate code.** Check `shared/` first.
- **Always use Repository Pattern.** Data access through `app/repository/repository.py`.
- **All configuration via environment variables.** Read from `app/config/settings.py`.
- **Every Python file must have a module docstring and TODO comment.**
- **Type hints on ALL function signatures.** Use Python 3.12+ syntax (`str | None`, not `Optional[str]`).
- **Pydantic v2 for all data validation.** No v1 syntax.
- **Google-style docstrings** for all public functions and classes.
- **No Django, no Flask, no raw SQL in services.**

## Test Requirements

Every change must include:
- Unit tests in `tests/unit/`
- The test type must match the right subdirectory (`unit/`, `integration/`, `performance/`, `security/`)

## Project Structure

- `services/` — 8 microservices (3-layer AI: customer-state → prediction → decision-intelligence)
- `shared/` — Reusable code (database, auth, logging, exceptions, ml, schemas)
- `gateway/` — API Gateway (auth, routing, rate limiting)
- `models/` — ML model artifacts (champion/challenger)

## What NOT to Do

- Do not implement ML logic yet (Phase 2 is database + APIs only)
- Do not use Kubernetes, Helm, or Terraform (Docker Compose only)
- Do not hardcode file paths, URLs, or credentials
- Do not skip type hints
- Do not write business logic in `routes.py` or `models.py`
