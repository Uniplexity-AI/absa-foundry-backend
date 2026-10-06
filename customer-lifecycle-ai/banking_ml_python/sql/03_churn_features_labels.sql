-- =============================================================================
-- CHURN / DORMANCY FEATURES + LABELS (extras; merged with shared in Python)
--
-- Label definition (updated from DBeaver 04_churn_dataset.sql):
--   DORMANT = >= dormancy_threshold_days consecutive days without qualifying activity.
--   churn_30d / churn_90d = 1 if the customer reaches that threshold within the
--   forward window (inactivity clock + future transaction resets).
--   Already-dormant at snapshot → label 0 (prospective prediction only).
--
-- Parameters:
--   %(snapshot_month)s, %(history_start)s,
--   %(churn_short_horizon_days)s, %(churn_horizon_days)s,
--   %(dormancy_threshold_days)s, %(large_outflow_threshold)s
-- =============================================================================

WITH
params AS (
    SELECT
        CAST(%(snapshot_month)s AS DATE) AS snapshot_month,
        CAST((CAST(%(snapshot_month)s AS DATE) + INTERVAL '1 month' - INTERVAL '1 day') AS DATE) AS snapshot_end,
        CAST(%(history_start)s AS DATE) AS history_start,
        %(churn_short_horizon_days)s::int AS churn_short_horizon_days,
        %(churn_horizon_days)s::int AS churn_horizon_days,
        %(dormancy_threshold_days)s::int AS dormancy_threshold_days,
        %(large_outflow_threshold)s::numeric AS large_outflow_threshold
),

-- History + forward window for volume features and dormancy gaps
txn AS (
    SELECT
        customer_number,
        CAST(COALESCE(bus_date, posting_date) AS DATE) AS txn_date,
        local_amount,
        transaction_code,
        narrative
    FROM a_brains_trans_zam_base_entries_zm
    CROSS JOIN params p
    WHERE CAST(COALESCE(bus_date, posting_date) AS DATE) >= p.history_start
      AND CAST(COALESCE(bus_date, posting_date) AS DATE) <= p.snapshot_end
          + CAST((p.churn_horizon_days || ' days') AS INTERVAL)
),

-- Recency at snapshot (independent of shared table so labels are self-contained)
recency AS (
    SELECT
        customer_number,
        MAX(txn_date) AS last_txn_date,
        CASE
            WHEN MAX(txn_date) IS NOT NULL
            THEN ((SELECT snapshot_end FROM params) - MAX(txn_date))
            ELSE NULL
        END AS recency_days
    FROM txn
    WHERE customer_number IS NOT NULL
      AND txn_date <= (SELECT snapshot_end FROM params)
    GROUP BY customer_number
),

vol AS (
    SELECT
        customer_number,
        COUNT(*) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '30 days'
              AND txn_date <= (SELECT snapshot_end FROM params)) AS txn_count_30d,
        COUNT(*) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '90 days'
              AND txn_date <= (SELECT snapshot_end FROM params)) AS txn_count_90d,
        COUNT(*) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '180 days'
              AND txn_date <= (SELECT snapshot_end FROM params)) AS txn_count_180d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '30 days'
              AND txn_date <= (SELECT snapshot_end FROM params)), 0) AS vol_30d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '90 days'
              AND txn_date <= (SELECT snapshot_end FROM params)), 0) AS vol_90d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '180 days'
              AND txn_date <= (SELECT snapshot_end FROM params)), 0) AS vol_180d,
        COUNT(*) FILTER (
            WHERE txn_date > (SELECT snapshot_end FROM params) - INTERVAL '180 days'
              AND txn_date <= (SELECT snapshot_end FROM params) - INTERVAL '90 days'
        ) AS txn_count_prev_90d
    FROM txn
    WHERE customer_number IS NOT NULL
      AND txn_date <= (SELECT snapshot_end FROM params)
    GROUP BY customer_number
),

