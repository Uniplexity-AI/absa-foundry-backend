import yaml
import sqlalchemy as sa
from etl.extraction.config_models import ExtractionConfigSpec
from etl.extraction.query_builder import DynamicQueryBuilder
from shared.database.postgres import get_sync_engine

spec_yaml = """
version: "1.0"
dataset_name: "test_c360"
trusted_config: true
primary_entity:
  table: "a_africa_zam_base_customer"
  alias: "c"
  select_fields:
    - field: "customer_number"
      alias: "customer_id"
pre_aggregations:
  - name: "trans_summary"
    from_table: "a_brains_trans_zam_base_entries_zm"
    alias: "ts"
    group_by: ["ts.customer_number"]
    aggregations:
      - function: MIN
        field: "ts.account_number"
        alias: account_number
joins:
  - table: "trans_summary"
    alias: "ts"
    join_type: "left"
    "on":
      - left: "c.customer_number"
        right: "ts.customer_number"
    select_fields:
      - field: "account_number"
        alias: "account_number"
"""

data = yaml.safe_load(spec_yaml)
spec = ExtractionConfigSpec(**data)
engine = get_sync_engine()
meta = sa.MetaData()
builder = DynamicQueryBuilder(engine, meta)
stmt = builder.build(spec)
print("QUERY:")
print(str(stmt))
with engine.connect() as conn:
    res = conn.execute(stmt).mappings().all()
    print("SUCCESS, rows returned:", len(res), res[0])
