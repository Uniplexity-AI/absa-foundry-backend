"""
Shared Database Session - Async session factory and context management.

Provides async SQLAlchemy sessions with automatic transaction handling:
- Source session: connects to the raw/validation database
- Target session: connects to the clean/transformed database

Use get_session() / get_target_session() as FastAPI dependencies
or with session_context() / target_session_context() for scripts.

TODO:
Add read/write session routing when read replicas are introduced.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.database.postgres import get_engine, get_target_engine

_session_factory: async_sessionmaker[AsyncSession] | None = None
_target_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the singleton async session factory for the source DB."""
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


def _get_target_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the singleton async session factory for the target (clean) DB."""
    global _target_session_factory
    if _target_session_factory is None:
        engine = get_target_engine()
        _target_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _target_session_factory


@asynccontextmanager
async def session_context() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager providing a source-DB session with automatic commit/rollback."""
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


@asynccontextmanager
async def target_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager providing a target (clean) DB session with auto commit/rollback."""
    factory = _get_target_session_factory()
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
    """FastAPI dependency that yields a source async database session."""
    async with session_context() as session:
        yield session


async def get_target_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a target (clean) async database session."""
    async with target_session_context() as session:
        yield session


def reset_session_factory() -> None:
    """Reset all session factories. Used in tests."""
    global _session_factory, _target_session_factory
    _session_factory = None
    _target_session_factory = None