"""Quick verification: run feature pipeline and check results."""
import sys, os

# Ensure project root is on path and .env is found
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_PROJ)
_FE_SVC = os.path.join(_PROJ, "services", "feature-engineering-service")
sys.path.insert(0, _PROJ)
sys.path.insert(0, _FE_SVC)

import psycopg2
from app.pipelines.pipeline import FeaturePipeline
from app.repository.repository import FeatureRepository

repo = FeatureRepository()
pipeline = FeaturePipeline(repo)

print("Running feature pipeline...")
result = pipeline.run()

print(f"Status: {result['status']}")
print(f"Total time: {result['total_duration_seconds']}s")
for stage, data in result["stages"].items():
    dur = data.get("duration_seconds", "?")
    if stage == "phase1":
        print(f"  {stage}: {data.get('customers_processed','?')} customers, {data.get('rows_upserted','?')} upserted, {dur}s")
    else:
        print(f"  {stage}: {data}")

# Verify results
conn = psycopg2.connect(repo._conn_str)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM customer_features")
total = cur.fetchone()[0]
print(f"\nTotal rows in customer_features: {total}")

# Check new columns are populated
cur.execute("""
    SELECT customer_id,
           prof_age_band, prof_primary_branch,
           behav_txn_count_7d, behav_active_days_90d, behav_inactive_days_90d,
           behav_recency_score, behav_frequency_score, behav_diversity_score,
           behav_activity_consistency, engagement_score,
           fin_total_credit_90d, fin_total_debit_90d,
           fin_median_txn_amount_90d, fin_salary_consistency, fin_income_growth,
           chan_mobile_ratio_90d, chan_atm_ratio_90d, chan_branch_ratio_90d,
           chan_digital_adoption_score, chan_channel_entropy
    FROM customer_features
    WHERE as_of_date = CURRENT_DATE
    LIMIT 3
""")
print("\nSample rows (new Phase 2 columns):")
for row in cur.fetchall():
    print(f"  {row[0]}: age_band={row[1]}, branch={row[2]}, txn7d={row[3]}, active90d={row[4]}, engagement={row[11]}, cred90d={row[12]}, growth={row[16]}, digital={row[19]}")

# Count non-NULL for key new features
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE prof_age_band IS NOT NULL) AS age_band,
        COUNT(*) FILTER (WHERE behav_txn_count_7d IS NOT NULL) AS txn7d,
        COUNT(*) FILTER (WHERE engagement_score IS NOT NULL) AS engagement,
        COUNT(*) FILTER (WHERE fin_total_credit_90d IS NOT NULL) AS cred90d,
        COUNT(*) FILTER (WHERE chan_digital_adoption_score IS NOT NULL) AS digital
    FROM customer_features
    WHERE as_of_date = CURRENT_DATE
""")
counts = cur.fetchone()
print(f"\nNon-NULL counts (of {total}):")
print(f"  prof_age_band:         {counts[0]}")
print(f"  behav_txn_count_7d:    {counts[1]}")
print(f"  engagement_score:      {counts[2]}")
print(f"  fin_total_credit_90d:  {counts[3]}")
print(f"  chan_digital_adoption: {counts[4]}")

cur.close()
conn.close()
print("\nDone.")
