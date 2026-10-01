import os
import logging
import pandas as pd
import psycopg2
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def get_db_connection():
    """Get connection to the target PostgreSQL database (etl_clean)."""
    load_dotenv()
    db_url = os.environ.get("DATABASE_TARGET_URL_SYNC") or "postgresql://postgres:wamulehi@localhost:5432/etl_clean"
    return psycopg2.connect(db_url)

def load_training_data(model_type: str, target_columns: list[str]) -> pd.DataFrame:
    """
    Dynamically joins feature_store_shared with the specific model table
    (feature_store_churn, feature_store_clv, etc.) and drops any rows 
    where the target label is NULL (i.e. scoring-only data).
    
    Args:
        model_type: One of 'churn', 'clv', 'lifecycle', 'balance'.
        target_columns: List of columns that must not be NULL (the labels).
        
    Returns:
        DataFrame containing the joined features and labels.
    """
    table_name = f"feature_store_{model_type}"
    
    # We join on customer_id and snapshot_month (or as_of_date for balance)
    if model_type == 'balance':
        join_cond = "s.customer_id = m.customer_id AND s.snapshot_month = DATE_TRUNC('month', m.as_of_date)::DATE"
    else:
        join_cond = "s.customer_id = m.customer_id AND s.snapshot_month = m.snapshot_month"

    # Construct the WHERE clause to filter out null targets
    where_clauses = [f"m.{col} IS NOT NULL" for col in target_columns]
    where_clause_sql = " AND ".join(where_clauses)
    
    query = f"""
        SELECT s.*, m.*
        FROM feature_store_shared s
        JOIN {table_name} m ON {join_cond}
        WHERE {where_clause_sql}
    """
    
    logger.info(f"Loading training data for {model_type} model...")
    
    conn = get_db_connection()
    try:
        df = pd.read_sql(query, conn)
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Ensure we restrict the dataset to exactly 15,000 unique customers
        # while keeping all 24 months of history for those specific customers
        unique_customers = df['customer_id'].unique()
        if len(unique_customers) > 15000:
            selected_customers = unique_customers[:15000]
            df = df[df['customer_id'].isin(selected_customers)].copy()
            logger.info(f"Restricted dataset from {len(unique_customers)} to 15000 unique customers.")
            
        logger.info(f"Extracted {len(df)} total rows across {len(df['customer_id'].unique())} customers with valid targets for {model_type}.")
        return df
    finally:
        conn.close()
