"""Signup, login, logout routes."""

from __future__ import annotations

import os
import re
from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from utils import db
from utils.i18n import DEFAULT_LANG, SUPPORTED_LANGS
from web.auth import (
    clear_session_cookie,
    get_current_user,
    issue_csrf_token,
    login_user,
    redirect_unauthenticated,
    verify_csrf_token,
)
from web.ratelimit import RateLimiter, client_key
from web.templates_setup import templates

router = APIRouter()


_VALID_CURRENCIES = db.SUPPORTED_CURRENCIES

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Per-IP throttles on the credential endpoints. Defaults are generous
# enough that no human hits them, but they cap scripted brute-force /
# credential-stuffing (each attempt costs a PBKDF2 verification).
_login_limiter = RateLimiter(
    max_attempts=int(os.getenv("WEB_LOGIN_MAX_ATTEMPTS", "10")),
    window_seconds=float(os.getenv("WEB_LOGIN_WINDOW_SECONDS", "300")),
)
_signup_limiter = RateLimiter(
    max_attempts=int(os.getenv("WEB_SIGNUP_MAX_ATTEMPTS", "5")),
    window_seconds=float(os.getenv("WEB_SIGNUP_WINDOW_SECONDS", "3600")),
)
# Escape hatch so the test suite (and anyone who wants to) can turn the
# throttle off without fighting shared per-process counters.
_RATE_LIMIT_ENABLED = os.getenv("WEB_RATE_LIMIT_ENABLED", "1").strip().lower() not in {
    "0", "false", "no", "off",
}


def _resolved_lang(form_lang: str | None, header_lang: str | None) -> str:
    if form_lang and form_lang in SUPPORTED_LANGS:
        return form_lang
    if header_lang:
        primary = header_lang.split(",")[0].split("-")[0].strip().lower()
        if primary in SUPPORTED_LANGS:
            return primary
    return DEFAULT_LANG


@router.get("/signup")
async def signup_form(request: Request, lang: str | None = None):
    redir = redirect_unauthenticated(request)
    if redir:
        return redir
    chosen_lang = lang or _resolved_lang(None, request.headers.get("accept-language"))
    csrf = issue_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "auth/signup.html",
        {"lang": chosen_lang, "csrf_token": csrf, "user": None, "errors": {}, "values": {}},
    )


