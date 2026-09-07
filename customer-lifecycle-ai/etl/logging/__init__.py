"""
ETL Logging - Structured JSON logging subsystem.

Separate log streams (7 categories):
- System: Infrastructure, service health
- ETL: Pipeline operations
- Validation: Rule results
- Transformation: Mapping decisions
- Performance: Timing data
- Audit: Compliance trail
- Security: Access events

All logs use structured JSON format for ELK/Splunk integration.
"""

from etl.logging.service import ETLLogger

__all__ = [
    "ETLLogger",
]
