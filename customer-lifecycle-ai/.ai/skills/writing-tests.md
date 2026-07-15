# Skill: Writing Tests

## Test Type Decision Tree

```
Is it testing a single function/class in isolation?
  → unit/

Is it testing database queries or API endpoints?
  → integration/

Is it measuring response time or throughput?
  → performance/

Is it testing for injection, auth bypass, or data leaks?
  → security/

Are you creating reusable test data?
  → fixtures/
```

## Unit Test Template

```python
"""Unit tests for PredictionService."""

import pytest
from unittest.mock import AsyncMock

from prediction_service.app.services.service import PredictionService


@pytest.fixture
def mock_repository() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_repository: AsyncMock) -> PredictionService:
    return PredictionService(repository=mock_repository)


class TestPredictChurn:
    async def test_returns_probability_for_valid_customer(
        self, service: PredictionService, mock_repository: AsyncMock
    ) -> None:
        mock_repository.get_features.return_value = FeatureSet(...)
        result = await service.predict_churn(PredictionRequest(customer_id="CUST001"))
        assert 0.0 <= result.churn_probability <= 1.0

    async def test_raises_not_found_for_missing_customer(
        self, service: PredictionService, mock_repository: AsyncMock
    ) -> None:
        mock_repository.get_features.side_effect = CustomerNotFoundError("CUST999")
        with pytest.raises(CustomerNotFoundError):
            await service.predict_churn(PredictionRequest(customer_id="CUST999"))
```

## Integration Test Template

```python
"""Integration tests for prediction API."""

import pytest
from httpx import AsyncClient, ASGITransport
from prediction_service.main import app


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestPredictChurnEndpoint:
    async def test_returns_200_and_probability(self, client: AsyncClient) -> None:
        response = await client.post(
            "/predict/churn", json={"customer_id": "CUST001"}
        )
        assert response.status_code == 200
        assert "churn_probability" in response.json()
```

## Rules

- Use `pytest` and `pytest-asyncio`
- Mark async tests with `@pytest.mark.asyncio` or use `asyncio_mode = "auto"`
- Mock external dependencies in unit tests, use real DB in integration
- Security tests MUST test: SQL injection, XSS, oversized payloads, missing auth
- Performance tests MUST have a baseline assertion (e.g., p99 < 100ms)
- Test data in `fixtures/data.py`, never hardcoded in test files
