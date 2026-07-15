# Standards — Detailed Conventions

## Naming Conventions

### Files
- `snake_case.py` for all Python files
- `test_<module>.py` for test files
- `conftest.py` for pytest fixtures
- `Dockerfile` (capital D, no extension)

### Classes
- `PascalCase` — `PredictionService`, `CustomerStateRepository`
- Suffix: `Service` for business logic, `Repository` for data access

### Functions & Methods
- `snake_case` — `predict_churn()`, `get_features()`
- Async methods: `async def` prefix

### Database Tables
- `snake_case`, plural where appropriate
- Schema-prefixed in queries: `features.customer_transactions`

### Environment Variables
- `UPPER_SNAKE_CASE`
- Service-specific: `PREDICTION_MODEL_TYPE`, `CUSTOMER_STATE_MARKOV_ORDER`

## Import Order

```
1. Standard library (os, sys, typing)
2. Third-party (fastapi, sqlalchemy, pydantic)
3. Shared modules (shared.database.base, shared.exceptions)
4. Service-local modules (from .services import ...)
```

## Git Conventions

### Branches
- `feature/<service>/<description>` — New features
- `fix/<service>/<description>` — Bug fixes
- `chore/<description>` — Infrastructure, docs, tooling

### Commits
- `feat(customer-state): add Markov transition matrix computation`
- `fix(prediction): handle null feature values in churn model`
- `chore(docs): update architecture diagram`

## Error Handling Patterns

```python
# ✅ DO: Custom exceptions with context
from shared.exceptions.base import DomainError

class CustomerNotFoundError(DomainError):
    """Raised when a customer ID does not exist in the system."""
    def __init__(self, customer_id: str) -> None:
        super().__init__(f"Customer {customer_id} not found")
        self.customer_id = customer_id

# ❌ DON'T: Generic exceptions
raise Exception("Customer not found")
```

## Logging Patterns

```python
import logging
logger = logging.getLogger(__name__)

# ✅ DO: Structured logging with context
logger.info("Churn prediction completed", extra={
    "customer_id": customer_id,
    "churn_probability": probability,
    "model_version": version,
})

# ❌ DON'T: Bare string logging
logger.info(f"Predicted churn for {customer_id}: {probability}")
```

## API Response Patterns

```python
# ✅ DO: Consistent response envelope
class APIResponse[T](BaseModel):
    success: bool = True
    data: T | None = None
    error: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

# For lists:
class PaginatedResponse[T](APIResponse[list[T]]):
    total: int
    page: int
    page_size: int
```
