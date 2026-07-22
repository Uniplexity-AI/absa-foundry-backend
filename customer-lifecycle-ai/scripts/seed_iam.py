"""
IAM Seed Script — create default admin user, service accounts, and API keys.

Usage:
    python scripts/seed_iam.py

Creates:
    - Default admin user (admin / admin123) for local development
    - Service accounts: etl_engine, prediction_service, feature_engineering
    - API keys for each service account
"""

from __future__ import annotations

import hashlib
import sys
import os

# Path setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.auth.user_repository import UserRepository
from shared.auth.api_key_service import ApiKeyService


def seed():
    repo = UserRepository()

    print("=== Seeding IAM ===")

    # ---- Default admin user ----
    try:
        user = repo.sync_user(
            username="admin",
            email="admin@absa.co.zm",
            display_name="System Administrator",
            dn="CN=admin,OU=Dev,DC=local",
            department="IT",
        )
        assigned = repo.assign_role("admin", "ADMIN")
        print(f"  Admin user: {user.username} (id={str(user.user_id)[:8]}...), ADMIN role={'assigned' if assigned else 'already had'}")
    except Exception as e:
        print(f"  Admin user: SKIPPED ({e})")

    # ---- Service Accounts ----
    services = [
        {
            "name": "etl_engine",
            "description": "ETL pipeline — extracts, transforms, loads data",
            "scopes": ["read:source_db", "write:target_db", "trigger:etl"],
        },
        {
            "name": "prediction_service",
            "description": "Prediction engine — churn, CLV, health scores",
            "scopes": ["read:features", "write:predictions", "read:models"],
        },
        {
            "name": "feature_engineering",
            "description": "Feature engineering — computes ML features",
            "scopes": ["read:source_db", "write:feature_store", "read:models"],
        },
        {
            "name": "dashboard_service",
            "description": "Dashboard — serves analytics to frontend",
            "scopes": ["read:customers", "read:predictions", "read:health_scores"],
        },
    ]

    for svc in services:
        try:
            raw_key, key_prefix, key_hash = ApiKeyService.generate_key(svc["name"])
            result = repo.store_api_key(
                service_name=svc["name"],
                key_hash=key_hash,
                key_prefix=key_prefix,
                key_name=f"{svc['name']}_default",
                scopes=svc["scopes"],
                expires_in_days=None,  # No expiry
            )
            print(f"  {svc['name']}: {key_prefix}... (scopes={svc['scopes']})")
        except Exception as e:
            print(f"  {svc['name']}: FAILED ({e})")

    print()
    print("=== IAM Seed Complete ===")


if __name__ == "__main__":
    seed()
