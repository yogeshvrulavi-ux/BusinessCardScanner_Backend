"""FastAPI dependency functions for authentication and authorization."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException, Request

from auth.constants import ROLE_SUPER_ADMIN


def get_current_user(request: Request) -> dict[str, Any]:
    """Return the authenticated user dict attached by RBACMiddleware.

    Raises 401 if not authenticated.
    """
    user = getattr(request.state, "auth_user", None)
    if not user or not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if not user.get("id"):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def require_role(*roles: str) -> Callable:
    """Return a dependency that enforces the user has one of the given roles.

    Usage in a route:
        @router.get("/...", dependencies=[Depends(require_role("ADMIN", "SUPER_ADMIN"))])
    """
    def _dependency(request: Request) -> dict[str, Any]:
        user = get_current_user(request)
        user_role = user.get("role", "")
        if user_role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient role. Required: {', '.join(roles)}. Current: {user_role}.",
            )
        return user
    return _dependency


def require_company_access(request: Request, target_company_id: str | None = None) -> dict[str, Any]:
    """Ensure the authenticated user belongs to the target company (or is SuperAdmin).

    Use this when a route param includes a company_id or user_id that must be scoped.
    """
    user = get_current_user(request)
    if user.get("role") == ROLE_SUPER_ADMIN:
        return user
    user_company = user.get("company_id")
    if not user_company:
        raise HTTPException(status_code=403, detail="You do not belong to any company.")
    if target_company_id and str(target_company_id) != str(user_company):
        raise HTTPException(status_code=403, detail="Access to another company's data is forbidden.")
    return user


def require_active_company(request: Request) -> dict[str, Any]:
    """Ensure the authenticated user's company is active (SuperAdmin bypasses)."""
    user = get_current_user(request)
    if user.get("role") == ROLE_SUPER_ADMIN:
        return user
    if not user.get("company_id"):
        return user  # No company assigned — not an error per se
    # Company status is checked by the middleware already, but we re-check for safety
    company_status = user.get("company_status", "active")
    if company_status != "active":
        raise HTTPException(status_code=403, detail="Your company account is inactive.")
    return user


def require_permission(permission_name: str) -> Callable:
    """Return a dependency that checks the user's role has the named permission."""
    def _dependency(request: Request) -> dict[str, Any]:
        user = get_current_user(request)
        permissions: list[str] = user.get("permissions", [])
        if user.get("role") == ROLE_SUPER_ADMIN:
            return user  # SuperAdmin always has all permissions
        if permission_name not in permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required permission: '{permission_name}'.",
            )
        return user
    return _dependency
