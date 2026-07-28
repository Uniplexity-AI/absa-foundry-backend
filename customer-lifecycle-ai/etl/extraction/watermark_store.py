"""
ETL Extraction Watermark Store — persists extraction progress for incremental runs.

Prevents gaps and duplicates by tracking the last successful extraction
timestamp per dataset.  On first run, falls back to the configured lookback.
On subsequent runs, extracts only rows where watermark_column > last_watermark.

Uses a JSON file as a lightweight store (no DB migration needed).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class WatermarkStore:
    """Persists extraction watermarks per dataset to prevent data gaps.

    Usage:
        store = WatermarkStore(Path("etl/checkpoint/watermarks.json"))
        last = store.get("customer_360_daily")  # None on first run
        # ... run extraction ...
        store.set("customer_360_daily", datetime.now(timezone.utc))
    """

    def __init__(self, store_path: Path) -> None:
        """Initialize with path to the watermark JSON file.

        The file is created on first write.  Directory must exist.
        """
        self._path = Path(store_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, dataset_name: str) -> datetime | None:
        """Return the last successful watermark for a dataset, or None.

        Returns None on first run — caller should fall back to
        the configured lookback window.
        """
        data = self._load()
        ts = data.get(dataset_name)
        if ts is None:
            return None
        value = datetime.fromisoformat(ts)
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def set(self, dataset_name: str, watermark: datetime) -> None:
        """Persist a new watermark after a COMPLETED extraction run.

        Should only be called after the full pipeline (extract →
        validate → load) succeeds, not mid-run.
        """
        if watermark.tzinfo is None:
            watermark = watermark.replace(tzinfo=timezone.utc)
        data = self._load()
        data[dataset_name] = watermark.isoformat()
        self._write_atomically(data)

    def delete(self, dataset_name: str) -> None:
        """Remove a watermark (forces full re-extraction on next run)."""
        data = self._load()
        data.pop(dataset_name, None)
        self._write_atomically(data)

    def list_all(self) -> dict[str, str]:
        """Return all stored watermarks as {dataset: iso_timestamp}."""
        return dict(self._load())

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Cannot read watermark store '{self._path}': {exc}") from exc

    def _write_atomically(self, data: dict[str, str]) -> None:
        """Write state by atomic replacement so a crash cannot leave partial JSON."""
        fd, temp_path = tempfile.mkstemp(prefix=f".{self._path.name}.", suffix=".tmp", dir=self._path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, default=str)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._path)
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
