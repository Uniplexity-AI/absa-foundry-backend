-- =============================================================================
-- CLV FEATURES + LABELS (extras only; merged with shared in Python)
-- Parameters: %(snapshot_month)s, %(history_start)s, %(clv_forward_months)s
-- Converted from DBeaver 03_clv_dataset.sql
-- =============================================================================

WITH
params AS (
    SELECT
        CAST(%(snapshot_month)s AS DATE) AS snapshot_month,
        CAST((CAST(%(snapshot_month)s AS DATE) + INTERVAL '1 month' - INTERVAL '1 day') AS DATE) AS snapshot_end,
        CAST(%(history_start)s AS DATE) AS history_start,
        %(clv_forward_months)s::int AS clv_forward_months
),

hist_fees AS (
    SELECT
        customer_number,
        CAST(DATE_TRUNC('month', COALESCE(event_start_date, load_date)) AS DATE) AS fee_month,
        SUM(COALESCE(fee_amt, 0) + COALESCE(insurance_amt, 0)) AS fee_income
    FROM ebox_loan_details
    CROSS JOIN params p
    WHERE COALESCE(event_start_date, load_date) >= p.history_start
      AND COALESCE(event_start_date, load_date) <= p.snapshot_end
    GROUP BY customer_number, DATE_TRUNC('month', COALESCE(event_start_date, load_date))
),

fee_agg AS (
    SELECT
        customer_number,
        SUM(fee_income) FILTER (
            WHERE fee_month > (SELECT snapshot_end FROM params) - INTERVAL '1 month'
              AND fee_month <= (SELECT snapshot_end FROM params)
        ) AS fee_income_m1,
        SUM(fee_income) FILTER (
            WHERE fee_month > (SELECT snapshot_end FROM params) - INTERVAL '12 months'
        ) AS fee_income_12m,
        AVG(fee_income) FILTER (
            WHERE fee_month > (SELECT snapshot_end FROM params) - INTERVAL '12 months'
        ) AS avg_monthly_fee_12m
    FROM hist_fees
    GROUP BY customer_number
),

-- Forward labels (TRAINING): fees after snapshot_end
future_fees AS (
    SELECT
        customer_number,
        SUM(COALESCE(fee_amt, 0) + COALESCE(insurance_amt, 0)) AS future_fee_income
    FROM ebox_loan_details
    CROSS JOIN params p
    WHERE COALESCE(event_start_date, load_date) > p.snapshot_end
      AND COALESCE(event_start_date, load_date) <= p.snapshot_end
           + (p.clv_forward_months || ' months')::interval
    GROUP BY customer_number
),

card_accounts AS (
    SELECT DISTINCT crd_acct_num
    FROM s_caas_sparrow_zam_base_crdrep
    WHERE crd_acct_num IS NOT NULL
),

card_spend AS (
    SELECT
        t.customer_number,
        SUM(ABS(t.local_amount)) AS card_spend_12m
    FROM a_brains_trans_zam_base_entries_zm t
    INNER JOIN card_accounts ca ON ca.crd_acct_num = t.account_number
    CROSS JOIN params p
    WHERE COALESCE(t.bus_date, t.posting_date) > p.snapshot_end - INTERVAL '12 months'
      AND COALESCE(t.bus_date, t.posting_date) <= p.snapshot_end
    GROUP BY t.customer_number
),

product_events AS (
    SELECT
        -- TODO: link card table to customer_number if not direct
        customer_number,
        COUNT(*) FILTER (
            WHERE eff_sta_dte > (SELECT snapshot_end FROM params) - INTERVAL '12 months'
              AND eff_sta_dte <= (SELECT snapshot_end FROM params)
        ) AS num_products_opened_12m,
        COUNT(*) FILTER (
            WHERE eff_end_dte > (SELECT snapshot_end FROM params) - INTERVAL '12 months'
              AND eff_end_dte <= (SELECT snapshot_end FROM params)
        ) AS num_products_closed_12m
    FROM s_caas_sparrow_zam_base_crdrep
    GROUP BY customer_number
),

-- All customers that appear in any CLV-related source (union of keys)
all_keys AS (
    SELECT customer_number FROM fee_agg
    UNION
    SELECT customer_number FROM future_fees
    UNION
    SELECT customer_number FROM card_spend
    UNION
    SELECT customer_number FROM product_events
)

SELECT
    k.customer_number AS customer_id,
    (SELECT snapshot_month FROM params) AS snapshot_month,

    COALESCE(fa.fee_income_m1, 0) AS fee_income_m1,
    COALESCE(fa.fee_income_12m, 0) AS fee_income_12m,
    COALESCE(fa.avg_monthly_fee_12m, 0) AS avg_monthly_fee_12m,
    COALESCE(cs.card_spend_12m, 0) AS card_spend_12m,
    COALESCE(pe.num_products_opened_12m, 0) AS num_products_opened_12m,
    COALESCE(pe.num_products_closed_12m, 0) AS num_products_closed_12m,
    COALESCE(pe.num_products_opened_12m, 0)
        - COALESCE(pe.num_products_closed_12m, 0) AS product_net_12m,

    -- NII placeholder until interest columns mapped
    0::numeric AS nii_m1,
    0::numeric AS avg_monthly_nii_12m,

    -- LABELS (dropped in scoring mode by Python)
    COALESCE(ff.future_fee_income, 0) AS target_fee_income_12m,
    COALESCE(ff.future_fee_income, 0) AS target_clv_12m,
    0::numeric AS target_margin_12m

FROM all_keys k
LEFT JOIN fee_agg fa ON fa.customer_number = k.customer_number
LEFT JOIN card_spend cs ON cs.customer_number = k.customer_number
LEFT JOIN product_events pe ON pe.customer_number = k.customer_number
LEFT JOIN future_fees ff ON ff.customer_number = k.customer_number
;
