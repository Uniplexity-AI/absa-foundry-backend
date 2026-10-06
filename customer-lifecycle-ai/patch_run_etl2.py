import sys

with open('run_etl.py', 'r', encoding='utf-8') as f:
    code = f.read()

target = '''    if ml_path not in sys.path:
        sys.path.insert(0, ml_path)'''

replacement = '''    if ml_path not in sys.path:
        sys.path.insert(0, ml_path)
        
    # MONKEY-PATCH: Make ML extractors connect to Denodo instead of Postgres if requested
    import os
    if "--source-type" in sys.argv and sys.argv[sys.argv.index("--source-type") + 1] == "denodo":
        from shared.config.settings import settings
        import banking_ml_python.config.db as ml_db
        import jaydebeapi
        import jpype
        from contextlib import contextmanager
        
        logger.info("Monkey-patching banking_ml_python to execute against Denodo...")
        
        if not jpype.isJVMStarted():
            cleaned_jh = settings.java_home.replace('"', '').replace('\\\\', '/')
            jvm_path = cleaned_jh + "/bin/server/jvm.dll"
            jpype.startJVM(jvm_path, classpath=[settings.denodo_jar_path])
            
        @contextmanager
        def denodo_get_conn():
            conn_url = f"jdbc:vdb://{settings.denodo_host}:{settings.denodo_port}/{settings.denodo_database}?sslTrustServerCertificate=true"
            conn = jaydebeapi.connect("com.denodo.vdp.jdbc.Driver", conn_url, [settings.denodo_username, settings.denodo_password])
            try:
                yield conn
            finally:
                conn.close()
                
        ml_db.get_conn = denodo_get_conn'''

code = code.replace(target, replacement)
with open('run_etl.py', 'w', encoding='utf-8') as f:
    f.write(code)