large_out AS (
    SELECT
        customer_number,
        COUNT(*) FILTER (
            WHERE local_amount < 0
              AND ABS(local_amount) >= (SELECT large_outflow_threshold FROM params)
              AND txn_date > (SELECT snapshot_end FROM params) - INTERVAL '30 days'
              AND txn_date <= (SELECT snapshot_end FROM params)
        ) AS large_outflow_count_30d,
        COALESCE(SUM(ABS(local_amount)) FILTER (
            WHERE local_amount < 0
              AND ABS(local_amount) >= (SELECT large_outflow_threshold FROM params)
              AND txn_date > (SELECT snapshot_end FROM params) - INTERVAL '30 days'
              AND txn_date <= (SELECT snapshot_end FROM params)
        ), 0) AS large_outflow_amount_30d
    FROM txn
    WHERE txn_date <= (SELECT snapshot_end FROM params)
    GROUP BY customer_number
),

future_txns AS (
    SELECT
        t.customer_number,
        t.txn_date,
        ROW_NUMBER() OVER (
            PARTITION BY t.customer_number
            ORDER BY t.txn_date
        ) AS txn_seq
    FROM txn t
    CROSS JOIN params p
    WHERE t.customer_number IS NOT NULL
      AND t.txn_date > p.snapshot_end
      AND t.txn_date <= p.snapshot_end + CAST((p.churn_horizon_days || ' days') AS INTERVAL)
),

future_gaps AS (
    SELECT
        r.customer_number,
        r.recency_days,
        p.snapshot_end,
        (p.snapshot_end + CAST((p.churn_short_horizon_days || ' days') AS INTERVAL))::date AS horizon_30_end,
        (p.snapshot_end + CAST((p.churn_horizon_days || ' days') AS INTERVAL))::date AS horizon_90_end,

        MIN(ft.txn_date) FILTER (
            WHERE ft.txn_date <= (p.snapshot_end + CAST((p.churn_short_horizon_days || ' days') AS INTERVAL))::date
        ) AS first_future_txn_30d,
        MIN(ft.txn_date) FILTER (
            WHERE ft.txn_date <= (p.snapshot_end + CAST((p.churn_horizon_days || ' days') AS INTERVAL))::date
        ) AS first_future_txn_90d,

        MAX(ft.txn_date) FILTER (
            WHERE ft.txn_date <= (p.snapshot_end + CAST((p.churn_short_horizon_days || ' days') AS INTERVAL))::date
        ) AS last_future_txn_30d,
        MAX(ft.txn_date) FILTER (
            WHERE ft.txn_date <= (p.snapshot_end + CAST((p.churn_horizon_days || ' days') AS INTERVAL))::date
        ) AS last_future_txn_90d
    FROM recency r
    CROSS JOIN params p
    LEFT JOIN future_txns ft ON ft.customer_number = r.customer_number
    GROUP BY
        r.customer_number,
        r.recency_days,
        p.snapshot_end,
        p.churn_short_horizon_days,
        p.churn_horizon_days
),

dormancy_labels AS (
    SELECT
        fg.customer_number,
        fg.recency_days,

        CASE
            WHEN fg.recency_days IS NULL THEN 0
            WHEN fg.recency_days >= (SELECT dormancy_threshold_days FROM params) THEN 0
            WHEN fg.recency_days +
                 COALESCE(
                     (fg.first_future_txn_30d - fg.snapshot_end),
                     (SELECT churn_short_horizon_days FROM params)
                 ) >= (SELECT dormancy_threshold_days FROM params)
            THEN 1
            WHEN fg.last_future_txn_30d IS NOT NULL
             AND (fg.horizon_30_end - fg.last_future_txn_30d) >= (SELECT dormancy_threshold_days FROM params)
            THEN 1
            ELSE 0
        END AS dormancy_30d,

        CASE
            WHEN fg.recency_days IS NULL THEN 0
            WHEN fg.recency_days >= (SELECT dormancy_threshold_days FROM params) THEN 0
            WHEN fg.recency_days +
                 COALESCE(
                     (fg.first_future_txn_90d - fg.snapshot_end),
                     (SELECT churn_horizon_days FROM params)
                 ) >= (SELECT dormancy_threshold_days FROM params)
            THEN 1
            WHEN fg.last_future_txn_90d IS NOT NULL
             AND (fg.horizon_90_end - fg.last_future_txn_90d) >= (SELECT dormancy_threshold_days FROM params)
            THEN 1
            ELSE 0
        END AS dormancy_90d
    FROM future_gaps fg
),

