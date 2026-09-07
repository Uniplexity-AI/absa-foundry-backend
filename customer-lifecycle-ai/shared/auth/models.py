"""
Shared Auth Models — Pydantic v2 schemas for authentication I/O.

All request/response models for login, token management, user management,
and API key operations.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ===========================================================================
# Auth Request/Response
# ===========================================================================

class LoginRequest(BaseModel):
    """Username + password login payload."""
    username: str = Field(min_length=1, max_length=100, description="AD username (sAMAccountName)")
    password: str = Field(min_length=1, description="AD password")


class TokenResponse(BaseModel):
    """Returned on successful login or token refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until access token expires")


class RefreshRequest(BaseModel):
    """Request a new access token using a refresh token."""
    refresh_token: str


class LogoutRequest(BaseModel):
    """Optional: revoke a specific refresh token. If omitted, all user tokens revoked."""
    refresh_token: str | None = None


# ===========================================================================
# User Models
# ===========================================================================

class UserResponse(BaseModel):
    """Public user profile — returned by /auth/me and admin endpoints."""
    user_id: UUID
    username: str
    email: str
    display_name: str
    department: str | None = None
    branch_code: str | None = None
    roles: list[str] = Field(default_factory=list)
    is_active: bool = True
    last_login_at: datetime | None = None
    created_at: datetime


class CreateUserRequest(BaseModel):
    """Admin creates a new user."""
    username: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=255)
    display_name: str = Field(min_length=1, max_length=200)
    dn: str = Field(min_length=1, max_length=500, description="LDAP distinguished name")
    department: str | None = None
    branch_code: str | None = None
    roles: list[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    """Admin updates an existing user."""
    email: str | None = None
    display_name: str | None = None
    department: str | None = None
    branch_code: str | None = None
    is_active: bool | None = None
    roles: list[str] | None = None


# ===========================================================================
# Role Models
# ===========================================================================

class RoleResponse(BaseModel):
    role_id: int
    role_name: str
    description: str | None = None


# ===========================================================================
# API Key Models
# ===========================================================================

class CreateApiKeyRequest(BaseModel):
    """Admin creates an API key for a service account."""
    service_name: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100, description="Human-readable key label")
    scopes: list[str] = Field(default_factory=list)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class ApiKeyResponse(BaseModel):
    """Returned once — the raw key is never stored, only shown at creation time."""
    key_id: UUID
    api_key: str = Field(description="The raw API key — store it now, it won't be shown again")
    key_prefix: str
    service_name: str
    name: str
    scopes: list[str]
    expires_at: datetime | None = None


class ApiKeyListResponse(BaseModel):
    """List of API keys for a service (without raw keys)."""
    key_id: UUID
    key_prefix: str
    service_name: str
    name: str
    scopes: list[str]
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool


# ===========================================================================
# Internal Context (injected by middleware)
# ===========================================================================

class UserContext(BaseModel):
    """Populated by JWT middleware, available to all downstream handlers."""
    user_id: UUID
    username: str
    display_name: str
    email: str
    roles: list[str]
    branch_code: str | None = None


class ServiceContext(BaseModel):
    """Populated by API key middleware for service-to-service calls."""
    service_id: UUID
    service_name: str
    scopes: list[str]
