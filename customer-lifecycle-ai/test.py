import sys, os
sys.path.insert(0, r'c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai')
from shared.database.postgres import get_sync_target_engine
from sqlalchemy import text
engine = get_sync_target_engine()
with engine.connect() as conn:
    print([r[0] + ' ' + r[1] for r in conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'feature_store_shared'")).fetchall()])
