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


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 Generator Test Fixtures
# ═══════════════════════════════════════════════════════════════════════════════
#
# Uses numeric-suffix IDs (CUST00097) that match customers_clean IDs (C01000097)
# via RIGHT(id, 5) join in the profile generator.
# ═══════════════════════════════════════════════════════════════════════════════

PHASE2_TXNS = [
    # customer_id, account_id, branch_code, txn_date, type, channel, currency, amount
    ("CUST00097", "ACC-97", "BR001", "2024-01-15", "CREDIT", "MOBILE", "USD", 100.00),
    ("CUST00097", "ACC-97", "BR001", "2024-03-20", "DEBIT", "ATM", "USD", 200.00),
    ("CUST00097", "ACC-97", "BR001", "2024-06-10", "CREDIT", "ONLINE", "USD", 300.00),
    ("CUST00097", "ACC-97", "BR001", "2024-09-01", "CREDIT", "BRANCH", "USD", 400.00),
    ("CUST00097", "ACC-97", "BR001", "2024-11-15", "CREDIT", "MOBILE", "USD", 500.00),
    ("CUST00097", "ACC-97", "BR001", "2024-12-01", "DEBIT", "ATM", "USD", 50.00),
    ("CUST00097", "ACC-97", "BR001", "2024-12-10", "CREDIT", "MOBILE", "USD", 600.00),
    ("CUST00097", "ACC-97", "BR001", "2024-12-20", "DEBIT", "POS", "USD", 75.00),
    # Second customer: transactions only in 180d window, sparse
    ("CUST00098", "ACC-98", "BR002", "2024-10-01", "CREDIT", "ATM", "USD", 1000.00),
    ("CUST00098", "ACC-98", "BR002", "2024-12-15", "DEBIT", "MOBILE", "USD", 200.00),
]
PHASE2_IDS = ["CUST00097", "CUST00098"]

# Customer profile data matching CUST00097 → C01000097, CUST00098 → C01000098
PHASE2_CUSTOMERS = [
    # id, customer_id, activation_date, branch_code, country, customer_type,
    # onboarding_channel, date_of_birth, gender, status
    (99901, "C01000097", "2023-01-15", "BR001", "ZM", "Retail",
     "Branch", "1995-06-15", "F", "Active"),
    (99902, "C01000098", "2023-06-01", "BR002", "ZM", "Corporate",
     "Online", "1988-03-22", "M", "Active"),
]

# ── Expected Phase 2 values for CUST00097 as of 2024-12-31 ──

# Profile (from customers_clean via RIGHT join)
EXPECTED_P2_PROFILE_97 = {
    "customer_segment": "Retail",
    "customer_tenure_days": 716,       # 2023-01-15 → 2024-12-31
    "age_years": 29,                    # 1995-06-15 → 2024-12-31
    "onboarding_channel": "Branch",
    "prof_primary_branch": "BR001",
    "prof_age_band": "26-35",  # 1995-06-15 → 29 as of 2024-12-31
}

# Behaviour (8 txns total; 4 active days in 90d: Nov 15, Dec 1, 10, 20)
# days_since_last = 11 (Dec 20→Dec 31); txn_count_30d = 3 (Dec 1, 10, 20)
# channels in 90d = 3 (MOBILE, ATM, POS); txn_types in 90d = 2 (CREDIT, DEBIT)
EXPECTED_P2_BEHAVIOUR_97 = {
    "behav_txn_count_7d": 0,
    "behav_active_days_90d": 4,
    "behav_inactive_days_90d": 86,
    "behav_activity_consistency": pytest.approx(0.04, abs=0.01),
    "engagement_score": 52,            # recency≈35.1 + freq≈3.5 + diversity=12.5 ≈ 51.1→52
    "txn_frequency_trend": pytest.approx(0.04, abs=0.01),
    "inactivity_streak_days": 86,
}

# Financial (90d: 500+50+600+75=1225; credit=1100, debit=125)
# Median of [50,75,500,600] = 287.5
# salary: Nov(500)+Dec(600) → CV = 70.71/550 ≈ 0.13
# income_growth: 1100 / (prev 90d: Jun 10=300, Sep 1=400) = 1100/700 ≈ 1.57
EXPECTED_P2_FINANCIAL_97 = {
    "fin_total_credit_90d": 1100.0,
    "fin_total_debit_90d": 125.0,
    "fin_median_txn_amount_90d": pytest.approx(287.5, rel=0.01),
    "fin_salary_consistency": pytest.approx(0.13, abs=0.02),
    "fin_income_growth": pytest.approx(1.57, rel=0.01),
}

# Channel (90d: MOBILE×2, ATM×1, POS×1, BRANCH×0, ONLINE×0; total=4)
# mobile_ratio=0.5, atm_ratio=0.25, branch_ratio=0.0
# digital = (2+0)/4*100 = 50
# entropy: 3 channels, normalized ≈ 0.95
EXPECTED_P2_CHANNEL_97 = {
    "chan_mobile_ratio_90d": pytest.approx(0.5, abs=0.01),
    "chan_atm_ratio_90d": pytest.approx(0.25, abs=0.01),
    "chan_branch_ratio_90d": pytest.approx(0.0, abs=0.01),
    "chan_digital_adoption_score": 50,
    "chan_channel_entropy": pytest.approx(0.95, abs=0.05),
}

