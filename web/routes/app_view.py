"""Main authenticated app: chat input + KPI strip + recent transactions."""

from __future__ import annotations

import datetime
import logging
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from utils import categories, db
from utils.i18n import ALL_GREETINGS, cat_name, fmt_currency
from utils.parser import parse_smart
from web.auth import issue_csrf_token, require_user, verify_csrf_token
from web.templates_setup import templates

log = logging.getLogger(__name__)
router = APIRouter()


_LOW_CONFIDENCE_THRESHOLD = 0.85


def _user_tz(user_id: int) -> ZoneInfo:
    prefs = db.get_user_preferences(user_id)
    tz_name = prefs.get("timezone") or "America/Sao_Paulo"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("America/Sao_Paulo")


def _utc_to_local(utc_iso: str, tz: ZoneInfo) -> datetime.datetime:
    dt = datetime.datetime.fromisoformat(utc_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(tz)


def _month_range_utc(user_id: int) -> tuple[str, str]:
    tz = _user_tz(user_id)
    now_local = datetime.datetime.now(tz)
    start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start_local.month == 12:
        end_local = start_local.replace(year=start_local.year + 1, month=1)
    else:
        end_local = start_local.replace(month=start_local.month + 1)
    to_iso = lambda dt: dt.astimezone(datetime.UTC).replace(microsecond=0).isoformat()  # noqa: E731
    return to_iso(start_local), to_iso(end_local)


def _kpi_strip(user_id: int, lang: str, currency: str) -> dict:
    start_iso, end_iso = _month_range_utc(user_id)
    txs = db.get_transactions(user_id, start_iso, end_iso)
    expense = sum(t["amount_original"] for t in txs if t.get("type", "expense") == "expense")
    income = sum(t["amount_original"] for t in txs if t.get("type") == "income")
    return {
        "expense_str": fmt_currency(expense, lang, currency_code=currency),
        "income_str": fmt_currency(income, lang, currency_code=currency),
        "balance_str": fmt_currency(income - expense, lang, currency_code=currency),
        "balance_positive": income >= expense,
        "tx_count": len(txs),
    }


def _format_tx_for_template(
    tx: dict, lang: str, tz: ZoneInfo, user_currency: str,
) -> dict:
    """Shape a transaction row for tx_row.html."""
    cur = tx.get("currency_code") or "BRL"
    is_income = tx.get("type") == "income"
    return {
        "id": tx["id"],
        "description": tx["description"],
        "amount_str": fmt_currency(tx["amount_original"], lang, currency_code=cur),
        "category_display": cat_name(tx.get("category", "Outros"), lang),
        "is_income": is_income,
        "currency_code": cur,
        "time_str": _utc_to_local(tx["created_at"], tz).strftime("%d/%m %H:%M"),
        "converted_str": (
            fmt_currency(tx["amount_converted"], lang, currency_code=user_currency)
            if tx.get("amount_converted") and tx.get("exchange_rate") else None
        ),
    }


def _recent_transactions(user_id: int, lang: str, currency: str, limit: int = 30) -> list[dict]:
    """Return the N most recent transactions for the chat sidebar."""
    with db._connect() as conn:
        rows = conn.execute(
            """SELECT id, description, amount_original, currency_code, category, type,
                      amount_converted, exchange_rate, created_at
               FROM transactions
               WHERE user_id = ? AND COALESCE(status, 'confirmed') != 'deleted'
               ORDER BY datetime(created_at) DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    tz = _user_tz(user_id)
    return [_format_tx_for_template(dict(r), lang, tz, currency) for r in rows]


@router.get("/app", response_class=HTMLResponse)
async def app_index(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
):
    lang = user.get("lang", "pt")
    prefs = db.get_user_preferences(user["id"])
    currency = prefs.get("currency_default", "BRL")
    return templates.TemplateResponse(
        request,
        "app/index.html",
        {
            "active": "app",
            "lang": lang,
            "user": user,
            "csrf_token": issue_csrf_token(),
            "kpi": _kpi_strip(user["id"], lang, currency),
            "transactions": _recent_transactions(user["id"], lang, currency),
            "user_currency": currency,
        },
    )


@router.post("/app/chat", response_class=HTMLResponse)
async def chat_send(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    text: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")

    lang = user.get("lang", "pt")
    prefs = db.get_user_preferences(user["id"])
    user_currency = prefs.get("currency_default", "BRL")

    raw_text = (text or "").strip()
    if not raw_text:
        return HTMLResponse("", status_code=204)

    normalized = " ".join(raw_text.lower().split())
    if normalized in ALL_GREETINGS:
        return templates.TemplateResponse(
            request,
            "app/chat_message.html",
            {
                "lang": lang,
                "kind": "info",
                "text": templates.env.globals["t"]("greeting", lang),
                "tx": None,
            },
        )

    is_income = raw_text.startswith("+")
    parse_text = raw_text.lstrip("+").strip() if is_income else raw_text
    action_type = "income" if is_income else "expense"

    try:
        result = parse_smart(parse_text)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "app/chat_message.html",
            {
                "lang": lang,
                "kind": "error",
                "text": templates.env.globals["t"]("invalid", lang),
                "tx": None,
            },
        )

    description = result.description
    value = result.value
    parsed_currency = result.currency
    date_offset = result.date_offset

    category, confidence = categories.infer_category_with_confidence(
        result.raw_description or description, action_type,
    )
    tx_currency = parsed_currency or user_currency

    amount_converted = None
    exchange_rate = None
    if tx_currency != user_currency:
        amount_converted, exchange_rate = db.convert_amount(value, tx_currency, user_currency)

    created_at_override = None
    if date_offset is not None and date_offset != 0:
        tz = _user_tz(user["id"])
        target = (datetime.datetime.now(tz) + datetime.timedelta(days=date_offset)).replace(
            hour=12, minute=0, second=0, microsecond=0,
        )
        created_at_override = target.astimezone(datetime.UTC).replace(microsecond=0).isoformat()

    tx_id = db.store_transaction(
        user["id"], user["username"], description, value, category, action_type,
        currency_code=tx_currency,
        amount_converted=amount_converted,
        exchange_rate=exchange_rate,
        created_at_override=created_at_override,
        confidence_score=confidence,
        source="web",
    )

    log.info(
        "Web stored #%d [%s] for user=%d: %s = %.2f %s [%s] (conf=%.2f)",
        tx_id, action_type, user["id"], description, value, tx_currency, category, confidence,
    )

    # Re-fetch the row in template-shape
    new_tx = next(
        (t for t in _recent_transactions(user["id"], lang, user_currency, limit=1)
         if t["id"] == tx_id),
        None,
    )
    if new_tx is None:
        # Fallback shape if for some reason we can't find the row
        new_tx = {
            "id": tx_id,
            "description": description,
            "amount_str": fmt_currency(value, lang, currency_code=tx_currency),
            "category_display": cat_name(category, lang),
            "is_income": is_income,
            "currency_code": tx_currency,
            "time_str": "",
            "converted_str": None,
        }

    kpi = _kpi_strip(user["id"], lang, user_currency)

    suggestions = []
    if 0 < confidence < _LOW_CONFIDENCE_THRESHOLD:
        top = categories.get_top_categories(
            result.raw_description or description, action_type, n=4,
        )
        suggestions = [
            {"key": cat, "display": cat_name(cat, lang)}
            for cat, _score in top if cat != category
        ][:3]

    return templates.TemplateResponse(
        request,
        "app/chat_message.html",
        {
            "lang": lang,
            "kind": "stored",
            "tx": new_tx,
            "is_income": is_income,
            "kpi": kpi,
            "user_currency": user_currency,
            "csrf_token": issue_csrf_token(),
            "suggestions": suggestions,
            "low_confidence": 0 < confidence < _LOW_CONFIDENCE_THRESHOLD,
            "converted_str": (
                fmt_currency(amount_converted, lang, currency_code=user_currency)
                if amount_converted else None
            ),
            "exchange_rate": exchange_rate,
            "tx_currency": tx_currency,
            "backdated_date": (
                _utc_to_local(created_at_override, _user_tz(user["id"])).strftime("%d/%m/%Y")
                if created_at_override else None
            ),
        },
    )


@router.delete("/api/transactions/{tx_id}", response_class=HTMLResponse)
async def delete_tx(
    request: Request,
    tx_id: int,
    user: Annotated[dict, Depends(require_user)],
):
    """HTMX-friendly delete: returns empty 200 (HTMX swaps the row out via hx-swap='outerHTML')
    plus an out-of-band update of the KPI strip.
    """
    if not db.delete_transaction(user["id"], tx_id):
        raise HTTPException(status_code=404, detail="not found")

    lang = user.get("lang", "pt")
    prefs = db.get_user_preferences(user["id"])
    currency = prefs.get("currency_default", "BRL")
    kpi = _kpi_strip(user["id"], lang, currency)

    return templates.TemplateResponse(
        request,
        "app/_kpi_oob.html",
        {"kpi": kpi, "lang": lang},
    )


@router.post("/api/transactions/{tx_id}/category", response_class=HTMLResponse)
async def fix_tx_category(
    request: Request,
    tx_id: int,
    user: Annotated[dict, Depends(require_user)],
    category: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=400, detail="invalid csrf token")

    if not db.update_transaction_category(user["id"], tx_id, category):
        raise HTTPException(status_code=404, detail="not found")

    lang = user.get("lang", "pt")
    return HTMLResponse(
        f'<span class="text-xs text-green-600 dark:text-green-400">'
        f'{templates.env.globals["t"]("category_corrected", lang, id=tx_id, category=cat_name(category, lang))}'
        f'</span>'
    )
