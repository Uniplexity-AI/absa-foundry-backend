
import sys, pandas as pd
sys.path.insert(0, r'c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai')
from shared.database.postgres import get_sync_raw_engine
engine = get_sync_raw_engine()
with engine.connect() as conn:
    df = pd.read_sql('SELECT customer_number FROM a_africa_zam_base_customer', conn)
    print(df)

