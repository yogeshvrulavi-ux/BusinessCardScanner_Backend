"""Audit log routes — view audit logs (SuperAdmin sees all, Admin sees own company)."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from auth.constants import ROLE_ADMIN, ROLE_SUPER_ADMIN
from auth.dependencies import get_current_user, require_role
from auth.audit_service import get_logs

router = APIRouter(prefix="/api/audit-logs", tags=["Audit"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    summary="View audit logs",
    description="SuperAdmin sees all logs. Admin sees only own company's logs.",
    dependencies=[Depends(require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN))],
)
def list_audit_logs(
    request: Request,
    user_id: str | None = Query(None, description="Filter by user ID"),
    action: str | None = Query(None, description="Filter by action type"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    user = get_current_user(request)
    company_id = None
    if user["role"] == ROLE_ADMIN:
        company_id = user.get("company_id")

    return get_logs(
        user_id=user_id,
        action=action,
        company_id=company_id,
        page=page,
        limit=limit,
    )
