"""Run Phase 2 migration — 21 new columns for 4 domains."""
import psycopg2
from shared.config.settings import settings

url = settings.database_target_url
if url.startswith("postgresql+asyncpg://"):
    url = url.replace("postgresql+asyncpg://", "postgresql://")

conn = psycopg2.connect(url)
conn.autocommit = True
cur = conn.cursor()

migrations = [
    # Profile
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS prof_age_band VARCHAR(16)",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS prof_primary_branch VARCHAR(16)",
    # Behaviour
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS behav_txn_count_7d INTEGER",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS behav_active_days_90d INTEGER",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS behav_inactive_days_90d INTEGER",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS behav_recency_score FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS behav_frequency_score FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS behav_diversity_score FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS behav_activity_consistency FLOAT",
    # Financial
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS fin_total_credit_90d FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS fin_total_debit_90d FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS fin_median_txn_amount_90d FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS fin_salary_consistency FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS fin_income_growth FLOAT",
    # Channel
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS chan_mobile_ratio_90d FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS chan_atm_ratio_90d FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS chan_branch_ratio_90d FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS chan_digital_adoption_score FLOAT",
    "ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS chan_channel_entropy FLOAT",
]

for m in migrations:
    try:
        cur.execute(m)
        print(f"OK  {m[20:70]}")
    except Exception as e:
        print(f"ERR {e}")

cur.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'customer_features'")
print(f"\nTotal columns: {cur.fetchone()[0]}")
cur.close()
conn.close()
print("Done.")
