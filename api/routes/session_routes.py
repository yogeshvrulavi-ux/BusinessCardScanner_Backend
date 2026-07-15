"""Session management routes — list active sessions, logout specific/all devices."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from auth.dependencies import get_current_user
from auth.session_service import end_all_sessions, end_session, get_active_sessions
from auth.token_service import revoke_all_for_user

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    summary="List active sessions",
    description="Returns all active sessions for the authenticated user (with device/browser info).",
)
def list_sessions(request: Request):
    user = get_current_user(request)
    sessions = get_active_sessions(user["id"])
    return {"sessions": sessions, "total": len(sessions)}


@router.delete(
    "/all",
    summary="Logout all devices",
    description="Ends all sessions and revokes all refresh tokens for the authenticated user.",
)
def logout_all_devices(request: Request):
    user = get_current_user(request)
    ended = end_all_sessions(user["id"])
    revoked = revoke_all_for_user(user["id"])
    return {"success": True, "sessions_ended": ended, "tokens_revoked": revoked}


@router.delete(
    "/{session_id}",
    summary="Logout specific device",
    description="Ends a single session by its ID. Only the session owner can do this.",
)
def logout_device(session_id: str, request: Request):
    user = get_current_user(request)
    sessions = get_active_sessions(user["id"])
    owned = any(s["id"] == session_id for s in sessions)
    if not owned:
        raise HTTPException(status_code=404, detail="Session not found or not owned by you.")

    end_session(session_id)
    return {"success": True, "message": "Session ended."}
