#!/usr/bin/env python3
"""
Provision Admin + User via existing HTTP APIs only (invitation flow).

Flow:
  1. SuperAdmin login
  2. POST /api/companies  → invites Admin
  3. POST /api/invitations/accept  → Admin registers (own password)
  4. Admin login
  5. POST /api/invitations  → invites User
  6. POST /api/invitations/accept  → User registers (own password)
  7. Verify both can login

Requires APP_ENV=development so invite responses include invite_token
(same value emailed as the Accept link). Production never returns the token.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.env_loader import load_env  # noqa: E402

load_env()

BASE = (
    os.getenv("BACKEND_BASE_URL")
    or os.getenv("API_BASE_URL")
    or "http://127.0.0.1:5000"
).rstrip("/")

SUPER_EMAIL = os.getenv("SUPERADMIN_EMAIL", "superadmin@ulavi.com")
SUPER_PASS = os.getenv("SUPERADMIN_PASSWORD", "SuperAdmin@123")

ADMIN_EMAIL = "admin@ulavi.com"
ADMIN_PASS = "Admin@123"
ADMIN_USER = "admin"

USER_EMAIL = "user@ulavi.com"
USER_PASS = "User@123"
USER_USER = "user"

COMPANY_NAME = "Demo Company"
COMPANY_CODE = "DEMO001"


def _print(label: str, data) -> None:
    print(f"\n=== {label} ===")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, default=str)[:2000])
    else:
        print(data)


def login(identifier: str, password: str) -> str:
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"identifier": identifier, "password": password},
        timeout=30,
    )
    if not r.ok:
        raise SystemExit(f"Login failed for {identifier}: {r.status_code} {r.text}")
    body = r.json()
    token = body.get("access_token") or body.get("tokens", {}).get("access_token")
    if not token:
        raise SystemExit(f"No access_token in login response: {body}")
    return token


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def revoke_pending_if_any(token: str, email: str) -> None:
    r = requests.get(
        f"{BASE}/api/invitations",
        headers=auth_headers(token),
        params={"status": "pending"},
        timeout=30,
    )
    if not r.ok:
        return
    for item in r.json().get("items") or []:
        if str(item.get("email", "")).lower() == email.lower():
            rid = item.get("id")
            if rid:
                requests.post(
                    f"{BASE}/api/invitations/{rid}/revoke",
                    headers=auth_headers(token),
                    timeout=30,
                )
                print(f"Revoked pending invite for {email}")


def main() -> int:
    print(f"API base: {BASE}")
    if (os.getenv("APP_ENV") or "").lower() != "development":
        print("Warning: APP_ENV is not development — invite_token may be missing.")

    # 1) SuperAdmin login
    sa_token = login(SUPER_EMAIL, SUPER_PASS)
    print("SuperAdmin login OK")

    revoke_pending_if_any(sa_token, ADMIN_EMAIL)

    # 2) SuperAdmin → invite Admin (company create API)
    r = requests.post(
        f"{BASE}/api/companies",
        headers=auth_headers(sa_token),
        json={
            "company_name": COMPANY_NAME,
            "company_code": COMPANY_CODE,
            "admin_email": ADMIN_EMAIL,
            "address": "Local",
            "email": ADMIN_EMAIL,
        },
        timeout=30,
    )
    if r.status_code == 409:
        # Company code exists — invite Admin via invitations API instead
        print("Company code exists; inviting Admin via /api/invitations")
        r = requests.post(
            f"{BASE}/api/invitations",
            headers=auth_headers(sa_token),
            json={
                "email": ADMIN_EMAIL,
                "role": "ADMIN",
                "company_name": COMPANY_NAME,
                "company_code": f"{COMPANY_CODE}A",
            },
            timeout=30,
        )
        if not r.ok:
            raise SystemExit(f"Invite Admin failed: {r.status_code} {r.text}")
        invite = r.json()
        admin_token_invite = invite.get("invite_token")
    else:
        if not r.ok:
            raise SystemExit(f"Create company / invite Admin failed: {r.status_code} {r.text}")
        body = r.json()
        _print("Company invite", body)
        invite = body.get("invitation") or body
        admin_token_invite = invite.get("invite_token")

    if not admin_token_invite:
        raise SystemExit(
            "invite_token missing. Ensure APP_ENV=development and restart the backend."
        )

    # 3) Admin accepts invitation (public API)
    r = requests.post(
        f"{BASE}/api/invitations/accept",
        json={
            "token": admin_token_invite,
            "first_name": "Demo",
            "last_name": "Admin",
            "password": ADMIN_PASS,
            "confirm_password": ADMIN_PASS,
            "username": ADMIN_USER,
            "phone": "+910000000001",
            "company_name": COMPANY_NAME,
            "company_code": COMPANY_CODE,
        },
        timeout=30,
    )
    if not r.ok:
        raise SystemExit(f"Admin accept failed: {r.status_code} {r.text}")
    _print("Admin registered", r.json())

    # 4) Admin login
    admin_token = login(ADMIN_EMAIL, ADMIN_PASS)
    print("Admin login OK")

    revoke_pending_if_any(admin_token, USER_EMAIL)

    # 5) Admin → invite User
    r = requests.post(
        f"{BASE}/api/invitations",
        headers=auth_headers(admin_token),
        json={"email": USER_EMAIL, "role": "USER"},
        timeout=30,
    )
    if not r.ok:
        raise SystemExit(f"Invite User failed: {r.status_code} {r.text}")
    user_invite = r.json()
    _print("User invite", user_invite)
    user_token_invite = user_invite.get("invite_token")
    if not user_token_invite:
        raise SystemExit("invite_token missing on user invite response.")

    # 6) User accepts
    r = requests.post(
        f"{BASE}/api/invitations/accept",
        json={
            "token": user_token_invite,
            "first_name": "Demo",
            "last_name": "User",
            "password": USER_PASS,
            "confirm_password": USER_PASS,
            "username": USER_USER,
            "phone": "+910000000002",
        },
        timeout=30,
    )
    if not r.ok:
        raise SystemExit(f"User accept failed: {r.status_code} {r.text}")
    _print("User registered", r.json())

    # 7) Verify logins
    login(ADMIN_EMAIL, ADMIN_PASS)
    login(USER_EMAIL, USER_PASS)

    print("\nDone — accounts created via invitation APIs only.")
    print("-----------------------------------------------")
    print(f"Admin  {ADMIN_EMAIL} / {ADMIN_PASS}  (username: {ADMIN_USER})")
    print(f"User   {USER_EMAIL} / {USER_PASS}  (username: {USER_USER})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
