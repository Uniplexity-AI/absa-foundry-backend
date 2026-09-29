-- =============================================================================
-- Synthetic schema for local testing of Banking ML Python ETL
-- Creates only the columns referenced by the feature SQL scripts.
-- Safe to re-run: drops and recreates tables.
-- =============================================================================

DROP TABLE IF EXISTS a_brains_trans_zam_base_entries_zm CASCADE;
DROP TABLE IF EXISTS ebox_loan_details CASCADE;
DROP TABLE IF EXISTS s_caas_sparrow_zam_base_crdrep CASCADE;
DROP TABLE IF EXISTS a_africa_zam_base_customer_employment_daily_zm CASCADE;
DROP TABLE IF EXISTS a_africa_zam_base_customers_new CASCADE;
DROP TABLE IF EXISTS a_africa_zam_base_customer CASCADE;

-- Customer master
CREATE TABLE a_africa_zam_base_customer (
    customer_number   VARCHAR(32) PRIMARY KEY,
    length_years      INTEGER,
    length_months     INTEGER
);

-- Customer attributes / product counts
CREATE TABLE a_africa_zam_base_customers_new (
    customer_number            VARCHAR(32) PRIMARY KEY,
    sex                        VARCHAR(16),
    market_segment             VARCHAR(64),
    risk_level                 VARCHAR(32),
    risk_score                 NUMERIC(10, 2),
    credit_rating              VARCHAR(16),
    solicitation_channel       VARCHAR(64),
    current_count              INTEGER DEFAULT 0,
    savings_count              INTEGER DEFAULT 0,
    investment_count           INTEGER DEFAULT 0,
    secured_count              INTEGER DEFAULT 0,
    unsecured_count            INTEGER DEFAULT 0,
    trade_or_insurance_count   INTEGER DEFAULT 0
);

-- Employment / demographics
CREATE TABLE a_africa_zam_base_customer_employment_daily_zm (
    customer_number      VARCHAR(32) PRIMARY KEY,
    district_or_region   VARCHAR(64),
    town_or_city         VARCHAR(64),
    country              VARCHAR(64),
    gross_income         NUMERIC(14, 2),
    other_income         NUMERIC(14, 2),
    job_title            VARCHAR(128),
    employment_type      VARCHAR(64),
    employment_status    VARCHAR(64),
    designation          VARCHAR(64),
    nature_of_business   VARCHAR(128)
);

-- Transactions (core activity source)
CREATE TABLE a_brains_trans_zam_base_entries_zm (
    id                 BIGSERIAL PRIMARY KEY,
    customer_number    VARCHAR(32),
    account_number     VARCHAR(32),
    bus_date           DATE,
    posting_date       DATE,
    local_amount       NUMERIC(18, 2),
    transaction_code   VARCHAR(32),
    process_code       VARCHAR(32),
    narrative          VARCHAR(256),
    terminal_number    VARCHAR(32),
    branch_number      VARCHAR(32),
    source_system      VARCHAR(32)
);

CREATE INDEX idx_txn_customer_date
    ON a_brains_trans_zam_base_entries_zm (customer_number, bus_date);
CREATE INDEX idx_txn_account
    ON a_brains_trans_zam_base_entries_zm (account_number);

-- Loan / fee source (also used for CLV fees and some demog fields)
CREATE TABLE ebox_loan_details (
    id                    BIGSERIAL PRIMARY KEY,
    customer_number       VARCHAR(32),
    event_start_date      DATE,
    load_date             DATE,
    fee_amt               NUMERIC(14, 2),
    insurance_amt         NUMERIC(14, 2),
    net_monthly_sal       NUMERIC(14, 2),
    interest_rate         NUMERIC(8, 4),
    outstanding_mortgage  NUMERIC(14, 2),
    other_bank_name       VARCHAR(64),
    other_bank_cde        VARCHAR(32),
    campaign_cde          VARCHAR(32),
    barclaycard_grade     VARCHAR(16)
);

CREATE INDEX idx_loan_customer_date
    ON ebox_loan_details (customer_number, event_start_date);

-- Card accounts / product events
CREATE TABLE s_caas_sparrow_zam_base_crdrep (
    id                BIGSERIAL PRIMARY KEY,
    customer_number   VARCHAR(32),
    crd_acct_num      VARCHAR(32),
    eff_sta_dte       DATE,
    eff_end_dte       DATE
);

CREATE INDEX idx_card_customer ON s_caas_sparrow_zam_base_crdrep (customer_number);
CREATE INDEX idx_card_acct ON s_caas_sparrow_zam_base_crdrep (crd_acct_num);

SELECT 'Synthetic schema created OK' AS status;
