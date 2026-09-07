"""
ETL Connector Factory - Centralized connector instantiation.

Provides a registry-based factory for creating connector instances
based on SourceType. New connector types are registered via the
@register_connector decorator.
"""

from __future__ import annotations

from typing import Callable

from etl.connectors.interfaces import Connector
from etl.schemas.connector_schemas import ConnectorConfig, ConnectorInfo, SourceType

# Global connector registry
_connector_registry: dict[SourceType, type[Connector]] = {}
_connector_info_registry: dict[SourceType, ConnectorInfo] = {}


def register_connector(
    source_type: SourceType,
    info: ConnectorInfo,
) -> Callable[[type[Connector]], type[Connector]]:
    """Decorator to register a connector class in the factory.

    Usage:
        @register_connector(SourceType.POSTGRESQL, ConnectorInfo(...))
        class PostgresConnector(DatabaseConnector):
            ...

    Args:
        source_type: The SourceType enum value this connector handles.
        info: Display metadata for this connector type.

    Returns:
        Decorator function that registers the class.
    """
    def decorator(cls: type[Connector]) -> type[Connector]:
        _connector_registry[source_type] = cls
        _connector_info_registry[source_type] = info
        return cls
    return decorator


def create_connector(
    config: ConnectorConfig,
) -> Connector:
    """Factory method to instantiate a connector from configuration.

    Looks up the appropriate connector class by source_type and
    instantiates it with the provided configuration.

    Args:
        config: Full connector configuration including source_type.

    Returns:
        An initialized Connector instance (not yet connected).

    Raises:
        ValueError: If the source_type is not registered.
    """
    connector_cls = _connector_registry.get(config.source_type)
    if connector_cls is None:
        raise ValueError(
            f"No connector registered for source type '{config.source_type.value}'. "
            f"Available types: {list(_connector_registry.keys())}"
        )
    return connector_cls(config)


def get_available_connectors() -> list[ConnectorInfo]:
    """List all registered connector types with their metadata.

    Returns:
        List of ConnectorInfo for all registered connector types.
    """
    return list(_connector_info_registry.values())


def get_connector_info(source_type: SourceType) -> ConnectorInfo | None:
    """Get metadata for a specific connector type.

    Args:
        source_type: The source type to look up.

    Returns:
        ConnectorInfo if registered, None otherwise.
    """
    return _connector_info_registry.get(source_type)


def is_connector_registered(source_type: SourceType) -> bool:
    """Check if a connector type is registered.

    Args:
        source_type: The source type to check.

    Returns:
        True if a connector is registered for this type.
    """
    return source_type in _connector_registry
