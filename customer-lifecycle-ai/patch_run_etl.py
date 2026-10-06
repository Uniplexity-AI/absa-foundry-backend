import sys
import os
import re

with open('run_etl.py', 'r', encoding='utf-8') as f:
    code = f.read()

target = '''        try:
            m_t0 = time.monotonic()
            if model == "shared":
                df = extract_shared(snap_date)
            elif model == "clv":
                df = build_clv(snap_date, mode=mode)
            elif model == "lifecycle":
                df = build_lifecycle(snap_date, mode=mode)
            elif model == "churn":
                df = build_churn(snap_date, mode=mode)
            elif model == "balance":
                df = build_balance(as_of_date, mode=mode)
            else:
                continue'''

replacement = '''        try:
            m_t0 = time.monotonic()
            
            # Retrieve global extractor if running Denodo, or setup a new one
            from etl.extraction.executor import ExtractionExecutor
            from sqlalchemy import MetaData
            global_extractor = globals().get("denodo_extractor", None)
            
            # Setup engine
            source_type_val = sys.argv[sys.argv.index("--source-type") + 1] if "--source-type" in sys.argv else "postgres"
            
            # Initialize executor for the model's YAML spec
            spec_path = f"etl/config/extraction_specs/{model}_features.yaml"
            
            # Note: We should use the same extraction executor logic as the main ETL
            engine_to_use = None if source_type_val == "denodo" else get_sync_engine()
            
            # Setup denodo extractor
            if source_type_val == "denodo" and not global_extractor:
                from etl.extraction.denodo_connector import DenodoStreamingExtractor
                from shared.config.settings import settings
                global_extractor = DenodoStreamingExtractor(
                    username=settings.denodo_username,
                    password=settings.denodo_password,
                    host=settings.denodo_host,
                    port=settings.denodo_port,
                    database=settings.denodo_database,
                    java_home=settings.java_home,
                    cacerts=settings.cacerts_path,
                    path_jar=settings.denodo_jar_path,
                )
            
            executor = ExtractionExecutor(
                engine=engine_to_use,
                metadata=MetaData(),
                engine_version="2.1",
                denodo_extractor=global_extractor,
            )
            
            # Inject dates into environment or use config overrides
            os.environ["SNAPSHOT_MONTH"] = str(snap_date)
            os.environ["HISTORY_START"] = str(snap_date.replace(year=snap_date.year - 2)) # Approx
            
            res = executor.execute(spec_path)
            if res.status == "FAILED":
                raise RuntimeError(f"Extraction failed for {model}: " + ", ".join(res.errors))
            
            df = res.valid_df'''

code = code.replace(target, replacement)
with open('run_etl.py', 'w', encoding='utf-8') as f:
    f.write(code)
