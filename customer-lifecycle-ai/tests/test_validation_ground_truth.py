"""
Fixture Regression Test -- Validation Logic Canary.

Runs the ETL pipeline via subprocess (python run_etl.py --csv FIXTURE --force)
and asserts the results match hardcoded expected values.

THIS TEST USES HARDCODED EXPECTED VALUES BY DESIGN -- the fixture CSV never changes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE_CSV = _PROJECT_ROOT / "tests" / "fixtures" / "etl_validation_customers.csv"

EXPECTED = {
    "DUP-001": 350,
    "BUSINESS-DATE-001": 50,
    "BUSINESS-CHN-001": 50,
    "BUSINESS-AMT-001": 50,
    "MANDATORY-ACCOUNT_ID": 50,
    "MANDATORY-AMOUNT": 50,
    "BUSINESS-DATE-002": 50,
    "BUSINESS-CUR-001": 50,
    "MANDATORY-BRANCH_CODE": 50,
    "MANDATORY-CUSTOMER_ID": 50,
}


def _get_settings():
    sys.path.insert(0, str(_PROJECT_ROOT))
    os.chdir(str(_PROJECT_ROOT))
    from shared.config.settings import settings
    return settings


def _clear_tables():
    s = _get_settings()
    c = psycopg2.connect(s.database_target_url_sync)
    try:
        cur = c.cursor()
        cur.execute("DELETE FROM customer_transactions_clean")
        cur.execute("DELETE FROM customer_transactions_rejected")
        cur.execute("DELETE FROM etl.etl_audit")
        c.commit()
    finally:
        c.close()


def _query_db():
    s = _get_settings()
    c = psycopg2.connect(s.database_target_url_sync)
    try:
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM customer_transactions_clean")
        clean = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM customer_transactions_rejected")
        rejected = cur.fetchone()[0]
        cur.execute("SELECT rejection_reason, COUNT(*) FROM customer_transactions_rejected GROUP BY rejection_reason")
        reasons = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT rows_skipped FROM etl.etl_audit ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return {"clean": clean, "rejected": rejected, "reasons": reasons, "skipped": row[0] if row else -1}
    finally:
        c.close()


class TestValidationGroundTruth:

    @pytest.fixture(scope="class", autouse=True)
    def _run(self) -> None:
        _clear_tables()
        r = subprocess.run(
            [sys.executable, str(_PROJECT_ROOT / "run_etl.py"), "--csv", str(_FIXTURE_CSV), "--force"],
            capture_output=True, text=True, cwd=str(_PROJECT_ROOT),
        )
        assert r.returncode == 0, f"Pipeline failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
        self.__class__.d = _query_db()

    def test_total_rejected(self): assert self.d["rejected"] == 800
    def test_total_clean(self): assert self.d["clean"] == 69672
    def test_conservation(self): assert self.d["clean"] + self.d["rejected"] == 70472
    def test_audit_skipped(self): assert self.d["skipped"] == 0

    def test_categories(self):
        for reason, exp in EXPECTED.items():
            assert self.d["reasons"].get(reason, 0) == exp, f"{reason}: {self.d['reasons'].get(reason, 0)} != {exp}"
        for reason in self.d["reasons"]:
            assert reason in EXPECTED, f"Unexpected: {reason}"

    def test_no_co_flagged(self):
        s = _get_settings()
        c = psycopg2.connect(s.database_target_url_sync)
        try:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM customer_transactions_rejected WHERE rejection_reason LIKE '%CUR%' AND rejection_reason LIKE '%DUP%'")
            assert cur.fetchone()[0] == 0
        finally:
            c.close()
