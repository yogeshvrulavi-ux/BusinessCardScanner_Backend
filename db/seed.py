"""Seed script — inserts default roles, permissions, and the SuperAdmin user."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from db.pool import db_cursor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default roles
# ---------------------------------------------------------------------------
DEFAULT_ROLES: list[tuple[str, str]] = [
    ("SUPER_ADMIN", "System-wide administrator with full access"),
    ("ADMIN",       "Company administrator — manages own company users and data"),
    ("USER",        "Standard user — limited to own company and own profile"),
]

# ---------------------------------------------------------------------------
# Default permissions + role assignments
# ---------------------------------------------------------------------------
DEFAULT_PERMISSIONS: list[tuple[str, str]] = [
    ("manage_companies", "Create, update, and delete companies"),
    ("manage_admins",    "Create and manage company admins"),
    ("manage_users",     "Create, update, and delete users within a company"),
    ("view_all_data",    "View data across all companies"),
    ("view_company_data","View data within own company"),
    ("manage_profile",   "Update own profile and change password"),
    ("view_audit_logs",  "View audit log entries"),
]

ROLE_PERMISSION_MAP: dict[str, list[str]] = {
    "SUPER_ADMIN": [
        "manage_companies",
        "manage_admins",
        "manage_users",
        "view_all_data",
        "view_company_data",
        "manage_profile",
        "view_audit_logs",
    ],
    "ADMIN": [
        "manage_users",
        "view_company_data",
        "manage_profile",
        "view_audit_logs",
    ],
    "USER": [
        "manage_profile",
    ],
}


def _insert_roles(cur) -> dict[str, int]:
    """Insert roles (idempotent) and return {role_name: role_id}."""
    role_ids: dict[str, int] = {}
    for name, description in DEFAULT_ROLES:
        cur.execute(
            "SELECT id FROM roles WHERE name = %s", (name,)
        )
        row = cur.fetchone()
        if row:
            role_ids[name] = row["id"]
        else:
            cur.execute(
                "INSERT INTO roles (name, description) VALUES (%s, %s) RETURNING id",
                (name, description),
            )
            role_ids[name] = cur.fetchone()["id"]
            logger.info("Seeded role: %s", name)
    return role_ids


def _insert_permissions(cur) -> dict[str, int]:
    """Insert permissions (idempotent) and return {perm_name: perm_id}."""
    perm_ids: dict[str, int] = {}
    for name, description in DEFAULT_PERMISSIONS:
        cur.execute("SELECT id FROM permissions WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            perm_ids[name] = row["id"]
        else:
            cur.execute(
                "INSERT INTO permissions (name, description) VALUES (%s, %s) RETURNING id",
                (name, description),
            )
            perm_ids[name] = cur.fetchone()["id"]
            logger.info("Seeded permission: %s", name)
    return perm_ids


def _insert_role_permissions(cur, role_ids: dict[str, int], perm_ids: dict[str, int]) -> None:
    """Map permissions to roles (idempotent)."""
    for role_name, perm_names in ROLE_PERMISSION_MAP.items():
        role_id = role_ids[role_name]
        for perm_name in perm_names:
            perm_id = perm_ids[perm_name]
            cur.execute(
                "INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (role_id, perm_id),
            )


def _seed_super_admin(cur, role_ids: dict[str, int]) -> None:
    """Create the default SuperAdmin user if it does not already exist."""
    from auth.password_utils import hash_password

    email = os.getenv("SUPERADMIN_EMAIL", "superadmin@ulavi.com").strip()
    password = os.getenv("SUPERADMIN_PASSWORD", "SuperAdmin@123")

    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        logger.info("SuperAdmin already exists (%s) — skipping seed.", email)
        return

    now = datetime.utcnow()
    cur.execute(
        """
        INSERT INTO users (
            first_name, last_name, email, username, password_hash,
            role_id, is_active, is_verified, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            "Super",
            "Admin",
            email,
            "superadmin",
            hash_password(password),
            role_ids["SUPER_ADMIN"],
            True,
            True,
            now,
            now,
        ),
    )
    logger.info("SuperAdmin seeded (%s).", email)


def run_seed() -> None:
    """Idempotent seed: roles → permissions → role_permissions → super-admin user."""
    with db_cursor(commit=True) as cur:
        role_ids = _insert_roles(cur)
        perm_ids = _insert_permissions(cur)
        _insert_role_permissions(cur, role_ids, perm_ids)
        _seed_super_admin(cur, role_ids)
    logger.info("Database seed completed.")
