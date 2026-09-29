-- =============================================================================
-- SHARED FEATURE FOUNDATION
-- Grain: one row per customer × snapshot_month
-- Parameters: %(snapshot_month)s  e.g. '2024-06-01' (first of month)
--             %(history_start)s   e.g. '2022-06-01'
-- Point-in-time: only data <= snapshot_end
-- Converted from DBeaver 02_shared_features.sql
-- =============================================================================

WITH
params AS (
    SELECT
        %(snapshot_month)s::date AS snapshot_month,
        (%(snapshot_month)s::date + INTERVAL '1 month' - INTERVAL '1 day')::date AS snapshot_end,
        %(history_start)s::date AS history_start
),

customer_base AS (
    SELECT
        c.customer_number,
        c.length_years,
        c.length_months,
        COALESCE(c.length_years, 0) * 12 + COALESCE(c.length_months, 0) AS tenure_months,
        cn.sex,
        ce.district_or_region,
        ce.town_or_city,
        ce.country,
        ce.gross_income,
        ce.other_income,
        ce.job_title,
        ce.employment_type,
        ce.employment_status,
        ce.designation,
        ce.nature_of_business,
        cn.market_segment,
        cn.risk_level,
        cn.risk_score,
        cn.credit_rating,
        cn.solicitation_channel,
        COALESCE(cn.current_count, 0) AS current_count,
        COALESCE(cn.savings_count, 0) AS savings_count,
        COALESCE(cn.investment_count, 0) AS investment_count,
        COALESCE(cn.secured_count, 0) AS secured_count,
        COALESCE(cn.unsecured_count, 0) AS unsecured_count,
        COALESCE(cn.trade_or_insurance_count, 0) AS trade_or_insurance_count
    FROM a_africa_zam_base_customer c
    LEFT JOIN a_africa_zam_base_customers_new cn
        ON cn.customer_number = c.customer_number
    LEFT JOIN a_africa_zam_base_customer_employment_daily_zm ce
        ON ce.customer_number = c.customer_number
),

product_depth AS (
    SELECT
        customer_number,
        (current_count + savings_count + investment_count
         + secured_count + unsecured_count + trade_or_insurance_count) AS num_active_products,
        CASE WHEN investment_count > 0 THEN 1 ELSE 0 END AS has_investment
    FROM customer_base
),

txn AS (
    SELECT
        t.customer_number,          -- TODO: confirm column exists; else join via account master
        t.account_number,
        COALESCE(t.bus_date, t.posting_date) AS txn_date,
        t.local_amount,
        t.transaction_code,
        t.process_code,
        t.narrative,
        t.terminal_number,
        t.branch_number,
        t.source_system
    FROM a_brains_trans_zam_base_entries_zm t
    CROSS JOIN params p
    WHERE COALESCE(t.bus_date, t.posting_date) >= p.history_start
      AND COALESCE(t.bus_date, t.posting_date) <= p.snapshot_end
),

rfm AS (
    SELECT
        customer_number,
        MAX(txn_date) AS last_txn_date,
        COUNT(*) FILTER (WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '30 days') AS frequency_30d,
        COUNT(*) FILTER (WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '90 days') AS frequency_90d,
        COUNT(*) FILTER (WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '12 months') AS frequency_12m,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '30 days'), 0) AS monetary_30d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '90 days'), 0) AS monetary_90d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '12 months'), 0) AS monetary_12m,
        COALESCE(MAX(ABS(local_amount)) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '12 months'), 0) AS max_transaction_value_12m,
        COUNT(DISTINCT txn_date) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '30 days') AS active_days_30d,
        COUNT(DISTINCT txn_date) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '90 days') AS active_days_90d
    FROM txn
    WHERE customer_number IS NOT NULL
    GROUP BY customer_number
),

-- Placeholder direction: positive local_amount = credit, negative = debit
-- TODO: replace with real credit/debit transaction_code lists
cashflow AS (
    SELECT
        customer_number,
        COALESCE(SUM(local_amount) FILTER (
            WHERE local_amount > 0
              AND txn_date > (SELECT snapshot_end FROM params) - INTERVAL '30 days'), 0) AS credits_30d,
        COALESCE(SUM(local_amount) FILTER (
            WHERE local_amount > 0
              AND txn_date > (SELECT snapshot_end FROM params) - INTERVAL '90 days'), 0) AS credits_90d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE local_amount < 0
              AND txn_date > (SELECT snapshot_end FROM params) - INTERVAL '30 days'), 0) AS debits_30d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE local_amount < 0
              AND txn_date > (SELECT snapshot_end FROM params) - INTERVAL '90 days'), 0) AS debits_90d
    FROM txn
    WHERE customer_number IS NOT NULL
    GROUP BY customer_number
),

