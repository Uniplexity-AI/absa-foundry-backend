"""
Banking ORM Models — Operational Database Tier.

Accounts, transactions, products, loans, cards, and digital channels.
All models follow the v2 Database Design Specification.

Schemas: accounts, transactions, products, loans, cards, channels
Owning Service: data-ingestion-service

TODO:
Add partition management for transaction and digital_activity tables.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.base import Base, StandardModel


# ---------------------------------------------------------------------------
# accounts schema
# ---------------------------------------------------------------------------

class Account(StandardModel, Base):
    """Bank account master — savings, current, fixed deposit, etc."""

    __tablename__ = "account"
    __table_args__ = (
        UniqueConstraint("account_number", name="uq_account_account_number"),
        {"schema": "accounts", "comment": "Bank account master data"},
    )

    account_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customer_master.customer.id"), nullable=False, index=True,
    )
    account_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="SAVINGS, CURRENT, FIXED_DEPOSIT, RECURRING_DEPOSIT, OVERDRAFT",
    )
    account_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE",
        comment="ACTIVE, DORMANT, FROZEN, CLOSED",
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", comment="ISO 4217")
    opened_date: Mapped[date] = mapped_column(Date, nullable=False)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    available_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    is_joint_account: Mapped[bool] = mapped_column(default=False)

    # ORM
    customer: Mapped["Customer"] = relationship(back_populates="accounts")
    holders: Mapped[list["AccountHolder"]] = relationship(back_populates="account")
    balance_snapshots: Mapped[list["AccountBalanceSnapshot"]] = relationship(back_populates="account")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class AccountHolder(StandardModel, Base):
    """Junction table for joint account ownership."""

    __tablename__ = "account_holder"
    __table_args__ = (
        UniqueConstraint("account_id", "customer_id", name="uq_account_holder"),
        {"schema": "accounts", "comment": "Joint account holder junction"},
    )

    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.account.id"), nullable=False,
    )
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customer_master.customer.id"), nullable=False,
    )
    holder_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="JOINT",
        comment="PRIMARY, JOINT, GUARANTOR",
    )
    ownership_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)

    # ORM
    account: Mapped[Account] = relationship(back_populates="holders")


class AccountBalanceSnapshot(StandardModel, Base):
    """Daily balance snapshot for trend analysis. Populated by nightly ETL."""

    __tablename__ = "account_balance_snapshot"
    __table_args__ = (
        UniqueConstraint("account_id", "snapshot_date", name="uq_balance_snapshot"),
        {"schema": "accounts", "comment": "Daily account balance snapshots"},
    )

    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.account.id"), nullable=False, index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    available_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_credits: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    total_debits: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # ORM
    account: Mapped[Account] = relationship(back_populates="balance_snapshots")


# ---------------------------------------------------------------------------
# transactions schema
# ---------------------------------------------------------------------------

class TransactionCategory(StandardModel, Base):
    """Configurable transaction category lookup."""

    __tablename__ = "transaction_category"
    __table_args__ = (
        UniqueConstraint("category_code", name="uq_txn_category_code"),
        {"schema": "transactions", "comment": "Transaction category lookup"},
    )

    category_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class Transaction(StandardModel, Base):
    """All financial transactions — partitioned by transaction_date (monthly)."""

    __tablename__ = "transaction"
    __table_args__ = (
        UniqueConstraint("transaction_ref", name="uq_transaction_ref"),
        {"schema": "transactions", "comment": "Financial transactions (partitioned by month)"},
    )

    transaction_ref: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.account.id"), nullable=False, index=True,
    )
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
        comment="Partition key — RANGE by month",
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    transaction_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="CREDIT, DEBIT, TRANSFER, FEE, INTEREST, REVERSAL",
    )
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="BRANCH, ATM, MOBILE, INTERNET, POS, AGENT, SWIFT",
    )
    category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transactions.transaction_category.id"), nullable=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    running_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_flagged: Mapped[bool] = mapped_column(default=False, comment="Flagged for review")

    # ORM
    account: Mapped[Account] = relationship(back_populates="transactions")


# ---------------------------------------------------------------------------
# products schema
# ---------------------------------------------------------------------------

class Product(StandardModel, Base):
    """Product catalog — all bank products."""

    __tablename__ = "product"
    __table_args__ = (
        UniqueConstraint("product_code", name="uq_product_code"),
        {"schema": "products", "comment": "Bank product catalog"},
    )

    product_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="ACCOUNT, LOAN, CARD, INSURANCE, INVESTMENT, FOREX",
    )
    product_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    fee_structure: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON fee structure")
    min_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)


class CustomerProductHolding(StandardModel, Base):
    """Which products each customer holds, with dates."""

    __tablename__ = "customer_product_holding"
    __table_args__ = (
        {"schema": "products", "comment": "Customer product holdings"},
    )

    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customer_master.customer.id"), nullable=False, index=True,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.product.id"), nullable=False,
    )
    acquired_date: Mapped[date] = mapped_column(Date, nullable=False)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    holding_status: Mapped[str] = mapped_column(
        String(20), default="ACTIVE",
        comment="ACTIVE, CLOSED, SUSPENDED",
    )
    account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("accounts.account.id"), nullable=True,
        comment="Link to the specific account if applicable",
    )

    # ORM
    customer: Mapped["Customer"] = relationship(back_populates="product_holdings")


# ---------------------------------------------------------------------------
# loans schema
# ---------------------------------------------------------------------------

class Loan(StandardModel, Base):
    """Loan accounts — personal, mortgage, auto, business."""

    __tablename__ = "loan"
    __table_args__ = (
        UniqueConstraint("loan_number", name="uq_loan_number"),
        {"schema": "loans", "comment": "Loan accounts"},
    )

    loan_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customer_master.customer.id"), nullable=False, index=True,
    )
    loan_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="PERSONAL, MORTGAGE, AUTO, BUSINESS, OVERDRAFT, CREDIT_LINE",
    )
    loan_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE",
        comment="ACTIVE, SETTLED, DEFAULTED, RESTRUCTURED, WRITTEN_OFF",
    )
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    outstanding_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    interest_rate_type: Mapped[str] = mapped_column(String(10), default="FIXED", comment="FIXED, VARIABLE")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    delinquency_days: Mapped[int] = mapped_column(Integer, default=0, comment="Days past due")
    monthly_installment: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # ORM
    customer: Mapped["Customer"] = relationship(back_populates="loans")
    repayments: Mapped[list["LoanRepayment"]] = relationship(back_populates="loan")


class LoanRepayment(StandardModel, Base):
    """Scheduled and actual loan repayments."""

    __tablename__ = "loan_repayment"
    __table_args__ = (
        {"schema": "loans", "comment": "Loan repayment schedule and actuals"},
    )

    loan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("loans.loan.id"), nullable=False, index=True,
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount_paid: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_on_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True,
        comment="TRUE if paid on or before due_date")
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # ORM
    loan: Mapped[Loan] = relationship(back_populates="repayments")


# ---------------------------------------------------------------------------
# cards schema
# ---------------------------------------------------------------------------

class Card(StandardModel, Base):
    """Credit and debit cards."""

    __tablename__ = "card"
    __table_args__ = (
        UniqueConstraint("card_number_suffix", "customer_id", name="uq_card_suffix_customer"),
        {"schema": "cards", "comment": "Credit and debit cards"},
    )

    card_number_suffix: Mapped[str] = mapped_column(String(4), nullable=False, comment="Last 4 digits only")
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customer_master.customer.id"), nullable=False, index=True,
    )
    account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("accounts.account.id"), nullable=True,
    )
    card_type: Mapped[str] = mapped_column(String(10), nullable=False, comment="DEBIT, CREDIT, PREPAID")
    card_status: Mapped[str] = mapped_column(String(20), default="ACTIVE", comment="ACTIVE, BLOCKED, EXPIRED, CANCELLED")
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    issued_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_contactless: Mapped[bool] = mapped_column(default=False)
    card_network: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="VISA, MASTERCARD, AMEX")

    # ORM
    customer: Mapped["Customer"] = relationship(back_populates="cards")


# ---------------------------------------------------------------------------
# channels schema
# ---------------------------------------------------------------------------

class DigitalActivity(StandardModel, Base):
    """Digital banking login and activity tracking. Used by customer-state-service."""

    __tablename__ = "digital_activity"
    __table_args__ = (
        {"schema": "channels", "comment": "Digital banking activity log"},
    )

    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customer_master.customer.id"), nullable=False, index=True,
    )
    activity_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    activity_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="LOGIN, BALANCE_CHECK, TRANSFER, BILL_PAY, PROFILE_UPDATE, PASSWORD_CHANGE",
    )
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="MOBILE_APP, WEB_BROWSER, USSD, ATM",
    )
    device_type: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="IOS, ANDROID, DESKTOP")
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    session_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_successful: Mapped[bool] = mapped_column(default=True, comment="FALSE if login failed")


class ChannelPreference(StandardModel, Base):
    """Customer channel preferences and adoption tracking."""

    __tablename__ = "channel_preference"
    __table_args__ = (
        {"schema": "channels", "comment": "Customer channel preferences"},
    )

    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customer_master.customer.id"), nullable=False, index=True,
    )
    channel: Mapped[str] = mapped_column(String(30), nullable=False, comment="BRANCH, MOBILE, INTERNET, ATM, CALL_CENTER")
    is_primary: Mapped[bool] = mapped_column(default=False)
    adoption_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_used_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    usage_frequency: Mapped[str | None] = mapped_column(String(20), nullable=True,
        comment="DAILY, WEEKLY, MONTHLY, RARELY, NEVER")