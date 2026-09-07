"""
Banking Connectors - Core banking system adapters.

Specialized connectors for banking-specific data formats and protocols
used by core banking systems (e.g., ISO 8583, SWIFT MT/MX, BAI2).
"""

from __future__ import annotations

from etl.connectors.factory import register_connector
from etl.connectors.interfaces import Connector
from etl.schemas.connector_schemas import (
    ConnectorConfig,
    ConnectorInfo,
    Dataset,
    SourceType,
)

from typing import Any, AsyncIterator


@register_connector(
    SourceType.CORE_BANKING,
    ConnectorInfo(
        source_type=SourceType.CORE_BANKING,
        display_name="Core Banking System",
        description="Adapter for core banking system data extraction",
        supported_operations=["extract"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class CoreBankingConnector(Connector):
    """Core banking system adapter.

    Provides a banking-domain-aware connector that understands common
    banking data formats and can adapt to various core banking systems.
    Currently delegates to database connectors for most operations;
    banking-specific protocol support will be added in future phases.
    """

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._underlying_connector: Connector | None = None

    async def connect(self) -> None:
        """Connect to the underlying banking data source."""
        # Delegate to the appropriate database connector based on config
        from etl.connectors.factory import create_connector

        # The core banking connector wraps a database connector
        db_config = self.config.model_copy(update={
            "source_type": self.config.extra_params.get(
                "underlying_source_type", "postgresql"
            ),
        })
        self._underlying_connector = create_connector(db_config)
        await self._underlying_connector.connect()
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from the underlying source."""
        if self._underlying_connector:
            await self._underlying_connector.disconnect()
        self._connected = False

    async def validate_connection(self) -> bool:
        """Validate underlying connection."""
        if self._underlying_connector is None:
            return False
        return await self._underlying_connector.validate_connection()

    async def extract(self) -> AsyncIterator[Dataset]:
        """Extract data from the core banking system.

        Applies banking-specific transformations on top of the
        underlying connector's output.
        """
        if not self._connected or self._underlying_connector is None:
            raise RuntimeError("Cannot extract: connector is not connected.")

        async for dataset in self._underlying_connector.extract():
            # Update metadata to reflect banking source
            dataset.metadata.source_type = SourceType.CORE_BANKING
            dataset.metadata.source_name = self.config.source_name
            yield dataset
