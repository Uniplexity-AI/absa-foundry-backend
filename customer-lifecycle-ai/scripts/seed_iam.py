"""
IAM Seed Script — demo login users, service accounts, and API keys.

Usage (from repo root):
    python scripts/seed_iam.py                          # seed admin/service accounts + demo users
    python scripts/seed_iam.py --list                   # list existing users and exit
    python scripts/seed_iam.py --password 'Demo#2025'   # override the demo password
    python scripts/seed_iam.py --skip-demo              # do NOT touch demo user passwords

Creates:
    - Service accounts + API keys (etl_engine, prediction_service, ...)
    - Four local demo login accounts with roles and a real password hash:
        admin    / ADMIN                  (System Administrator)
        rm.demo  / RELATIONSHIP_MANAGER   (Relationship Manager)
        ds.demo  / DATA_SCIENTIST         (Data Scientist)
        ops.demo / OPERATIONS             (Operations Analyst)
    Default demo password: Pilot@2025  (set via --password to change)

Re-running is idempotent; --password resets the demo password on each run.
"""

from __future__ import annotations

import argparse
import os
import sys

# Path setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.auth.password import hash_password
from shared.auth.user_repository import UserRepository
from shared.auth.api_key_service import ApiKeyService

# username -> (email, display_name, department, roles)
DEMO_ACCOUNTS = [
    ("admin",    "admin@absa.co.zm",     "System Administrator",        "IT",              ["ADMIN"]),
    ("rm.demo",  "rm.demo@absa.co.zm",   "Relationship Manager (Demo)", "Retail Banking",  ["RELATIONSHIP_MANAGER"]),
    ("ds.demo",  "ds.demo@absa.co.zm",   "Data Scientist (Demo)",       "Data & Analytics", ["DATA_SCIENTIST"]),
    ("ops.demo", "ops.demo@absa.co.zm",  "Operations Analyst (Demo)",   "Operations",      ["OPERATIONS"]),
]

DEFAULT_DEMO_PASSWORD = "Pilot@2025"


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


def seed_demo_users(repo: UserRepository, password: str = DEFAULT_DEMO_PASSWORD) -> None:
    """Create/update the demo login accounts and set their local passwords."""
    print("\n=== Seeding Demo Users ===")
    for username, email, display_name, department, roles in DEMO_ACCOUNTS:
        try:
            user = repo.sync_user(
                username=username,
                email=email,
                display_name=display_name,
                dn=f"CN={username},OU=Dev,DC=local",
                department=department,
            )
            for role in roles:
                repo.assign_role(username, role)
            repo.set_password(user.user_id, hash_password(password))
            print(f"  {username:10s} -> {display_name}  roles={','.join(roles)}  password set")
        except Exception as e:
            print(f"  {username}: SKIPPED ({e})")


def list_users(repo: UserRepository) -> None:
    """Print current users and roles."""
    print("\n=== IAM Users ===")
    users = repo.list_users()
    if not users:
        print("  (no users)")
    for u in users:
        roles = ", ".join(u["roles"]) if u.get("roles") else "(no roles)"
        active = "active" if u.get("is_active", True) else "DEACTIVATED"
        print(f"  {u['username']:10s} {u.get('email', ''):35s} [{roles}]  {active}")
    roles = repo.get_roles()
    print("\nAvailable roles: " + ", ".join(r["role_name"] for r in roles))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed IAM users / demo accounts.")
    parser.add_argument("--list", action="store_true", help="List existing users and exit")
    parser.add_argument("--password", default=DEFAULT_DEMO_PASSWORD,
                        help=f"Demo account password (default: {DEFAULT_DEMO_PASSWORD})")
    parser.add_argument("--skip-demo", action="store_true",
                        help="Do NOT seed/reset demo user accounts")
    args = parser.parse_args()

    repo = UserRepository()

    if args.list:
        list_users(repo)
        sys.exit(0)

    seed()
    if not args.skip_demo:
        seed_demo_users(repo, password=args.password)

    print()
    print("=== Seed Complete ===")
    print(f"Demo login credentials (password: {args.password}):")
    for username, _email, _name, _dept, roles in DEMO_ACCOUNTS:
        print(f"    {username:10s} / {args.password}   roles={','.join(roles)}")
