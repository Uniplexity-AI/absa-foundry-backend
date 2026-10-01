# Historical Data Extraction & Training Plan

To ensure our models learn seasonal patterns and have enough churn examples to prevent overfitting, we will extract 24 months of historical snapshots from the ABSA Hadoop environment.

## Phase 1: Automated Multi-Snapshot Extraction
Currently, `run_etl.py` processes one snapshot at a time. To extract 24 months of data efficiently without manual intervention, we will create a dedicated automation script.

1. **Create `run_historical_etl.ps1` (PowerShell Script):**
   - This script will define an array of 24 snapshot dates (e.g., first of the month from July 2022 to June 2024).
   - It will loop through each date and execute: 
     `python run_etl.py --models shared,churn,clv,lifecycle,balance --snapshot <DATE> --source-type denodo --force`
   - It will include basic error handling to skip and log any months that fail, ensuring the entire 2-year job doesn't crash halfway through.

2. **Database Architecture Confirmation:**
   - The target PostgreSQL tables (`feature_store_churn`, etc.) already use a composite Primary Key of `(customer_id, snapshot_month)`.
   - As the loop runs, the database will safely append each month's data in the **Long Format** we discussed, naturally avoiding duplicates.

## Phase 2: Execute the Extraction
Once the script is written, we will execute it. 
- *Note:* Because it is connecting to the real Hadoop (Denodo) cluster and querying 24 separate time windows, this extraction phase may take some time depending on the network and cluster load.

## Phase 3: Update Data Loader and Train the Models
After the ETL engine finishes populating the `etl_clean` database, we need to ensure the models only train on exactly 15,000 unique customers while maintaining their full 24-month time-series history.

1. **Update `data_loader.py`:**
   - Modify the `load_training_data` function to isolate 15,000 unique `customer_id`s.
   - Filter the resulting dataframe so that it only includes rows belonging to those specific 15,000 customers across all extracted snapshots.

2. **Execute Training Scripts:**
   Run the newly refactored training scripts:
   - **`python scripts/train_churn_model.py`**
   - **`python scripts/train_clv_model.py`**
   - **`python scripts/train_lifecycle_models.py`**
   - **`python scripts/train_balance_growth_model.py`**

   *Note:* The `walk_forward_split` logic inside the scripts will automatically use the older snapshots for training and the newest snapshot for validation, proving that the model can predict the future.

## Phase 4: Validation
- Check the output logs for the `AUC` (Area Under Curve) and `Recall` scores to ensure the models have generalized well across the 2-year period.
