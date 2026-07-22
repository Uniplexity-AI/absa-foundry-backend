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

