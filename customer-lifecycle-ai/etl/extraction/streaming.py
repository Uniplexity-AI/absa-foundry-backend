"""
ETL Extraction Streaming — cursor-based chunked data retrieval.

Replaces bulk List[Dict] loading with server-side cursor streaming.
Memory usage stays constant regardless of dataset size (10K rows
uses the same RAM as 10M rows).

Section 14 of dynamic-extractor-spec.md.
"""

from __future__ import annotations

import logging
import time as _time
from collections.abc import Iterator
from typing import Any

import sqlalchemy as sa
from sqlalchemy import exc as sa_exc
from sqlalchemy.sql import Select

logger = logging.getLogger("etl.extraction.streaming")


class StreamingExtractor:
    """Yields chunks of rows from a SQL query using server-side cursors.

    Usage:
        extractor = StreamingExtractor(engine, batch_size=10000)
        for chunk in extractor.stream(query):
            process(chunk)  # chunk is list[dict]
    """

    _MAX_RETRIES = 3  # Retry mid-stream disconnections
    _RETRY_DELAY = 1.0  # Seconds base delay, doubles each retry

    def __init__(
        self,
        engine: sa.Engine,
        batch_size: int = 10000,
        query_timeout: int = 0,
    ) -> None:
        """Initialize the streaming extractor.

        Args:
            engine: Connected SQLAlchemy engine.
            batch_size: Number of rows per yielded chunk (minimum 100).
            query_timeout: Statement timeout in seconds (0 = no timeout).
        """
        self._engine = engine
        self._batch_size = max(batch_size, 100)
        self._query_timeout = query_timeout

    def stream(self, query: Select) -> Iterator[list[dict[str, Any]]]:
        """Execute a query and yield row chunks as list[dict].

        Uses server-side cursors (stream_results=True) with automatic
        retry on transient disconnections (up to 3 attempts with backoff).

        Args:
            query: SQLAlchemy Select statement to execute.

        Yields:
            List of dicts, each dict representing one row.

        Raises:
            sa_exc.OperationalError: If all retries are exhausted.
        """
        last_exception = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                exec_opts: dict[str, Any] = {
                    "stream_results": True,
                    "max_row_buffer": self._batch_size,
                }
                if self._query_timeout > 0:
                    exec_opts["timeout"] = self._query_timeout

                with self._engine.connect() as conn:
                    result = conn.execution_options(**exec_opts).execute(query)

                    for partition in result.mappings().partitions(self._batch_size):
                        chunk: list[dict[str, Any]] = []
                        for row in partition:
                            chunk.append(dict(row))
                        if chunk:
                            yield chunk
                    return  # Stream completed successfully

            except sa_exc.OperationalError as e:
                last_exception = e
                if attempt < self._MAX_RETRIES:
                    delay = self._RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Stream disconnected (attempt %d/%d), retrying in %.1fs: %s",
                        attempt, self._MAX_RETRIES, delay, e,
                    )
                    _time.sleep(delay)
                else:
                    logger.error("Stream failed after %d retries: %s", self._MAX_RETRIES, e)

        raise last_exception  # type: ignore[misc]

    def stream_all(self, query: Select) -> list[dict[str, Any]]:
        """Execute a query and return all rows as a single list of dicts.

        Convenience wrapper around stream() for smaller datasets.
        For large datasets, use stream() to iterate in chunks.

        Args:
            query: SQLAlchemy Select statement to execute.

        Returns:
            List of dicts for all rows.
        """
        all_rows: list[dict[str, Any]] = []
        for chunk in self.stream(query):
            all_rows.extend(chunk)
        return all_rows
