"""Feature Engineering Service — FastAPI Application Entry Point."""
from __future__ import annotations
from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="Feature Engineering Service", version="1.0.0")
app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "service": "feature-engineering-service"}