# Expected Phase 2 values for CUST00098 (sparse: 2 txns, both in 90d window)
EXPECTED_P2_PROFILE_98 = {
    "customer_segment": "Corporate",
    "prof_primary_branch": "BR002",
    "prof_age_band": "36-50",           # 1988 → 36 as of 2024
}
EXPECTED_P2_BEHAVIOUR_98 = {
    "behav_active_days_90d": 2,
    "behav_inactive_days_90d": 88,
    "behav_txn_count_7d": 0,
}
EXPECTED_P2_FINANCIAL_98 = {
    "fin_total_credit_90d": 1000.0,
    "fin_total_debit_90d": 200.0,
}
EXPECTED_P2_CHANNEL_98 = {
    "chan_mobile_ratio_90d": pytest.approx(0.5, abs=0.01),
    "chan_atm_ratio_90d": pytest.approx(0.5, abs=0.01),
}


@pytest.fixture(autouse=True)
def _clean_phase2():
    """Clean Phase 2 fixture data before/after each test."""
    for cid in PHASE2_IDS:
        c = _conn(); cur = c.cursor()
        cur.execute("DELETE FROM customer_features WHERE customer_id = %s", (cid,))
        cur.execute("DELETE FROM customer_transactions_clean WHERE customer_id = %s", (cid,))
        c.commit(); c.close()
    # Also clean customers_clean for matching C01 IDs
    for cid in PHASE2_IDS:
        numeric = cid[4:]
        c01_id = "C01" + numeric.rjust(6, "0")
        c = _conn(); cur = c.cursor()
        cur.execute("DELETE FROM customers_clean WHERE customer_id = %s", (c01_id,))
        c.commit(); c.close()
    yield
    for cid in PHASE2_IDS:
        c = _conn(); cur = c.cursor()
        cur.execute("DELETE FROM customer_features WHERE customer_id = %s", (cid,))
        cur.execute("DELETE FROM customer_transactions_clean WHERE customer_id = %s", (cid,))
        c.commit(); c.close()
        numeric = cid[4:]
        c01_id = "C01" + numeric.rjust(6, "0")
        c = _conn(); cur = c.cursor()
        cur.execute("DELETE FROM customers_clean WHERE customer_id = %s", (c01_id,))
        c.commit(); c.close()


def insert_phase2_fixture():
    """Insert Phase 2 transaction and customer fixtures."""
    c = _conn(); cur = c.cursor(); now = datetime.now(timezone.utc)

    # Insert transactions
    for row in PHASE2_TXNS:
        cur.execute(
            "INSERT INTO customer_transactions_clean (customer_id,account_id,branch_code,"
            "transaction_date,transaction_type,channel,currency,amount,loaded_at,batch_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (*row, now, "test-phase2"))

    # Insert customers_clean with matching IDs
    for row in PHASE2_CUSTOMERS:
        cur.execute(
            "INSERT INTO customers_clean (id,customer_id,activation_date,branch_code,"
            "country,customer_type,onboarding_channel,date_of_birth,gender,status,"
            "loaded_at,batch_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (*row, now, "test-phase2"))

    c.commit(); c.close()


def run_phase1(date_str: str):
    """Run Phase 1 for Phase 2 test IDs."""
    from app.repository.repository import FeatureRepository
    FeatureRepository().compute_for_customers(date.fromisoformat(date_str), PHASE2_IDS)


def run_generators(date_str: str):
    """Run all 7 domain generators for the given date."""
    from app.features.customer.generator import CustomerProfileGenerator
    from app.features.behaviour.generator import BehaviourGenerator
    from app.features.financial.generator import FinancialGenerator
    from app.features.channel.generator import ChannelGenerator
    from app.features.temporal.generator import TemporalGenerator
    from app.features.risk.generator import RiskGenerator
    from app.features.relationship.generator import RelationshipGenerator

    conn = _conn()
    try:
        for name, GenCls in [
            ("profile", CustomerProfileGenerator),
            ("behaviour", BehaviourGenerator),
            ("financial", FinancialGenerator),
            ("channel", ChannelGenerator),
            ("temporal", TemporalGenerator),
            ("risk", RiskGenerator),
            ("relationship", RelationshipGenerator),
        ]:
            gen = GenCls(conn)
            gen.generate(date.fromisoformat(date_str))
    finally:
        conn.close()


def get_p2_features(customer_id: str, as_of_date: str) -> dict:
    """Fetch all columns for a Phase 2 customer snapshot."""
    c = _conn(); cur = c.cursor()
    cur.execute(
        "SELECT * FROM customer_features WHERE customer_id=%s AND as_of_date=%s",
        (customer_id, as_of_date),
    )
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    c.close()
    if row is None:
        return None
    return dict(zip(cols, row))
