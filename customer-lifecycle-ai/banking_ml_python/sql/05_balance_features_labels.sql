-- =============================================================================
-- BALANCE FORECAST FEATURES + LABELS
-- Parameters: %(as_of_date)s, %(history_start)s,
--             %(balance_forward_days)s, %(large_outflow_threshold)s
-- Converted from DBeaver 06_balance_dataset.sql
-- Balance lags / DAB targets remain NULL until an EOD balance table exists.
-- =============================================================================

WITH
params AS (
    SELECT
        %(as_of_date)s::date AS as_of_date,
        %(history_start)s::date AS history_start,
        %(balance_forward_days)s::int AS balance_forward_days,
        %(large_outflow_threshold)s::numeric AS large_outflow_threshold
),

txn AS (
    SELECT
        customer_number,
        account_number,
        COALESCE(bus_date, posting_date) AS txn_date,
        local_amount
    FROM a_brains_trans_zam_base_entries_zm
    CROSS JOIN params p
    WHERE COALESCE(bus_date, posting_date) >= p.history_start
      AND COALESCE(bus_date, posting_date) <= p.as_of_date
           + (p.balance_forward_days || ' days')::interval
),

cashflow AS (
    SELECT
        customer_number,
        COALESCE(SUM(local_amount) FILTER (
            WHERE local_amount > 0
              AND txn_date > (SELECT as_of_date FROM params) - INTERVAL '7 days'
              AND txn_date <= (SELECT as_of_date FROM params)), 0) AS credits_7d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE local_amount < 0
              AND txn_date > (SELECT as_of_date FROM params) - INTERVAL '7 days'
              AND txn_date <= (SELECT as_of_date FROM params)), 0) AS debits_7d,
        COALESCE(SUM(local_amount) FILTER (
            WHERE local_amount > 0
              AND txn_date > (SELECT as_of_date FROM params) - INTERVAL '30 days'
              AND txn_date <= (SELECT as_of_date FROM params)), 0) AS credits_30d,
        COALESCE(SUM(local_amount) FILTER (
            WHERE local_amount > 0
              AND txn_date > (SELECT as_of_date FROM params) - INTERVAL '90 days'
              AND txn_date <= (SELECT as_of_date FROM params)), 0) AS credits_90d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE local_amount < 0
              AND txn_date > (SELECT as_of_date FROM params) - INTERVAL '30 days'
              AND txn_date <= (SELECT as_of_date FROM params)), 0) AS debits_30d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE local_amount < 0
              AND txn_date > (SELECT as_of_date FROM params) - INTERVAL '90 days'
              AND txn_date <= (SELECT as_of_date FROM params)), 0) AS debits_90d,
        COUNT(*) FILTER (
            WHERE local_amount > 0 AND ABS(local_amount) >= (SELECT large_outflow_threshold FROM params)
              AND txn_date > (SELECT as_of_date FROM params) - INTERVAL '30 days'
              AND txn_date <= (SELECT as_of_date FROM params)
        ) AS large_inflow_count_30d,
        COUNT(*) FILTER (
            WHERE local_amount < 0 AND ABS(local_amount) >= (SELECT large_outflow_threshold FROM params)
              AND txn_date > (SELECT as_of_date FROM params) - INTERVAL '30 days'
              AND txn_date <= (SELECT as_of_date FROM params)
        ) AS large_outflow_count_30d
    FROM txn
    WHERE customer_number IS NOT NULL
      AND txn_date <= (SELECT as_of_date FROM params)
    GROUP BY customer_number
),

calendar AS (
    SELECT
        as_of_date,
        EXTRACT(DAY FROM as_of_date)::int AS day_of_month,
        EXTRACT(DOW FROM as_of_date)::int AS day_of_week,
        EXTRACT(MONTH FROM as_of_date)::int AS month_of_year,
        CASE WHEN EXTRACT(DAY FROM (as_of_date + INTERVAL '1 day')) = 1 THEN 1 ELSE 0 END AS is_month_end,
        CASE WHEN EXTRACT(DAY FROM as_of_date) = 1 THEN 1 ELSE 0 END AS is_month_start,
        SIN(2 * PI() * EXTRACT(DAY FROM as_of_date) / 31.0) AS sin_day_of_month,
        COS(2 * PI() * EXTRACT(DAY FROM as_of_date) / 31.0) AS cos_day_of_month,
        SIN(2 * PI() * EXTRACT(MONTH FROM as_of_date) / 12.0) AS sin_month_of_year,
        COS(2 * PI() * EXTRACT(MONTH FROM as_of_date) / 12.0) AS cos_month_of_year
    FROM params
)

SELECT
    cf.customer_number AS customer_id,
    p.as_of_date,

    cf.credits_7d,
    cf.debits_7d,
    cf.credits_7d - cf.debits_7d AS net_cashflow_7d,
    cf.credits_30d,
    cf.credits_90d,
    cf.debits_30d,
    cf.debits_90d,
    cf.credits_30d - cf.debits_30d AS net_cashflow_30d,
    cf.credits_90d - cf.debits_90d AS net_cashflow_90d,
    cf.large_inflow_count_30d,
    cf.large_outflow_count_30d,

    cal.day_of_month,
    cal.day_of_week,
    cal.month_of_year,
    cal.is_month_end,
    cal.is_month_start,
    cal.sin_day_of_month,
    cal.cos_day_of_month,
    cal.sin_month_of_year,
    cal.cos_month_of_year,

    -- Placeholders until EOD balance table exists
    NULL::numeric AS balance_t,
    NULL::numeric AS balance_t_minus_30,
    NULL::numeric AS ma_30d,
    NULL::numeric AS std_30d,

    -- LABELS (dropped in scoring mode by Python)
    NULL::numeric AS target_dab_30d,
    NULL::numeric AS target_dab_60d,
    NULL::numeric AS target_dab_90d

FROM params p
JOIN cashflow cf ON TRUE
CROSS JOIN calendar cal
;
