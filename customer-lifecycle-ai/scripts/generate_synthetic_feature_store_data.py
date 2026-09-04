"""Generate fully synthetic source data for the customer feature store.

The data intentionally includes recent transactions, novel recent channels,
unactivated cards, and cards expiring soon so that feature-store edge cases can
be exercised.  It never uses production customer data.

Install dependencies:
    pip install Faker pandas psycopg2-binary

Examples:
    python scripts/generate_synthetic_feature_store_data.py --dry-run
    python scripts/generate_synthetic_feature_store_data.py --load --database-url "$DATABASE_URL"
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import uuid
from dataclasses import dataclass

import numpy as np
import pandas as pd
import psycopg2
from faker import Faker


DDL_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS customers_clean (
        customer_id VARCHAR(64) PRIMARY KEY, full_name VARCHAR(128),
        date_of_birth DATE, gender VARCHAR(16), branch_code VARCHAR(16),
        customer_since_date DATE, loaded_at TIMESTAMPTZ, batch_id VARCHAR(64)
    )
    """,
    "ALTER TABLE customers_clean ADD COLUMN IF NOT EXISTS kyc_tier VARCHAR(16)",
    "ALTER TABLE customers_clean ADD COLUMN IF NOT EXISTS nationality VARCHAR(64)",
    "ALTER TABLE customers_clean ADD COLUMN IF NOT EXISTS status VARCHAR(16)",
    """
    CREATE TABLE IF NOT EXISTS customer_transactions_clean (
        transaction_id VARCHAR(64) PRIMARY KEY,
        customer_id VARCHAR(64) REFERENCES customers_clean(customer_id),
        transaction_date TIMESTAMP, amount NUMERIC(14,2),
        transaction_type VARCHAR(16), channel VARCHAR(16),
        merchant_category VARCHAR(32), currency VARCHAR(8),
        loaded_at TIMESTAMPTZ, batch_id VARCHAR(64)
    )
    """,
    """
    DO $$ BEGIN
      IF (SELECT data_type FROM information_schema.columns
          WHERE table_name = 'customer_transactions_clean'
            AND column_name = 'transaction_date') = 'date' THEN
        ALTER TABLE customer_transactions_clean ALTER COLUMN transaction_date
          TYPE TIMESTAMP USING transaction_date::timestamp;
      END IF;
    END $$
    """,
    """CREATE TABLE IF NOT EXISTS accounts_clean (
        account_id VARCHAR(64) PRIMARY KEY,
        customer_id VARCHAR(64) REFERENCES customers_clean(customer_id),
        account_type VARCHAR(32) NOT NULL, status VARCHAR(16) NOT NULL,
        opened_date DATE, loaded_at TIMESTAMPTZ NOT NULL, batch_id VARCHAR(64) NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS loans_clean (
        loan_id VARCHAR(64) PRIMARY KEY,
        customer_id VARCHAR(64) REFERENCES customers_clean(customer_id),
        loan_type VARCHAR(32) NOT NULL, status VARCHAR(16) NOT NULL,
        origination_date DATE, loaded_at TIMESTAMPTZ NOT NULL, batch_id VARCHAR(64) NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS cards_clean (
        card_id VARCHAR(64) PRIMARY KEY,
        customer_id VARCHAR(64) REFERENCES customers_clean(customer_id),
        card_type VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL,
        issued_date DATE, expiry_date DATE, activated_date DATE,
        loaded_at TIMESTAMPTZ NOT NULL, batch_id VARCHAR(64) NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS digital_engagement_clean (
        engagement_id VARCHAR(64) PRIMARY KEY,
        customer_id VARCHAR(64) REFERENCES customers_clean(customer_id),
        login_date DATE NOT NULL, platform VARCHAR(32) NOT NULL,
        session_duration_seconds INTEGER, actions_count INTEGER,
        loaded_at TIMESTAMPTZ NOT NULL, batch_id VARCHAR(64) NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS demographics_clean (
        customer_id VARCHAR(64) PRIMARY KEY REFERENCES customers_clean(customer_id),
        employment_status VARCHAR(32), employer_name VARCHAR(128),
        monthly_income_declared NUMERIC(14,2), education_level VARCHAR(32),
        marital_status VARCHAR(16), loaded_at TIMESTAMPTZ NOT NULL, batch_id VARCHAR(64) NOT NULL)""",
)


