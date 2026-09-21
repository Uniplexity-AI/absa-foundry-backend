"""Model Management Service - ML model registry, versioning, deployment, and A/B testing - FastAPI Application Entry Point."""
from __future__ import annotations

import os
import sys

# Ensure project root for shared.* imports
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

from app.main import app