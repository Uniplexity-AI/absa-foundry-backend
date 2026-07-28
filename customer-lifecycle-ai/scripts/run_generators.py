"""Run only Phase 2 generators (Phase 1 data already exists)."""
import sys, os

# Ensure project root is on path and .env is found
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_PROJ)
_FE_SVC = os.path.join(_PROJ, "services", "feature-engineering-service")
sys.path.insert(0, _PROJ)
sys.path.insert(0, _FE_SVC)

import psycopg2
from datetime import date
from app.repository.repository import FeatureRepository
from app.features.customer.generator import CustomerProfileGenerator
from app.features.behaviour.generator import BehaviourGenerator
from app.features.financial.generator import FinancialGenerator
from app.features.channel.generator import ChannelGenerator

repo = FeatureRepository()
conn = psycopg2.connect(repo._conn_str)
today = date.today()

gen_order = [
    ("profile", CustomerProfileGenerator(conn)),
    ("behaviour", BehaviourGenerator(conn)),
    ("financial", FinancialGenerator(conn)),
    ("channel", ChannelGenerator(conn)),
]

for name, gen in gen_order:
    print(f"Running {name}...", end=" ", flush=True)
    result = gen.generate(today)
    print(result)

conn.close()

# Verify
conn2 = psycopg2.connect(repo._conn_str)
cur = conn2.cursor()
cur.execute("""
    SELECT COUNT(*),
           COUNT(*) FILTER (WHERE prof_age_band IS NOT NULL) AS age_band,
           COUNT(*) FILTER (WHERE behav_txn_count_7d IS NOT NULL) AS txn7d,
           COUNT(*) FILTER (WHERE engagement_score IS NOT NULL) AS engagement,
           COUNT(*) FILTER (WHERE fin_total_credit_90d IS NOT NULL) AS cred90d,
           COUNT(*) FILTER (WHERE chan_digital_adoption_score IS NOT NULL) AS digital
    FROM customer_features WHERE as_of_date = %s
""", (today,))
c = cur.fetchone()
print(f"\nPhase 2 features populated (of {c[0]} rows):")
print(f"  prof_age_band:         {c[1]}")
print(f"  behav_txn_count_7d:    {c[2]}")
print(f"  engagement_score:      {c[3]}")
print(f"  fin_total_credit_90d:  {c[4]}")
print(f"  chan_digital_adoption: {c[5]}")
cur.close()
conn2.close()
print("Done.")
