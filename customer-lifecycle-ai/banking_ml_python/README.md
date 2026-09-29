# Banking ML Python ETL

Python conversion of **banking_ml_dbeaver_sql_updated**, using the same architecture as **banking_ml_etl**.

Builds training and scoring datasets for four models:

| Model | Grain | Labels |
|-------|--------|--------|
| CLV | customer × month | `target_clv_12m`, `target_fee_income_12m`, `target_margin_12m` |
| Lifecycle | customer × month | optional `lifecycle_stage_label` (heuristic; unsupervised) |
| Churn | customer × month | `churn_30d`, `churn_90d` (dormancy-threshold based) |
| Balance | customer × day | `target_dab_30/60/90d` (placeholder until balance table exists) |

## What changed vs pure SQL (DBeaver)

| DBeaver SQL | Python ETL |
|-------------|------------|
| `01_set_parameters.sql` → `ml_etl_params` table | CLI args + `config/settings.py` |
| `CREATE TABLE ml_*_training` in the database | Queries return DataFrames → `output/<model>/<mode>/*.parquet` (+ `.csv`) |
| Manual re-run / comment-out labels for scoring | `--mode training\|scoring` drops label columns automatically |
| Scripts run in order inside DBeaver | `python run_extract.py ...` orchestrates extractors |

Business logic (especially the **dormancy-based churn labels**) is preserved from the updated DBeaver scripts.

## Architecture

```
Shared feature foundation  (sql/01_shared_features.sql)
        │
        ├── CLV        + fees, card spend, product velocity + forward revenue labels
        ├── Lifecycle  + salary consistency, activity change  (no supervised target)
        ├── Churn      + volume ratios, large outflows       + dormancy labels
        └── Balance    + cash-flow, calendar                 + forward DAB labels
```

- **Training mode**: features + labels  
- **Scoring mode**: features only (labels dropped in Python)

## Setup

```bash
export PGHOST=... PGPORT=5432 PGDATABASE=absa_dw PGUSER=... PGPASSWORD=...
pip install -r requirements.txt
cd banking_ml_python
```


## Local testing with synthetic data

1. Start Postgres and create an empty database (e.g. `absa_dw`).
2. Set connection env vars (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`).
3. Seed a **minimal** test set (default: 15 customers, ~4 months history, ~90 days forward):

```bash
python seed_synthetic_data.py --snapshot 2024-06-01
# optional: python seed_synthetic_data.py --customers 20 --history-months 4 --forward-days 90
```

4. Smoke-test the ETL:

```bash
python test_extract.py --limit 5 --snapshot 2024-06-01
```

Schema DDL: `sql/00_create_synthetic_schema.sql` (only columns used by the feature queries).

## Smoke test (recommended first)

Limits each query to a few rows so you can confirm connectivity, SQL, and merges without a full extract:

```bash
python test_extract.py --limit 5 --snapshot 2024-06-01
python test_extract.py --limit 5 --models shared,clv --mode scoring
```

Exit code 0 = all selected checks passed. Sample CSVs land in `output/test/`.

## Run (full extract)

```bash
# All models, training, snapshot June 2024
python run_extract.py --mode training --models all --snapshot 2024-06-01

# Churn scoring only
python run_extract.py --mode scoring --models churn --snapshot 2024-09-01

# Balance (daily as-of)
python run_extract.py --mode training --models balance --as-of 2024-06-30
```

Output: `output/<model>/<mode>/*.parquet` and `.csv`

## Churn label definition (important)

The target is **not** simply “status became Inactive/Pre-dormant”.

```
DORMANT = >= dormancy_threshold_days (default 365) consecutive days
          without qualifying activity
```

For a customer who is **not already dormant** at the snapshot:

- `churn_30d = 1` if they reach the dormancy threshold (or would) within 30 days, accounting for future transactions that reset the inactivity clock.
- `churn_90d = 1` for the 90-day horizon.

Example: `recency_days = 275` → `days_to_dormancy = 90` → can get `churn_90d = 1` because the 365-day threshold is reached within 90 days if there is no intervening activity.

Already-dormant customers at snapshot receive label `0` (model predicts future transition, not rediscovery).

Tune in `config/settings.py`:

- `DORMANCY_THRESHOLD_DAYS` (default 365)
- `CHURN_SHORT_HORIZON_DAYS` (30)
- `CHURN_HORIZON_DAYS` (90)
- `LARGE_OUTFLOW_THRESHOLD` (10000 ZMW)

## TODOs / business-rule placeholders

Same as the DBeaver package — update when ABSA confirms:

- Credit/debit/ATM transaction codes
- Salary narrative keywords and min amount
- External transfer / competitor bank codes
- Card table → customer_number link
- EOD balance table for Balance lags and DAB targets
- Explicit account-closure events for churn labels
- NII columns for CLV revenue

## Package layout

```
banking_ml_python/
├── README.md
├── requirements.txt
├── run_extract.py
├── config/
│   ├── db.py          # psycopg2 + pandas read_sql
│   └── settings.py    # tables, horizons, business rules
├── extractors/
│   ├── base.py        # load_sql, run_query, save_dataset
│   ├── shared.py
│   ├── clv.py
│   ├── churn.py
│   ├── lifecycle.py
│   └── balance.py
└── sql/
    ├── 01_shared_features.sql
    ├── 02_clv_features_labels.sql
    ├── 03_churn_features_labels.sql
    ├── 04_lifecycle_features.sql
    └── 05_balance_features_labels.sql
```
