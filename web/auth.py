"""Web authentication: session cookies + CSRF tokens.

Sessions are stored on the users.session_token column (already part of the
schema). CSRF tokens are short-lived, stored in a server-side dict keyed by
the session token.
"""

from __future__ import annotations

import secrets
import time
from typing import Annotated, Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from utils import db

SESSION_COOKIE = "finance_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days
CSRF_COOKIE = "finance_csrf"
CSRF_TTL_SECONDS = 4 * 3600


_csrf_tokens: dict[str, float] = {}


def issue_csrf_token() -> str:
    """Mint a fresh CSRF token, prune expired ones, return the new token."""
    now = time.time()
    expired = [k for k, exp in _csrf_tokens.items() if exp < now]
    for k in expired:
        _csrf_tokens.pop(k, None)
    token = secrets.token_urlsafe(24)
    _csrf_tokens[token] = now + CSRF_TTL_SECONDS
    return token


def verify_csrf_token(token: str | None) -> bool:
    if not token:
        return False
    exp = _csrf_tokens.get(token)
    if exp is None or exp < time.time():
        _csrf_tokens.pop(token, None)
        return False
    return True


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


def redirect_unauthenticated(request: Request) -> Optional[RedirectResponse]:
    """Helper for routes that *prefer* anonymous users (e.g. /signup, /login)."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie and db.get_user_by_session(cookie):
        return RedirectResponse("/app", status_code=303)
    return None