future_activity AS (
    SELECT
        customer_number,
        COUNT(*) AS future_txn_count
    FROM txn
    CROSS JOIN params p
    WHERE txn_date > p.snapshot_end
      AND txn_date <= p.snapshot_end + CAST((p.churn_horizon_days || ' days') AS INTERVAL)
    GROUP BY customer_number
),

all_keys AS (
    SELECT customer_number FROM vol
    UNION
    SELECT customer_number FROM large_out
    UNION
    SELECT customer_number FROM recency
    UNION
    SELECT customer_number FROM dormancy_labels
    UNION
    SELECT customer_number FROM future_activity
)

SELECT
    k.customer_number AS customer_id,

    COALESCE(v.txn_count_30d, 0) AS txn_count_30d,
    COALESCE(v.txn_count_90d, 0) AS txn_count_90d,
    COALESCE(v.txn_count_180d, 0) AS txn_count_180d,
    COALESCE(v.vol_30d, 0) AS vol_30d,
    COALESCE(v.vol_90d, 0) AS vol_90d,
    COALESCE(v.vol_180d, 0) AS vol_180d,
    CASE WHEN COALESCE(v.vol_180d, 0) > 0
         THEN v.vol_30d / v.vol_180d
         ELSE NULL END AS vol_ratio_30_180,
    CASE WHEN COALESCE(v.vol_90d, 0) > 0
         THEN v.vol_30d / v.vol_90d
         ELSE NULL END AS vol_ratio_30_90,
    CASE WHEN COALESCE(v.txn_count_prev_90d, 0) > 0
         THEN (v.txn_count_90d - v.txn_count_prev_90d)::numeric / v.txn_count_prev_90d
         ELSE NULL END AS txn_count_change_pct_90d,

    COALESCE(lo.large_outflow_count_30d, 0) AS large_outflow_count_30d,
    COALESCE(lo.large_outflow_amount_30d, 0) AS large_outflow_amount_30d,

    -- Operational: how close to the 365-day threshold at snapshot
    CASE
        WHEN r.recency_days IS NULL THEN NULL
        WHEN r.recency_days >= (SELECT dormancy_threshold_days FROM params) THEN 0
        ELSE (SELECT dormancy_threshold_days FROM params) - r.recency_days
    END AS days_to_dormancy,

    CASE
        WHEN r.recency_days IS NULL THEN 'UNKNOWN'
        WHEN r.recency_days < 60 THEN 'ACTIVE'
        WHEN r.recency_days < 90 THEN 'EARLY_WARNING'
        WHEN r.recency_days < 180 THEN 'INACTIVE'
        WHEN r.recency_days < (SELECT dormancy_threshold_days FROM params) THEN 'PRE_DORMANT'
        ELSE 'DORMANT'
    END AS lifecycle_status_at_snapshot,

    COALESCE(fa.future_txn_count, 0) AS future_txn_count_90d,

    -- SUPERVISED LABELS (dropped in scoring mode by Python)
    CASE
        WHEN r.recency_days IS NOT NULL
         AND r.recency_days < (SELECT dormancy_threshold_days FROM params)
        THEN dl.dormancy_30d
        ELSE 0
    END AS churn_30d,

    CASE
        WHEN r.recency_days IS NOT NULL
         AND r.recency_days < (SELECT dormancy_threshold_days FROM params)
        THEN dl.dormancy_90d
        ELSE 0
    END AS churn_90d

    -- TODO: OR explicit account-closure events into both labels when status source is confirmed

FROM all_keys k
LEFT JOIN vol v ON v.customer_number = k.customer_number
LEFT JOIN large_out lo ON lo.customer_number = k.customer_number
LEFT JOIN recency r ON r.customer_number = k.customer_number
LEFT JOIN future_activity fa ON fa.customer_number = k.customer_number
LEFT JOIN dormancy_labels dl ON dl.customer_number = k.customer_number
;
