"""
Shared PostgreSQL Connection - Async engine and connection pool configuration.

Creates a single async SQLAlchemy engine instance for the entire application.
Configured for PostgreSQL 16 with asyncpg driver.

TODO:
Add read-replica engine support when horizontal scaling is needed.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from shared.config.settings import settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Return the singleton async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            echo=settings.environment == "development",
            future=True,
        )
    return _engine


def get_sync_url() -> str:
    """Return the synchronous database URL for Alembic migrations."""
    return settings.database_url_sync


def reset_engine() -> None:
    """Dispose and reset the engine singleton. Used in tests."""
    global _engine
    if _engine is not None:
        _engine.sync_engine.dispose()
        _engine = None