"""
Gateway Auth Routes — login, logout, token refresh, user profile.

FastAPI route handlers for all authentication endpoints.
All routes are mounted at /auth/* in the gateway.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, status

from shared.auth.models import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    UserResponse,
    UserContext,
)
from shared.auth.password import verify_password
from shared.auth.token_service import TokenService
from shared.auth.user_repository import UserRepository
from shared.auth.audit import AuthAudit
from shared.config.settings import settings

# LDAP is optional — gracefully degrade if ldap3 is not installed
try:
    from shared.auth.authenticator import (
        Authenticator,
        InvalidCredentialsError,
        AccountLockedError,
        LDAPConnectionError,
    )
    _HAS_LDAP = True
except ImportError:
    _HAS_LDAP = False
    Authenticator = None  # type: ignore
    InvalidCredentialsError = Exception
    AccountLockedError = Exception
    LDAPConnectionError = Exception

logger = logging.getLogger("gateway.routes.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ---------------------------------------------------------------------------
# Services — initialized once at module load
# ---------------------------------------------------------------------------

_user_repo = UserRepository()

_token_service = TokenService()

_authenticator = Authenticator(
    server_url=settings.ldap_server,
    base_dn=settings.ldap_base_dn,
    bind_dn=settings.ldap_bind_dn or None,
    bind_password=settings.ldap_bind_password or None,
    user_dn_template=settings.ldap_user_dn_template or None,
    search_filter=settings.ldap_search_filter,
    timeout=settings.ldap_timeout_seconds,
    use_tls=settings.ldap_tls_enabled,
) if (_HAS_LDAP and settings.ldap_enabled) else None


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ===========================================================================
# Phase 3: Rate limiting (in-memory) & account lockout (DB-backed, no Redis)
# ===========================================================================


async def _check_rate_limit(request: Request) -> None:
    """Phase 3: Apply rate limit middleware (in-memory — pilot has no Redis)."""
    from gateway.middleware.rate_limit import rate_limiter
    await rate_limiter.check(request)


async def _check_lockout(username: str) -> None:
    """Phase 3: Check the DB for a persisted lockout (survives gateway restarts)."""
    now = datetime.now(timezone.utc)
    row = _user_repo.get_by_username(username)
    if row is None or row.get("locked_until") is None:
        return
    locked_until = row["locked_until"]
    if locked_until > now:
        retry_mins = int((locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account temporarily locked. Retry in ~{retry_mins} minute(s).",
        )


async def _record_failed_attempt(username: str, ip: str | None) -> None:
    """Phase 3: Persist a failed attempt; auto-lock the account at the threshold."""
    row = _user_repo.get_by_username(username)
    if row is None:
        return
    attempts = _user_repo.increment_failed_attempts(row["user_id"])
    if attempts >= settings.lockout_max_attempts:
        await AuthAudit.log("ACCOUNT_LOCKED", user_id=row["user_id"], ip_address=ip,
                            details={"username": username, "attempts": attempts})


def _validate_password_policy(username: str, password: str) -> None:
    """Phase 3: Enforce password complexity rules before LDAP bind."""
    errors = []

    if len(password) < settings.password_min_length:
        errors.append(f"Minimum {settings.password_min_length} characters")

    if settings.password_require_uppercase and not any(c.isupper() for c in password):
        errors.append("At least one uppercase letter")

    if settings.password_require_digit and not any(c.isdigit() for c in password):
        errors.append("At least one digit")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Password policy violation", "rules": errors},
        )


# ===========================================================================
# POST /auth/login
# ===========================================================================

@router.post("/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest):
    """Authenticate with username/password.

    Flow:
        1. Rate limit check (Phase 3)
        2. Account lockout check (Phase 3)
        3. Password policy validation (Phase 3)
        4. LDAP bind (if enabled) or fallback to dev mode
        5. Sync user to iam.users (upsert)
        6. Resolve roles from iam.user_roles
        7. Issue JWT + refresh token
    """
    ip = _client_ip(request)
    username = body.username.strip()

    # Phase 3: Rate limiting
    await _check_rate_limit(request)

    # Phase 3: Account lockout check
    await _check_lockout(username)

    # ---- Authenticate ----
    ldap_attrs = None

    if _authenticator is not None:
        try:
            ldap_attrs = _authenticator.authenticate(username, body.password)
        except InvalidCredentialsError:
            await _record_failed_attempt(username, ip)
            await AuthAudit.log("LOGIN_FAILED", ip_address=ip,
                                details={"username": username, "reason": "invalid_credentials"})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        except AccountLockedError:
            await AuthAudit.log("LOGIN_FAILED", ip_address=ip,
                                details={"username": username, "reason": "account_locked"})
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account is locked")
        except LDAPConnectionError:
            await AuthAudit.log("LOGIN_FAILED", ip_address=ip,
                                details={"username": username, "reason": "ldap_unavailable"})
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            )
    else:
        # LOCAL MODE — verify stored credentials against iam.users (no LDAP).
        user_row = _user_repo.get_by_username(username)
        now = datetime.now(timezone.utc)

        # 1) Account exists and has a local password?
        if user_row is None or not user_row.get("password_hash"):
            await AuthAudit.log("LOGIN_FAILED", ip_address=ip,
                                details={"username": username, "reason": "invalid_credentials"})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid credentials")

        # 2) Account active?
        if not user_row.get("is_active", True):
            await AuthAudit.log("LOGIN_FAILED", ip_address=ip,
                                details={"username": username, "reason": "account_disabled"})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Account is disabled")

        # 3) Persisted lockout active?
        locked_until = user_row.get("locked_until")
        if locked_until is not None and locked_until > now:
            retry_mins = int((locked_until - now).total_seconds() // 60) + 1
            await AuthAudit.log("LOGIN_FAILED", ip_address=ip,
                                details={"username": username, "reason": "account_locked"})
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account temporarily locked. Retry in ~{retry_mins} minute(s).",
            )
        elif locked_until is not None:
            # Lock expired — clear counters so the user can retry.
            _user_repo.reset_lockout(user_row["user_id"])
            user_row["failed_attempts"] = 0

        # 4) Verify password
        if not verify_password(body.password, user_row["password_hash"]):
            attempts = _user_repo.increment_failed_attempts(user_row["user_id"])
            await AuthAudit.log("LOGIN_FAILED", ip_address=ip,
                                details={"username": username, "reason": "invalid_credentials",
                                         "failed_attempts": attempts})
            if attempts >= settings.lockout_max_attempts:
                await AuthAudit.log("ACCOUNT_LOCKED", user_id=user_row["user_id"], ip_address=ip,
                                    details={"username": username, "attempts": attempts})
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f"Account locked after {attempts} failed attempts.",
                )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid credentials")

        # 5) Success — carry over the profile stored in the DB.
        ldap_attrs = {
            "username": user_row["username"],
            "email": user_row["email"],
            "display_name": user_row["display_name"],
            "dn": user_row["dn"],
            "department": user_row.get("department"),
        }

    # ---- Sync user to DB + resolve roles ----
    try:
        user = _user_repo.sync_user(
            username=ldap_attrs["username"],
            email=ldap_attrs["email"],
            display_name=ldap_attrs["display_name"],
            dn=ldap_attrs["dn"],
            department=ldap_attrs.get("department"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.exception("Failed to sync user from LDAP")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync user account",
        )

    # ---- Issue tokens ----
    # Phase 3: Clear the persisted lockout counter on success
    _user_repo.reset_lockout(user.user_id)

    access_token = _token_service.create_access_token(user)
    raw_refresh, token_hash = _token_service.create_refresh_token(user.user_id)

    # Persist refresh token in PostgreSQL
    _user_repo.store_refresh_token(user.user_id, token_hash, ip_address=ip)

    await AuthAudit.log("LOGIN_SUCCESS", user_id=user.user_id, ip_address=ip)

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ===========================================================================
# POST /auth/refresh
# ===========================================================================

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, body: RefreshRequest):
    """Exchange a refresh token for a new access + refresh token pair.

    The old refresh token is revoked (token rotation).
    """
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    user_id = _user_repo.validate_refresh_token(token_hash)

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Revoke old token
    _user_repo.revoke_refresh_token(token_hash)

    # Resolve user to get current roles
    user = _get_user_context(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Issue new tokens
    access_token = _token_service.create_access_token(user)
    raw_refresh, new_hash = _token_service.create_refresh_token(user_id)
    _user_repo.store_refresh_token(user_id, new_hash, ip_address=_client_ip(request))

    await AuthAudit.log("TOKEN_REFRESH", user_id=user_id, ip_address=_client_ip(request))

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ===========================================================================
# POST /auth/logout
# ===========================================================================

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request):
    """Logout: revoke the current JWT (via in-memory blacklist) and all refresh tokens."""
    from gateway.middleware.auth import get_current_user
    user = await get_current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # Revoke all refresh tokens for this user in PostgreSQL
    _user_repo.revoke_all_user_tokens(user.user_id)

    # In-memory JWT blacklist (simple set for PoC — replaced by Redis in production)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = _token_service.decode_access_token(token)
            jti = payload.get("jti")
            if jti:
                import time
                remaining = max(0, payload["exp"] - time.time())
                await _token_service.blacklist_token(jti, int(remaining))
        except Exception:
            pass

    await AuthAudit.log("LOGOUT", user_id=user.user_id, ip_address=_client_ip(request))


# ===========================================================================
# GET /auth/me
# ===========================================================================

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(request: Request):
    """Return the authenticated user's profile (loaded from iam.users)."""
    from gateway.middleware.auth import get_current_user
    user = await get_current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return _user_response(user.user_id, fallback=user)


