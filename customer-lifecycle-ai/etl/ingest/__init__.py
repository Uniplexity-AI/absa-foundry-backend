"""Customer data ingest — bring customer data into Postgres for analysis.

Two entry points, one write path:

* :mod:`etl.ingest.customer_csv` — operator CSV upload (My Customers page),
  with a column-mapping contract derived from :mod:`etl.ingest.customer_schema`.
* :mod:`etl.ingest.core_banking` — ETL Engine pull from the core Absa system.

Both validate against the same field catalogue in
:mod:`etl.ingest.customer_schema` and load through
:meth:`etl.ingest.loader.load_batch`, which owns the single write path.

Two datasets are loadable, selected by key (see ``DATASETS``):

* ``customers``         → ``public.customers_clean``   key ``customer_id``
* ``customer_features`` → ``public.customer_features`` key ``(customer_id, as_of_date)``

The earlier single-dataset names (``load_customer_batch``, ``customer_count``)
remain as thin wrappers so existing callers keep working.
"""

from etl.ingest.customer_schema import (
    CUSTOMER_FIELDS,
    DATASETS,
    DEFAULT_DATASET,
    FEATURE_FIELDS,
    FIELDS_BY_NAME,
    TARGET_TABLE,
    auto_map,
    coerce_row,
    describe_schema,
    get_dataset,
    validate_mapping,
)
from etl.ingest.loader import (
    customer_count,
    load_batch,
    load_customer_batch,
    recent_ingest_runs,
    row_count,
)

__all__ = [
    "CUSTOMER_FIELDS",
    "DATASETS",
    "DEFAULT_DATASET",
    "FEATURE_FIELDS",
    "FIELDS_BY_NAME",
    "TARGET_TABLE",
    "auto_map",
    "coerce_row",
    "describe_schema",
    "get_dataset",
    "validate_mapping",
    "customer_count",
    "load_batch",
    "load_customer_batch",
    "recent_ingest_runs",
    "row_count",
]
