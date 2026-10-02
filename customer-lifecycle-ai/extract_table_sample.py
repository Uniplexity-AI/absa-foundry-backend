import os
import sys
import csv
import jaydebeapi
import jpype
from dotenv import load_dotenv

load_dotenv()

# The exact table highlighted in your image
TARGET_TABLE = "Aro_emdw_db.A_BRAINS_TRANS_ZAM_BASE_Daily_accounts_ALL"
OUTPUT_FILE = "table_sample.csv"

# DB Config
host = os.getenv("DENODO_HOST", "aus1-prod")
port = os.getenv("DENODO_PORT", "9999")
db = os.getenv("DENODO_DB", "aro_emdw_db")
user = os.getenv("DENODO_USERNAME", "SVC-m1-portal-zm")
password = os.getenv("DENODO_PASSWORD", "yNUT;1Y1VT6=)e")
java_home = os.getenv("JAVA_HOME")

print(f"Connecting to Denodo...")
print(f"Target Table: {TARGET_TABLE}")

try:
    # 1. Start JVM
    base_dir = os.path.dirname(os.path.abspath(__file__))
    jar_path = os.path.join(base_dir, "scripts", "Jar.jar")
    
    if java_home:
        java_home = java_home.replace('"', '').replace('\\', '/')
        os.environ["PATH"] = java_home + "/bin;" + os.environ.get("PATH", "")
        jvm_path = java_home + "/bin/server/jvm.dll"
        if not jpype.isJVMStarted():
            jpype.startJVM(jvm_path, classpath=[jar_path])
    else:
        if not jpype.isJVMStarted():
            jpype.startJVM(jpype.getDefaultJVMPath(), classpath=[jar_path])

    # 2. Connect
    jdbc_url = f"jdbc:vdb://{host}:{port}/{db}?sslTrustServerCertificate=true"
    conn = jaydebeapi.connect("com.denodo.vdp.jdbc.Driver", jdbc_url, [user, password])
    
    cursor = conn.cursor()
    
    # 3. Query 5 rows
    query = f"SELECT * FROM {TARGET_TABLE} LIMIT 5"
    print(f"\nRunning Query: {query}")
    cursor.execute(query)
    
    # 4. Extract data and column names
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    
    # 5. Save to CSV
    with open(OUTPUT_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(columns)  # Write headers
        writer.writerows(rows)    # Write data
        
    print(f"\n✅ SUCCESS!")
    print(f"Saved {len(rows)} rows and {len(columns)} columns to: {OUTPUT_FILE}")
    print(f"\nColumn Names Found:\n{columns}")
    
    cursor.close()
    conn.close()

except Exception as e:
    print(f"\n❌ ERROR: {e}")