loan_feats AS (
    SELECT
        customer_number,            -- TODO: confirm key on ebox_loan_details
        MAX(net_monthly_sal) AS net_monthly_sal,
        MAX(interest_rate) AS interest_rate,
        MAX(outstanding_mortgage) AS outstanding_mortgage,
        MAX(other_bank_name) AS other_bank_name,
        MAX(other_bank_cde) AS other_bank_cde,
        MAX(campaign_cde) AS campaign_cde,
        MAX(barclaycard_grade) AS barclaycard_grade
    FROM ebox_loan_details
    GROUP BY customer_number
)

SELECT
    cb.customer_number AS customer_id,
    p.snapshot_month,
    p.snapshot_end AS snapshot_date,

    cb.tenure_months,
    cb.sex,
    cb.district_or_region AS geo_region,
    cb.town_or_city,
    cb.country,
    cb.gross_income,
    cb.other_income,
    COALESCE(lf.net_monthly_sal, cb.gross_income) AS income_proxy,
    cb.job_title,
    cb.employment_type,
    cb.employment_status,
    cb.market_segment,
    cb.risk_level,
    cb.risk_score,
    cb.credit_rating,
    lf.barclaycard_grade,
    cb.solicitation_channel,
    lf.campaign_cde AS acquisition_campaign,

    pd.num_active_products,
    pd.has_investment,
    cb.current_count,
    cb.savings_count,
    cb.investment_count,
    cb.secured_count,
    cb.unsecured_count,
    CASE WHEN lf.outstanding_mortgage IS NOT NULL AND lf.outstanding_mortgage > 0
         THEN 1 ELSE 0 END AS has_mortgage,

    CASE WHEN rfm.last_txn_date IS NOT NULL
         THEN (p.snapshot_end - rfm.last_txn_date)
         ELSE NULL END AS recency_days,
    COALESCE(rfm.frequency_30d, 0) AS frequency_30d,
    COALESCE(rfm.frequency_90d, 0) AS frequency_90d,
    COALESCE(rfm.frequency_12m, 0) AS frequency_12m,
    COALESCE(rfm.monetary_30d, 0) AS monetary_30d,
    COALESCE(rfm.monetary_90d, 0) AS monetary_90d,
    COALESCE(rfm.monetary_12m, 0) AS monetary_12m,
    COALESCE(rfm.max_transaction_value_12m, 0) AS max_transaction_value_12m,
    COALESCE(rfm.active_days_30d, 0) AS active_days_30d,
    COALESCE(rfm.active_days_90d, 0) AS active_days_90d,
    CASE WHEN COALESCE(rfm.frequency_12m, 0) > 0
         THEN rfm.monetary_12m / rfm.frequency_12m
         ELSE NULL END AS avg_transaction_value_12m,

    COALESCE(cf.credits_30d, 0) AS credits_30d,
    COALESCE(cf.credits_90d, 0) AS credits_90d,
    COALESCE(cf.debits_30d, 0) AS debits_30d,
    COALESCE(cf.debits_90d, 0) AS debits_90d,
    COALESCE(cf.credits_30d, 0) - COALESCE(cf.debits_30d, 0) AS net_cashflow_30d,
    COALESCE(cf.credits_90d, 0) - COALESCE(cf.debits_90d, 0) AS net_cashflow_90d,
    CASE WHEN COALESCE(cf.debits_90d, 0) > 0
         THEN cf.credits_90d / cf.debits_90d
         ELSE NULL END AS inbound_vs_outbound_ratio_90d,

    lf.interest_rate,
    lf.other_bank_name,
    lf.other_bank_cde

FROM params p
CROSS JOIN customer_base cb
LEFT JOIN product_depth pd ON pd.customer_number = cb.customer_number
LEFT JOIN rfm ON rfm.customer_number = cb.customer_number
LEFT JOIN cashflow cf ON cf.customer_number = cb.customer_number
LEFT JOIN loan_feats lf ON lf.customer_number = cb.customer_number
;
