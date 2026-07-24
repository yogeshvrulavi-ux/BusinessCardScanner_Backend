#!/usr/bin/env python3
"""Update SuperAdmin login email from .env — does NOT delete any data.

Finds the existing SUPER_ADMIN user by role and sets users.email to
SUPERADMIN_EMAIL from .env. Password and all other rows are left alone.

Usage (from BusinessCardScanner_Backend):
  1. Edit .env → SUPERADMIN_EMAIL=your-new@email.com
  2. python scripts/update_superadmin_email.py

Optional: also sync password from SUPERADMIN_PASSWORD:
  python scripts/update_superadmin_email.py --with-password
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.env_loader import load_env  # noqa: E402

load_env()


def main() -> int:
    parser = argparse.ArgumentParser(description="Update SuperAdmin email from .env (no data wipe).")
    parser.add_argument(
        "--with-password",
        action="store_true",
        help="Also set password from SUPERADMIN_PASSWORD in .env.",
    )
    args = parser.parse_args()

    from auth.password_utils import hash_password, validate_password_policy
    from db.pool import close_pool, db_cursor, init_pool

    new_email = (os.getenv("SUPERADMIN_EMAIL") or "").strip().lower()
    if not new_email or "@" not in new_email:
        print("SUPERADMIN_EMAIL is missing or invalid in .env", file=sys.stderr)
        return 1

    password = os.getenv("SUPERADMIN_PASSWORD") or ""
    if args.with_password:
        if not password:
            print("SUPERADMIN_PASSWORD is not set in .env", file=sys.stderr)
            return 1
        ok, errors = validate_password_policy(password)
        if not ok:
            print("Password does not meet policy:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

    init_pool()
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT u.id, u.email
                FROM users u
                JOIN roles r ON r.id = u.role_id
                WHERE upper(r.name) = 'SUPER_ADMIN' AND u.deleted_at IS NULL
                ORDER BY u.created_at ASC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                print("No SUPER_ADMIN user found in the database.", file=sys.stderr)
                return 1

            old_email = str(row["email"] or "").strip().lower()
            user_id = row["id"]

            if old_email == new_email and not args.with_password:
                print(f"SuperAdmin email already set to {new_email}. Nothing to change.")
                return 0

            # Avoid unique-email clash with another account.
            cur.execute(
                """
                SELECT id FROM users
                WHERE lower(email) = %s AND id <> %s AND deleted_at IS NULL
                """,
                (new_email, user_id),
            )
            clash = cur.fetchone()
            if clash:
                print(
                    f"Cannot change email: {new_email} is already used by another user.",
                    file=sys.stderr,
                )
                return 1

            now = datetime.now(timezone.utc)
            if args.with_password:
                cur.execute(
                    """
                    UPDATE users
                    SET email = %s,
                        password_hash = %s,
                        last_password_change = %s,
                        updated_at = %s,
                        failed_login_attempts = 0,
                        locked_until = NULL
                    WHERE id = %s
                    """,
                    (new_email, hash_password(password), now, now, user_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE users
                    SET email = %s,
                        updated_at = %s,
                        failed_login_attempts = 0,
                        locked_until = NULL
                    WHERE id = %s
                    """,
                    (new_email, now, user_id),
                )

        try:
            from auth import session_service, token_service

            token_service.revoke_all_for_user(str(user_id))
            session_service.end_all_sessions(str(user_id))
        except Exception as exc:  # noqa: BLE001
            print(f"Email updated; session revoke skipped: {exc}")

        print(f"SuperAdmin email updated: {old_email} → {new_email}")
        if args.with_password:
            print("Password also updated from SUPERADMIN_PASSWORD.")
        print("No other data was deleted or modified.")
        print("Sign in with the new SUPERADMIN_EMAIL from .env.")
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
