"""
ETL Orchestration Engine - DAG-based workflow pipeline management.

Pipeline flow:
    Extract → Ingest → Validate → Transform → Stage → Load
    → Feature Engineering → Markov State Classification
    → Prediction → Decision Engine → Dashboard Refresh

Features:
- Topological sort for dependency resolution
- Parallel execution (max_concurrent_steps)
- Retry with exponential backoff
- Timeout enforcement per step
- Cancel/pause support
"""

from etl.orchestration.service import OrchestrationService

__all__ = [
    "OrchestrationService",
]
