"""Profile routes — self-service for the authenticated user."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from api.schemas import ChangeEmailRequest, ChangePasswordRequest, UpdateProfileRequest
from auth.dependencies import get_current_user
from auth.service import AuthError, change_password, request_email_change
from db.pool import db_cursor

router = APIRouter(prefix="/api/profile", tags=["Profile"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    summary="Get own profile",
    description="Returns the authenticated user's profile information.",
)
def get_profile(request: Request):
    user = get_current_user(request)
    with db_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT u.id, u.email, u.first_name, u.last_name, u.username, u.phone,
                   u.profile_image, u.is_active, u.is_verified, u.company_id,
                   u.last_login, u.last_password_change, u.created_at, u.updated_at,
                   r.name AS role
            FROM users u JOIN roles r ON r.id = u.role_id
            WHERE u.id = %s AND u.deleted_at IS NULL
            """,
            (user["id"],),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found.")

    row = dict(row)
    for k in ("id", "company_id"):
        if row.get(k) is not None:
            row[k] = str(row[k])
    for k in ("last_login", "last_password_change", "created_at", "updated_at"):
        if row.get(k) and hasattr(row[k], "isoformat"):
            row[k] = row[k].isoformat()
    return row


@router.put(
    "",
    summary="Update own profile",
    description="Update first name, last name, and phone number.",
)
def update_profile(body: UpdateProfileRequest, request: Request):
    user = get_current_user(request)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"success": True, "message": "No fields to update."}

    updates["updated_at"] = datetime.now(timezone.utc)
    set_parts = []
    params: list = []
    for col, val in updates.items():
        set_parts.append(f'"{col}" = %s')
        params.append(val)
    params.append(user["id"])

    with db_cursor() as cur:
        cur.execute(f"UPDATE users SET {', '.join(set_parts)} WHERE id = %s AND deleted_at IS NULL", params)
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Profile not found.")

    return {"success": True, "message": "Profile updated."}


@router.post(
    "/change-password",
    summary="Change own password",
    description="Requires current password. Validates new password against enterprise policy.",
)
def change_password_route(body: ChangePasswordRequest, request: Request):
    user = get_current_user(request)
    meta = {"ip": request.client.host if request.client else "", "user_agent": request.headers.get("user-agent", "")}
    try:
        return change_password(
            user["id"], body.current_password, body.new_password,
            ip=meta["ip"], user_agent=meta["user_agent"],
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc


@router.post(
    "/change-email",
    summary="Request email change",
    description="Sends a verification link to the new email address. Email is updated after verification.",
)
def change_email_route(body: ChangeEmailRequest, request: Request):
    user = get_current_user(request)
    meta = {"ip": request.client.host if request.client else "", "user_agent": request.headers.get("user-agent", "")}
    try:
        return request_email_change(user["id"], body.new_email, ip=meta["ip"], user_agent=meta["user_agent"])
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
