"""Run all generators against 2026-07-27 data."""
import sys, time, os

# Add both project root and feature-engineering-service to path
_PROJ = os.path.dirname(os.path.abspath(__file__))
os.chdir(_PROJ)  # Ensure .env is found
_FE_SVC = os.path.join(_PROJ, "services", "feature-engineering-service")
sys.path.insert(0, _PROJ)
sys.path.insert(0, _FE_SVC)

import psycopg2
from shared.config.settings import settings

from app.features.customer.generator import CustomerProfileGenerator
from app.features.behaviour.generator import BehaviourGenerator
from app.features.financial.generator import FinancialGenerator
from app.features.channel.generator import ChannelGenerator
from app.features.temporal.generator import TemporalGenerator
from app.features.risk.generator import RiskGenerator
from app.features.relationship.generator import RelationshipGenerator

conn = psycopg2.connect(settings.database_target_url_sync)
as_of_date = "2026-07-27"

print(f"Running all generators for as_of_date={as_of_date}")
print("=" * 60)

# Profile
t0 = time.time()
gen = CustomerProfileGenerator(conn)
result = gen.generate(as_of_date)
print(f"Profile:   {result} ({time.time()-t0:.1f}s)")

# Behaviour
t0 = time.time()
gen = BehaviourGenerator(conn)
result = gen.generate(as_of_date)
print(f"Behaviour: {result} ({time.time()-t0:.1f}s)")

# Financial
t0 = time.time()
gen = FinancialGenerator(conn)
result = gen.generate(as_of_date)
print(f"Financial: {result} ({time.time()-t0:.1f}s)")

# Channel
t0 = time.time()
gen = ChannelGenerator(conn)
result = gen.generate(as_of_date)
print(f"Channel:   {result} ({time.time()-t0:.1f}s)")

# Temporal
t0 = time.time()
gen = TemporalGenerator(conn)
result = gen.generate(as_of_date)
print(f"Temporal:  {result} ({time.time()-t0:.1f}s)")

# Risk
t0 = time.time()
gen = RiskGenerator(conn)
result = gen.generate(as_of_date)
print(f"Risk:      {result} ({time.time()-t0:.1f}s)")

# Relationship
t0 = time.time()
gen = RelationshipGenerator(conn)
result = gen.generate(as_of_date)
print(f"Relation:  {result} ({time.time()-t0:.1f}s)")

# Verify
print("\nVerification:")
cur = conn.cursor()
cur.execute("""
    SELECT count(*), count(*) FILTER (WHERE prof_age_band IS NOT NULL),
           count(*) FILTER (WHERE engagement_score IS NOT NULL),
           count(*) FILTER (WHERE fin_total_credit_90d IS NOT NULL),
           count(*) FILTER (WHERE chan_digital_adoption_score IS NOT NULL)
    FROM customer_features WHERE as_of_date = %s::date
""", (as_of_date,))
row = cur.fetchone()
print(f"  Total: {row[0]}, Profile: {row[1]}, Behaviour: {row[2]}, Financial: {row[3]}, Channel: {row[4]}")

conn.close()
print("\nDone!")
