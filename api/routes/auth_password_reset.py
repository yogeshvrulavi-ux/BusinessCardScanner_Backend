import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from services.password_reset_service import (
    PasswordResetError,
    confirm_password_reset_async,
    send_password_reset_otp,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/password-reset", tags=["Auth"])


class SendOtpRequest(BaseModel):
    email: EmailStr


class ConfirmResetRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    password: str = Field(min_length=8)
    confirmPassword: str = Field(min_length=8)


@router.post("/send-otp")
async def send_otp(body: SendOtpRequest):
    try:
        return send_password_reset_otp(body.email)
    except PasswordResetError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("send-otp failed")
        raise HTTPException(
            status_code=500,
            detail=f"Could not send verification code: {exc}",
        ) from exc


@router.post("/confirm")
async def confirm_reset(body: ConfirmResetRequest):
    try:
        return await confirm_password_reset_async(
            body.email,
            body.otp,
            body.password,
            body.confirmPassword,
        )
    except PasswordResetError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("password reset confirm failed")
        raise HTTPException(status_code=500, detail="Could not reset password.") from exc
