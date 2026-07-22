"""
ETL Extraction Streaming — cursor-based chunked data retrieval.

Replaces bulk List[Dict] loading with server-side cursor streaming.
Memory usage stays constant regardless of dataset size (10K rows
uses the same RAM as 10M rows).

Section 14 of dynamic-extractor-spec.md.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql import Select


class StreamingExtractor:
    """Yields chunks of rows from a SQL query using server-side cursors.

    Usage:
        extractor = StreamingExtractor(engine, batch_size=10000)
        for chunk in extractor.stream(query):
            process(chunk)  # chunk is list[dict]
    """

    def __init__(
        self,
        engine: sa.Engine,
        batch_size: int = 10000,
    ) -> None:
        """Initialize the streaming extractor.

        Args:
            engine: Connected SQLAlchemy engine.
            batch_size: Number of rows per yielded chunk.
        """
        self._engine = engine
        self._batch_size = max(batch_size, 100)  # Minimum 100 rows per chunk

    def stream(self, query: Select) -> Iterator[list[dict[str, Any]]]:
        """Execute a query and yield row chunks as list[dict].

        Uses server-side cursors (stream_results=True) to avoid loading
        the entire result set into memory.

        Args:
            query: SQLAlchemy Select statement to execute.

        Yields:
            List of dicts, each dict representing one row.

        Raises:
            RuntimeError: If the database connection fails mid-stream.
        """
        with self._engine.connect() as conn:
            result = conn.execution_options(
                stream_results=True,
                max_row_buffer=self._batch_size,
            ).execute(query)

            keys: list[str] | None = None

            for partition in result.mappings().partitions(self._batch_size):
                if keys is None:
                    keys = list(partition[0].keys()) if partition else []

                chunk: list[dict[str, Any]] = []
                for row in partition:
                    chunk.append(dict(row))
                if chunk:
                    yield chunk

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
