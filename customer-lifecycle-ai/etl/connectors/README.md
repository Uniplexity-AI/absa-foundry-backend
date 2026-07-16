# ETL Connectors

## Overview

The connectors module provides a unified abstraction layer over diverse data sources. Every connector implements the `Connector` interface and outputs a standardized `Dataset + BatchMetadata` format, ensuring downstream ETL components operate on consistent data regardless of source type.

## Architecture

```
Connector (ABC)
├── DatabaseConnector (ABC)
│   ├── PostgresConnector      ✅ Implemented
│   ├── SqlServerConnector     ✅ Implemented
│   ├── OracleConnector        ✅ Implemented
│   └── MySQLConnector         ✅ Implemented
├── FileConnector (ABC)
│   ├── CsvConnector           ✅ Implemented
│   ├── ExcelConnector         ✅ Implemented
│   ├── JsonConnector          ✅ Implemented
│   └── XmlConnector           ✅ Implemented
├── ApiConnector (ABC)
│   ├── RestConnector          ✅ Implemented
│   └── SoapConnector          ✅ Implemented
├── StreamingConnector (ABC)
│   ├── KafkaConnector         ⏳ Future
│   └── DebeziumConnector      ⏳ Future
└── CoreBankingConnector       ✅ Implemented
```

## Usage

```python
from etl.connectors import create_connector
from etl.schemas.connector_schemas import ConnectorConfig, SourceType

# Configure a PostgreSQL connector
config = ConnectorConfig(
    source_type=SourceType.POSTGRESQL,
    source_name="Core Banking DB",
    host="localhost",
    port=5432,
    database="core_banking",
    username="etl_user",
    password="secret",
    table_name="transactions",
    batch_size=10000,
)

# Create and use the connector
async with create_connector(config) as connector:
    async for dataset in connector.extract():
        print(f"Extracted {dataset.row_count} rows from chunk {dataset.chunk_index}")
```

## Skills

### Adding a New Connector

1. Create a class extending the appropriate ABC (`DatabaseConnector`, `FileConnector`, etc.)
2. Implement all abstract methods (`connect`, `disconnect`, `extract`, `validate_connection`)
3. Register with the factory using `@register_connector(SourceType.X, ConnectorInfo(...))`
4. Import the module in `etl/connectors/__init__.py` to trigger auto-registration
5. Add tests in `tests/etl/connectors/`

## Configuration

All connector configuration is via `ConnectorConfig` (Pydantic v2). Sensitive values (passwords, API keys) should be loaded from environment variables or a secrets manager:

```python
import os
config = ConnectorConfig(
    source_type=SourceType.POSTGRESQL,
    source_name="Core Banking DB",
    host=os.environ["DB_HOST"],
    password=os.environ["DB_PASSWORD"],
    ...
)
```

## Examples

See `examples/` directory for complete usage examples.
