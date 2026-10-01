import os
import jaydebeapi
import jpype
from dotenv import load_dotenv

# 1. Load environment variables from .env
load_dotenv()

host = os.getenv("DENODO_HOST", "aus1-prod")
port = os.getenv("DENODO_PORT", "9999")
db = os.getenv("DENODO_DB", "aro_emdw_db")
user = os.getenv("DENODO_USERNAME", "SVC-m1-portal-zm")
password = os.getenv("DENODO_PASSWORD", "yNUT;1Y1VT6=)e")
java_home = os.getenv("JAVA_HOME")

print("========================================")
print(f"Testing Denodo Connection...")
print(f"Host: {host}")
print(f"Port: {port}")
print(f"User: {user}")
print("========================================\n")

try:
    # 2. Safely start the Java Virtual Machine
    if java_home:
        java_home = java_home.replace('"', '').replace('\\', '/')
        os.environ["PATH"] = java_home + "/bin;" + os.environ.get("PATH", "")
        jvm_path = java_home + "/bin/server/jvm.dll"
        print(f"-> Starting JVM at: {jvm_path}")
        if not jpype.isJVMStarted():
            jpype.startJVM(jvm_path)
    else:
        print("-> JAVA_HOME not set in .env! Attempting default system Java...")
        if not jpype.isJVMStarted():
            jpype.startJVM(jpype.getDefaultJVMPath())

    # 3. Connect to Denodo using the JDBC driver
    jdbc_url = f"jdbc:vdb://{host}:{port}/{db}?sslTrustServerCertificate=true"
    jar_path = "./scripts/Jar.jar"
    driver_class = "com.denodo.vdp.jdbc.Driver"
    
    print(f"-> Connecting to JDBC URL: {jdbc_url}")
    conn = jaydebeapi.connect(
        jclassname=driver_class,
        url=jdbc_url,
        driver_args=[user, password],
        jars=jar_path
    )
    
    # 4. Run a quick ping query
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    print(f"\n✅ SUCCESS! Connected to Hadoop/Denodo perfectly. Response: {result}")
    
    cursor.close()
    conn.close()

except Exception as e:
    print(f"\n❌ FAILED to connect!")
    print(f"Error Details: {e}")
