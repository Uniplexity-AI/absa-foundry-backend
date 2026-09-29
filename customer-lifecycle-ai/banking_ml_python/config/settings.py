"""
Central configuration for Banking ML Python ETL.

Converted from banking_ml_dbeaver_sql_updated — same business logic,
parameterised queries instead of a persistent ml_etl_params table.

Update SCHEMA, table names, and BUSINESS RULES placeholders as ABSA confirms them.
"""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT_DIR / "sql"
OUTPUT_DIR = ROOT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SCHEMA = "public"

# Source tables (exact names from feature mapping)
TABLES = {
    "customer": "a_africa_zam_base_customer",
    "customer_emp": "a_africa_zam_base_customer_employment_daily_zm",
    "customer_notes": "a_africa_zam_base_customer_notes",
    "customer_new": "a_africa_zam_base_customers_new",
    "txn_entries": "a_brains_trans_zam_base_entries_zm",
    "txn_postings": "a_brains_trans_zam_base_postings_add_dets_a",
    "txn_interest": "a_brains_trans_zam_base_daily_interest_all",
    "txn_today": "a_brains_trans_zam_base_today_ent",
    "txn_fixed": "a_brains_trans_zam_base_fixed_deposits_placings_a",
    "card": "s_caas_sparrow_zam_base_crdrep",
    "card_dl": "dl_sprw_zm_sparrow_zm_crdrep",
    "loans": "ebox_loan_details",
}

FEATURE_HISTORY_MONTHS = 24
CLV_FORWARD_MONTHS = 12
CHURN_SHORT_HORIZON_DAYS = 30
CHURN_HORIZON_DAYS = 90
DORMANCY_THRESHOLD_DAYS = 365
BALANCE_FORWARD_DAYS = 90
LARGE_OUTFLOW_THRESHOLD = 10000  # ZMW; tune later

# BUSINESS RULES – placeholders (update with ABSA confirmed rules later)
BUSINESS_RULES = {
    "credit_transaction_codes": [],
    "debit_transaction_codes": [],
    "atm_transaction_codes": [],
    "atm_terminal_pattern": None,
    "external_transfer_codes": [],
    "external_narrative_keywords": ["RTGS", "SWIFT", "INTERBANK", "TRANSFER TO"],
    "salary_narrative_keywords": ["SALARY", "WAGES", "PAYROLL", "SAL"],
    "salary_min_amount": 500,
    "salary_recurrence_months": 3,
    "churn_inactivity_days": 90,
    "churn_explicit_statuses": ["CLOSED", "INACTIVE", "DORMANT"],
    "large_outflow_threshold": LARGE_OUTFLOW_THRESHOLD,
    "competitor_bank_codes": [],
    "competitor_bank_names": [],
}

MODELS = ["clv", "lifecycle", "churn", "balance"]

GRAIN = {
    "clv": "customer_month",
    "lifecycle": "customer_month",
    "churn": "customer_month",
    "balance": "customer_day",
}
