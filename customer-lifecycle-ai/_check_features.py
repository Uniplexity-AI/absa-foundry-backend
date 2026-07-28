"""List customer_features columns and check populated features."""
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

import psycopg2
from shared.config.settings import settings

conn = psycopg2.connect(settings.database_target_url_sync)
cur = conn.cursor()

# List columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='customer_features' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print(f"Columns ({len(cols)}):")
for c in cols:
    print(f"  {c}")

# Check feature population for 2026-07-27
print("\nFeature population for 2026-07-27 (5000 rows):")
checks = [
    "customer_segment", "customer_tenure_days", "age_years",
    "onboarding_channel", "prof_primary_branch", "prof_age_band",
    "behav_txn_count_7d", "behav_active_days_90d", "behav_inactive_days_90d",
    "behav_activity_consistency", "behav_recency_score", "behav_frequency_score",
    "behav_diversity_score", "engagement_score",
    "txn_frequency_trend", "inactivity_streak_days",
    "fin_total_credit_90d", "fin_total_debit_90d", "fin_median_txn_amount_90d",
    "fin_salary_consistency", "fin_income_growth",
    "chan_mobile_ratio_90d", "chan_atm_ratio_90d", "chan_branch_ratio_90d",
    "chan_digital_adoption_score", "chan_channel_entropy",
]
for col in checks:
    if col in cols:
        cur.execute(f"SELECT count(*) FILTER (WHERE {col} IS NOT NULL) FROM customer_features WHERE as_of_date='2026-07-27'")
        cnt = cur.fetchone()[0]
        print(f"  {col}: {cnt}/5000")
    else:
        print(f"  {col}: COLUMN MISSING")

conn.close()

# Check feature population for 2026-07-27
print("\nFeature population for 2026-07-27 (5000 rows):")
checks = [
    "customer_segment", "customer_tenure_days", "age_years",
    "onboarding_channel", "prof_primary_branch", "prof_age_band",
    "behav_txn_count_7d", "behav_active_days_90d", "behav_inactive_days_90d",
    "behav_activity_consistency", "behav_recency_score", "behav_frequency_score",
    "behav_diversity_score", "engagement_score",
    "fin_total_credit_90d", "fin_total_debit_90d", "fin_median_txn_amount_90d",
    "fin_salary_consistency", "fin_income_growth",
    "chan_mobile_ratio_90d", "chan_atm_ratio_90d", "chan_branch_ratio_90d",
    "chan_digital_adoption_score", "chan_channel_entropy",
]
for col in checks:
    if col in cols:
        cur.execute(f"SELECT count(*) FILTER (WHERE {col} IS NOT NULL) FROM customer_features WHERE as_of_date='2026-07-27'")
        cnt = cur.fetchone()[0]
        print(f"  {col}: {cnt}/5000")
    else:
        print(f"  {col}: COLUMN MISSING")

conn.close()
