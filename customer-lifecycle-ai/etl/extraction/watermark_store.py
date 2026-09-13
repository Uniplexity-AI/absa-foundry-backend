"""
ETL Extraction Watermark Store — persists extraction progress for incremental runs.

Prevents gaps and duplicates by tracking the last successful extraction
timestamp per dataset.  On first run, falls back to the configured lookback.
On subsequent runs, extracts only rows where watermark_column > last_watermark.

Uses a JSON file with OS-level file locking to prevent race conditions
between concurrent extraction processes sharing the same watermark file.
"""

from __future__ import annotations

import json
import logging
import os as _os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("etl.extraction.watermark_store")


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
        lock_fd = self._acquire_lock()
        try:
            data = self._load_locked()
        finally:
            self._release_lock(lock_fd)
        ts = data.get(dataset_name)
        if ts is None:
            return None
        value = datetime.fromisoformat(ts)
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def set(self, dataset_name: str, watermark: datetime) -> None:
        """Persist a new watermark after a COMPLETED extraction run.

        Uses file locking to prevent race conditions between concurrent
        extraction processes sharing the same watermark file.
        """
        if watermark.tzinfo is None:
            watermark = watermark.replace(tzinfo=timezone.utc)
        lock_fd = self._acquire_lock()
        try:
            data = self._load_locked()
            data[dataset_name] = watermark.isoformat()
            self._write_atomically(data)
            logger.debug("Watermark updated: %s -> %s", dataset_name, watermark.isoformat())
        finally:
            self._release_lock(lock_fd)

    def delete(self, dataset_name: str) -> None:
        """Remove a watermark (forces full re-extraction on next run)."""
        lock_fd = self._acquire_lock()
        try:
            data = self._load_locked()
            data.pop(dataset_name, None)
            self._write_atomically(data)
        finally:
            self._release_lock(lock_fd)

    def list_all(self) -> dict[str, str]:
        """Return all stored watermarks as {dataset: iso_timestamp}."""
        return dict(self._load())

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load_locked(self) -> dict[str, str]:
        """Load watermarks without acquiring a lock (caller holds the lock)."""
        return self._load()

    def _load(self) -> dict[str, str]:
        """Read the watermark file.  Corrupt JSON is treated as empty (first run)."""
        if not self._path.exists():
            return {}
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupt file — treat as first run rather than crashing
            return {}

    # ------------------------------------------------------------------
    # File locking (cross-platform)
    # ------------------------------------------------------------------

    def _acquire_lock(self) -> int:
        """Acquire an exclusive OS-level lock on the watermark file.

        Uses fcntl.flock on POSIX, msvcrt.locking on Windows.
        Blocks until the lock is acquired.  Returns a file descriptor
        that must be passed to _release_lock.
        """
        lock_path = self._path.with_suffix(self._path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = _os.open(str(lock_path), _os.O_CREAT | _os.O_RDWR)
        try:
            if _os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX)
        except Exception:
            _os.close(fd)
            raise
        return fd

    def _release_lock(self, fd: int) -> None:
        """Release the file lock and close the descriptor."""
        try:
            if _os.name == "nt":
                import msvcrt
                _os.lseek(fd, 0, _os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            _os.close(fd)

    def _write_atomically(self, data: dict[str, str]) -> None:
        """Write state by atomic replacement so a crash cannot leave partial JSON."""
        fd, temp_path = tempfile.mkstemp(prefix=f".{self._path.name}.", suffix=".tmp", dir=self._path.parent)
        try:
            with _os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, default=str)
                handle.flush()
                _os.fsync(handle.fileno())
            _os.replace(temp_path, self._path)
        except Exception:
            try:
                _os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
