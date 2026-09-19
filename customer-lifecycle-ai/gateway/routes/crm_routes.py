"""
Gateway CRM Routes — Endpoints for CRM functionality.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/crm", tags=["CRM"])

# Dummy schemas for requests/responses
class CaseCreate(BaseModel):
    customer_id: str
    case_type: str
    assigned_agent_id: Optional[str] = None

class InteractionCreate(BaseModel):
    interaction_channel: str
    notes: Optional[str] = None

class PromiseCreate(BaseModel):
    promise_type: str
    promise_date: datetime
    amount: Optional[float] = None

@router.get("/cases")
async def list_cases():
    """List all engagement cases."""
    # In a real implementation, you would query the DB using shared.database.session
    return {"cases": []}

@router.post("/cases")
async def create_case(case: CaseCreate):
    """Create a new engagement case."""
    return {"status": "success", "case": case.dict()}

@router.post("/cases/{case_id}/interactions")
async def add_interaction(case_id: int, interaction: InteractionCreate):
    """Add a new interaction to a case."""
    return {"status": "success", "case_id": case_id, "interaction": interaction.dict()}

@router.post("/cases/{case_id}/promises")
async def add_promise(case_id: int, promise: PromiseCreate):
    """Add a new promise (e.g. promise-to-pay) to a case."""
    return {"status": "success", "case_id": case_id, "promise": promise.dict()}

@router.get("/reports/promise-to-fund")
async def promise_to_fund_report():
    """Get a report on promises to fund."""
    return {"report": []}
