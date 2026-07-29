"""
Database index migration for customer_features and customer_transactions_clean.

Creates performance-critical indexes used by the feature engineering pipeline.
All queries filter by (customer_id, transaction_date) combinations — without
these indexes, every query performs a sequential scan of 209K+ rows.

Run once:
    python scripts/add_feature_indexes.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from shared.config.settings import settings

INDEXES = [
    # Primary lookup: every generator queries transactions by customer + date range
    (
        "customer_transactions_clean",
        "CREATE INDEX IF NOT EXISTS idx_txn_customer_date "
        "ON customer_transactions_clean (customer_id, transaction_date DESC)"
    ),
    # Financial generator: filters by type within date range
    (
        "customer_transactions_clean",
        "CREATE INDEX IF NOT EXISTS idx_txn_customer_date_type "
        "ON customer_transactions_clean (customer_id, transaction_date DESC, transaction_type)"
    ),
    # Channel generator: filters by channel within date range
    (
        "customer_transactions_clean",
        "CREATE INDEX IF NOT EXISTS idx_txn_customer_date_channel "
        "ON customer_transactions_clean (customer_id, transaction_date DESC, channel)"
    ),
    # Fetch/lookup: get_features, get_latest
    (
        "customer_features",
        "CREATE INDEX IF NOT EXISTS idx_feat_customer_date "
        "ON customer_features (customer_id, as_of_date DESC)"
    ),
    # Phase 2 bulk update: all rows for a single as_of_date
    (
        "customer_features",
        "CREATE INDEX IF NOT EXISTS idx_feat_as_of_date "
        "ON customer_features (as_of_date)"
    ),
    # Profile generator: RIGHT join on customers_clean
    (
        "customers_clean",
        "CREATE INDEX IF NOT EXISTS idx_cust_clean_customer_id "
        "ON customers_clean (customer_id)"
    ),
]


def main():
    conn = psycopg2.connect(
        settings.database_target_url_sync,
        connect_timeout=10,
    )
    conn.autocommit = True
    cur = conn.cursor()

    created = 0
    skipped = 0
    for table, sql in INDEXES:
        # Check if index already exists
        idx_name = sql.split("IF NOT EXISTS ")[1].split(" ")[0] if "IF NOT EXISTS" in sql else "?"
        cur.execute(
            "SELECT 1 FROM pg_indexes WHERE tablename = %s AND indexname = %s",
            (table, idx_name),
        )
        if cur.fetchone():
            print(f"  SKIP: {idx_name} (already exists)")
            skipped += 1
        else:
            try:
                cur.execute(sql)
                print(f"  OK:   {idx_name}")
                created += 1
            except Exception as e:
                print(f"  FAIL: {idx_name} — {e}")

    print(f"\nDone: {created} created, {skipped} skipped")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
