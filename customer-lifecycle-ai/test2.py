import sys, os, pandas as pd
sys.path.insert(0, r'c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai')
from shared.database.postgres import get_sync_target_engine
from sqlalchemy import text
engine = get_sync_target_engine()
with engine.connect() as conn:
    df = pd.read_sql("SELECT * FROM a_africa_zam_base_customer LIMIT 5", conn)
    print(df.dtypes)
    print(df.head())
