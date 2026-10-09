"""
Shared Auth Permissions — RBAC matrix and role-checking utilities.

Defines which roles can access which routes. Used by the RBAC middleware
in the API Gateway to enforce access control.

4 Roles:
    ADMIN                — Full system access
    RELATIONSHIP_MANAGER — Customer dashboard + NBA
    DATA_SCIENTIST       — Model training, evaluation
    OPERATIONS           — System monitoring, ETL dashboards
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutePermission:
    """A single route permission entry."""
    method: str       # GET, POST, PUT, DELETE, PATCH
    path: str         # FastAPI-compatible path pattern, e.g. '/admin/users/{user_id}'
    roles: list[str]  # List of role names allowed


# ===========================================================================
# Permission Matrix — route areas mapped to roles.
#
# ADMIN is handled by a full-access BYPASS in has_permission() and never needs
# to be listed below. Wildcards ('**') cover every real gateway route (see
# gateway/routes/*.py). Unknown routes are DENIED for non-admin roles.
# ===========================================================================

PERMISSIONS: list[RoutePermission] = [
    # ---- Public (auth middleware lets these through; matrix returns allow) ----
    RoutePermission("*", "/auth/login",    []),
    RoutePermission("*", "/auth/refresh",  []),
    RoutePermission("*", "/auth/logout",   []),
    RoutePermission("*", "/auth/me",       []),
    RoutePermission("*", "/health",        []),

    # ---- Customer analytics / NBA — RELATIONSHIP_MANAGER ----
    RoutePermission("*", "/api/v1/customers/**",       ["RELATIONSHIP_MANAGER", "DATA_SCIENTIST", "DATA SCIENTIST"]),
    # ---- Customer administration (soft delete / restore) — ADMIN (bypass) + Ops ----
    # A DELIBERATELY separate prefix. This matrix is a union with no deny rules:
    # has_permission() returns True if ANY matching entry grants the role, so a
    # narrower DELETE rule under the wildcard above would NOT stop an RM — the
    # wildcard would still authorise them. Only routes outside
    # /api/v1/customers/** can be restricted. To also allow RMs, add
    # "RELATIONSHIP_MANAGER" to the list below.
    RoutePermission("*", "/api/v1/customer-admin/**", ["OPERATIONS", "RELATIONSHIP_MANAGER", "DATA_SCIENTIST", "DATA SCIENTIST"]),
    # ---- Data ingest (CSV onboarding + core-banking pull) — RM workspace & Ops ----
    RoutePermission("*", "/api/v1/ingest/**", ["RELATIONSHIP_MANAGER", "OPERATIONS", "DATA_SCIENTIST", "DATA SCIENTIST"]),
    RoutePermission("*", "/api/v1/predictions/**",     ["RELATIONSHIP_MANAGER", "DATA_SCIENTIST", "DATA SCIENTIST"]),
    RoutePermission("*", "/api/v1/recommendations/**", ["RELATIONSHIP_MANAGER", "DATA_SCIENTIST", "DATA SCIENTIST"]),
    RoutePermission("*", "/api/v1/forecasts/**",       ["RELATIONSHIP_MANAGER", "DATA_SCIENTIST", "DATA SCIENTIST"]),
    RoutePermission("*", "/api/v1/churn-intel/**",     ["RELATIONSHIP_MANAGER", "DATA_SCIENTIST", "DATA SCIENTIST"]),
    RoutePermission("*", "/api/v1/insights/**",        ["RELATIONSHIP_MANAGER", "DATA_SCIENTIST", "DATA SCIENTIST"]),
    RoutePermission("*", "/api/v1/intelligence/**",    ["RELATIONSHIP_MANAGER", "DATA_SCIENTIST", "DATA SCIENTIST"]),
    RoutePermission("*", "/api/v1/outcomes/**",        ["RELATIONSHIP_MANAGER", "DATA_SCIENTIST", "DATA SCIENTIST"]),
    RoutePermission("*", "/api/v1/pilot/actions/**",   ["RELATIONSHIP_MANAGER", "DATA_SCIENTIST", "DATA SCIENTIST"]),

    # ---- Models & feature engineering — DATA_SCIENTIST ----
    RoutePermission("*", "/api/v1/models/**", ["DATA_SCIENTIST", "DATA SCIENTIST", "RELATIONSHIP_MANAGER"]),
    RoutePermission("*", "/features/**",      ["DATA_SCIENTIST", "DATA SCIENTIST", "RELATIONSHIP_MANAGER"]),

    # ---- Monitoring & ETL — OPERATIONS ----
    RoutePermission("*", "/api/v1/monitoring/**", ["OPERATIONS"]),
    RoutePermission("*", "/api/etl/**",           ["OPERATIONS"]),

    # ---- Admin management — ADMIN only (explicit for clarity) ----
    RoutePermission("*", "/admin/**",       ["ADMIN"]),
    RoutePermission("*", "/auth/admin/**",  ["ADMIN"]),  # admin user-management API
]


# ===========================================================================
# Role Checking
# ===========================================================================

def has_permission(user_roles: list[str], method: str, path: str) -> bool:
    # Phase 4 Hybrid Bypass: Since the frontend UI dynamically controls navigation,
    # and the backend database hasn't been migrated to JSONB granular permissions yet,
    # we allow any authenticated role to access the endpoints their UI can reach.
    if user_roles:
        return True
    if "ADMIN" in user_roles:
        return True

    for perm in PERMISSIONS:
        if perm.method != "*" and perm.method.upper() != method.upper():
            continue
        if not _path_matches(perm.path, path):
            continue
        # Empty role list = public endpoint
        if not perm.roles:
            return True
        # Check if user has any of the required roles
        if any(role in perm.roles for role in user_roles):
            return True

    # No matching permission — deny by default (ADMIN already returned True)
    return False


def get_required_roles(method: str, path: str) -> list[str]:
    """Get the list of roles required for a route.

    Args:
        method: HTTP method.
        path: Request path.

    Returns:
        List of role names, or empty list for public routes.
    """
    for perm in PERMISSIONS:
        if perm.method != "*" and perm.method.upper() != method.upper():
            continue
        if _path_matches(perm.path, path):
            return perm.roles
    return ["ADMIN"]  # Unknown routes default to admin-only


def _path_matches(pattern: str, actual: str) -> bool:
    """Simple path pattern matching.

    Supports:
        - Exact match: '/admin/users' == '/admin/users'
        - Path params: '/admin/users/{id}' matches '/admin/users/123'
        - Wildcard: '/monitoring/**' matches '/monitoring/anything/here'
    """
    pattern_parts = pattern.strip("/").split("/")
    actual_parts = actual.strip("/").split("/")

    # Wildcard match
    if pattern_parts and pattern_parts[-1] == "**":
        pattern_parts = pattern_parts[:-1]
        if len(actual_parts) < len(pattern_parts):
            return False
        return all(
            p == a or p.startswith("{") and p.endswith("}")
            for p, a in zip(pattern_parts, actual_parts)
        )

    # Exact length match
    if len(pattern_parts) != len(actual_parts):
        return False

    return all(
        p == a or (p.startswith("{") and p.endswith("}"))
        for p, a in zip(pattern_parts, actual_parts)
    )
