"""
ETL Validation Engine - Modular, configurable data validation.

Validation categories:
- Schema validation — column presence and types
- Mandatory field checks — banking-specific required fields
- Business rule validation — date, amount, currency, type, channel rules
- Duplicate detection — exact, near-duplicate, batch dedup
- Referential integrity checks — customer, account, branch lookups

All rules are configurable via ValidationConfig — nothing hardcoded.

Pipeline order:
    SchemaValidator → MandatoryFieldValidator → BusinessRuleValidator
    → DuplicateDetector → ReferentialIntegrityValidator
"""

from etl.validation.interfaces import BaseValidator
from etl.validation.service import ValidationService
from etl.validation.validators import (
    BusinessRuleValidator,
    DuplicateDetector,
    LookupProvider,
    MandatoryFieldValidator,
    ReferentialIntegrityValidator,
    SchemaValidator,
)

__all__ = [
    # Base
    "BaseValidator",
    # Service
    "ValidationService",
    # Validators
    "SchemaValidator",
    "MandatoryFieldValidator",
    "BusinessRuleValidator",
    "DuplicateDetector",
    "ReferentialIntegrityValidator",
    # Protocols
    "LookupProvider",
]
