"""
ETL Staging Layer - Temporary tables for validated, transformed data.

Staging tables (schema: staging):
- stg_customer: Customer master data
- stg_account: Account data
- stg_transaction: Banking transactions
- stg_branch: Branch/channel reference data

Data flows: Landing → Validation → Transformation → Staging → Loading
Staging is truncated after successful production load.
Never load directly into production.
"""

from etl.staging.repository import StagingRepository
from etl.staging.service import StagingService

__all__ = [
    "StagingRepository",
    "StagingService",
]
