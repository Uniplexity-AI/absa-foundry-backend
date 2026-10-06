"""
Gateway Admin Routes — user, role, and API key management.

All endpoints require ADMIN role (enforced by RBAC middleware).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status, Request

from shared.auth.models import (
    UserResponse,
    RoleResponse,
)
from shared.auth.user_repository import UserRepository

logger = logging.getLogger("gateway.routes.admin")

router = APIRouter(prefix="/admin", tags=["Admin"])

_user_repo = UserRepository()


# ===========================================================================
# GET /admin/users
# ===========================================================================

@router.get("/users", response_model=list[UserResponse])
async def list_users(request: Request):
    """List all users with their roles. ADMIN only."""
    try:
        users = _user_repo.list_users()
        return [
            UserResponse(
                user_id=u["user_id"],
                username=u["username"],
                email=u["email"],
                display_name=u["display_name"],
                department=u.get("department"),
                branch_code=u.get("branch_code"),
                roles=list(u["roles"]) if u["roles"] else [],
                is_active=u["is_active"],
                last_login_at=u.get("last_login_at"),
                created_at=u["created_at"],
            )
            for u in users
        ]
    except Exception as e:
        logger.exception("Failed to list users")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ===========================================================================
# GET /admin/roles
# ===========================================================================

@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(request: Request):
    """List all roles. ADMIN only."""
    try:
        roles = _user_repo.get_roles()
        return [
            RoleResponse(role_id=r["role_id"], role_name=r["role_name"], description=r.get("description"))
            for r in roles
        ]
    except Exception as e:
        logger.exception("Failed to list roles")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

from pydantic import BaseModel
from typing import Optional
from shared.database.postgres import get_sync_target_engine
from sqlalchemy import text as sa_text

class BranchRequest(BaseModel):
    branch_code: str
    name: str
    location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = "active"

class BranchUpdateRequest(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None

@router.get("/branches")
async def list_branches():
    try:
        engine = get_sync_target_engine()
        with engine.begin() as conn:
            res = conn.execute(sa_text("SELECT * FROM iam.branches ORDER BY created_at DESC")).mappings().fetchall()
            return [dict(r) for r in res]
    except Exception as e:
        logger.exception("Failed to list branches")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/branches")
async def create_branch(body: BranchRequest):
    try:
        engine = get_sync_target_engine()
        with engine.begin() as conn:
            conn.execute(
                sa_text("INSERT INTO iam.branches (branch_code, name, location, phone, email, status) VALUES (:b, :n, :l, :p, :e, :s)"),
                {"b": body.branch_code, "n": body.name, "l": body.location, "p": body.phone, "e": body.email, "s": body.status}
            )
        return {"success": True, "branch_code": body.branch_code}
    except Exception as e:
        logger.exception("Failed to create branch")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/branches/{branch_code}")
async def update_branch(branch_code: str, body: BranchUpdateRequest):
    try:
        engine = get_sync_target_engine()
        updates = []
        params = {"b": branch_code}
        if body.name is not None:
            updates.append("name = :n")
            params["n"] = body.name
        if body.location is not None:
            updates.append("location = :l")
            params["l"] = body.location
        if body.phone is not None:
            updates.append("phone = :p")
            params["p"] = body.phone
        if body.email is not None:
            updates.append("email = :e")
            params["e"] = body.email
        if body.status is not None:
            updates.append("status = :s")
            params["s"] = body.status
            
        if not updates:
            return {"success": True}
            
        with engine.begin() as conn:
            conn.execute(sa_text(f"UPDATE iam.branches SET {', '.join(updates)}, updated_at = NOW() WHERE branch_code = :b"), params)
        return {"success": True}
    except Exception as e:
        logger.exception("Failed to update branch")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/branches/{branch_code}")
async def delete_branch(branch_code: str):
    try:
        engine = get_sync_target_engine()
        with engine.begin() as conn:
            conn.execute(sa_text("DELETE FROM iam.branches WHERE branch_code = :b"), {"b": branch_code})
        return {"success": True}
    except Exception as e:
        logger.exception("Failed to delete branch")
        raise HTTPException(status_code=500, detail=str(e))

