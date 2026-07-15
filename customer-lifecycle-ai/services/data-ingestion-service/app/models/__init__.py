"""
Data Ingestion Service — ORM Model Registry.

All models are imported here so Alembic and SQLAlchemy can discover them.
Organized by schema per the v2 Database Design Specification:
  - customer_master.py — Core customer identity and profiles
  - banking.py          — Accounts, transactions, products, loans, cards, channels
  - data_lake.py        — Raw, staging, and clean data lake layers

TODO:
Add remaining schemas as they are implemented (feature_store, predictions, etc.)
"""

from data_ingestion_service.app.models.customer_master import (
    Customer,
    CustomerRiskProfile,
    CustomerSegment,
    RelationshipManager,
    Branch,
    CustomerRMAssignment,
    CustomerContact,
    CustomerAddress,
    CustomerDocument,
    CustomerDemographic,
)
from data_ingestion_service.app.models.banking import (
    Account,
    AccountHolder,
    AccountBalanceSnapshot,
    TransactionCategory,
    Transaction,
    Product,
    CustomerProductHolding,
    Loan,
    LoanRepayment,
    Card,
    DigitalActivity,
    ChannelPreference,
)
from data_ingestion_service.app.models.data_lake import (
    RawCustomer,
    RawTransaction,
    RawAccount,
    RawLoan,
    RawCard,
    StagingCustomer,
    StagingTransaction,
    CleanCustomer,
    CleanTransaction,
)

__all__ = [
    # customer_master
    "Customer",
    "CustomerRiskProfile",
    "CustomerSegment",
    "RelationshipManager",
    "Branch",
    "CustomerRMAssignment",
    "CustomerContact",
    "CustomerAddress",
    "CustomerDocument",
    "CustomerDemographic",
    # banking
    "Account",
    "AccountHolder",
    "AccountBalanceSnapshot",
    "TransactionCategory",
    "Transaction",
    "Product",
    "CustomerProductHolding",
    "Loan",
    "LoanRepayment",
    "Card",
    "DigitalActivity",
    "ChannelPreference",
    # data_lake
    "RawCustomer",
    "RawTransaction",
    "RawAccount",
    "RawLoan",
    "RawCard",
    "StagingCustomer",
    "StagingTransaction",
    "CleanCustomer",
    "CleanTransaction",
]