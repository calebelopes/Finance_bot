"""Web authentication: session cookies + stateless CSRF tokens.

Sessions are stored on the ``users.session_token`` column (already part
of the schema). CSRF tokens are *stateless* HMAC-signed strings — no
server-side state is required, so the same token validates across
multiple uvicorn workers, restarts, and (eventually) replicated
instances. The previous implementation kept a process-local dict, which
silently broke under any horizontal scale-out.

Token format
------------

    <issued_at_unix_ts>.<base64url(HMAC_SHA256(secret, issued_at))>

Validation checks (in order):

1. Two-segment shape with a numeric timestamp.
2. Token age ≤ ``CSRF_TTL_SECONDS``.
3. ``hmac.compare_digest`` over the recomputed signature.

The HMAC secret is read from ``WEB_CSRF_SECRET``; missing it falls back
to a per-process random secret. That fallback is intentionally
ephemeral — production deployments must set the env var or all forms
break on restart, which is loud and easy to spot.
"""

from __future__ import annotations

import base64
import hmac
import logging
import os
import secrets
import time
from hashlib import sha256
from typing import Annotated, Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from utils import db

log = logging.getLogger(__name__)

SESSION_COOKIE = "finance_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days
CSRF_COOKIE = "finance_csrf"
CSRF_TTL_SECONDS = 4 * 3600


_DEV_SECRET: bytes | None = None


def _csrf_secret() -> bytes:
    """Return the HMAC secret for CSRF signing.

    Honors ``WEB_CSRF_SECRET`` first; falls back to a process-local
    random secret if unset (good for local dev, bad for production —
    we log a one-time warning so the operator notices).
    """
    env = os.getenv("WEB_CSRF_SECRET", "").strip()
    if env:
        return env.encode("utf-8")
    global _DEV_SECRET
    if _DEV_SECRET is None:
        _DEV_SECRET = secrets.token_bytes(32)
        log.warning(
            "WEB_CSRF_SECRET is not set — using an ephemeral per-process "
            "secret. CSRF tokens will not survive restarts or validate "
            "across multiple workers. Set WEB_CSRF_SECRET in production."
        )
    return _DEV_SECRET


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(ts_str: str) -> str:
    sig = hmac.new(_csrf_secret(), ts_str.encode("ascii"), sha256).digest()
    return _b64url_encode(sig)


def issue_csrf_token() -> str:
    """Mint a fresh stateless CSRF token bound to ``time.time()``."""
    ts = str(int(time.time()))
    return f"{ts}.{_sign(ts)}"


def verify_csrf_token(token: str | None) -> bool:
    """Validate a CSRF token: shape, age, and HMAC signature."""
    if not token or "." not in token:
        return False
    ts_str, sig_b64 = token.split(".", 1)
    if not ts_str.isdigit():
        return False

    issued = int(ts_str)
    age = time.time() - issued
    # Allow a small ±60s skew for issuance to handle clock drift, but
    # reject anything older than the TTL.
    if age < -60 or age > CSRF_TTL_SECONDS:
        return False

    try:
        provided_sig = _b64url_decode(sig_b64)
    except (ValueError, base64.binascii.Error):
        return False
    expected_sig = _b64url_decode(_sign(ts_str))
    return hmac.compare_digest(expected_sig, provided_sig)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # tighten in production behind TLS
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def login_user(response: Response, user_id: int) -> str:
    token = db.create_session(user_id)
    set_session_cookie(response, token)
    return token


async def get_current_user(
    finance_session: Annotated[Optional[str], Cookie()] = None,
) -> Optional[dict]:
    """Resolve the active user from the session cookie, or return None."""
    if not finance_session:
        return None
    return db.get_user_by_session(finance_session)


async def require_user(
    request: Request,
    user: Annotated[Optional[dict], Depends(get_current_user)],
) -> dict:
    """Dependency that redirects to /login when no session is present."""
    if user is None:
        # HTMX requests get a 401 + HX-Redirect header so the browser follows
        if request.headers.get("HX-Request") == "true":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="login required",
                headers={"HX-Redirect": "/login"},
            )
        # Regular nav requests get a 303 to /login with ?next=
        next_url = request.url.path
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="login required",
            headers={"Location": f"/login?next={next_url}"},
        )
    return user


async def require_user_with_email(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    """Like require_user but also redirects to /email-setup when email is missing.

    Used to gate the main app surfaces (chat, dashboard, recurring, admin) so
    every account ends up with a recoverable email on file. The /email-setup
    page itself depends on require_user (not this) so the flow can complete.
    """
    if not user.get("email"):
        next_url = request.url.path
        if request.headers.get("HX-Request") == "true":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="email required",
                headers={"HX-Redirect": f"/email-setup?next={next_url}"},
            )
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="email required",
            headers={"Location": f"/email-setup?next={next_url}"},
        )
    return user


def redirect_unauthenticated(request: Request) -> Optional[RedirectResponse]:
    """Helper for routes that *prefer* anonymous users (e.g. /signup, /login)."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie and db.get_user_by_session(cookie):
        return RedirectResponse("/app", status_code=303)
    return None
