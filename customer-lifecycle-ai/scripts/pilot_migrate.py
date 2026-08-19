"""
Pilot Database Migration Runner.

Applies SQL migration files to the correct databases without requiring
`psql` on PATH. Uses psycopg2 (already a project dependency).

Reads connection details from .env (same keys the application uses).

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\pilot_migrate.py [--create-databases]

The runner applies:
    - iam schema          -> source DB (POSTGRES_DB, default etl_validation)
    - etl schema          -> target DB (POSTGRES_TARGET_DB, default etl_clean)
    - feature_store       -> target DB
    - state_engine        -> target DB

With --create-databases it first creates the two databases if missing.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

ROOT = Path(__file__).resolve().parent.parent

# (sql_file_relative_path, target_db_key)
MIGRATIONS = [
    ("database/iam/001_initial_schema.sql", "source"),
    ("database/migrations/001_etl_schema.sql", "target"),
    ("database/feature_store/001_customer_features.sql", "target"),
    ("database/state_engine/001_customer_states.sql", "target"),
]


def load_env() -> dict[str, str]:
    """Parse .env into a dict (keys as-is, UPPER_CASE)."""
    env: dict[str, str] = {}
    env_file = ROOT / ".env"
    if not env_file.exists():
        print(f"ERROR: {env_file} not found. Run scripts/pilot_setup.ps1 first.")
        sys.exit(1)
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def conn_params(env: dict[str, str], db_key: str) -> dict[str, str]:
    """Build psycopg2 connection kwargs for a database."""
    if db_key == "source":
        return {
            "host": env.get("POSTGRES_HOST", "localhost"),
            "port": int(env.get("POSTGRES_PORT", "5432")),
            "dbname": env.get("POSTGRES_DB", "etl_validation"),
            "user": env.get("POSTGRES_USER", "postgres"),
            "password": env.get("POSTGRES_PASSWORD", ""),
        }
    return {
        "host": env.get("POSTGRES_TARGET_HOST", "localhost"),
        "port": int(env.get("POSTGRES_TARGET_PORT", "5432")),
        "dbname": env.get("POSTGRES_TARGET_DB", "etl_clean"),
        "user": env.get("POSTGRES_TARGET_USER", "postgres"),
        "password": env.get("POSTGRES_TARGET_PASSWORD", ""),
    }


def create_databases(env: dict[str, str]) -> None:
    """Create source and target databases if they do not exist."""
    for db_key in ("source", "target"):
        params = conn_params(env, db_key)
        dbname = params.pop("dbname")
        conn = psycopg2.connect(**params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
            print(f"Created database: {dbname}")
        else:
            print(f"Database exists: {dbname}")
        cur.close()
        conn.close()


def apply_migrations(env: dict[str, str]) -> None:
    """Apply each migration SQL file to its target database."""
    for rel_path, db_key in MIGRATIONS:
        sql_file = ROOT / rel_path
        if not sql_file.exists():
            print(f"SKIP (missing): {rel_path}")
            continue
        params = conn_params(env, db_key)
        dbname = params["dbname"]
        ddl = sql_file.read_text(encoding="utf-8")
        print(f"Applying {rel_path} -> {dbname}")
        conn = psycopg2.connect(**params)
        try:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()
        finally:
            conn.close()
    print("\nAll migrations applied successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pilot DB migration runner")
    parser.add_argument("--create-databases", action="store_true",
                        help="Create etl_validation and etl_clean if missing")
    args = parser.parse_args()

    env = load_env()
    if args.create_databases:
        create_databases(env)
    apply_migrations(env)


if __name__ == "__main__":
    main()
