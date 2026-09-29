import yaml
import sqlalchemy as sa
from etl.extraction.executor import ExtractionExecutor
from shared.database.postgres import get_sync_engine

engine = get_sync_engine()
meta = sa.MetaData()
executor = ExtractionExecutor(engine, meta, engine_version="2.1")
res = executor.execute("scratch_spec.yaml")
print("RESULT STATUS:", res.status)
print("ROWS EXTRACTED:", res.rows_extracted)
print("ROWS VALID:", res.rows_valid)
print("ERRORS:", res.errors)
if not res.valid_df.empty:
    print(res.valid_df.head(2).to_dict(orient="records"))
