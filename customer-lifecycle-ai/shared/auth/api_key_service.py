"""
Shared Auth API Key Service — generation, hashing, and validation.

Service accounts authenticate with API keys instead of JWT for
machine-to-machine communication (ETL engine, prediction service, etc.).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone


class ApiKeyService:
    """Manages the lifecycle of API keys for service accounts."""

    PREFIX = "clp_sk"  # Shared prefix for all keys — aids in log scanning

    @classmethod
    def generate_key(cls, service_name: str, key_version: int = 1) -> tuple[str, str, str]:
        """Generate a new API key.

        Args:
            service_name: Short name of the service, e.g. 'etl'.
            key_version: Monotonically increasing version for rotation.

        Returns:
            Tuple of (raw_key, key_prefix, key_hash).
            - raw_key: The full key to give to the service (never stored).
            - key_prefix: First few chars for identification in logs.
            - key_hash: SHA-256 hash to store in the database.
        """
        secret = secrets.token_hex(32)
        raw_key = f"{cls.PREFIX}_{service_name}_{key_version:02d}_{secret}"
        key_hash = cls.hash_key(raw_key)
        key_prefix = raw_key[:len(cls.PREFIX) + len(service_name) + 6]
        return raw_key, key_prefix, key_hash

    @classmethod
    def hash_key(cls, raw_key: str) -> str:
        """Hash a raw API key for secure storage.

        Args:
            raw_key: The full API key string.

        Returns:
            SHA-256 hex digest.
        """
        return hashlib.sha256(raw_key.encode()).hexdigest()

    @classmethod
    def validate_format(cls, raw_key: str) -> bool:
        """Check if a key string matches the expected format.

        Args:
            raw_key: The key string to validate.

        Returns:
            True if the key format looks valid.
        """
        parts = raw_key.split("_")
        return (
            len(parts) >= 5
            and parts[0] == "clp"
            and parts[1] == "sk"
            and len(parts[-1]) == 64  # 32 bytes hex = 64 chars
        )
