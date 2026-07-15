# Skill: Implementing a New API Endpoint

## Steps (In Order)

1. **Define the Schema** — `app/schemas/schemas.py`
   - Create Pydantic v2 models for `Request` and `Response`
   - Use `pydantic.BaseModel`, not `dataclasses`
   - Add `model_config = ConfigDict(from_attributes=True)` for ORM compatibility

2. **Define the ORM Model (if new table)** — `app/models/models.py`
   - Use SQLAlchemy 2.0 declarative style
   - Include `__tablename__` and all columns
   - Add relationships if needed

3. **Implement Repository Method** — `app/repository/repository.py`
   - Add data access method
   - Use async SQLAlchemy sessions
   - Raise domain-specific exceptions for not-found cases

4. **Implement Service Method** — `app/services/service.py`
   - All business logic here
   - Call repository, not raw SQL
   - Transform ORM → Pydantic response
   - Add logging at INFO level for important operations

5. **Add Route** — `app/api/routes.py`
   - Keep it thin — one line delegation to service
   - Add proper HTTP status codes
   - Use `Depends()` for dependency injection

6. **Write Tests**
   - Unit test the service with mocked repository
   - Integration test the endpoint with test database
   - Security test input validation edge cases

## Checklist

- [ ] Schema uses Pydantic v2
- [ ] Repository uses async sessions
- [ ] Service has type hints on all methods
- [ ] Route delegates to service (no logic in route)
- [ ] Custom exceptions from `shared/exceptions/`
- [ ] Module docstring and TODO comment present
- [ ] Unit test covers happy path + error cases
- [ ] Integration test hits the endpoint
