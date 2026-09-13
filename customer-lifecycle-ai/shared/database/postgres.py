"""
Shared PostgreSQL Connection - Async engine and connection pool configuration.

Creates async SQLAlchemy engine instances for the entire application:
- Source engine: connects to the raw/validation database (etl_validation)
- Target engine: connects to the clean/transformed database (etl_clean)

Configured for PostgreSQL 16 with asyncpg driver.

TODO:
Add read-replica engine support when horizontal scaling is needed.
"""

from __future__ import annotations

from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy import Engine as SyncEngine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from shared.config.settings import settings

_engine: AsyncEngine | None = None
_target_engine: AsyncEngine | None = None
_sync_engine: SyncEngine | None = None
_sync_target_engine: SyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Return the singleton async SQLAlchemy engine for the source DB."""
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


def get_target_engine() -> AsyncEngine:
    """Return the singleton async SQLAlchemy engine for the target (clean) DB."""
    global _target_engine
    if _target_engine is None:
        _target_engine = create_async_engine(
            settings.database_target_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            echo=settings.environment == "development",
            future=True,
        )
    return _target_engine


def get_sync_url() -> str:
    """Return the synchronous database URL for Alembic migrations."""
    return settings.database_url_sync


def get_sync_engine() -> SyncEngine:
    """Return a singleton synchronous SQLAlchemy engine for the source DB.

    Used by the Dynamic Extractor and any component that needs
    synchronous DB access (reflection, inspection, raw queries).
    """
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_sync_engine(
            settings.database_url_sync,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            echo=settings.environment == "development",
            future=True,
        )
    return _sync_engine


def get_sync_target_engine() -> SyncEngine:
    """Return a singleton synchronous SQLAlchemy engine for the target (clean) DB.

    Used by services that expose synchronous SQLAlchemy Session dependencies
    (e.g. the Model Management Service, whose tables live in the clean DB).
    """
    global _sync_target_engine
    if _sync_target_engine is None:
        _sync_target_engine = create_sync_engine(
            settings.database_target_url_sync,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            echo=settings.environment == "development",
            future=True,
        )
    return _sync_target_engine


def reset_engine() -> None:
    """Dispose and reset the engine singletons. Used in tests."""
    global _engine, _target_engine, _sync_engine, _sync_target_engine
    if _engine is not None:
        _engine.sync_engine.dispose()
        _engine = None
    if _target_engine is not None:
        _target_engine.sync_engine.dispose()
        _target_engine = None
    if _sync_engine is not None:
        _sync_engine.dispose()
        _sync_engine = None
    if _sync_target_engine is not None:
        _sync_target_engine.dispose()
        _sync_target_engine = None
    return None