"""
Data Lake ORM Models — Raw, Staging, and Clean layers.

Implements the v2 tiered data lake architecture:
  raw.*    — Exact copy from source. Immutable. Never modified.
  staging.*— Light transformations. Temporary. Truncated after clean load.
  clean.*  — Business-validated, deduplicated, standardized.

Schemas: raw, staging, clean
Owning Service: data-ingestion-service

TODO:
Add CDC (Change Data Capture) tracking columns for real-time ingestion.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, ImmutableModel, TimestampMixin


# ===========================================================================
# raw schema — Immutable, exact copy from source systems
# ===========================================================================

class RawCustomer(ImmutableModel, Base):
    """Raw customer data — exact copy from core banking system. Immutable."""

    __tablename__ = "raw_customer"
    __table_args__ = (
        {"schema": "raw", "comment": "Raw customer data from source systems (immutable)"},
    )

    ingest_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
        comment="Partition key — date this record was ingested",
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, comment="CORE_BANKING, CRM, etc.")
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="ID in the source system")
    raw_data: Mapped[dict] = mapped_column(
        String, nullable=False,
        comment="Full JSON payload from source system",
    )
    ingestion_batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="SHA-256 of raw_data for dedup")


class RawTransaction(ImmutableModel, Base):
    """Raw transaction data — exact copy from core banking system. Immutable."""

    __tablename__ = "raw_transaction"
    __table_args__ = (
        {"schema": "raw", "comment": "Raw transaction data from source systems (immutable)"},
    )

    ingest_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_data: Mapped[dict] = mapped_column(String, nullable=False)
    ingestion_batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class RawAccount(ImmutableModel, Base):
    """Raw account data — exact copy from core banking system. Immutable."""

    __tablename__ = "raw_account"
    __table_args__ = (
        {"schema": "raw", "comment": "Raw account data from source systems (immutable)"},
    )

    ingest_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_data: Mapped[dict] = mapped_column(String, nullable=False)
    ingestion_batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class RawLoan(ImmutableModel, Base):
    """Raw loan data — exact copy from core banking system. Immutable."""

    __tablename__ = "raw_loan"
    __table_args__ = (
        {"schema": "raw", "comment": "Raw loan data from source systems (immutable)"},
    )

    ingest_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_data: Mapped[dict] = mapped_column(String, nullable=False)
    ingestion_batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class RawCard(ImmutableModel, Base):
    """Raw card data — exact copy from core banking system. Immutable."""

    __tablename__ = "raw_card"
    __table_args__ = (
        {"schema": "raw", "comment": "Raw card data from source systems (immutable)"},
    )

    ingest_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_data: Mapped[dict] = mapped_column(String, nullable=False)
    ingestion_batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)


# ===========================================================================
# staging schema — Light transformations, temporary
# ===========================================================================

class StagingCustomer(TimestampMixin, Base):
    """Staging customer data — type casting, null handling. Transient."""

    __tablename__ = "staging_customer"
    __table_args__ = (
        {"schema": "staging", "comment": "Staging customer data (transient — truncated after clean load)"},
    )

    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("raw.raw_customer.id"), nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_ref: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(20), default="PENDING",
        comment="PENDING, VALID, INVALID")
    validation_errors: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON array of validation errors")


class StagingTransaction(TimestampMixin, Base):
    """Staging transaction data — type casting, null handling. Transient."""

    __tablename__ = "staging_transaction"
    __table_args__ = (
        {"schema": "staging", "comment": "Staging transaction data (transient)"},
    )

    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("raw.raw_transaction.id"), nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    transaction_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    transaction_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    validation_errors: Mapped[str | None] = mapped_column(Text, nullable=True)


# ===========================================================================
# clean schema — Business-validated, deduplicated. Foundation for features.
# ===========================================================================

class CleanCustomer(StandardModel, Base):
    """
    Clean customer data — validated, standardized, deduplicated.
    This is the source of truth for feature engineering.
    """

    __tablename__ = "clean_customer"
    __table_args__ = (
        UniqueConstraint("customer_ref", name="uq_clean_customer_ref"),
        UniqueConstraint("clean_hash", name="uq_clean_customer_hash"),
        {"schema": "clean", "comment": "Clean, validated customer data"},
    )

    customer_ref: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    clean_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False,
        comment="SHA-256 of all clean columns for change detection")
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    customer_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    customer_type: Mapped[str] = mapped_column(String(20), default="INDIVIDUAL")
    customer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("customer_master.customer.id"), nullable=True,
        comment="Link to operational customer record once matched",
    )
    last_clean_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="When this record was last cleaned/updated",
    )


class CleanTransaction(StandardModel, Base):
    """Clean transaction data — validated, standardized. Foundation for feature engineering."""

    __tablename__ = "clean_transaction"
    __table_args__ = (
        UniqueConstraint("transaction_ref", name="uq_clean_transaction_ref"),
        {"schema": "clean", "comment": "Clean, validated transaction data"},
    )

    transaction_ref: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("accounts.account.id"), nullable=True,
    )
    customer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("customer_master.customer.id"), nullable=True, index=True,
    )
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transactions.transaction_category.id"), nullable=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    clean_hash: Mapped[str] = mapped_column(String(64), nullable=False)


from sqlalchemy import UniqueConstraint