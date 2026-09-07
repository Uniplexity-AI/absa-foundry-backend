"""
ETL Monitoring - Real-time pipeline observability.

Tracks:
- Running / Completed / Failed jobs
- Rows processed per step
- Validation failure rates
- CPU, RAM, execution time
- Throughput (rows/sec)

Alerts when thresholds are breached (quality, error rate, throughput, memory).
"""

from etl.monitoring.service import MonitoringService

__all__ = [
    "MonitoringService",
]
