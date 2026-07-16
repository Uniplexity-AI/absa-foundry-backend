"""
ETL Connectors - Data source abstraction layer.

Each connector implements a common interface that outputs a standardized
format: Dataset + Metadata (Batch ID, Source, Checksum, Timestamp).

Supported sources:
- Databases: PostgreSQL, SQL Server, Oracle, MySQL
- Files: CSV, Excel, JSON, XML
- APIs: REST, SOAP
- Streaming (future): Kafka, Debezium, CDC
- Banking: Core banking system adapters
"""

from etl.connectors.interfaces import (
    ApiConnector,
    Connector,
    DatabaseConnector,
    FileConnector,
    StreamingConnector,
)
from etl.connectors.factory import (
    create_connector,
    get_available_connectors,
    get_connector_info,
    register_connector,
)

# Import connector implementations to trigger auto-registration with factory
from etl.connectors.database import connectors as _db  # noqa: F401
from etl.connectors.files import connectors as _files  # noqa: F401
from etl.connectors.api import connectors as _api  # noqa: F401
from etl.connectors.streaming import connectors as _streaming  # noqa: F401
from etl.connectors.banking import connectors as _banking  # noqa: F401

__all__ = [
    # Interfaces
    "Connector",
    "DatabaseConnector",
    "FileConnector",
    "ApiConnector",
    "StreamingConnector",
    # Factory
    "create_connector",
    "get_available_connectors",
    "get_connector_info",
    "register_connector",
]
