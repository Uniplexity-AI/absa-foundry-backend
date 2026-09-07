"""
CSV TO POSTGRESQL IMPORTER
==========================

This script imports every CSV file from your Windows Downloads folder
into PostgreSQL.

Features
--------
✓ Automatically finds all CSV files
✓ Detects comma or pipe delimiters
✓ Detects UTF-8 or Latin-1 encoding
✓ Cleans table and column names
✓ Creates tables automatically
✓ Imports data in batches
✓ Displays progress
✓ Continues even if one file fails

Requirements
------------
pip install pandas sqlalchemy psycopg2-binary
"""

import os
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

# ============================================================
# CONFIGURATION
# ============================================================

# Downloads folder (works automatically on Windows)
CSV_DIRECTORY = Path.home() / "Downloads"

# PostgreSQL Connection

DB_HOST=localhost
DB_PORT=5432
DB_NAME=etl_validation
DB_USER=postgres
DB_PASSWORD=wamulehi
DATABASE_URL=postgresql://postgres:wamulehi@localhost:5432/etl_validation

# PostgreSQL schema
SCHEMA = "public"

# Options:
# replace -> Drop table and recreate
# append  -> Add new rows
# fail    -> Error if table exists
LOAD_MODE = "replace"

# ============================================================
# DATABASE CONNECTION
# ============================================================

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL)


# ============================================================
# HELPERS
# ============================================================

def detect_encoding(filepath):
    """
    Detect UTF-8 or Latin-1 encoding.
    """

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            f.readline()
        return "utf-8"

    except UnicodeDecodeError:
        return "latin-1"


def detect_delimiter(filepath):
    """
    Detect CSV delimiter.
    """

    with open(filepath, "r", encoding="latin-1") as f:
        first_line = f.readline()

    if first_line.count("|") > first_line.count(","):
        return "|"

    return ","


def clean_column_name(name):
    """
    Convert column names into PostgreSQL-safe names.
    """

    name = str(name).strip().lower()

    name = re.sub(r"[^\w]+", "_", name)

    name = re.sub(r"_+", "_", name)

    return name.strip("_")


def clean_table_name(filename):
    """
    Remove extension and date from filename.

    Example:
        customers_core_20260727.csv
            -> customers_core

        cards_page1_20260727.csv
            -> cards_page1

        transactions_core_20260727_batch1.csv
            -> transactions_core_batch1
    """

    table = os.path.splitext(filename)[0]

    # Remove YYYYMMDD wherever it appears
    table = re.sub(r"_20\d{6}", "", table)

    table = table.lower()

    table = re.sub(r"[^\w]+", "_", table)

    table = re.sub(r"_+", "_", table)

    return table.strip("_")


# ============================================================
# IMPORT ONE FILE
# ============================================================

def import_csv(filepath):

    print("=" * 80)
    print(f"Loading: {filepath.name}")

    encoding = detect_encoding(filepath)

    delimiter = detect_delimiter(filepath)

    print(f"Encoding : {encoding}")
    print(f"Delimiter: '{delimiter}'")

    df = pd.read_csv(
        filepath,
        sep=delimiter,
        encoding=encoding,
        low_memory=False
    )

    # Clean columns
    df.columns = [clean_column_name(c) for c in df.columns]

    table_name = clean_table_name(filepath.name)

    print(f"Table    : {table_name}")
    print(f"Rows     : {len(df):,}")
    print(f"Columns  : {len(df.columns)}")

    # Upload to PostgreSQL
    df.to_sql(
        table_name,
        engine,
        schema=SCHEMA,
        if_exists=LOAD_MODE,
        index=False,
        chunksize=5000,
        method="multi",
    )

    print("SUCCESS")


# ============================================================
# MAIN
# ============================================================

def main():

    print("\nSearching Downloads folder...\n")

    csv_files = sorted(CSV_DIRECTORY.glob("*.csv"))

    if not csv_files:
        print("No CSV files found.")
        return

    print(f"Found {len(csv_files)} CSV files.\n")

    loaded = 0
    failed = 0

    for csv_file in csv_files:

        try:

            import_csv(csv_file)

            loaded += 1

        except Exception as e:

            failed += 1

            print("\nFAILED")
            print(csv_file.name)
            print(e)

    print("\n")
    print("=" * 80)
    print("IMPORT SUMMARY")
    print("=" * 80)
    print(f"Loaded Successfully : {loaded}")
    print(f"Failed              : {failed}")
    print("=" * 80)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()