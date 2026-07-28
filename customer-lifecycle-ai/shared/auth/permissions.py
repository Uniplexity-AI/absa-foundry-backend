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
# Permission Matrix — 4 Roles
# ===========================================================================

PERMISSIONS: list[RoutePermission] = [
    # ---- Auth (public) ----
    RoutePermission("POST",  "/auth/login",    []),
    RoutePermission("POST",  "/auth/refresh",  []),
    RoutePermission("POST",  "/auth/logout",   []),
    RoutePermission("GET",   "/auth/me",       []),

    # ---- Admin — user management ----
    RoutePermission("GET",    "/admin/users",         ["ADMIN"]),
    RoutePermission("POST",   "/admin/users",         ["ADMIN"]),
    RoutePermission("GET",    "/admin/users/{id}",   ["ADMIN"]),
    RoutePermission("PUT",    "/admin/users/{id}",   ["ADMIN"]),
    RoutePermission("DELETE", "/admin/users/{id}",   ["ADMIN"]),

    # ---- Admin — role management ----
    RoutePermission("GET",    "/admin/roles",         ["ADMIN"]),
    RoutePermission("POST",   "/admin/roles",         ["ADMIN"]),

    # ---- Admin — API keys ----
    RoutePermission("GET",    "/admin/api-keys",      ["ADMIN"]),
    RoutePermission("POST",   "/admin/api-keys",      ["ADMIN"]),
    RoutePermission("DELETE", "/admin/api-keys/{id}", ["ADMIN"]),

    # ---- Dashboard — RM + ADMIN ----
    RoutePermission("GET",  "/dashboard/customers",       ["ADMIN", "RELATIONSHIP_MANAGER"]),
    RoutePermission("GET",  "/dashboard/customers/{id}",  ["ADMIN", "RELATIONSHIP_MANAGER"]),
    RoutePermission("POST", "/dashboard/recommendations", ["ADMIN", "RELATIONSHIP_MANAGER"]),
    RoutePermission("GET",  "/dashboard/health-scores",   ["ADMIN", "RELATIONSHIP_MANAGER"]),

    # ---- Models — Data Scientists + ADMIN ----
    RoutePermission("GET",  "/models/registry",        ["ADMIN", "DATA_SCIENTIST"]),
    RoutePermission("POST", "/models/train",            ["ADMIN", "DATA_SCIENTIST"]),
    RoutePermission("GET",  "/models/training-history", ["ADMIN", "DATA_SCIENTIST"]),
    RoutePermission("POST", "/models/deploy",           ["ADMIN"]),
    RoutePermission("POST", "/models/evaluate",         ["ADMIN", "DATA_SCIENTIST"]),

    # ---- Monitoring — Operations + ADMIN ----
    RoutePermission("GET",  "/monitoring/health",    ["ADMIN", "OPERATIONS"]),
    RoutePermission("GET",  "/monitoring/metrics",   ["ADMIN", "OPERATIONS"]),
    RoutePermission("GET",  "/monitoring/pipelines", ["ADMIN", "OPERATIONS"]),

    # ---- ETL — Operations + ADMIN ----
    RoutePermission("GET",  "/api/etl/**", ["ADMIN", "OPERATIONS"]),

    # ---- Feature Engineering — Data Scientists + ADMIN ----
    RoutePermission("POST", "/features/compute-batch",   ["ADMIN", "DATA_SCIENTIST"]),
    RoutePermission("GET",  "/features/{customer_id}",   ["ADMIN", "DATA_SCIENTIST"]),
    RoutePermission("GET",  "/features/{customer_id}/latest", ["ADMIN", "DATA_SCIENTIST"]),
]


# ===========================================================================
# Role Checking
# ===========================================================================

def has_permission(user_roles: list[str], method: str, path: str) -> bool:
    """Check if a user has permission to access a route.

    Args:
        user_roles: List of role names from the JWT.
        method: HTTP method (GET, POST, etc.).
        path: Request path (e.g. '/admin/users/123').

    Returns:
        True if any of the user's roles match the required roles.
    """
    for perm in PERMISSIONS:
        if perm.method.upper() != method.upper():
            continue
        if not _path_matches(perm.path, path):
            continue
        # Empty role list = public endpoint
        if not perm.roles:
            return True
        # Check if user has any of the required roles
        if any(role in perm.roles for role in user_roles):
            return True
        return False

    # No matching route — deny by default
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
        if perm.method.upper() == method.upper() and _path_matches(perm.path, path):
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
