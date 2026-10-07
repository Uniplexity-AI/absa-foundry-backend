"""
inspect_denodo_tables.py
========================
Manually samples 10 rows from every Denodo source table that the
"Trigger Manual Run" pipeline touches. Each table is saved as a
separate CSV inside scripts/csv_samples/ for manual verification.

Tables sampled
--------------
1. a_africa_zam_base_customers_new            -> csv_samples/customers_new.csv
2. a_africa_zam_base_customer_employment_daily_zm -> csv_samples/customer_employment.csv
3. a_africa_zam_base_customer_sms             -> csv_samples/customer_sms.csv
4. a_brains_trans_zam_base_entries_zm         -> csv_samples/transactions.csv
5. A_BRAINS_TRANS_ZAM_BASE_Daily_accounts_ALL -> csv_samples/daily_accounts.csv

Usage (run from the customer-lifecycle-ai directory):
    .venv\\Scripts\\python.exe scripts/inspect_denodo_tables.py

    # Sample more rows:
    .venv\\Scripts\\python.exe scripts/inspect_denodo_tables.py --limit 50
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap so we can import project modules without installing the pkg
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from shared.config.settings import settings
from etl.extraction.denodo_connector import DenodoStreamingExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-7s] %(message)s",
)
logger = logging.getLogger("inspect_denodo")

# Output directory
OUT_DIR = PROJECT_ROOT / "scripts" / "csv_samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helper: build a fresh extractor from project settings
# ---------------------------------------------------------------------------
def _build_extractor() -> DenodoStreamingExtractor:
    return DenodoStreamingExtractor(
        username=settings.denodo_username,
        password=settings.denodo_password,
        host=settings.denodo_host,
        port=settings.denodo_port,
        database=settings.denodo_db,
        java_home=settings.java_home,
        cacerts=settings.denodo_cacerts_path,
        path_jar=settings.denodo_jar_path,
        batch_size=500,
    )


# ---------------------------------------------------------------------------
# Helper: run a raw SQL SELECT and return a DataFrame
# ---------------------------------------------------------------------------
def _query(extractor: DenodoStreamingExtractor, sql: str, limit: int) -> pd.DataFrame:
    """
    DenodoStreamingExtractor.stream() expects a SQLAlchemy Select object, but
    for simple raw inspection queries we bypass that by directly calling
    the JDBC machinery.  We replicate the JDBC call here using the same
    jaydebeapi / jpype setup that the connector already wires up internally.
    """
    import jpype
    import jaydebeapi

    java_home = settings.java_home
    jar_path  = settings.denodo_jar_path
    cacerts   = settings.denodo_cacerts_path

    conn_url = (
        f"jdbc:vdb://{settings.denodo_host}:{settings.denodo_port}/{settings.denodo_db}"
        f"?sslTrustServerCertificate=true"
        f"&sslTrustStoreLocation={cacerts}"
        f"&queryTimeout=0"
        f"&chunkTimeout=0"
    )

    if java_home:
        cleaned = java_home.replace('"', "").replace("\\", "/")
        os.environ["PATH"] = cleaned + "/bin;" + os.environ.get("PATH", "")
        jvm_dll = cleaned + "/bin/server/jvm.dll"
        if not jpype.isJVMStarted():
            logger.info("Starting JVM at %s", jvm_dll)
            jpype.startJVM(jvm_dll, classpath=[jar_path])
    else:
        if not jpype.isJVMStarted():
            jpype.startJVM(jpype.getDefaultJVMPath(), classpath=[jar_path])

    conn   = jaydebeapi.connect("com.denodo.vdp.jdbc.Driver", conn_url,
                                [settings.denodo_username, settings.denodo_password])
    cursor = conn.cursor()

    final_sql = f"{sql} LIMIT {limit}"
    logger.info("Executing: %s", final_sql)
    cursor.execute(final_sql)

    columns = [d[0] for d in cursor.description]
    rows    = cursor.fetchall()
    cursor.close()
    conn.close()

    # Clean Java type wrappers
    cleaned_rows = []
    for row in rows:
        cleaned = []
        for v in row:
            if v is None:
                cleaned.append(None)
            else:
                s = str(v).strip()
                cleaned.append(None if s.upper() in ("NULL", "NONE", "") else s)
        cleaned_rows.append(cleaned)

    return pd.DataFrame(cleaned_rows, columns=columns)


# ---------------------------------------------------------------------------
# Individual table samplers (chained via customer_number)
# ---------------------------------------------------------------------------
def sample_customers_new(extractor, limit: int) -> tuple[pd.DataFrame, list[str]]:
    """
    Table 1/5: a_africa_zam_base_customers_new
    Returns the DataFrame AND a list of distinct customer_numbers to chain
    into the other tables.
    """
    logger.info("=" * 60)
    logger.info("TABLE 1/5: a_africa_zam_base_customers_new")
    logger.info("=" * 60)

    # Get 10 DISTINCT customers (not just 10 random rows)
    sql = (
        "SELECT DISTINCT customer_number "
        "FROM a_africa_zam_base_customers_new "
        "WHERE load_date >= '2026-01-01' AND customer_number IS NOT NULL"
    )
    id_df = _query(extractor, sql, limit)
    customer_ids = id_df["customer_number"].dropna().tolist()
    logger.info("Found %d distinct customer_numbers: %s", len(customer_ids), customer_ids)

    if not customer_ids:
        logger.warning("No customers found! Skipping remaining tables.")
        return pd.DataFrame(), []

    # Now pull ALL columns for those specific customers
    in_clause = ", ".join(f"'{c}'" for c in customer_ids)
    sql = (
        f"SELECT * FROM a_africa_zam_base_customers_new "
        f"WHERE customer_number IN ({in_clause}) AND load_date >= '2026-01-01'"
    )
    df = _query(extractor, sql, limit=9999)  # no limit — get all rows for these customers
    logger.info("Columns found (%d): %s", len(df.columns), df.columns.tolist())
    out = OUT_DIR / "customers_new.csv"
    df.to_csv(out, index=False)
    logger.info("Saved %d rows -> %s", len(df), out)
    print(df.to_string(index=False))
    return df, customer_ids


def sample_customer_employment(extractor, customer_ids: list[str]) -> None:
    """
    Table 2/5: a_africa_zam_base_customer_employment_daily_zm
    Pulls data for the SAME customers from table 1.
    """
    logger.info("=" * 60)
    logger.info("TABLE 2/5: a_africa_zam_base_customer_employment_daily_zm")
    logger.info("=" * 60)

    in_clause = ", ".join(f"'{c}'" for c in customer_ids)
    sql = (
        f"SELECT * FROM a_africa_zam_base_customer_employment_daily_zm "
        f"WHERE customer_number IN ({in_clause})"
    )
    df = _query(extractor, sql, limit=9999)
    logger.info("Columns found (%d): %s", len(df.columns), df.columns.tolist())
    out = OUT_DIR / "customer_employment.csv"
    df.to_csv(out, index=False)
    logger.info("Saved %d rows for %d customers -> %s", len(df), len(customer_ids), out)
    print(df.to_string(index=False))


def sample_customer_sms(extractor, customer_ids: list[str]) -> list[str]:
    """
    Table 3/5: a_africa_zam_base_customer_sms
    Pulls data for the SAME customers. Returns all account_numbers found
    so we can chain into transactions and accounts tables.
    """
    logger.info("=" * 60)
    logger.info("TABLE 3/5: a_africa_zam_base_customer_sms")
    logger.info("=" * 60)

    in_clause = ", ".join(f"'{c}'" for c in customer_ids)
    sql = (
        f"SELECT * FROM a_africa_zam_base_customer_sms "
        f"WHERE customer_number IN ({in_clause})"
    )
    df = _query(extractor, sql, limit=9999)
    logger.info("Columns found (%d): %s", len(df.columns), df.columns.tolist())
    out = OUT_DIR / "customer_sms.csv"
    df.to_csv(out, index=False)
    logger.info("Saved %d rows for %d customers -> %s", len(df), len(customer_ids), out)
    print(df.to_string(index=False))

    # Extract all account numbers for chaining
    account_numbers = []
    if "account_number" in df.columns:
        account_numbers = df["account_number"].dropna().unique().tolist()
        logger.info("Found %d unique account_numbers across %d customers: %s",
                     len(account_numbers), len(customer_ids), account_numbers)
    else:
        logger.warning("No 'account_number' column found in customer_sms!")
    return account_numbers


def sample_transactions(extractor, account_numbers: list[str]) -> None:
    """
    Table 4/5: a_brains_trans_zam_base_entries_zm
    Pulls transactions for the account_numbers linked to our 10 customers.
    """
    logger.info("=" * 60)
    logger.info("TABLE 4/5: a_brains_trans_zam_base_entries_zm")
    logger.info("=" * 60)

    if not account_numbers:
        logger.warning("No account_numbers to query — skipping transactions.")
        return

    in_clause = ", ".join(f"'{a}'" for a in account_numbers)

    # First probe with SELECT * LIMIT 1 to discover columns
    logger.info("Probing column names ...")
    probe_df = _query(extractor, "SELECT * FROM a_brains_trans_zam_base_entries_zm", limit=1)
    logger.info("Columns found (%d): %s", len(probe_df.columns), probe_df.columns.tolist())

    # Determine join key — try account_number first, fallback to customer_number
    if "account_number" in probe_df.columns:
        join_col = "account_number"
    elif "customer_number" in probe_df.columns:
        join_col = "customer_number"
    else:
        logger.error("Cannot find account_number or customer_number in transactions table!")
        # Fallback: just dump 10 rows
        df = _query(extractor, "SELECT * FROM a_brains_trans_zam_base_entries_zm", limit=10)
        out = OUT_DIR / "transactions.csv"
        df.to_csv(out, index=False)
        logger.info("Saved %d unfiltered rows -> %s", len(df), out)
        print(df.to_string(index=False))
        return

    logger.info("Using join key: %s", join_col)
    sql = (
        f"SELECT * FROM a_brains_trans_zam_base_entries_zm "
        f"WHERE {join_col} IN ({in_clause}) "
        f"AND system_date >= '2026-01-01'"
    )
    df = _query(extractor, sql, limit=200)  # cap at 200 rows to avoid huge output
    out = OUT_DIR / "transactions.csv"
    df.to_csv(out, index=False)
    logger.info("Saved %d rows for %d accounts -> %s", len(df), len(account_numbers), out)
    print(df.to_string(index=False))


def sample_daily_accounts(extractor, account_numbers: list[str]) -> None:
    """
    Table 5/5: A_BRAINS_TRANS_ZAM_BASE_Daily_accounts_ALL
    Pulls daily account snapshots for the same account_numbers.
    """
    logger.info("=" * 60)
    logger.info("TABLE 5/5: A_BRAINS_TRANS_ZAM_BASE_Daily_accounts_ALL")
    logger.info("=" * 60)

    if not account_numbers:
        logger.warning("No account_numbers to query — skipping daily accounts.")
        return

    in_clause = ", ".join(f"'{a}'" for a in account_numbers)
    sql = (
        f"SELECT * FROM A_BRAINS_TRANS_ZAM_BASE_Daily_accounts_ALL "
        f"WHERE account_number IN ({in_clause}) "
        f"AND system_date >= '2026-01-01'"
    )
    df = _query(extractor, sql, limit=200)  # cap at 200
    logger.info("Columns found (%d): %s", len(df.columns), df.columns.tolist())
    out = OUT_DIR / "daily_accounts.csv"
    df.to_csv(out, index=False)
    logger.info("Saved %d rows for %d accounts -> %s", len(df), len(account_numbers), out)
    print(df.to_string(index=False))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Sample data for 10 customers from all Denodo source tables and save as CSV."
    )
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Number of distinct customers to sample (default: 10)"
    )
    args = parser.parse_args()
    limit = args.limit

    logger.info("Connecting to Denodo at %s:%s/%s ...",
                settings.denodo_host, settings.denodo_port, settings.denodo_db)
    extractor = _build_extractor()

    logger.info("Sampling %d distinct customers. Output -> %s", limit, OUT_DIR)
    logger.info("")

    # Step 1: Get 10 distinct customers (anchor for everything else)
    cust_df, customer_ids = sample_customers_new(extractor, limit)
    if not customer_ids:
        logger.error("No customers found — aborting.")
        return

    # Step 2: Employment data for same customers
    sample_customer_employment(extractor, customer_ids)

    # Step 3: SMS/account data for same customers (returns account numbers)
    account_numbers = sample_customer_sms(extractor, customer_ids)

    # Step 4: Transactions for those accounts
    sample_transactions(extractor, account_numbers)

    # Step 5: Daily account snapshots for those accounts
    sample_daily_accounts(extractor, account_numbers)

    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("  Customers sampled: %d", len(customer_ids))
    logger.info("  Account numbers found: %d", len(account_numbers))
    logger.info("  CSVs saved to: %s", OUT_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

