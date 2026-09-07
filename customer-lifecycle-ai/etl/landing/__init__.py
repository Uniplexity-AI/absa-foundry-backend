"""
ETL Landing Zone - Immutable raw data storage.

Implements time-partitioned directory structure:
    landing/YYYY/MM/DD/{batch_id}/chunk_0000.parquet

Files in the landing zone are NEVER modified after initial write.
Provides full data lineage and replay capability.

Components:
- LocalLandingZoneWriter: Writes datasets as Parquet to disk
- LocalLandingZoneReader: Reads raw data for downstream processing
- LandingFileSqlRepository: Tracks files in database
"""

from etl.landing.interfaces import LandingFileRepository, LandingZoneReader
from etl.landing.reader import LocalLandingZoneReader
from etl.landing.repository import LandingFileSqlRepository
from etl.landing.writer import LocalLandingZoneWriter

__all__ = [
    # Writer
    "LocalLandingZoneWriter",
    # Reader
    "LandingZoneReader",
    "LocalLandingZoneReader",
    # Repository
    "LandingFileRepository",
    "LandingFileSqlRepository",
]
