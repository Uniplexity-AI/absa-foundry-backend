"""
ETL Checkpoint Engine - Resumable pipeline execution.

Stores per-batch progress:
- Batch ID, Pipeline Name, Current Step
- Current Record Index, Total Records
- Status (IN_PROGRESS, COMPLETED, FAILED)
- Retry Count, Metadata, Error Message

Pipeline resumes from last checkpoint after failure.
Never restarts completed work.
"""

from etl.checkpoint.service import CheckpointService

__all__ = [
    "CheckpointService",
]
