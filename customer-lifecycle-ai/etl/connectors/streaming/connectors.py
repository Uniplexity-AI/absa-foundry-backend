"""
Streaming Connectors - Kafka, Debezium, CDC (Future).

Placeholder for future streaming data source integration.
Not implemented in the current phase.
"""

from __future__ import annotations

from etl.connectors.factory import register_connector
from etl.connectors.interfaces import StreamingConnector
from etl.schemas.connector_schemas import (
    BatchMetadata,
    ConnectorConfig,
    ConnectorInfo,
    Dataset,
    SourceType,
)

from typing import AsyncIterator


@register_connector(
    SourceType.KAFKA,
    ConnectorInfo(
        source_type=SourceType.KAFKA,
        display_name="Apache Kafka",
        description="Connector for Apache Kafka message streams (future)",
        supported_operations=["subscribe", "consume"],
        version="0.1.0",
        is_implemented=False,
    ),
)
class KafkaConnector(StreamingConnector):
    """Apache Kafka connector — NOT YET IMPLEMENTED.

    Reserved for future phases when event-streaming architecture is adopted.
    Will use aiokafka for async Kafka consumer/producer.
    """

    async def connect(self) -> None:
        raise NotImplementedError("Kafka connector is not yet implemented.")

    async def disconnect(self) -> None:
        raise NotImplementedError("Kafka connector is not yet implemented.")

    async def validate_connection(self) -> bool:
        raise NotImplementedError("Kafka connector is not yet implemented.")

    async def extract(self) -> AsyncIterator[Dataset]:
        raise NotImplementedError("Kafka connector is not yet implemented.")

    async def subscribe(self, topic: str) -> None:
        raise NotImplementedError("Kafka connector is not yet implemented.")

    async def consume(self) -> AsyncIterator[Dataset]:
        raise NotImplementedError("Kafka connector is not yet implemented.")


@register_connector(
    SourceType.DEBEZIUM,
    ConnectorInfo(
        source_type=SourceType.DEBEZIUM,
        display_name="Debezium CDC",
        description="Connector for Debezium Change Data Capture streams (future)",
        supported_operations=["subscribe", "consume"],
        version="0.1.0",
        is_implemented=False,
    ),
)
class DebeziumConnector(StreamingConnector):
    """Debezium CDC connector — NOT YET IMPLEMENTED.

    Reserved for future CDC-based data ingestion from database transaction logs.
    """

    async def connect(self) -> None:
        raise NotImplementedError("Debezium connector is not yet implemented.")

    async def disconnect(self) -> None:
        raise NotImplementedError("Debezium connector is not yet implemented.")

    async def validate_connection(self) -> bool:
        raise NotImplementedError("Debezium connector is not yet implemented.")

    async def extract(self) -> AsyncIterator[Dataset]:
        raise NotImplementedError("Debezium connector is not yet implemented.")

    async def subscribe(self, topic: str) -> None:
        raise NotImplementedError("Debezium connector is not yet implemented.")

    async def consume(self) -> AsyncIterator[Dataset]:
        raise NotImplementedError("Debezium connector is not yet implemented.")
