-- =============================================================================
-- LIFECYCLE FEATURES (extras; merged with shared in Python)
-- Parameters: %(snapshot_month)s, %(history_start)s
-- Converted from DBeaver 05_lifecycle_dataset.sql
-- =============================================================================

WITH
params AS (
    SELECT
        %(snapshot_month)s::date AS snapshot_month,
        (%(snapshot_month)s::date + INTERVAL '1 month' - INTERVAL '1 day')::date AS snapshot_end,
        %(history_start)s::date AS history_start
),

txn AS (
    SELECT
        customer_number,
        COALESCE(bus_date, posting_date) AS txn_date,
        local_amount,
        narrative
    FROM a_brains_trans_zam_base_entries_zm
    CROSS JOIN params p
    WHERE COALESCE(bus_date, posting_date) >= p.history_start
      AND COALESCE(bus_date, posting_date) <= p.snapshot_end
),

salary AS (
    SELECT
        customer_number,
        COUNT(DISTINCT DATE_TRUNC('month', txn_date)) FILTER (
            WHERE local_amount > 500
              AND (
                    UPPER(COALESCE(narrative, '')) LIKE '%%SALARY%%'
                 OR UPPER(COALESCE(narrative, '')) LIKE '%%WAGES%%'
                 OR UPPER(COALESCE(narrative, '')) LIKE '%%PAYROLL%%'
              )
              AND txn_date > (SELECT snapshot_end FROM params) - INTERVAL '6 months'
        ) AS salary_months_6m,
        MAX(CASE
                WHEN local_amount > 500
                 AND (
                       UPPER(COALESCE(narrative, '')) LIKE '%%SALARY%%'
                    OR UPPER(COALESCE(narrative, '')) LIKE '%%WAGES%%'
                 ) THEN 1 ELSE 0
            END) AS direct_deposit_flag
    FROM txn
    GROUP BY customer_number
),

activity_change AS (
    SELECT
        customer_number,
        COUNT(*) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '90 days'
        ) AS txn_90d,
        COUNT(*) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '180 days'
              AND txn_date <= (SELECT snapshot_end FROM params) - INTERVAL '90 days'
        ) AS txn_prev_90d
    FROM txn
    GROUP BY customer_number
),

all_keys AS (
    SELECT customer_number FROM salary
    UNION
    SELECT customer_number FROM activity_change
)

SELECT
    k.customer_number AS customer_id,

    COALESCE(sal.direct_deposit_flag, 0) AS direct_deposit_flag,
    CASE WHEN COALESCE(sal.salary_months_6m, 0) >= 3 THEN 1 ELSE 0 END AS direct_deposit_consistency_flag,
    COALESCE(sal.salary_months_6m, 0) / 6.0 AS direct_deposit_consistency_index,

    CASE WHEN COALESCE(ac.txn_prev_90d, 0) > 0
         THEN (ac.txn_90d - ac.txn_prev_90d)::numeric / ac.txn_prev_90d
         ELSE NULL END AS activity_change_pct_90d,

    -- Wallet-share placeholders until external transfer codes confirmed
    NULL::numeric AS external_outflow_ratio_90d,
    NULL::numeric AS competitor_transfer_count_90d,
    NULL::numeric AS competitor_transfer_amount_90d

FROM all_keys k
LEFT JOIN salary sal ON sal.customer_number = k.customer_number
LEFT JOIN activity_change ac ON ac.customer_number = k.customer_number
;
