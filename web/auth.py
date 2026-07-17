"""Web authentication: session cookies + double-submit CSRF tokens.

Sessions are stored on the ``users.session_token`` column (already part
of the schema).

CSRF protection uses the **double-submit cookie** pattern:

* :class:`CSRFMiddleware` assigns each browser a random, unguessable
  ``finance_csrf`` cookie (once, then reused).
* Every form embeds that same value in a hidden ``csrf_token`` field
  (rendered via :func:`issue_csrf_token`).
* :func:`verify_csrf_token` accepts a request only when the submitted
  field matches the cookie (constant-time compare).

Because the token is tied to a per-browser cookie that an attacker can
neither read (SameSite + same-origin) nor set, a token minted in one
browser is worthless in another — which the previous stateless
HMAC-over-timestamp scheme did *not* guarantee (any freshly issued
token validated for any user). ``SameSite=Lax`` remains as defense in
depth.

Cookie ``Secure`` flag is controlled by ``WEB_COOKIE_SECURE`` (set it to
``1`` once the app is served over HTTPS).
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
from typing import Annotated, Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from utils import db

log = logging.getLogger(__name__)

SESSION_COOKIE = "finance_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days
CSRF_COOKIE = "finance_csrf"
CSRF_MAX_AGE = 7 * 24 * 3600  # 7 days


def _cookie_secure() -> bool:
    """Whether to set the ``Secure`` flag on auth cookies.

    Defaults to off so plain-HTTP local dev keeps working; set
    ``WEB_COOKIE_SECURE=1`` in any TLS-terminated deployment so the
    session and CSRF cookies are never sent over cleartext.
    """
    return os.getenv("WEB_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Ensure every browser carries a stable, random ``finance_csrf`` cookie.

    The value is stashed on ``request.state.csrf_token`` so template
    rendering (via :func:`issue_csrf_token`) embeds the exact value the
    browser will submit back.
    """

    async def dispatch(self, request: Request, call_next):
        token = request.cookies.get(CSRF_COOKIE)
        is_new = not token
        if is_new:
            token = secrets.token_urlsafe(32)
        request.state.csrf_token = token
        response = await call_next(request)
        if is_new:
            response.set_cookie(
                CSRF_COOKIE, token,
                max_age=CSRF_MAX_AGE,
                httponly=True,
                samesite="lax",
                secure=_cookie_secure(),
                path="/",
            )
        return response


def issue_csrf_token(request: Request) -> str:
    """Return this browser's CSRF token (the double-submit cookie value).

    Populated by :class:`CSRFMiddleware`; falls back to an ephemeral
    value if the middleware is somehow absent so templates never render
    an empty field.
    """
    token = getattr(request.state, "csrf_token", "")
    if not token:
        token = secrets.token_urlsafe(32)
        request.state.csrf_token = token
    return token


def verify_csrf_token(request: Request, token: str | None) -> bool:
    """Accept the request only if the submitted token matches the cookie."""
    cookie_val = request.cookies.get(CSRF_COOKIE) or getattr(request.state, "csrf_token", "")
    if not token or not cookie_val:
        return False
    return hmac.compare_digest(token, cookie_val)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
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
