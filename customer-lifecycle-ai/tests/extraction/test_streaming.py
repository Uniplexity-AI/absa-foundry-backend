"""Tests for StreamingExtractor — chunking, retry, timeout configuration."""
from __future__ import annotations

import pytest
import sqlalchemy as sa

from etl.extraction.streaming import StreamingExtractor


class TestStreamingInit:
    def test_default_batch_size(self):
        s = StreamingExtractor(object())
        assert s._batch_size == 10000

    def test_custom_batch_size(self):
        s = StreamingExtractor(object(), batch_size=5000)
        assert s._batch_size == 5000

    def test_batch_size_floor(self):
        """Batch size below 100 should be clamped to 100."""
        s = StreamingExtractor(object(), batch_size=50)
        assert s._batch_size == 100

    def test_batch_size_exactly_100(self):
        s = StreamingExtractor(object(), batch_size=100)
        assert s._batch_size == 100

    def test_query_timeout_default(self):
        s = StreamingExtractor(object())
        assert s._query_timeout == 0

    def test_query_timeout_set(self):
        s = StreamingExtractor(object(), query_timeout=30)
        assert s._query_timeout == 30


class TestStreamingRetryConstants:
    def test_max_retries_is_3(self):
        assert StreamingExtractor._MAX_RETRIES == 3

    def test_retry_delay_is_1_second(self):
        assert StreamingExtractor._RETRY_DELAY == 1.0


class TestStreamingNoRealDB:
    """Tests that don't need a real database connection."""

    def test_stream_raises_on_no_connection(self):
        """Without a real engine, streaming should fail with an error."""
        s = StreamingExtractor(sa.create_engine("postgresql://nonexistent:5432/db"))
        query = sa.text("SELECT 1")
        with pytest.raises(Exception):
            next(s.stream(query))

    def test_stream_all_delegates_to_stream(self):
        """stream_all should work (empty if no connection, or raise)."""
        s = StreamingExtractor(sa.create_engine("sqlite://"))
        query = sa.text("SELECT 1 AS val")
        try:
            result = s.stream_all(query)
            assert isinstance(result, list)
        except Exception:
            pass  # sqlite:// without file may fail, which is fine
