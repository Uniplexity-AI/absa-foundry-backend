"""
Gateway API Key Routes — create, list, and revoke API keys.

All endpoints require ADMIN role (enforced by RBAC middleware).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status, Request

from shared.auth.api_key_service import ApiKeyService
from shared.auth.user_repository import UserRepository
from shared.auth.models import CreateApiKeyRequest, ApiKeyResponse, ApiKeyListResponse

logger = logging.getLogger("gateway.routes.api_keys")

router = APIRouter(prefix="/admin/api-keys", tags=["API Keys"])

_repo = UserRepository()


# ===========================================================================
# POST /admin/api-keys
# ===========================================================================

@router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(request: Request, body: CreateApiKeyRequest):
    """Create a new API key for a service account. ADMIN only.

    The raw key is returned only once — store it securely.
    """
    raw_key, key_prefix, key_hash = ApiKeyService.generate_key(body.service_name)

    result = _repo.store_api_key(
        service_name=body.service_name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        key_name=body.name,
        scopes=body.scopes,
        expires_in_days=body.expires_in_days,
    )

    return ApiKeyResponse(
        key_id=result["key_id"],
        api_key=raw_key,
        key_prefix=key_prefix,
        service_name=result["service_name"],
        name=body.name,
        scopes=body.scopes,
        expires_at=None,  # TODO: compute from expires_in_days
    )


# ===========================================================================
# GET /admin/api-keys
# ===========================================================================

@router.get("", response_model=list[ApiKeyListResponse])
async def list_api_keys(request: Request):
    """List all API keys (without raw key values). ADMIN only."""
    keys = _repo.list_api_keys()
    return [
        ApiKeyListResponse(
            key_id=k["key_id"],
            key_prefix=k["key_prefix"],
            service_name=k["service_name"],
            name=k["name"],
            scopes=list(k["scopes"]) if k["scopes"] else [],
            last_used_at=k.get("last_used_at"),
            expires_at=k.get("expires_at"),
            is_active=k["is_active"],
        )
        for k in keys
    ]


# ===========================================================================
# DELETE /admin/api-keys/{key_id}
# ===========================================================================

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(request: Request, key_id: str):
    """Revoke an API key (soft-delete). ADMIN only."""
    found = _repo.revoke_api_key(key_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
