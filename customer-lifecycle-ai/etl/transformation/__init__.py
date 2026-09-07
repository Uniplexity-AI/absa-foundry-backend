"""
ETL Transformation Engine - Data mapping, standardization, and enrichment.

Capabilities:
- Field mapping (source → target columns)
- Standardization (DR → DEBIT, Mobile Banking → MOBILE)
- Lookup resolution (Branch Name → Branch Code)
- Derived field computation (is_high_value, year_month, days_since)
- Data enrichment (branch info, customer segment)
- Date normalization (all dates to ISO 8601)

All transforms are idempotent and composable.

Pipeline order:
    FieldMapper → ValueStandardizer → DataEnricher
"""

from etl.transformation.interfaces import BaseTransform
from etl.transformation.mappers.field_mapper import FieldMapper
from etl.transformation.standardizers.value_standardizer import ValueStandardizer
from etl.transformation.enrichers.data_enricher import DataEnricher, EnrichmentLookupProvider
from etl.transformation.service import TransformationService

__all__ = [
    "BaseTransform",
    "FieldMapper",
    "ValueStandardizer",
    "DataEnricher",
    "EnrichmentLookupProvider",
    "TransformationService",
]
