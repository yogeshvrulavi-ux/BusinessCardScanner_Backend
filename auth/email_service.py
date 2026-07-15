"""Auth-related email sending — welcome, verification, forgot-password OTP."""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _smtp_config() -> dict[str, str]:
    return {
        "host": os.getenv("SMTP_HOST", os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")),
        "port": os.getenv("SMTP_PORT", os.getenv("GMAIL_SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", os.getenv("GMAIL_USER", "")),
        "password": os.getenv("SMTP_PASSWORD", os.getenv("GMAIL_APP_PASSWORD", "")),
        "from": os.getenv("SMTP_FROM", os.getenv("BUSINESS_EMAIL", "noreply@cardsync.ai")),
    }


def _send_email(to: str, subject: str, html_body: str) -> dict:
    cfg = _smtp_config()
    if not cfg["user"] or not cfg["password"]:
        logger.warning("SMTP not configured — skipping email to %s", to)
        return {"sent": False, "reason": "SMTP not configured"}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = to
    msg.set_content(html_body, subtype="html")

    try:
        with smtplib.SMTP(cfg["host"], int(cfg["port"])) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        return {"sent": True}
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)
        return {"sent": False, "error": str(exc)}


def send_welcome_email(to_email: str, full_name: str) -> dict:
    subject = "Welcome to CardSync AI"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color: #0891b2;">Welcome, {full_name}!</h2>
      <p>Your CardSync AI account has been created successfully.</p>
      <p>You can now log in and start managing your contacts and CRM leads.</p>
      <hr style="border: none; border-top: 1px solid #e2e8f0;" />
      <p style="color: #64748b; font-size: 12px;">If you did not expect this email, please ignore it.</p>
    </div>
    """
    return _send_email(to_email, subject, html)


def send_forgot_password_otp(to_email: str, otp_code: str) -> dict:
    subject = "CardSync AI — Password Reset Code"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color: #0891b2;">Password Reset Code</h2>
      <p>Your one-time verification code is:</p>
      <div style="background: #f1f5f9; padding: 16px; border-radius: 8px; text-align: center; margin: 16px 0;">
        <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #0891b2;">{otp_code}</span>
      </div>
      <p style="color: #64748b;">This code expires in 10 minutes. Do not share it with anyone.</p>
    </div>
    """
    return _send_email(to_email, subject, html)


def send_email_verification(to_email: str, token: str, frontend_url: str | None = None) -> dict:
    base = frontend_url or os.getenv("FRONTEND_URL", "http://localhost:5173")
    verify_link = f"{base.rstrip('/')}/verify-email?token={token}"
    subject = "Verify your CardSync AI email"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color: #0891b2;">Verify Your Email</h2>
      <p>Click the button below to verify your email address:</p>
      <a href="{verify_link}"
         style="display: inline-block; padding: 12px 24px; background: #0891b2; color: white;
                border-radius: 8px; text-decoration: none; font-weight: bold;">
        Verify Email
      </a>
      <p style="color: #64748b; margin-top: 16px;">This link expires in 24 hours.</p>
    </div>
    """
    return _send_email(to_email, subject, html)


def send_email_change_verification(to_email: str, token: str, frontend_url: str | None = None) -> dict:
    base = frontend_url or os.getenv("FRONTEND_URL", "http://localhost:5173")
    verify_link = f"{base.rstrip('/')}/verify-email-change?token={token}"
    subject = "CardSync AI — Confirm Email Change"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color: #0891b2;">Confirm Email Change</h2>
      <p>You requested to change your email to <strong>{to_email}</strong>.</p>
      <a href="{verify_link}"
         style="display: inline-block; padding: 12px 24px; background: #0891b2; color: white;
                border-radius: 8px; text-decoration: none; font-weight: bold;">
        Confirm Change
      </a>
      <p style="color: #64748b; margin-top: 16px;">This link expires in 24 hours.</p>
    </div>
    """
    return _send_email(to_email, subject, html)
