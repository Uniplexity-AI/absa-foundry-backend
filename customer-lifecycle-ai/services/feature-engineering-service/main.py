"""Feature Engineering Service — FastAPI Application Entry Point."""
from __future__ import annotations

import os
import sys

# Ensure project root is on sys.path for shared.* imports
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="Feature Engineering Service", version="1.0.0")
app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "service": "feature-engineering-service"}
