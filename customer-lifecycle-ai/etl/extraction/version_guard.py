"""
ETL Extraction Version Guard — compatibility checking for extraction specs.

Validates that the running engine version satisfies the minimum required
by the extraction spec before query execution begins.

Section 7 of dynamic-extractor-spec.md.
"""

from __future__ import annotations

from packaging.version import Version, InvalidVersion

from etl.extraction.config_models import ExtractionConfigSpec


class IncompatibleSpecError(Exception):
    """Raised when the extraction spec requires a newer engine version."""


class VersionGuard:
    """Validates engine ↔ extraction spec compatibility."""

    def __init__(self, engine_version: str) -> None:
        """Initialize with the current engine version.

        Args:
            engine_version: Semantic version of the running engine, e.g. '2.1'.
        """
        self._engine = Version(engine_version)

    def check(self, spec: ExtractionConfigSpec) -> None:
        """Validate that this engine can execute the given spec.

        Args:
            spec: Loaded extraction configuration.

        Raises:
            IncompatibleSpecError: If the engine is too old for this spec.
        """
        if spec.versioning is None:
            return  # No versioning block — allow execution

        minimum = spec.versioning.compatibility.minimum_engine
        try:
            min_ver = Version(minimum)
        except InvalidVersion:
            raise IncompatibleSpecError(
                f"Invalid minimum_engine version in spec: '{minimum}'"
            )

        if self._engine < min_ver:
            raise IncompatibleSpecError(
                f"Extraction spec '{spec.dataset_name}' requires engine >= {minimum}, "
                f"but current engine is {self._engine}. "
                f"Upgrade the engine or use an older spec version."
            )
