"""User settings: language, currency, timezone, password, link Telegram, delete account."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from utils import db
from utils.i18n import SUPPORTED_LANGS
from web.auth import (
    clear_session_cookie,
    issue_csrf_token,
    require_user,
    verify_csrf_token,
)
from web.templates_setup import templates

router = APIRouter()


_VALID_CURRENCIES = {"BRL", "USD", "EUR", "JPY", "GBP"}


def _bot_username() -> str:
    import os
    return os.getenv("BOT_USERNAME", "your_finance_bot")


def _settings_context(request: Request, user: dict) -> dict:
    prefs = db.get_user_preferences(user["id"])
    with db._connect() as conn:
        row = conn.execute(
            "SELECT telegram_id, email FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
    telegram_id = row["telegram_id"] if row else None
    email = row["email"] if row else None

    return {
        "lang": user.get("lang", "pt"),
        "user": user,
        "prefs": prefs,
        "telegram_id": telegram_id,
        "email": email,
        "csrf_token": issue_csrf_token(),
        "messages": [],
        "errors": {},
        "bot_username": _bot_username(),
    }


@router.get("/settings")
async def settings_page(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
):
    ctx = _settings_context(request, user)
    return templates.TemplateResponse(request, "settings/index.html", ctx)


@router.post("/settings/preferences")
async def update_prefs(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    lang: Annotated[str, Form()] = "pt",
    currency: Annotated[str, Form()] = "BRL",
    timezone: Annotated[str, Form()] = "America/Sao_Paulo",
    csrf_token: Annotated[str, Form()] = "",
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")

    if lang in SUPPORTED_LANGS:
        db.set_lang(user["id"], lang)
    if currency.upper() in _VALID_CURRENCIES:
        db.set_user_preference(user["id"], "currency_default", currency.upper())
    db.set_user_preference(user["id"], "timezone", timezone)

    response = RedirectResponse("/settings?saved=1", status_code=303)
    return response


@router.post("/settings/password")
async def change_password(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    current_password: Annotated[str, Form()] = "",
    new_password: Annotated[str, Form()] = "",
    new_password_confirm: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")

    ctx = _settings_context(request, user)

    if not db.authenticate_user(user["username"], current_password):
        ctx["errors"] = {"current_password": "settings_err_wrong_password"}
        return templates.TemplateResponse(request, "settings/index.html", ctx, status_code=400)
    if len(new_password) < 6:
        ctx["errors"] = {"new_password": "signup_err_password_short"}
        return templates.TemplateResponse(request, "settings/index.html", ctx, status_code=400)
    if new_password != new_password_confirm:
        ctx["errors"] = {"new_password_confirm": "signup_err_password_mismatch"}
        return templates.TemplateResponse(request, "settings/index.html", ctx, status_code=400)

    db.set_password(user["id"], new_password)
    return RedirectResponse("/settings?password_saved=1", status_code=303)


@router.post("/settings/link-telegram")
async def generate_link_code(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    csrf_token: Annotated[str, Form()] = "",
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")

    code = db.create_telegram_link_code(user["id"], ttl_minutes=10)
    ctx = _settings_context(request, user)
    ctx["link_code"] = code
    ctx["bot_username"] = _bot_username()
    return templates.TemplateResponse(request, "settings/link_code.html", ctx)


@router.post("/settings/unlink-telegram")
async def unlink_telegram(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    csrf_token: Annotated[str, Form()] = "",
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")
    db.unlink_telegram(user["id"])
    return RedirectResponse("/settings?unlinked=1", status_code=303)


@router.post("/settings/delete-account")
async def delete_account(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    confirm_username: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")
    if confirm_username.strip().lower() != (user["username"] or "").lower():
        ctx = _settings_context(request, user)
        ctx["errors"] = {"delete_confirm": "settings_err_delete_confirm"}
        return templates.TemplateResponse(request, "settings/index.html", ctx, status_code=400)

    user_id = user["id"]
    with db._connect() as conn:
        conn.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        conn.execute(
            "DELETE FROM recurring_logs WHERE recurring_id IN "
            "(SELECT id FROM recurring_transactions WHERE user_id = ?)",
            (user_id,),
        )
        conn.execute("DELETE FROM recurring_transactions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM usage_events WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM telegram_link_codes WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

    response = RedirectResponse("/", status_code=303)
    clear_session_cookie(response)
    return response
