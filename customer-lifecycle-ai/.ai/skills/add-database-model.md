# Skill: Implementing a Database Model

## Steps (In Order)

1. **Create ORM Model** — `app/models/models.py`
   ```python
   from sqlalchemy.orm import Mapped, mapped_column
   from shared.database.base import Base

   class CustomerState(Base):
       __tablename__ = "customer_states"

       id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
       customer_id: Mapped[str] = mapped_column(unique=True, index=True)
       current_state: Mapped[str] = mapped_column(default="Active")
       transition_probability: Mapped[float | None]
   ```

2. **Create Pydantic Schema** — `app/schemas/schemas.py`
   ```python
   from pydantic import BaseModel, ConfigDict

   class CustomerStateResponse(BaseModel):
       model_config = ConfigDict(from_attributes=True)
       id: int
       customer_id: str
       current_state: str
       transition_probability: float | None
   ```

3. **Register Migration** — run `alembic revision --autogenerate -m "add customer_states"`

4. **Add to `__init__.py`** — make sure model is imported so Alembic discovers it

## Rules

- Always extend `shared.database.base.Base`
- Use `Mapped[T]` and `mapped_column()` (SQLAlchemy 2.0 style)
- Use `str | None`, not `Optional[str]`
- Always add indexes on foreign keys and frequently queried columns
- Never put business logic in model classes (they're pure data)
- Table names: snake_case, plural where appropriate
