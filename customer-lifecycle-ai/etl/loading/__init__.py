"""
ETL Loading Engine - Production database loading with dependency ordering.

Loading order:
1. Customer → 2. Accounts → 3. Branches → 4. Transactions
→ (future: Products, Loans, Cards, Digital Activity)
→ Feature Store → Customer Behaviour → Predictions → Decision Intelligence
→ Dashboard

Strategies: UPSERT (INSERT ... ON CONFLICT UPDATE), APPEND, REPLACE
Dependencies resolved via topological sort.

Never loads directly into production — always via staging.
Staging truncated after successful production load.
"""

from etl.loading.repository import LoadingRepository
from etl.loading.service import LoadingService

__all__ = [
    "LoadingRepository",
    "LoadingService",
]