@dataclass(frozen=True)
class Configuration:
    customers: int
    as_of_date: dt.date
    seed: int


class SyntheticDataGenerator:
    channels = ("ATM", "POS", "MOBILE_APP", "USSD", "BRANCH", "ONLINE_BANKING")
    categories = ("GROCERY", "ELECTRONICS", "FUEL", "UTILITIES", "RESTAURANT", "PHARMACY", "AIRTIME", "TRANSPORT", "RETAIL", "EDUCATION")

    def __init__(self, config: Configuration) -> None:
        self.config = config
        self.rng = np.random.default_rng(config.seed)
        Faker.seed(config.seed)
        self.fake = Faker()
        self.loaded_at = dt.datetime.now(dt.timezone.utc)
        self.batch_id = f"synthetic_{config.as_of_date:%Y-%m-%d}_{uuid.uuid4().hex[:8]}"

    def _choice(self, values, probabilities=None):
        return self.rng.choice(values, p=probabilities)

    def customers(self) -> pd.DataFrame:
        n, today = self.config.customers, self.config.as_of_date
        ids = [f"CUST{i:07d}" for i in range(1, n + 1)]
        # Behaviourally-driven churn: ~5% of customers are marked Closed, and
        # transactions() gives them a 90+ day activity gap so the churn label is
        # causally linked to recent transaction behaviour (learnable by the model).
        churn = self.rng.random(n) < 0.05
        status = np.where(churn, "Closed", "Active")
        return pd.DataFrame({
            "customer_id": ids, "full_name": [self.fake.name() for _ in ids],
            "date_of_birth": [today - dt.timedelta(days=int(self.rng.integers(18 * 365, 80 * 365))) for _ in ids],
            "gender": self.rng.choice(("M", "F"), n),
            "branch_code": self.rng.choice([f"BR{i:03d}" for i in range(1, 26)], n),
            "customer_since_date": [today - dt.timedelta(days=int(self.rng.integers(30, 15 * 365))) for _ in ids],
            "kyc_tier": self.rng.choice(("TIER_1", "TIER_2", "TIER_3"), n, p=(.55, .35, .10)),
            "nationality": self.rng.choice(("ZM", "ZA", "ZW", "TZ", "KE", "MW", "CD", "NG", "GB", "IN"), n, p=(.62, .08, .06, .05, .04, .04, .04, .03, .02, .02)),
            "status": status,
            "loaded_at": self.loaded_at, "batch_id": self.batch_id,
        })

    def transactions(self, customer_ids: list[str], churned_ids: set[str]) -> pd.DataFrame:
        rows, today = [], self.config.as_of_date
        novel_customers = set(self.rng.choice(customer_ids, max(1, int(.15 * len(customer_ids))), replace=False))
        for customer_id in customer_ids:
            habitual = list(self.rng.choice(self.channels, int(self.rng.integers(2, 4)), replace=False))
            count = int(self.rng.integers(20, 120))
            if customer_id in churned_ids:
                # Churned customers: activity stops 90+ days before as_of_date,
                # producing a clean recency/frequency churn signal.
                offsets = list(self.rng.integers(90, 181, count))
            else:
                offsets = list(self.rng.integers(31, 181, count - max(1, count // 4))) + list(self.rng.integers(0, 31, max(1, count // 4)))
            for offset in offsets:
                recent = offset <= 30
                available = habitual
                if recent and customer_id in novel_customers:
                    available = [channel for channel in self.channels if channel not in habitual]
                timestamp = dt.datetime.combine(today - dt.timedelta(days=int(offset)), dt.time(int(self.rng.integers(0, 24)), int(self.rng.integers(0, 60))))
                rows.append({"transaction_id": f"TXN{uuid.uuid4().hex[:16]}", "customer_id": customer_id,
                    "transaction_date": timestamp, "amount": round(min(float(self.rng.lognormal(4.2, 1.1)), 50_000), 2),
                    "transaction_type": self._choice(("DEBIT", "CREDIT"), (.72, .28)), "channel": self._choice(available),
                    "merchant_category": self._choice(self.categories), "currency": "ZMW", "loaded_at": self.loaded_at, "batch_id": self.batch_id})
        return pd.DataFrame(rows).sort_values(["customer_id", "transaction_date"]).reset_index(drop=True)

    def products(self, customer_ids: list[str], table: str) -> pd.DataFrame:
        rows, today = [], self.config.as_of_date
        spec = {
            "accounts_clean": (1.0, "account_id", ("SAVINGS", "CURRENT", "FIXED_DEPOSIT"), ("Active", "Dormant", "Closed"), (.78, .15, .07), "opened_date"),
            "loans_clean": (.35, "loan_id", ("PERSONAL", "MORTGAGE", "BUSINESS", "AUTO"), ("Active", "Closed", "Defaulted"), (.62, .30, .08), "origination_date"),
        }[table]
        penetration, id_col, types, statuses, weights, date_col = spec
        for customer_id in self.rng.choice(customer_ids, int(len(customer_ids) * penetration), replace=False):
            for _ in range(int(self.rng.choice((1, 2), p=(.85, .15)))):
                rows.append({id_col: f"{id_col[:3].upper()}{uuid.uuid4().hex[:16]}", "customer_id": customer_id,
                    "account_type" if table == "accounts_clean" else "loan_type": self._choice(types), "status": self._choice(statuses, weights),
                    date_col: today - dt.timedelta(days=int(self.rng.integers(30, 15 * 365))), "loaded_at": self.loaded_at, "batch_id": self.batch_id})
        return pd.DataFrame(rows)

    def cards(self, customer_ids: list[str]) -> pd.DataFrame:
        rows, today = [], self.config.as_of_date
        for customer_id in self.rng.choice(customer_ids, int(.8 * len(customer_ids)), replace=False):
            for _ in range(int(self.rng.choice((1, 2), p=(.75, .25)))):
                issued = today - dt.timedelta(days=int(self.rng.integers(30, 4 * 365)))
                expiry = today + dt.timedelta(days=int(self.rng.integers(1, 31))) if self.rng.random() < .08 else issued + dt.timedelta(days=int(self.rng.integers(3, 5) * 365))
                status = self._choice(("Active", "Blocked", "Expired", "Cancelled", "Pending_Activation"), (.68, .06, .10, .06, .10))
                activated = None if status == "Pending_Activation" or self.rng.random() < .12 else issued + dt.timedelta(days=int(self.rng.integers(0, max(1, (today-issued).days))))
                rows.append({"card_id": f"CARD{uuid.uuid4().hex[:16]}", "customer_id": customer_id, "card_type": self._choice(("DEBIT", "CREDIT", "PREPAID"), (.55, .30, .15)), "status": status, "issued_date": issued, "expiry_date": expiry, "activated_date": activated, "loaded_at": self.loaded_at, "batch_id": self.batch_id})
        return pd.DataFrame(rows)

    def engagement(self, customer_ids: list[str]) -> pd.DataFrame:
        rows, today = [], self.config.as_of_date
        for customer_id in self.rng.choice(customer_ids, int(.7 * len(customer_ids)), replace=False):
            level = self._choice(("light", "regular", "heavy"), (.4, .4, .2))
            low, high = {"light": (2, 8), "regular": (8, 30), "heavy": (30, 90)}[level]
            preferred = self._choice(("MOBILE_APP", "WEB", "USSD"), (.65, .20, .15))
            for _ in range(int(self.rng.integers(low, high))):
                rows.append({"engagement_id": f"ENG{uuid.uuid4().hex[:16]}", "customer_id": customer_id, "login_date": today - dt.timedelta(days=int(self.rng.integers(0, 91))), "platform": preferred if self.rng.random() < .85 else self._choice(("MOBILE_APP", "WEB", "USSD")), "session_duration_seconds": int(self.rng.integers(15, 1800)), "actions_count": int(self.rng.integers(1, 40)), "loaded_at": self.loaded_at, "batch_id": self.batch_id})
        return pd.DataFrame(rows)

    def demographics(self, customer_ids: list[str]) -> pd.DataFrame:
        employment = self.rng.choice(("Employed", "Self_Employed", "Unemployed", "Retired", "Student"), len(customer_ids), p=(.55, .20, .10, .08, .07))
        return pd.DataFrame({"customer_id": customer_ids, "employment_status": employment,
            "employer_name": [self.fake.company() if status == "Employed" else f"Self-employed: {self.fake.bs()}" if status == "Self_Employed" else None for status in employment],
            "monthly_income_declared": np.where(employment == "Unemployed", 0, self.rng.lognormal(7.5, .6, len(customer_ids)).round(2)),
            "education_level": self.rng.choice(("Primary", "Secondary", "Tertiary", "Postgraduate"), len(customer_ids), p=(.1, .4, .4, .1)),
            "marital_status": self.rng.choice(("Single", "Married", "Divorced", "Widowed"), len(customer_ids), p=(.42, .45, .09, .04)), "loaded_at": self.loaded_at, "batch_id": self.batch_id})

    def build(self) -> dict[str, pd.DataFrame]:
        customers = self.customers()
        customer_ids = customers["customer_id"].tolist()
        churned_ids = set(customers.loc[customers["status"] == "Closed", "customer_id"])
        return {"customers_clean": customers, "customer_transactions_clean": self.transactions(customer_ids, churned_ids),
                "accounts_clean": self.products(customer_ids, "accounts_clean"), "loans_clean": self.products(customer_ids, "loans_clean"),
                "cards_clean": self.cards(customer_ids), "digital_engagement_clean": self.engagement(customer_ids), "demographics_clean": self.demographics(customer_ids)}


def validate(tables: dict[str, pd.DataFrame], as_of_date: dt.date) -> None:
    transactions = tables["customer_transactions_clean"]
    recent = transactions[transactions.transaction_date >= pd.Timestamp(as_of_date - dt.timedelta(days=30))]
    assert not recent.empty, "No transactions in the 30-day window"
    customers = set(tables["customers_clean"].customer_id)
    for table, frame in tables.items():
        assert set(frame.customer_id).issubset(customers), f"{table} has orphaned customer IDs"
    print(f"Validated {len(recent):,} recent transactions across {recent.customer_id.nunique():,} customers.")


def apply_ddl(connection) -> None:
    with connection.cursor() as cursor:
        for statement in DDL_STATEMENTS:
            cursor.execute(statement)
    connection.commit()


def copy_frame(connection, table: str, frame: pd.DataFrame) -> None:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, header=False, na_rep="\\N")
    buffer.seek(0)
    columns = ", ".join(frame.columns)
    with connection.cursor() as cursor:
        cursor.copy_expert(f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", buffer)
    connection.commit()
    print(f"Loaded {len(frame):,} rows into {table}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customers", type=int, default=5_000, help="Number of synthetic customers (default: 5000).")
    parser.add_argument("--as-of-date", type=dt.date.fromisoformat, default=dt.date.today(), help="Reference date in YYYY-MM-DD format.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true", help="Build and validate data without writing to PostgreSQL.")
    parser.add_argument("--load", action="store_true", help="Apply DDL and load generated data into PostgreSQL.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL URL (or DATABASE_URL).")
    args = parser.parse_args()
    if args.customers < 1:
        parser.error("--customers must be positive")
    if args.load == args.dry_run:
        parser.error("Specify exactly one of --dry-run or --load")
    if args.load and not args.database_url:
        parser.error("--database-url or DATABASE_URL is required with --load")
    return args


def main() -> None:
    args = parse_args()
    generator = SyntheticDataGenerator(Configuration(args.customers, args.as_of_date, args.seed))
    tables = generator.build()
    print(f"Generated batch {generator.batch_id} for {args.customers:,} customers (as of {args.as_of_date}).")
    for name, frame in tables.items():
        print(f"  {name}: {len(frame):,} rows")
    validate(tables, args.as_of_date)
    if args.dry_run:
        print("Dry run complete; no database changes made.")
        return
    connection = psycopg2.connect(args.database_url)
    try:
        # DDL already handled by pilot_migrate.py; skip in data generator.
        # apply_ddl(connection)
        for name, frame in tables.items():
            copy_frame(connection, name, frame)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
