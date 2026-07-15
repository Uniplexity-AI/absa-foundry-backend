# Coding Standards — Customer Lifecycle Prediction System

## Python Style

- **Python 3.12+** syntax only (use `str | None`, not `Optional[str]`)
- **Type hints on ALL function signatures** — no untyped parameters or returns
- **Pydantic v2** for all data validation (no v1 syntax)
- **Google-style docstrings** for all public functions and classes

### Example Function Signature

```python
from pydantic import BaseModel

class PredictionRequest(BaseModel):
    customer_id: str
    model_type: str = "xgboost"

def predict_churn(
    request: PredictionRequest,
    model_version: str | None = None,
) -> dict[str, float]:
    """Predict customer churn probability.

    Args:
        request: Prediction request with customer ID and model type.
        model_version: Optional specific model version to use. Defaults to champion.

    Returns:
        Dict with churn_probability and model_metadata.

    Raises:
        ModelNotFoundError: If specified model version does not exist.
    """
    ...
```

## Project Structure Rules

### Every Service Module Must Have

```
module/
├── __init__.py          # Module docstring only
├── api/
│   ├── __init__.py
│   ├── routes.py        # FastAPI route definitions (thin — delegate to services)
│   └── dependencies.py  # FastAPI dependency injection
├── services/
│   ├── __init__.py
│   └── service.py       # ALL business logic here
├── repository/
│   ├── __init__.py
│   └── repository.py    # ALL data access here (SQLAlchemy sessions)
├── models/
│   ├── __init__.py
│   └── models.py        # SQLAlchemy ORM models
├── schemas/
│   ├── __init__.py
│   └── schemas.py       # Pydantic v2 models (request/response)
└── config/
    ├── __init__.py
    ├── settings.py      # pydantic-settings BaseSettings
    └── logging.py       # Service-specific logging config
```

### Test Module

```
tests/
├── __init__.py
├── conftest.py          # Pytest fixtures shared across test types
├── unit/                # Fast, no I/O, mock dependencies
│   └── test_*.py
├── integration/         # Database, API, inter-service
│   └── test_*.py
├── performance/         # Latency benchmarks, load tests
│   └── test_*.py
├── security/            # Input validation, injection, auth bypass
│   └── test_*.py
└── fixtures/            # Test data factories, mock data
    └── data.py
```

## Layer Separation Rules

### Routes (api/routes.py)

```python
# ✅ CORRECT: Thin route, delegates to service
@router.post("/predict/churn")
async def predict_churn(
    request: PredictionRequest,
    service: PredictionService = Depends(get_prediction_service),
) -> PredictionResponse:
    return await service.predict_churn(request)

# ❌ WRONG: Business logic in route
@router.post("/predict/churn")
async def predict_churn(request: PredictionRequest, db: Session = Depends(get_db)):
    model = load_model(...)  # NO — this goes in the service
    result = model.predict(...)
    return result
```

### Services (services/service.py)

```python
# ✅ CORRECT: Service uses repository for data access
class PredictionService:
    def __init__(self, repository: PredictionRepository) -> None:
        self._repo = repository

    async def predict_churn(self, request: PredictionRequest) -> PredictionResponse:
        features = await self._repo.get_features(request.customer_id)
        model = await self._get_model(request.model_type)
        probability = model.predict(features)
        shap_values = self._compute_shap(model, features)
        return PredictionResponse(churn_probability=probability, shap_values=shap_values)

# ❌ WRONG: Service doing raw SQL
class PredictionService:
    async def predict_churn(self, request):
        session.execute(text("SELECT * FROM features"))  # NO — use repository
```

### Repository (repository/repository.py)

```python
# ✅ CORRECT: Repository encapsulates all data access
class PredictionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_features(self, customer_id: str) -> FeatureSet:
        stmt = select(CustomerFeatures).where(CustomerFeatures.customer_id == customer_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise CustomerNotFoundError(customer_id)
        return FeatureSet.from_orm(row)

# ❌ WRONG: Repository with business logic
class PredictionRepository:
    async def get_features(self, customer_id):
        features = ...
        scored = some_business_rule(features)  # NO — this goes in service
        return scored
```

## Configuration

All configuration via environment variables. Use `pydantic-settings`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PREDICTION_")

    model_type: str = "xgboost"
    database_url: str
    redis_url: str | None = None
    health_score_churn_weight: float = 0.40
    health_score_clv_weight: float = 0.30
    health_score_behaviour_weight: float = 0.30
```

**Never** hardcode URLs, paths, or credentials.

## Error Handling

- Use custom exceptions from `shared/exceptions/`
- Never expose internal errors in API responses
- Always log exceptions with full context before re-raising
- Catch specific exceptions, never bare `except:`

## Imports

- Standard library first, then third-party, then project modules
- Use absolute imports: `from prediction_service.app.services.service import PredictionService`
- Avoid wildcard imports: `from module import *`

## What NOT to Do

- ❌ Import Django (not used in this project)
- ❌ Use `os.environ` directly (use `Settings` class)
- ❌ Create `utils.py` dump files (use `shared/utils/` with focused modules)
- ❌ Hardcode file paths (use config)
- ❌ Write ML training code in API services (use `training/` modules)
- ❌ Skip type hints on any public function
- ❌ Write business logic in routes, models, or schemas
