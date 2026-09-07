"""
ETL Pipelines - Assembled end-to-end data processing pipelines.

Composes: Connector → Ingestion → Validation → Transformation
→ Staging → Loading → Audit → downstream service triggers.

Pipeline registry and runner for dynamic pipeline execution.
"""

from etl.pipelines.runner import PipelineRegistry, PipelineRunner

__all__ = [
    "PipelineRegistry",
    "PipelineRunner",
]
