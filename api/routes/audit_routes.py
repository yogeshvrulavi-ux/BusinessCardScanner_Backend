"""Audit log routes — SuperAdmin system-wide audit trail."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from auth.constants import ROLE_SUPER_ADMIN
from auth.dependencies import require_role
from auth.audit_service import get_logs

router = APIRouter(prefix="/api/audit-logs", tags=["Audit"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    summary="View audit logs",
    description="SuperAdmin only — system-wide audit trail.",
    dependencies=[Depends(require_role(ROLE_SUPER_ADMIN))],
)
def list_audit_logs(
    user_id: str | None = Query(None, description="Filter by user ID"),
    action: str | None = Query(None, description="Filter by action type"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    return get_logs(
        user_id=user_id,
        action=action,
        company_id=None,
        page=page,
        limit=limit,
    )
