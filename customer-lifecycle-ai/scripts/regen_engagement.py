"""Regenerate engagement scores with configurable frequency window."""
import os, sys

# Project root setup (mirrors main.py pattern)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

# Override frequency window to 90 days
os.environ["FE_ENGAGEMENT_FREQUENCY_WINDOW_DAYS"] = "90"

from services.feature_engineering_service.app.features.behaviour.generator import BehaviourGenerator
from services.feature_engineering_service.app.config.settings import FeatureConfig
from shared.config.settings import settings
import psycopg2

cfg = FeatureConfig()
print(f"Frequency window: {cfg.engagement_frequency_window_days} days")
print(f"Max frequency txn: {cfg.engagement_max_frequency_txn}")

conn = psycopg2.connect(settings.database_target_url_sync, connect_timeout=10)

gen = BehaviourGenerator(conn, cfg)

for dt in ["2026-07-17", "2026-07-22", "2026-07-27"]:
    result = gen.generate(dt)
    print(f"  {dt}: {result}")

conn.close()

# Verify
conn2 = psycopg2.connect(settings.database_target_url_sync, connect_timeout=10)
cur = conn2.cursor()
cur.execute("""
    SELECT
        CASE WHEN engagement_score IS NULL THEN 'NULL'
             WHEN engagement_score = 0 THEN 'Zero'
             WHEN engagement_score < 20 THEN '1-19'
             WHEN engagement_score < 40 THEN '20-39'
             WHEN engagement_score < 60 THEN '40-59'
             ELSE '60+'
        END AS bucket,
        COUNT(*) AS n
    FROM customer_features WHERE as_of_date='2026-07-27'
    GROUP BY 1 ORDER BY 1
""")
print("\nengagement_score distribution after fix (2026-07-27):")
for row in cur.fetchall():
    print(f"  {row[0]:>8s}: {row[1]:5d}")

cur.execute("SELECT AVG(behav_frequency_score) FROM customer_features WHERE as_of_date='2026-07-27' AND txn_count_90d > 0")
avg = cur.fetchone()[0]
print(f"\nAverage frequency_score (active customers): {avg:.1f}")

conn2.close()
print("\nDone!")