@router.post("/signup")
async def signup_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    password_confirm: Annotated[str, Form()],
    email: Annotated[str, Form()] = "",
    lang: Annotated[str, Form()] = DEFAULT_LANG,
    currency: Annotated[str, Form()] = "BRL",
    csrf_token: Annotated[str, Form()] = "",
    honeypot: Annotated[str, Form()] = "",
):
    if _RATE_LIMIT_ENABLED:
        allowed, retry = _signup_limiter.check(client_key(request))
        if not allowed:
            chosen_lang = _resolved_lang(lang, request.headers.get("accept-language"))
            return templates.TemplateResponse(
                request,
                "auth/signup.html",
                {
                    "lang": chosen_lang, "csrf_token": issue_csrf_token(request),
                    "user": None, "errors": {},
                    "values": {"username": username, "email": email,
                               "lang": lang, "currency": currency},
                    "form_error": "err_rate_limited",
                },
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")
    if honeypot:
        raise HTTPException(status_code=400, detail="bot detected")

    errors: dict[str, str] = {}
    email = (email or "").strip()
    values = {"username": username, "email": email, "lang": lang, "currency": currency}

    username = (username or "").strip().lstrip("@")
    if not username or len(username) < 3 or len(username) > 32:
        errors["username"] = "signup_err_username_length"
    elif not username.replace("_", "").replace("-", "").isalnum():
        errors["username"] = "signup_err_username_chars"

    if email:
        if len(email) > 254 or not _EMAIL_RE.match(email):
            errors["email"] = "signup_err_email_invalid"
        elif db.email_exists(email):
            errors["email"] = "signup_err_email_taken"

    if not password or len(password) < 6:
        errors["password"] = "signup_err_password_short"
    if password != password_confirm:
        errors["password_confirm"] = "signup_err_password_mismatch"

    chosen_lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    chosen_currency = currency.upper() if currency.upper() in _VALID_CURRENCIES else "BRL"

    if not errors and db.username_exists(username):
        errors["username"] = "signup_err_username_taken"

    if errors:
        new_csrf = issue_csrf_token(request)
        return templates.TemplateResponse(
            request,
            "auth/signup.html",
            {
                "lang": chosen_lang, "csrf_token": new_csrf,
                "user": None, "errors": errors, "values": values,
            },
            status_code=400,
        )

    user_id = db.create_web_user(
        username, password,
        lang=chosen_lang, currency=chosen_currency,
        email=email or None,
    )
    if user_id is None:
        new_csrf = issue_csrf_token(request)
        return templates.TemplateResponse(
            request,
            "auth/signup.html",
            {
                "lang": chosen_lang, "csrf_token": new_csrf,
                "user": None, "errors": {"username": "signup_err_username_taken"},
                "values": values,
            },
            status_code=400,
        )

    response = RedirectResponse("/app", status_code=303)
    login_user(response, user_id)
    return response


@router.get("/login")
async def login_form(request: Request, lang: str | None = None, next: str = "/app"):
    redir = redirect_unauthenticated(request)
    if redir:
        return redir
    chosen_lang = lang or _resolved_lang(None, request.headers.get("accept-language"))
    csrf = issue_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "lang": chosen_lang, "csrf_token": csrf,
            "user": None, "next": next, "error": None,
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    password: Annotated[str, Form()],
    username: Annotated[str, Form()] = "",
    identifier: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/app",
    csrf_token: Annotated[str, Form()] = "",
    lang: str | None = None,
):
    key = client_key(request)
    if _RATE_LIMIT_ENABLED:
        allowed, retry = _login_limiter.check(key)
        if not allowed:
            chosen_lang = lang or _resolved_lang(None, request.headers.get("accept-language"))
            return templates.TemplateResponse(
                request,
                "auth/login.html",
                {
                    "lang": chosen_lang, "csrf_token": issue_csrf_token(request),
                    "user": None, "next": next, "error": "err_rate_limited",
                },
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")

    raw = (identifier or username or "").strip().lstrip("@")
    user = db.authenticate_by_identifier(raw, password or "")
    if user is None:
        new_csrf = issue_csrf_token(request)
        chosen_lang = lang or _resolved_lang(None, request.headers.get("accept-language"))
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {
                "lang": chosen_lang, "csrf_token": new_csrf,
                "user": None, "next": next, "error": "login_err_invalid",
            },
            status_code=401,
        )

    # Successful auth: clear this client's throttle so a legitimate user
    # who fat-fingered their password a few times isn't penalised.
    _login_limiter.reset(key)
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/app"
    response = RedirectResponse(safe_next, status_code=303)
    login_user(response, user["id"])
    return response


@router.get("/email-setup")
async def email_setup_form(
    request: Request,
    user: Annotated[Optional[dict], Depends(get_current_user)] = None,
    next: str = "/app",
):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user.get("email"):
        # Already has an email — nothing to do, send them along.
        safe_next = next if next.startswith("/") and not next.startswith("//") else "/app"
        return RedirectResponse(safe_next, status_code=303)
    csrf = issue_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "auth/email_setup.html",
        {
            "lang": user.get("lang", "pt"),
            "user": user,
            "csrf_token": csrf,
            "next": next,
            "errors": {},
            "values": {},
        },
    )


@router.post("/email-setup")
async def email_setup_submit(
    request: Request,
    email: Annotated[str, Form()],
    user: Annotated[Optional[dict], Depends(get_current_user)] = None,
    next: Annotated[str, Form()] = "/app",
    csrf_token: Annotated[str, Form()] = "",
):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")

    email = (email or "").strip()
    errors: dict[str, str] = {}
    if not email:
        errors["email"] = "signup_err_email_invalid"
    elif len(email) > 254 or not _EMAIL_RE.match(email):
        errors["email"] = "signup_err_email_invalid"
    elif db.email_exists(email) and (
        (db.get_user_email(user["id"]) or "").lower() != email.lower()
    ):
        errors["email"] = "signup_err_email_taken"

    if errors:
        new_csrf = issue_csrf_token(request)
        return templates.TemplateResponse(
            request,
            "auth/email_setup.html",
            {
                "lang": user.get("lang", "pt"),
                "user": user,
                "csrf_token": new_csrf,
                "next": next,
                "errors": errors,
                "values": {"email": email},
            },
            status_code=400,
        )

    db.set_user_email(user["id"], email)
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/app"
    return RedirectResponse(safe_next, status_code=303)


@router.post("/logout")
async def logout(
    request: Request,
    finance_session: Annotated[Optional[str], Cookie()] = None,
):
    if finance_session:
        user = db.get_user_by_session(finance_session)
        if user:
            db.clear_session(user["id"])
    response = RedirectResponse("/", status_code=303)
    clear_session_cookie(response)
    return response
