"""
Pytest configuration and shared fixtures for ETL tests.

TODO:
Add test database provisioning fixture for CI (ephemeral Postgres container).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path for all test modules
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Ensure project root is on sys.path before any imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(_PROJECT_ROOT))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Absolute path to the project root directory."""
    return _PROJECT_ROOT


@pytest.fixture(scope="session")
def fixture_csv() -> Path:
    """Path to the known-answer fixture CSV (never changes)."""
    return _PROJECT_ROOT / "tests" / "fixtures" / "etl_validation_customers.csv"


@pytest.fixture(scope="session")
def db_settings():
    """Load database settings once per test session."""
    from shared.config.settings import settings
    return settings
