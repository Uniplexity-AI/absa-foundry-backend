"""Run financial + channel generators."""
import sys, os, time
_PROJ = r"c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai"
os.chdir(_PROJ)  # Ensure .env is found
_FE_SVC = os.path.join(_PROJ, "services", "feature-engineering-service")
sys.path.insert(0, _PROJ)
sys.path.insert(0, _FE_SVC)

import psycopg2
from shared.config.settings import settings
from app.features.financial.generator import FinancialGenerator
from app.features.channel.generator import ChannelGenerator

conn = psycopg2.connect(settings.database_target_url_sync)

print("Financial generator...")
t0 = time.time()
gen = FinancialGenerator(conn)
r = gen.generate("2026-07-27")
print(f"  {r} ({time.time()-t0:.1f}s)")

print("Channel generator...")
t0 = time.time()
gen = ChannelGenerator(conn)
r = gen.generate("2026-07-27")
print(f"  {r} ({time.time()-t0:.1f}s)")

print("\nVerification:")
cur = conn.cursor()
for col in ["fin_total_credit_90d", "fin_total_debit_90d", "fin_median_txn_amount_90d",
            "fin_salary_consistency", "fin_income_growth",
            "chan_mobile_ratio_90d", "chan_atm_ratio_90d", "chan_branch_ratio_90d",
            "chan_digital_adoption_score", "chan_channel_entropy"]:
    cur.execute(f"SELECT count(*) FILTER (WHERE {col} IS NOT NULL) FROM customer_features WHERE as_of_date='2026-07-27'")
    print(f"  {col}: {cur.fetchone()[0]}/5000")

conn.close()
print("Done!")
