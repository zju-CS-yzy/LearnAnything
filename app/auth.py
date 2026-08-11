"""Shared authentication and system-authorization dependencies."""

from typing import Optional

from fastapi import Header, HTTPException

from core.user_manager import get_user_manager


ANONYMOUS_USER_IDS = {"default", "anonymous"}


def get_current_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
) -> str:
    """Resolve a request identity without trusting arbitrary X-User-ID values."""
    if authorization:
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization scheme")
        token = authorization[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Bearer token is required")
        user_id = get_user_manager().verify_token(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Bearer token is invalid or expired")
        return user_id

    if x_user_id in ANONYMOUS_USER_IDS:
        return x_user_id
    if x_user_id:
        raise HTTPException(status_code=401, detail="Valid Bearer token required")
    return "default"


def require_authenticated_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
) -> str:
    """Require a password-authenticated user and return its user id."""
    user_id = get_current_user_id(x_user_id, authorization)
    if user_id in ANONYMOUS_USER_IDS:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def require_admin(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
) -> str:
    """Require an authenticated application administrator."""
    user_id = require_authenticated_user(x_user_id, authorization)
    if not get_user_manager().is_system_admin(user_id):
        raise HTTPException(status_code=403, detail="System administrator role required")
    return user_id


def resolve_legacy_user_id(
    x_user_id: Optional[str],
    authorization: Optional[str],
    legacy_user_id: Optional[str] = None,
) -> str:
    """Resolve identity for endpoints that still accept a legacy user_id value."""
    effective = get_current_user_id(x_user_id, authorization)
    if effective in ANONYMOUS_USER_IDS and legacy_user_id in ANONYMOUS_USER_IDS:
        return legacy_user_id
    return effective


def get_effective_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
) -> str:
    """FastAPI dependency returning the effective request user."""
    return get_current_user_id(x_user_id, authorization)
