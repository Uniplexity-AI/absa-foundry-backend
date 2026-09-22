
import sys
sys.path.append('.')
from shared.database.postgres import get_sync_target_engine
conn = get_sync_target_engine().connect().connection
cur = conn.cursor()
try:
    cur.execute('INSERT INTO iam.roles (role_name, description) VALUES (''TEST_ROLE'', ''Test'')')
    conn.commit()
    print('Success')
except Exception as e:
    print('Error:', e)

