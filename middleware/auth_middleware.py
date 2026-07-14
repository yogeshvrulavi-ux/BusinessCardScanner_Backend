"""HTTP middleware — require Neon Auth bearer token on protected API routes."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config.settings import cors_headers_for_origin
from services.auth_service import is_auth_enabled, is_public_path, verify_neon_session


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if is_public_path(path) or not is_auth_enabled():
            return await call_next(request)

        cors = cors_headers_for_origin(request.headers.get("origin"))

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid authorization header."},
                headers=cors,
            )

        token = auth_header[7:].strip()
        session_payload = await verify_neon_session(token)
        if not session_payload:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired session. Please sign in again."},
                headers=cors,
            )

        request.state.auth_user = session_payload["user"]
        request.state.auth_session = session_payload["session"]
        return await call_next(request)
