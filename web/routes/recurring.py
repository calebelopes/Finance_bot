"""Recurring transactions UI: list, add, toggle, delete."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from utils import categories, db
from utils.i18n import cat_name, fmt_currency
from utils.parser import parse_number_ptbr
from web.auth import issue_csrf_token, require_user_with_email, verify_csrf_token
from web.templates_setup import templates

router = APIRouter()


def _shape_recurring(row: dict, lang: str) -> dict:
    cur = row.get("currency_code") or "BRL"
    return {
        "id": row["id"],
        "description": row["description"],
        "amount": row["amount"],
        "amount_str": fmt_currency(row["amount"], lang, currency_code=cur),
        "currency_code": cur,
        "category_display": cat_name(row.get("category", "Outros") or "Outros", lang),
        "is_income": row.get("type") == "income",
        "frequency": row.get("frequency", "monthly"),
        "day_of_month": row.get("day_of_month"),
        "next_run": row.get("next_run"),
        "active": bool(row.get("active")),
    }


@router.get("/recurring")
async def list_recurring(
    request: Request,
    user: Annotated[dict, Depends(require_user_with_email)],
):
    lang = user.get("lang", "pt")
    raw = db.get_recurring(user["id"])
    rules = [_shape_recurring(r, lang) for r in raw]
    prefs = db.get_user_preferences(user["id"])
    return templates.TemplateResponse(
        request,
        "recurring/index.html",
        {
            "active": "recurring",
            "lang": lang,
            "user": user,
            "rules": rules,
            "csrf_token": issue_csrf_token(),
            "user_currency": prefs.get("currency_default", "BRL"),
        },
    )


@router.post("/recurring")
async def add_recurring(
    request: Request,
    user: Annotated[dict, Depends(require_user_with_email)],
    description: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    type: Annotated[str, Form()] = "expense",
    day: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")

    description = (description or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="empty description")

    try:
        amount_val = parse_number_ptbr(amount)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="invalid amount") from None
    if amount_val <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    action_type = "income" if type == "income" else "expense"

    day_of_month = None
    if day.strip().isdigit():
        day_of_month = max(1, min(28, int(day)))

    prefs = db.get_user_preferences(user["id"])
    currency = prefs.get("currency_default", "BRL")
    category = categories.infer_category(description, action_type)

    db.add_recurring(
        user["id"], description, amount_val, category, action_type,
        currency_code=currency, day_of_month=day_of_month,
    )
    return RedirectResponse("/recurring?added=1", status_code=303)


@router.post("/recurring/{rec_id}/toggle")
async def toggle_recurring(
    rec_id: int,
    user: Annotated[dict, Depends(require_user_with_email)],
    csrf_token: Annotated[str, Form()] = "",
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")
    if db.toggle_recurring(user["id"], rec_id) is None:
        raise HTTPException(status_code=404, detail="not found")
    return RedirectResponse("/recurring?toggled=1", status_code=303)


@router.post("/recurring/{rec_id}/delete")
async def delete_recurring(
    rec_id: int,
    user: Annotated[dict, Depends(require_user_with_email)],
    csrf_token: Annotated[str, Form()] = "",
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")
    if not db.delete_recurring(user["id"], rec_id):
        raise HTTPException(status_code=404, detail="not found")
    return RedirectResponse("/recurring?deleted=1", status_code=303)
