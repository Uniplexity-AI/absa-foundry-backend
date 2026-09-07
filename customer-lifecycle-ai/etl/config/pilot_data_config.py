"""
Pilot Data Configuration — single source of truth for pilot-time business/data
decisions.

Extraction specs reference values from ``pilot_data_config.yaml`` using
``${dotted.path}`` placeholders (e.g. ``${source_tables.customer_master}``).
``resolve_placeholders`` substitutes them before Pydantic validation so that
editing one YAML file drives every extraction spec.

Placeholder resolution is recursive over the spec dict. Unknown placeholders are
left untouched (with a warning) so they surface as clear table/column errors
rather than silently disappearing.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("etl.config.pilot_data_config")

DEFAULT_CONFIG_PATH = Path(__file__).with_name("pilot_data_config.yaml")

_PLACEHOLDER_RE = re.compile(r"\$\{([^}]+)\}")


class PilotDataConfig:
    """Loads pilot_data_config.yaml and resolves ${...} placeholders."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_CONFIG_PATH
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            logger.warning("Pilot data config not found: %s", self.path)
            return {}
        with open(self.path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        logger.info("Loaded pilot data config: %s", self.path)
        return data

    def resolve(self, obj: Any) -> Any:
        """Resolve ${...} placeholders in `obj` using this config."""
        return resolve_placeholders(obj, self.data)


def resolve_placeholders(obj: Any, config: dict[str, Any]) -> Any:
    """Recursively replace ${dotted.path} placeholders using `config`."""
    if isinstance(obj, str):
        return _PLACEHOLDER_RE.sub(
            lambda m: _lookup(config, m.group(1), m.group(0)), obj
        )
    if isinstance(obj, list):
        return [resolve_placeholders(item, config) for item in obj]
    if isinstance(obj, dict):
        return {key: resolve_placeholders(value, config) for key, value in obj.items()}
    return obj


def _lookup(config: dict[str, Any], path: str, fallback: str) -> str:
    """Resolve a dotted path (e.g. 'source_tables.customer_master')."""
    current: Any = config
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            logger.warning("Unresolved placeholder ${%s} (missing key)", path)
            return fallback
    return str(current)
