"""
Auth Middleware — Request/response processing for authentication.

Responsibilities:
  1. Add X-Org-Id header to responses (for debugging / client awareness)
  2. Log authentication events to audit log
  3. Handle auth errors with consistent JSON responses
  4. Rate-limit failed auth attempts

This middleware sits between CORS and route handlers.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .config import get_auth_config

logger = logging.getLogger("agentcost.auth.middleware")

# Simple in-memory rate limiter for failed auth attempts
_fail_counts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 300  # 5 minutes
_RATE_LIMIT_MAX = 20  # max failed attempts per window


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that adds auth-related headers and logging to every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        get_auth_config()
        start_time = time.time()

        # Skip auth processing for health/docs endpoints
        path = request.url.path
        if path in ("/api/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        # Rate limit check for auth endpoints
        if path.startswith("/auth/"):
            client_ip = _get_client_ip(request)
            if _is_rate_limited(client_ip):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many authentication attempts. Try again later."
                    },
                )

        # Process request
        response = await call_next(request)

        # Add auth headers to response
        duration_ms = (time.time() - start_time) * 1000

        # If the request was authenticated, add org context header
        auth_context = getattr(request.state, "auth_context", None)
        if auth_context and hasattr(auth_context, "org_id"):
            response.headers["X-Org-Id"] = auth_context.org_id

        # Track failed auth attempts
        if response.status_code == 401 and path.startswith("/auth/"):
            client_ip = _get_client_ip(request)
            _record_failure(client_ip)

        # Log auth-related requests
        if path.startswith("/auth/") or response.status_code in (401, 403):
            logger.info(
                "auth path=%s method=%s status=%d duration=%.1fms",
                path,
                request.method,
                response.status_code,
                duration_ms,
            )

        return response


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For for proxied requests."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_rate_limited(client_ip: str) -> bool:
    """Check if a client IP has exceeded the failed auth rate limit."""
    now = time.time()
    attempts = _fail_counts.get(client_ip, [])
    # Clean old entries
    recent = [t for t in attempts if (now - t) < _RATE_LIMIT_WINDOW]
    _fail_counts[client_ip] = recent
    return len(recent) >= _RATE_LIMIT_MAX


def _record_failure(client_ip: str) -> None:
    """Record a failed authentication attempt."""
    _fail_counts[client_ip].append(time.time())
