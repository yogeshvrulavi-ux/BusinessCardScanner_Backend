"""Password-reset API — PostgreSQL + SMTP (RBAC users table). Neon Auth removed."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from auth.service import AuthError, forgot_password, reset_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/password-reset", tags=["Auth"])


class SendOtpRequest(BaseModel):
    email: EmailStr


class ConfirmResetRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    password: str = Field(min_length=8)
    confirmPassword: str = Field(min_length=8)


def _meta(request: Request) -> dict[str, str]:
    return {
        "ip": request.client.host if request.client else "",
        "user_agent": request.headers.get("user-agent", ""),
    }


@router.post("/send-otp")
async def send_otp(body: SendOtpRequest, request: Request):
    meta = _meta(request)
    try:
        return forgot_password(body.email, ip=meta["ip"], user_agent=meta["user_agent"])
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except Exception as exc:
        logger.exception("send-otp failed")
        raise HTTPException(
            status_code=500,
            detail=f"Could not send verification code: {exc}",
        ) from exc


@router.post("/confirm")
async def confirm_reset(body: ConfirmResetRequest, request: Request):
    if body.password != body.confirmPassword:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    meta = _meta(request)
    try:
        return reset_password(
            body.email,
            body.otp,
            body.password,
            ip=meta["ip"],
            user_agent=meta["user_agent"],
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except Exception as exc:
        logger.exception("password reset confirm failed")
        raise HTTPException(status_code=500, detail="Could not reset password.") from exc
