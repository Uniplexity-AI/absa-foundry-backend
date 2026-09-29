"""PostgreSQL connection helper. Credentials via environment variables."""
from __future__ import annotations

import os
from contextlib import contextmanager

import pandas as pd
import psycopg2

from .settings import DEFAULT_SCHEMA


def get_connection_params() -> dict:
    return {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("PGDATABASE", "absa_dw"),
        "user": os.getenv("PGUSER", "postgres"),
        "password": os.getenv("PGPASSWORD", "wamulehi"),
    }


@contextmanager
def get_conn():
    conn = psycopg2.connect(**get_connection_params())
    try:
        yield conn
    finally:
        conn.close()


def read_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a parameterised SQL query (%(name)s style) and return a DataFrame."""
    with get_conn() as conn:
        return pd.read_sql(sql, conn, params=params or {})


def execute_sql(sql: str, params: dict | None = None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
        conn.commit()


def qualified(table_key: str) -> str:
    """Return schema-qualified table name from settings.TABLES key."""
    from .settings import TABLES

    name = TABLES[table_key]
    if "." in name:
        return name
    return f"{DEFAULT_SCHEMA}.{name}"
