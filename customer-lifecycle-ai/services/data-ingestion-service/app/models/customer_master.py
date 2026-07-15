"""
Shared Database Base - SQLAlchemy 2.0 declarative base and common model mixins.

Every ORM model in the project extends Base.
Mixins provide created_at, updated_at, soft-delete, and schema-aware table naming.

TODO:
Add tenant_id mixin when multi-tenancy support is needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Return current datetime in UTC. Used as default for timestamp columns."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base. All ORM models extend this."""
    pass


class TimestampMixin:
    """Adds created_at and updated_at columns to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
        comment="Timestamp when the record was created (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        onupdate=utcnow,
        nullable=False,
        comment="Timestamp when the record was last updated (UTC)",
    )


class AuditMixin(TimestampMixin):
    """Extends TimestampMixin with created_by and updated_by for audit trails."""

    created_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Identifier of the user or service that created this record",
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Identifier of the user or service that last updated this record",
    )


class SoftDeleteMixin:
    """Adds soft-delete support via is_deleted flag."""

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=func.false(), nullable=False,
        comment="Soft-delete flag - TRUE means logically deleted",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp when the record was soft-deleted (UTC)",
    )


class SurrogatePK:
    """Adds a BIGINT surrogate primary key named id."""

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
        comment="Surrogate primary key",
    )


class UUIDBusinessKey:
    """Adds a UUID business key column for external identification."""

    uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False,
        comment="UUID business key for external identification",
    )


class StandardModel(SurrogatePK, AuditMixin, SoftDeleteMixin):
    """Complete standard model: surrogate PK + audit timestamps + soft-delete."""
    pass


class ImmutableModel(SurrogatePK, TimestampMixin):
    """Base for append-only tables. No soft-delete, no updated_by."""
    pass