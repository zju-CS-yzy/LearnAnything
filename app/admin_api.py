"""Local administrator bootstrap and administrator user-management API."""

import ipaddress
import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import require_admin, require_authenticated_user
from config.settings import DATA_ROOT
from core.user_manager import get_user_manager


router = APIRouter(prefix="/api/admin", tags=["admin"])
AUDIT_LOG_PATH = DATA_ROOT / "logs" / "admin_audit.jsonl"

_BOOTSTRAP_FAILURE_LIMIT = 5
_BOOTSTRAP_FAILURE_WINDOW_SECONDS = 15 * 60
_bootstrap_failures: Dict[str, Deque[float]] = defaultdict(deque)
_bootstrap_failure_lock = threading.Lock()
_audit_lock = threading.Lock()


class BootstrapStatus(BaseModel):
    bootstrap_required: bool
    can_claim_locally: bool


class BootstrapClaimRequest(BaseModel):
    password: str = Field(min_length=6, max_length=256)


class AdminUserItem(BaseModel):
    user_id: str
    username: str
    display_name: str
    system_role: Literal["admin", "user"]


class AdminUserListResponse(BaseModel):
    users: List[AdminUserItem]
    admin_count: int


class SystemRoleUpdateRequest(BaseModel):
    role: Literal["admin", "user"]
    current_password: str = Field(min_length=6, max_length=256)


def _is_loopback_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        address = ipaddress.ip_address(host)
        if address.version == 6 and address.ipv4_mapped:
            address = address.ipv4_mapped
        return address.is_loopback
    except ValueError:
        return False


def _failure_key(request: Request, user_id: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{user_id}"


def _prune_failures(key: str, now: float) -> Deque[float]:
    failures = _bootstrap_failures[key]
    cutoff = now - _BOOTSTRAP_FAILURE_WINDOW_SECONDS
    while failures and failures[0] < cutoff:
        failures.popleft()
    return failures


def _check_bootstrap_rate_limit(key: str) -> None:
    with _bootstrap_failure_lock:
        if len(_prune_failures(key, time.monotonic())) >= _BOOTSTRAP_FAILURE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Too many failed administrator initialization attempts",
            )


def _record_bootstrap_failure(key: str) -> None:
    with _bootstrap_failure_lock:
        _prune_failures(key, time.monotonic()).append(time.monotonic())


def _clear_bootstrap_failures(key: str) -> None:
    with _bootstrap_failure_lock:
        _bootstrap_failures.pop(key, None)


def _write_audit_event(actor_user_id: str, action: str, details: dict) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": actor_user_id,
        "action": action,
        "details": details,
    }
    with _audit_lock:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        try:
            os.chmod(AUDIT_LOG_PATH, 0o600)
        except OSError:
            pass


@router.get("/bootstrap/status", response_model=BootstrapStatus)
def get_bootstrap_status(request: Request):
    required = get_user_manager().count_system_admins() == 0
    return BootstrapStatus(
        bootstrap_required=required,
        can_claim_locally=required and _is_loopback_request(request),
    )


@router.post("/bootstrap/claim")
def claim_first_administrator(
    payload: BootstrapClaimRequest,
    request: Request,
    user_id: str = Depends(require_authenticated_user),
):
    if not _is_loopback_request(request):
        raise HTTPException(
            status_code=403,
            detail="Administrator initialization is only available from this device",
        )

    key = _failure_key(request, user_id)
    _check_bootstrap_rate_limit(key)
    manager = get_user_manager()
    try:
        manager.claim_first_system_admin(user_id, payload.password)
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message:
            raise HTTPException(status_code=409, detail=message)
        if "password is incorrect" in message:
            _record_bootstrap_failure(key)
            raise HTTPException(status_code=401, detail=message)
        raise HTTPException(status_code=400, detail=message)

    _clear_bootstrap_failures(key)
    _write_audit_event(user_id, "admin.bootstrap.claim", {"target_user_id": user_id})
    return {
        "success": True,
        "system_role": "admin",
        "message": "System administrator initialized",
    }


@router.get("/users", response_model=AdminUserListResponse)
def list_administrator_users(admin_user_id: str = Depends(require_admin)):
    manager = get_user_manager()
    users = [
        AdminUserItem(
            user_id=user["user_id"],
            username=user["username"],
            display_name=user.get("display_name") or user["username"],
            system_role=user.get("system_role", "user"),
        )
        for user in manager.list_users()
        if user["user_id"] not in ("default", "anonymous")
    ]
    return AdminUserListResponse(users=users, admin_count=manager.count_system_admins())


@router.post("/users/{target_user_id}/role")
def update_administrator_user_role(
    target_user_id: str,
    payload: SystemRoleUpdateRequest,
    admin_user_id: str = Depends(require_admin),
):
    manager = get_user_manager()
    if not manager.verify_user_password(admin_user_id, payload.current_password):
        raise HTTPException(status_code=401, detail="Current administrator password is incorrect")
    if not manager.get_user(target_user_id):
        raise HTTPException(status_code=404, detail="User does not exist")

    try:
        manager.set_system_role(target_user_id, payload.role)
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "last system administrator" in message else 400
        raise HTTPException(status_code=status_code, detail=message)

    _write_audit_event(
        admin_user_id,
        "admin.role.update",
        {"target_user_id": target_user_id, "role": payload.role},
    )
    return {"success": True, "user_id": target_user_id, "system_role": payload.role}
