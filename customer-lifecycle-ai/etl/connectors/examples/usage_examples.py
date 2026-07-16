"""
Example: Using ETL Connectors

This example demonstrates how to configure and use various connector types.
"""

import os
from etl.connectors import create_connector
from etl.schemas.connector_schemas import ConnectorConfig, SourceType


# ---------------------------------------------------------------------------
# Example 1: PostgreSQL Database Connector
# ---------------------------------------------------------------------------

async def example_postgres_connector():
    """Extract data from a PostgreSQL database."""
    config = ConnectorConfig(
        source_type=SourceType.POSTGRESQL,
        source_name="Core Banking Database",
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ.get("DB_NAME", "core_banking"),
        username=os.environ.get("DB_USER", "etl_user"),
        password=os.environ.get("DB_PASSWORD", ""),
        table_name="public.transactions",
        batch_size=10000,
        timeout_seconds=300,
    )

    async with create_connector(config) as connector:
        async for dataset in connector.extract():
            print(
                f"Chunk {dataset.chunk_index}: "
                f"{dataset.row_count} rows, "
                f"columns: {dataset.column_names}"
            )


# ---------------------------------------------------------------------------
# Example 2: CSV File Connector
# ---------------------------------------------------------------------------

async def example_csv_connector():
    """Extract data from CSV files."""
    config = ConnectorConfig(
        source_type=SourceType.CSV,
        source_name="Monthly Transaction Export",
        file_path="/data/exports/transactions_202607.csv",
        delimiter=",",
        has_header=True,
        encoding="utf-8",
    )

    async with create_connector(config) as connector:
        async for dataset in connector.extract():
            print(
                f"File: {dataset.metadata.file_path}, "
                f"Rows: {dataset.row_count}, "
                f"Checksum: {dataset.metadata.checksum_sha256}"
            )


# ---------------------------------------------------------------------------
# Example 3: REST API Connector
# ---------------------------------------------------------------------------

async def example_rest_connector():
    """Extract data from a REST API with pagination."""
    config = ConnectorConfig(
        source_type=SourceType.REST,
        source_name="Customer 360 API",
        api_base_url="https://api.bank.internal/v1",
        api_key=os.environ.get("API_KEY", ""),
        query="/customers",
        batch_size=500,
        extra_params={
            "pagination": "offset",
            "data_key": "customers",
            "query_params": {"status": "active"},
            "auth_header": "X-API-Key",
            "auth_prefix": "",
        },
    )

    async with create_connector(config) as connector:
        async for dataset in connector.extract():
            print(f"API response: {dataset.row_count} customers retrieved")


# ---------------------------------------------------------------------------
# Example 4: Listing available connectors
# ---------------------------------------------------------------------------

def example_list_connectors():
    """List all registered connector types."""
    from etl.connectors import get_available_connectors

    connectors = get_available_connectors()
    for info in connectors:
        status = "Ready" if info.is_implemented else "Not Yet Implemented"
        print(f"  [{status}] {info.display_name}: {info.description}")


# ---------------------------------------------------------------------------
# Example 5: Sample connector configuration (YAML)
# ---------------------------------------------------------------------------

SAMPLE_CONFIG_YAML = """
# etl/connectors/examples/sample_config.yaml
# Save as etl_config.yaml and load at startup

connectors:
  - connector_id: pg-core-banking
    source_type: postgresql
    source_name: "Core Banking Database - Production"
    host: "${DB_HOST}"
    port: 5432
    database: core_banking
    username: "${DB_USER}"
    password: "${DB_PASSWORD}"
    table_name: public.transactions
    batch_size: 10000
    timeout_seconds: 300

  - connector_id: csv-monthly-export
    source_type: csv
    source_name: "Monthly Transaction Export"
    file_path: "/data/exports/transactions.csv"
    delimiter: ","
    has_header: true
    encoding: utf-8

  - connector_id: rest-customer-api
    source_type: rest
    source_name: "Customer 360 API"
    api_base_url: "https://api.bank.internal/v1"
    api_key: "${API_KEY}"
    query: "/customers"
    batch_size: 500
    extra_params:
      pagination: offset
      data_key: customers
      auth_header: X-API-Key
      auth_prefix: ""
"""
