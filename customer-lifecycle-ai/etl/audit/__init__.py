"""
ETL Audit Trail - Complete batch lifecycle recording.

Every batch records:
- Batch ID, Source, Start/Finish timestamps, Duration
- Rows Received / Valid / Rejected / Loaded / Skipped
- Duplicate counts and warnings
- Quality Score (computed)
- Operator / service identifier

All records are immutable — write-once, never modified.
Required for banking compliance and regulatory reporting.
"""

from etl.audit.service import AuditService

__all__ = [
    "AuditService",
]
