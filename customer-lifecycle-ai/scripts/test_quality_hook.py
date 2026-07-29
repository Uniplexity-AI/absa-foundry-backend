"""Test quality check integration into pipeline.

TODO: Remove after verification.

Run from within services/feature-engineering-service/:
    cd services/feature-engineering-service
    uv run python ../../scripts/test_quality_hook.py
"""
import sys, os
# This script MUST run from services/feature-engineering-service/
# Ensure both app/ and shared/ are on sys.path
svc_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "services", "feature-engineering-service"
)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in [svc_dir, project_root]:
    if d not in sys.path:
        sys.path.insert(0, d)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from app.pipelines.pipeline import _run_quality_check
from app.repository.repository import FeatureRepository
from datetime import date

repo = FeatureRepository()
result = _run_quality_check(repo, date(2026, 7, 27))
print(f"Scanned: {result['scanned']} features")
print(f"Dead: {result['dead_features']}")
for f in result.get("flagged", [])[:5]:
    print(f"  {f['feature']}: {f['issue']}")
print("Quality hook works!")