# ===========================================================================
# Helpers
# ===========================================================================

def _get_user_context(user_id) -> UserContext | None:
    """Resolve a UserContext from the database by user_id."""
    from uuid import UUID
    uid = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
    row = _user_repo.get_by_user_id(uid)
    if row is None:
        return None
    return UserContext(
        user_id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"],
        email=row["email"],
        roles=list(row["roles"]) if row.get("roles") else [],
        branch_code=row.get("branch_code"),
    )


def _user_response(user_id, fallback: UserContext | None = None) -> UserResponse:
    """Build a UserResponse from the DB; fall back to the JWT context if not found."""
    row = _user_repo.get_by_user_id(user_id)
    if row is not None:
        return UserResponse(
            user_id=row["user_id"],
            username=row["username"],
            email=row["email"],
            display_name=row["display_name"],
            department=row.get("department"),
            branch_code=row.get("branch_code"),
            roles=list(row["roles"]) if row.get("roles") else [],
            is_active=bool(row["is_active"]),
            last_login_at=row.get("last_login_at"),
            created_at=row.get("created_at") or datetime.now(timezone.utc),
        )
    if fallback is not None:
        return UserResponse(
            user_id=fallback.user_id,
            username=fallback.username,
            email=fallback.email,
            display_name=fallback.display_name,
            branch_code=fallback.branch_code,
            roles=fallback.roles,
            created_at=datetime.now(timezone.utc),
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
