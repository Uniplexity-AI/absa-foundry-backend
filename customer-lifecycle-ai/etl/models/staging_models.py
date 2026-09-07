"""
ETL Staging Models - SQLAlchemy 2.0 ORM models for staging tables.

Staging tables in the 'staging' schema mirror production tables.
They are temporary — truncated after successful clean load.

Tables:
- stg_customer: Customer master data
- stg_account: Account data
- stg_transaction: Banking transactions
- stg_branch: Branch/channel data
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Staging Customer
# ---------------------------------------------------------------------------

class StgCustomer(Base, TimestampMixin):
    """Staging table for customer master data."""
    __tablename__ = "stg_customer"
    __table_args__ = {
        "schema": "staging",
        "comment": "Staging table for customer master data — truncated after clean load",
    }

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="Batch that loaded this record",
    )
    customer_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="Source system customer identifier",
    )
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    address_postal_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    customer_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    segment_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    risk_category: Mapped[str | None] = mapped_column(String(16), nullable=True)
    onboarding_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


# ---------------------------------------------------------------------------
# Staging Account
# ---------------------------------------------------------------------------

class StgAccount(Base, TimestampMixin):
    """Staging table for account data."""
    __tablename__ = "stg_account"
    __table_args__ = {
        "schema": "staging",
        "comment": "Staging table for account data — truncated after clean load",
    }

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    account_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    available_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    branch_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


# ---------------------------------------------------------------------------
# Staging Transaction
# ---------------------------------------------------------------------------

class StgTransaction(Base, TimestampMixin):
    """Staging table for banking transactions."""
    __tablename__ = "stg_transaction"
    __table_args__ = {
        "schema": "staging",
        "comment": "Staging table for transactions — truncated after clean load",
    }

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True,
    )
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    transaction_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    transaction_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    branch_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_qualifying_activity: Mapped[bool] = mapped_column(default=False)
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


# ---------------------------------------------------------------------------
# Staging Branch
# ---------------------------------------------------------------------------

class StgBranch(Base, TimestampMixin):
    """Staging table for branch/channel reference data."""
    __tablename__ = "stg_branch"
    __table_args__ = {
        "schema": "staging",
        "comment": "Staging table for branch data — truncated after clean load",
    }

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    branch_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    province: Mapped[str | None] = mapped_column(String(128), nullable=True)
    branch_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    opened_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
