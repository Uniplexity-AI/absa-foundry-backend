import sys
import os

with open('run_etl.py', 'r', encoding='utf-8') as f:
    code = f.read()

target = '''    if ml_path not in sys.path:
        sys.path.insert(0, ml_path)'''

replacement = '''    if ml_path not in sys.path:
        sys.path.insert(0, ml_path)
        
    # MONKEY-PATCH: Make ML extractors connect to Denodo if requested
    import os
    if "--source-type" in sys.argv and sys.argv[sys.argv.index("--source-type") + 1] == "denodo":
        from shared.config.settings import settings
        import banking_ml_python.config.db as ml_db
        import jaydebeapi
        import jpype
        import re
        import pandas as pd
        
        logger.info("Monkey-patching banking_ml_python to execute against Denodo...")
        
        if not jpype.isJVMStarted():
            cleaned_jh = settings.java_home.replace('"', '').replace('\\\\', '/')
            jvm_path = cleaned_jh + "/bin/server/jvm.dll"
            os.environ["PATH"] = cleaned_jh + "/bin;" + os.environ.get("PATH", "")
            jpype.startJVM(jvm_path, classpath=[settings.denodo_jar_path])
            
        def denodo_read_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
            conn_url = f"jdbc:vdb://{settings.denodo_host}:{settings.denodo_port}/{settings.denodo_database}?sslTrustServerCertificate=true"
            conn = jaydebeapi.connect("com.denodo.vdp.jdbc.Driver", conn_url, [settings.denodo_username, settings.denodo_password])
            try:
                param_list = []
                if params:
                    def replacer(m):
                        param_list.append(params[m.group(1)])
                        return '?'
                    sql = re.sub(r'%\(([a-zA-Z0-9_]+)\)s', replacer, sql)
                
                # We can't easily do cursor.fetchall() to a dataframe if it's huge, but read_sql does it.
                # However pd.read_sql expects a DBAPI connection, and jaydebeapi is one!
                # Wait, pd.read_sql requires standard DBAPI fetchall. JayDeBeApi cursor supports fetchall.
                
                cursor = conn.cursor()
                cursor.execute(sql, param_list)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                df = pd.DataFrame(rows, columns=columns)
                cursor.close()
                return df
            finally:
                conn.close()
                
        ml_db.read_sql = denodo_read_sql'''

if 'denodo_read_sql' not in code:
    code = code.replace(target, replacement)
    with open('run_etl.py', 'w', encoding='utf-8') as f:
        f.write(code)
