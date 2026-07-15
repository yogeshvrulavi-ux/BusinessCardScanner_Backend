"""Company management routes — CRUD for companies (SuperAdmin only, with /me for any user)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.schemas import CreateCompanyRequest, UpdateCompanyRequest
from auth.constants import AUDIT_COMPANY_CREATED, AUDIT_COMPANY_DELETED, AUDIT_COMPANY_UPDATED, ROLE_ADMIN, ROLE_SUPER_ADMIN
from auth.dependencies import get_current_user, require_role
from auth.password_utils import hash_password
from auth.service import AuthError, register_user
from auth import audit_service
from db.pool import db_cursor

router = APIRouter(prefix="/api/companies", tags=["Companies"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    summary="List all companies",
    dependencies=[Depends(require_role(ROLE_SUPER_ADMIN))],
)
def list_companies(page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200)):
    offset = (page - 1) * limit
    with db_cursor(commit=False) as cur:
        cur.execute("SELECT COUNT(*) AS total FROM companies")
        total = cur.fetchone()["total"]
        cur.execute(
            """
            SELECT id, company_name, company_code, admin_id, address, phone, email, website,
                   status, created_at, updated_at
            FROM companies ORDER BY created_at DESC LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        rows = cur.fetchall()

    items = []
    for row in rows:
        row = dict(row)
        for k in ("id", "admin_id"):
            if row.get(k) is not None:
                row[k] = str(row[k])
        for k in ("created_at", "updated_at"):
            if row.get(k) and hasattr(row[k], "isoformat"):
                row[k] = row[k].isoformat()
        items.append(row)

    return {"items": items, "total": total, "page": page, "limit": limit}


@router.post(
    "",
    summary="Create company + admin user",
    description="Creates a new company and its Admin user in a single transaction.",
    dependencies=[Depends(require_role(ROLE_SUPER_ADMIN))],
)
def create_company(body: CreateCompanyRequest, request: Request):
    user = get_current_user(request)
    meta = {"ip": request.client.host if request.client else "", "user_agent": request.headers.get("user-agent", "")}

    with db_cursor(commit=True) as cur:
        # Check company_code uniqueness
        cur.execute("SELECT 1 FROM companies WHERE company_code = %s", (body.company_code,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Company code already exists.")

        company_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Get ADMIN role id
        cur.execute("SELECT id FROM roles WHERE name = 'ADMIN'")
        admin_role = cur.fetchone()
        if not admin_role:
            raise HTTPException(status_code=500, detail="ADMIN role not seeded.")
        admin_role_id = admin_role["id"]

        # Create admin user first
        cur.execute("SELECT 1 FROM users WHERE LOWER(email) = %s AND deleted_at IS NULL", (body.admin_email.lower(),))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Admin email already exists.")
        cur.execute("SELECT 1 FROM users WHERE LOWER(username) = %s AND deleted_at IS NULL", (body.admin_username.lower(),))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Admin username already exists.")

        admin_id = str(uuid.uuid4())
        # Create admin user WITHOUT company_id first (FK: company doesn't exist yet)
        cur.execute(
            """
            INSERT INTO users (
                id, first_name, last_name, email, username, password_hash,
                role_id, is_active, is_verified, created_by, created_at, updated_at, last_password_change
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (admin_id, body.admin_first_name, body.admin_last_name,
             body.admin_email.lower(), body.admin_username.lower(),
             hash_password(body.admin_password),
             admin_role_id,
             True, True, user["id"], now, now, now),
        )

        # Create company (references admin_id)
        cur.execute(
            """
            INSERT INTO companies (
                id, company_name, company_code, admin_id, address, phone, email, website,
                status, created_at, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,%s)
            """,
            (company_id, body.company_name, body.company_code, admin_id,
             body.address, body.phone, body.email, body.website, now, now),
        )

        # Now link admin user → company
        cur.execute(
            "UPDATE users SET company_id = %s WHERE id = %s",
            (company_id, admin_id),
        )

    audit_service.log_action(user["id"], AUDIT_COMPANY_CREATED, ip=meta["ip"], user_agent=meta["user_agent"],
                             new_value={"company_id": company_id, "company_name": body.company_name})

    return {
        "success": True,
        "company": {"id": company_id, "company_name": body.company_name, "company_code": body.company_code},
        "admin": {"id": admin_id, "email": body.admin_email},
    }


@router.get(
    "/me",
    summary="Get own company",
    description="Returns the company the authenticated user belongs to.",
)
def get_my_company(request: Request):
    user = get_current_user(request)
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=404, detail="You are not associated with any company.")

    with db_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM companies WHERE id = %s", (company_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Company not found.")

    row = dict(row)
    for k in ("id", "admin_id"):
        if row.get(k) is not None:
            row[k] = str(row[k])
    for k in ("created_at", "updated_at"):
        if row.get(k) and hasattr(row[k], "isoformat"):
            row[k] = row[k].isoformat()
    return row


@router.get(
    "/{company_id}",
    summary="Get company details",
    dependencies=[Depends(require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN))],
)
def get_company(company_id: str, request: Request):
    user = get_current_user(request)
    if user["role"] == ROLE_ADMIN and str(user.get("company_id")) != company_id:
        raise HTTPException(status_code=403, detail="Forbidden.")

    with db_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM companies WHERE id = %s", (company_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Company not found.")

    row = dict(row)
    for k in ("id", "admin_id"):
        if row.get(k) is not None:
            row[k] = str(row[k])
    for k in ("created_at", "updated_at"):
        if row.get(k) and hasattr(row[k], "isoformat"):
            row[k] = row[k].isoformat()
    return row


@router.put(
    "/{company_id}",
    summary="Update company",
    dependencies=[Depends(require_role(ROLE_SUPER_ADMIN))],
)
def update_company(company_id: str, body: UpdateCompanyRequest, request: Request):
    user = get_current_user(request)
    meta = {"ip": request.client.host if request.client else "", "user_agent": request.headers.get("user-agent", "")}

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"success": True, "message": "No fields to update."}

    updates["updated_at"] = datetime.now(timezone.utc)
    set_parts = []
    params: list = []
    for col, val in updates.items():
        set_parts.append(f"{col} = %s")
        params.append(val)
    params.append(company_id)

    with db_cursor() as cur:
        cur.execute(f"UPDATE companies SET {', '.join(set_parts)} WHERE id = %s", params)
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Company not found.")

    audit_service.log_action(user["id"], AUDIT_COMPANY_UPDATED, ip=meta["ip"], user_agent=meta["user_agent"],
                             new_value={"company_id": company_id, "updates": list(updates.keys())})
    return {"success": True, "message": "Company updated."}


@router.delete(
    "/{company_id}",
    summary="Soft delete company",
    dependencies=[Depends(require_role(ROLE_SUPER_ADMIN))],
)
def delete_company(company_id: str, request: Request):
    user = get_current_user(request)
    meta = {"ip": request.client.host if request.client else "", "user_agent": request.headers.get("user-agent", "")}

    with db_cursor() as cur:
        cur.execute("UPDATE companies SET status = 'deleted', updated_at = %s WHERE id = %s AND status != 'deleted'",
                    (datetime.now(timezone.utc), company_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Company not found or already deleted.")

    audit_service.log_action(user["id"], AUDIT_COMPANY_DELETED, ip=meta["ip"], user_agent=meta["user_agent"],
                             new_value={"company_id": company_id})
    return {"success": True, "message": "Company deleted (soft)."}
