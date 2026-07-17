"""Test fixtures for feature-engineering-service — deterministic, hand-crafted data."""
from __future__ import annotations
import os, sys
from datetime import date, datetime, timezone
from pathlib import Path
import psycopg2, pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
os.chdir(str(_PROJECT_ROOT))
if str(_PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(_PROJECT_ROOT))
_svc = _PROJECT_ROOT / "services" / "feature-engineering-service"
if str(_svc) not in sys.path: sys.path.insert(0, str(_svc))

# Hand-crafted fixture transactions with exact expected values
FIXTURE_TXNS = [
    ("CUST-TEST-A", "ACC-A", "BR001", "2024-01-15", "CREDIT", "ATM", "USD", 100.00),
    ("CUST-TEST-A", "ACC-A", "BR001", "2024-03-20", "DEBIT", "POS", "USD", 200.00),
    ("CUST-TEST-A", "ACC-A", "BR001", "2024-06-10", "TRANSFER", "ONLINE", "USD", 300.00),
    ("CUST-TEST-A", "ACC-A", "BR001", "2024-09-01", "CREDIT", "BRANCH", "ZMW", 400.00),
    ("CUST-TEST-A", "ACC-A", "BR001", "2025-01-05", "DEBIT", "ATM", "ZMW", 500.00),  # after as_of
    ("CUST-TEST-B", "ACC-B", "BR002", "2024-05-01", "CREDIT", "MOBILE", "USD", 150.00),
    ("CUST-TEST-C", "ACC-C", "BR003", "2025-06-01", "CREDIT", "ATM", "USD", 999.00),  # after as_of
    ("CUST-TEST-D", "ACC-D", "BR004", "2024-11-01", "CREDIT", "ATM", "USD", 100.00),
    ("CUST-TEST-D", "ACC-D", "BR004", "2024-11-15", "CREDIT", "ATM", "USD", 100.00),
]
TEST_IDS = ["CUST-TEST-A", "CUST-TEST-B", "CUST-TEST-C", "CUST-TEST-D"]

EXPECTED_A_DEC31 = {"days_since_last_txn": 121, "days_since_first_txn": 351,
    "txn_count_30d": 0, "txn_count_90d": 0, "txn_count_180d": 1,
    "avg_days_between_txn": 117.0, "total_amount_90d": None, "avg_amount_90d": None,
    "total_amount_180d": 400.00, "amount_growth_ratio": None,
    "distinct_channels_90d": 0, "distinct_txn_types_90d": 0, "dominant_channel": None}

EXPECTED_A_JUN30 = {"days_since_last_txn": 20, "days_since_first_txn": 167,
    "txn_count_30d": 1, "txn_count_90d": 1, "txn_count_180d": 3,
    "avg_days_between_txn": 83.5, "total_amount_90d": 300.00, "avg_amount_90d": 300.00,
    "total_amount_180d": 600.00, "amount_growth_ratio": 1.0,
    "distinct_channels_90d": 1, "distinct_txn_types_90d": 1, "dominant_channel": "ONLINE"}

EXPECTED_B_DEC31 = {"days_since_last_txn": 244, "days_since_first_txn": 244,
    "txn_count_30d": 0, "txn_count_90d": 0, "txn_count_180d": 0,
    "avg_days_between_txn": None, "total_amount_90d": None, "avg_amount_90d": None,
    "total_amount_180d": None, "amount_growth_ratio": None}

EXPECTED_D_DEC31 = {"amount_growth_ratio": None, "total_amount_90d": 200.00, "total_amount_180d": 200.00,
    "txn_count_90d": 2}

def _conn():
    from shared.config.settings import settings
    return psycopg2.connect(settings.database_target_url_sync)

@pytest.fixture(autouse=True)
def _clean():
    for cid in TEST_IDS:
        c = _conn(); cur = c.cursor()
        cur.execute("DELETE FROM customer_features WHERE customer_id = %s", (cid,))
        cur.execute("DELETE FROM customer_transactions_clean WHERE customer_id = %s", (cid,))
        c.commit(); c.close()
    yield
    for cid in TEST_IDS:
        c = _conn(); cur = c.cursor()
        cur.execute("DELETE FROM customer_features WHERE customer_id = %s", (cid,))
        cur.execute("DELETE FROM customer_transactions_clean WHERE customer_id = %s", (cid,))
        c.commit(); c.close()

def insert_fixture():
    c = _conn(); cur = c.cursor(); now = datetime.now(timezone.utc)
    for row in FIXTURE_TXNS:
        cur.execute(
            "INSERT INTO customer_transactions_clean (customer_id,account_id,branch_code,"
            "transaction_date,transaction_type,channel,currency,amount,loaded_at,batch_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (*row, now, "test-fixture"))
    c.commit(); c.close()

def compute(as_of_date: str):
    from app.repository.repository import FeatureRepository
    FeatureRepository().compute_for_customers(date.fromisoformat(as_of_date), TEST_IDS)

def get_features(customer_id: str, as_of_date: str) -> dict | None:
    from app.repository.repository import FeatureRepository
    return FeatureRepository().get_features(customer_id, date.fromisoformat(as_of_date))

def get_latest(customer_id: str) -> dict | None:
    from app.repository.repository import FeatureRepository
    return FeatureRepository().get_latest(customer_id)
