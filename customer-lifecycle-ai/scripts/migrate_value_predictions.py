"""
Database migration script to add ML Value Prediction columns to customer_states.
"""
import logging
import os
import sys

import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def migrate_db():
    load_dotenv()
    db_url = os.environ.get("DATABASE_TARGET_URL_SYNC") or "postgresql://postgres:wamulehi@localhost:5432/etl_clean"
    
    try:
        conn = psycopg2.connect(db_url)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)
        
    queries = [
        "ALTER TABLE customer_states ADD COLUMN IF NOT EXISTS erosion_probability FLOAT;",
        "ALTER TABLE customer_states ADD COLUMN IF NOT EXISTS erosion_risk_level VARCHAR(32);",
        "ALTER TABLE customer_states ADD COLUMN IF NOT EXISTS predicted_future_value NUMERIC;",
        "ALTER TABLE customer_states ADD COLUMN IF NOT EXISTS future_value_percentile FLOAT;",
        "ALTER TABLE customer_states ADD COLUMN IF NOT EXISTS model_version VARCHAR(64);",
        "ALTER TABLE customer_states ADD COLUMN IF NOT EXISTS prediction_date DATE;"
    ]
    
    try:
        with conn.cursor() as cur:
            for q in queries:
                logger.info(f"Executing: {q}")
                cur.execute(q)
        conn.commit()
        logger.info("Successfully added ML Value Prediction columns to customer_states.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_db()
