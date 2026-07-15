"""
Shared Database Session - Async session factory and context management.

Provides async SQLAlchemy sessions with automatic transaction handling.
Use get_session() as a FastAPI dependency or with session_context() for scripts.

TODO:
Add read/write session routing when read replicas are introduced.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.database.postgres import get_engine

_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the singleton async session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def session_context() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager providing a session with automatic commit/rollback."""
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with session_context() as session:
        yield session


def reset_session_factory() -> None:
    """Reset the session factory. Used in tests."""
    global _session_factory
    _session_factory = None