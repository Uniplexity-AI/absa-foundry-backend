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
# Individual table samplers
# ---------------------------------------------------------------------------
def sample_customers_new(extractor, limit: int) -> None:
    """
    Table: a_africa_zam_base_customers_new
    Purpose: Core customer identity fields — the PRIMARY TABLE of the pipeline.
    Fields we care about (mapped in customer_360.yaml):
        customer_number -> customer_id
        first_name + family_name -> full_name
        sex -> gender
        market_segment -> market_segment_code / market_segment
        risk_level, risk_score
        current_count, savings_count, investment_count,
        secured_count, unsecured_count
        id_card_number -> national_id
        customer_status -> status
        relationship_established -> customer_since_date
        kyc_status -> kyc_tier
    """
    logger.info("=" * 60)
    logger.info("TABLE 1/5: a_africa_zam_base_customers_new")
    logger.info("=" * 60)

    sql = """
        SELECT
            customer_number,
            first_name,
            family_name,
            sex,
            market_segment,
            risk_level,
            risk_score,
            current_count,
            savings_count,
            investment_count,
            secured_count,
            unsecured_count,
            id_card_number,
            customer_status,
            relationship_established,
            kyc_status,
            display_name,
            company_name,
            date_of_status
        FROM a_africa_zam_base_customers_new
        WHERE customer_number IS NOT NULL
    """
    df = _query(extractor, sql.strip(), limit)
    out = OUT_DIR / "customers_new.csv"
    df.to_csv(out, index=False)
    logger.info("Saved %d rows -> %s", len(df), out)
    print(df.to_string(index=False))


def sample_customer_employment(extractor, limit: int) -> None:
    """
    Table: a_africa_zam_base_customer_employment_daily_zm
    Purpose: Employment & location fields joined via customer_number.
    Fields we care about:
        customer_number (join key)
        country -> nationality
        district_or_region -> branch_code
        gross_income, other_income
        employment_type, employment_status
        job_title, town_or_city
    """
    logger.info("=" * 60)
    logger.info("TABLE 2/5: a_africa_zam_base_customer_employment_daily_zm")
    logger.info("=" * 60)

    sql = """
        SELECT
            customer_number,
            country,
            district_or_region,
            gross_income,
            other_income,
            employment_type,
            employment_status,
            job_title,
            town_or_city,
            employer,
            employment_status_date
        FROM a_africa_zam_base_customer_employment_daily_zm
        WHERE customer_number IS NOT NULL
    """
    df = _query(extractor, sql.strip(), limit)
    out = OUT_DIR / "customer_employment.csv"
    df.to_csv(out, index=False)
    logger.info("Saved %d rows -> %s", len(df), out)
    print(df.to_string(index=False))


def sample_customer_sms(extractor, limit: int) -> None:
    """
    Table: a_africa_zam_base_customer_sms
    Purpose: Contact/account fields joined via customer_number.
    Fields we care about:
        customer_number (join key)
        account_number -> account_number
    """
    logger.info("=" * 60)
    logger.info("TABLE 3/5: a_africa_zam_base_customer_sms")
    logger.info("=" * 60)

    sql = """
        SELECT
            customer_number,
            account_number,
            branch_number,
            africa_country_code
        FROM a_africa_zam_base_customer_sms
        WHERE customer_number IS NOT NULL
    """
    df = _query(extractor, sql.strip(), limit)
    out = OUT_DIR / "customer_sms.csv"
    df.to_csv(out, index=False)
    logger.info("Saved %d rows -> %s", len(df), out)
    print(df.to_string(index=False))


def sample_transactions(extractor, limit: int) -> None:
    """
    Table: a_brains_trans_zam_base_entries_zm
    Purpose: Raw transaction history — source for churn / CLV / shared features.
    Fields the ML models aggregate:
        customer_number
        local_amount (transaction amount)
        bus_date / posting_date (transaction date)
        tran_type / tran_code (credit / debit indicator)
    """
    logger.info("=" * 60)
    logger.info("TABLE 4/5: a_brains_trans_zam_base_entries_zm")
    logger.info("=" * 60)

    sql = """
        SELECT
            customer_number,
            account_number,
            local_amount,
            bus_date,
            posting_date,
            tran_type,
            tran_code,
            description,
            africa_country_code
        FROM a_brains_trans_zam_base_entries_zm
        WHERE customer_number IS NOT NULL
    """
    df = _query(extractor, sql.strip(), limit)
    out = OUT_DIR / "transactions.csv"
    df.to_csv(out, index=False)
    logger.info("Saved %d rows -> %s", len(df), out)
    print(df.to_string(index=False))


def sample_daily_accounts(extractor, limit: int) -> None:
    """
    Table: A_BRAINS_TRANS_ZAM_BASE_Daily_accounts_ALL
    Purpose: Daily account snapshots — source for balance / CLV / lifecycle features.
    Fields the ML models use:
        customer_number, account_number
        local_balance, effective_debit_limit
        current_status, date_opened
        market_segment, branch_number
    """
    logger.info("=" * 60)
    logger.info("TABLE 5/5: A_BRAINS_TRANS_ZAM_BASE_Daily_accounts_ALL")
    logger.info("=" * 60)

    sql = """
        SELECT
            customer_number,
            account_number,
            account_type,
            local_balance,
            effective_debit_limit,
            current_status,
            date_opened,
            market_segment,
            branch_number,
            africa_country_code,
            short_name,
            accrued_cr_interest,
            accrued_dr_interest
        FROM A_BRAINS_TRANS_ZAM_BASE_Daily_accounts_ALL
        WHERE customer_number IS NOT NULL
    """
    df = _query(extractor, sql.strip(), limit)
    out = OUT_DIR / "daily_accounts.csv"
    df.to_csv(out, index=False)
    logger.info("Saved %d rows -> %s", len(df), out)
    print(df.to_string(index=False))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Sample 10 rows from each Denodo source table and save as CSV."
    )
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Number of rows to sample per table (default: 10)"
    )
    parser.add_argument(
        "--tables", nargs="+",
        choices=["customers", "employment", "sms", "transactions", "accounts", "all"],
        default=["all"],
        help="Which tables to sample. Default: all"
    )
    args = parser.parse_args()

    run_all = "all" in args.tables
    limit   = args.limit

    logger.info("Connecting to Denodo at %s:%s/%s ...",
                settings.denodo_host, settings.denodo_port, settings.denodo_db)
    extractor = _build_extractor()

    logger.info("Sampling %d rows per table. Output -> %s", limit, OUT_DIR)
    logger.info("")

    if run_all or "customers" in args.tables:
        sample_customers_new(extractor, limit)

    if run_all or "employment" in args.tables:
        sample_customer_employment(extractor, limit)

    if run_all or "sms" in args.tables:
        sample_customer_sms(extractor, limit)

    if run_all or "transactions" in args.tables:
        sample_transactions(extractor, limit)

    if run_all or "accounts" in args.tables:
        sample_daily_accounts(extractor, limit)

    logger.info("")
    logger.info("All done! CSVs saved to: %s", OUT_DIR)


if __name__ == "__main__":
    main()
