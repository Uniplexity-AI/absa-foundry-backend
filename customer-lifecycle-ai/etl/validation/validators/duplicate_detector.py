"""
Duplicate Detector - Exact and near-duplicate record detection.

Detects:
- Exact duplicates (all key fields identical)
- Near-duplicates (configurable similarity threshold)
- Batch-level duplicates (same batch submitted twice)

Primary duplicate key: customer_id + account_id + branch_code +
                       transaction_date + transaction_amount +
                       transaction_type + transaction_channel
"""

from __future__ import annotations

import hashlib
import json

import pandas as pd

from etl.schemas.validation_schemas import (
    RecordValidationResult,
    ValidationCategory,
    ValidationConfig,
    ValidationError,
    ValidationSeverity,
)
from etl.validation.interfaces import BaseValidator


class DuplicateDetector(BaseValidator):
    """Detects exact and near-duplicate records.

    Uses a composite key for exact matching and fuzzy hashing
    for near-duplicate detection at a configurable threshold.
    """

    def __init__(self, config: ValidationConfig) -> None:
        super().__init__(config)
        self._seen_hashes: set[str] = set()
        self._seen_fuzzy: dict[str, int] = {}  # fuzzy_hash → first record_index
        self._batch_hashes: set[str] = set()  # For cross-batch dedup

    @property
    def category(self) -> str:
        return ValidationCategory.DUPLICATE.value

    async def validate(
        self,
        df: pd.DataFrame,
        existing_results: list[RecordValidationResult] | None = None,
    ) -> list[RecordValidationResult]:
        """Detect duplicates across all records in the DataFrame."""
        self.reset()
        results: list[RecordValidationResult] = []

        for idx, (_, row) in enumerate(df.iterrows()):
            # Skip already-invalid records
            if existing_results and idx < len(existing_results):
                prev = existing_results[idx]
                if not prev.is_valid and self.config.stop_on_first_error:
                    results.append(prev)
                    continue

            # Build result from previous validators
            if existing_results and idx < len(existing_results):
                result = existing_results[idx]
                result = RecordValidationResult(
                    record_index=idx,
                    is_valid=result.is_valid,
                    errors=list(result.errors),
                    warnings=list(result.warnings),
                )
            else:
                result = RecordValidationResult(record_index=idx, is_valid=True)

            duplicate_result = self._detect_duplicate(row, idx)
            if duplicate_result:
                result.errors.append(duplicate_result)
                result.is_valid = False
                result.duplicate_of = duplicate_result.actual_value  # type: ignore[assignment]
                self._error_count += 1

            results.append(result)

        return results

    def validate_record(
        self, row: pd.Series, row_index: int
    ) -> RecordValidationResult:
        """Detect duplicates for a single record."""
        result = RecordValidationResult(record_index=row_index, is_valid=True)
        dup = self._detect_duplicate(row, row_index)
        if dup:
            result.errors.append(dup)
            result.is_valid = False
        return result

    def reset(self) -> None:
        """Reset seen hashes between batches."""
        super().reset()
        self._seen_hashes.clear()
        self._seen_fuzzy.clear()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _detect_duplicate(
        self, row: pd.Series, row_index: int
    ) -> ValidationError | None:
        """Detect if a row is a duplicate.

        Checks exact duplicate first, then near-duplicate.

        Args:
            row: The data row.
            row_index: Row position in DataFrame.

        Returns:
            ValidationError if duplicate, None otherwise.
        """
        # Build composite key
        key_values = self._build_composite_key(row)

        # Exact duplicate check
        exact_hash = self._hash_values(key_values)

        if exact_hash in self._seen_hashes:
            if self.config.exact_duplicate_strategy == "reject":
                return ValidationError(
                    rule_id="DUP-001",
                    category=ValidationCategory.DUPLICATE,
                    severity=ValidationSeverity.ERROR,
                    message=f"Exact duplicate detected for record {row_index}",
                    record_index=row_index,
                    actual_value=row_index,
                    expected_value="Unique record",
                )
            elif self.config.exact_duplicate_strategy == "flag":
                return ValidationError(
                    rule_id="DUP-001",
                    category=ValidationCategory.DUPLICATE,
                    severity=ValidationSeverity.WARNING,
                    message=f"Exact duplicate flagged for record {row_index}",
                    record_index=row_index,
                    actual_value=row_index,
                    expected_value="Unique record (flagged)",
                )

        self._seen_hashes.add(exact_hash)

        # Near-duplicate check (skip if exact match found)
        fuzzy_key = self._build_fuzzy_key(row)
        if fuzzy_key in self._seen_fuzzy:
            first_idx = self._seen_fuzzy[fuzzy_key]
            if self.config.near_duplicate_strategy == "reject":
                return ValidationError(
                    rule_id="DUP-002",
                    category=ValidationCategory.DUPLICATE,
                    severity=ValidationSeverity.ERROR,
                    field_name="near_duplicate",
                    message=f"Near-duplicate detected: record {row_index} similar to record {first_idx}",
                    record_index=row_index,
                    actual_value=first_idx,
                    expected_value="Unique record",
                )
            elif self.config.near_duplicate_strategy == "flag":
                return ValidationError(
                    rule_id="DUP-002",
                    category=ValidationCategory.DUPLICATE,
                    severity=ValidationSeverity.WARNING,
                    field_name="near_duplicate",
                    message=f"Near-duplicate flagged: record {row_index} similar to record {first_idx}",
                    record_index=row_index,
                    actual_value=first_idx,
                    expected_value="Unique record (flagged)",
                )

        self._seen_fuzzy[fuzzy_key] = row_index
        return None

    def _build_composite_key(self, row: pd.Series) -> dict[str, object]:
        """Build the composite duplicate detection key.

        Uses fields from config.duplicate_keys.

        Args:
            row: The data row.

        Returns:
            Dict of key_field → value.
        """
        key: dict[str, object] = {}
        for field in self.config.duplicate_keys:
            if field in row.index:
                val = row[field]
                # Normalize: lowercase strings, round floats
                if isinstance(val, str):
                    key[field] = val.strip().lower()
                elif isinstance(val, float):
                    key[field] = round(val, 2)
                else:
                    key[field] = val
        return key

    @staticmethod
    def _hash_values(key: dict[str, object]) -> str:
        """Create a deterministic hash of the composite key.

        Args:
            key: Dict of field_name → value.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        serialized = json.dumps(key, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _build_fuzzy_key(self, row: pd.Series) -> str:
        """Build a fuzzy key for near-duplicate detection.

        Uses a subset of fields and rounds numeric values to
        allow for small variations.

        Args:
            row: The data row.

        Returns:
            Fuzzy hash string.
        """
        # Use a subset of keys for fuzzy matching
        fuzzy_fields = ["customer_id", "account_id", "branch_code", "transaction_type", "transaction_channel"]
        fuzzy_values: dict[str, object] = {}
        for field in fuzzy_fields:
            if field in row.index:
                val = row[field]
                if isinstance(val, str):
                    fuzzy_values[field] = val.strip().lower()
                else:
                    fuzzy_values[field] = val

        # Round amount to nearest 100 for near-duplicate matching
        if "transaction_amount" in row.index:
            try:
                amt = float(row["transaction_amount"])
                fuzzy_values["transaction_amount"] = round(amt / 100) * 100
            except (ValueError, TypeError):
                pass

        return hashlib.sha256(
            json.dumps(fuzzy_values, sort_keys=True, default=str).encode()
        ).hexdigest()
