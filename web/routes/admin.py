"""Admin panel: per-user stats + platform-wide activity charts."""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from utils import db
from utils.i18n import d, fmt_currency
from web.auth import require_user
from web.templates_setup import templates

router = APIRouter()


def _admin_only(user: dict) -> None:
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="not found")


def _build_admin_charts(daily_rows: list[dict], lang: str) -> tuple[dict, dict]:
    days = [r["day"] for r in daily_rows]
    expenses = [r.get("expenses") or 0 for r in daily_rows]
    income = [r.get("income") or 0 for r in daily_rows]
    actives = [r.get("active_users") or 0 for r in daily_rows]

    activity_chart = {
        "data": [
            {"type": "bar", "name": d("type_expense", lang), "x": days, "y": expenses,
             "marker": {"color": "#EF5350"}},
            {"type": "bar", "name": d("type_income", lang), "x": days, "y": income,
             "marker": {"color": "#4CAF50"}},
        ],
        "layout": {
            "barmode": "group",
            "margin": {"l": 50, "r": 10, "t": 10, "b": 40},
            "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "yaxis": {"title": {"text": d("currency_axis", lang)}},
            "legend": {"orientation": "h", "y": -0.2},
            "font": {"family": "system-ui, sans-serif"},
        },
    }
    users_chart = {
        "data": [{
            "type": "scatter", "mode": "lines", "fill": "tozeroy",
            "x": days, "y": actives, "line": {"color": "#2196F3"},
            "fillcolor": "rgba(33,150,243,0.2)",
        }],
        "layout": {
            "margin": {"l": 50, "r": 10, "t": 10, "b": 40},
            "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"family": "system-ui, sans-serif"},
        },
    }
    return activity_chart, users_chart


@router.get("/admin")
async def admin_panel(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
):
    _admin_only(user)
    lang = user.get("lang", "pt")

    users_raw = db.get_all_users_stats()
    daily_raw = db.get_platform_daily_stats()

    today = datetime.date.today()
    cutoff_7 = (today - datetime.timedelta(days=7)).isoformat()
    cutoff_30 = (today - datetime.timedelta(days=30)).isoformat()

    active_7 = sum(1 for u in users_raw if u.get("last_activity") and u["last_activity"][:10] >= cutoff_7)
    active_30 = sum(1 for u in users_raw if u.get("last_activity") and u["last_activity"][:10] >= cutoff_30)
    total_tx = sum(u.get("total_tx", 0) or 0 for u in users_raw)

    users_shaped = []
    for u in users_raw:
        bal = (u.get("total_income") or 0) - (u.get("total_expenses") or 0)
        users_shaped.append({
            "id": u["id"],
            "username": u.get("username") or "—",
            "lang": u.get("lang") or "pt",
            "total_tx": u.get("total_tx", 0) or 0,
            "expenses": fmt_currency(u.get("total_expenses") or 0, lang),
            "income": fmt_currency(u.get("total_income") or 0, lang),
            "balance": fmt_currency(bal, lang),
            "balance_positive": bal >= 0,
            "first_activity": (u.get("first_activity") or "")[:10],
            "last_activity": (u.get("last_activity") or "")[:10],
        })

    activity_chart, users_chart = _build_admin_charts(daily_raw, lang)
    has_data = bool(daily_raw)

    return templates.TemplateResponse(
        request,
        "admin/index.html",
        {
            "active": "admin",
            "lang": lang,
            "user": user,
            "kpi": {
                "users": len(users_raw),
                "active_7": active_7,
                "active_30": active_30,
                "total_tx": total_tx,
            },
            "users": users_shaped,
            "activity_chart": activity_chart,
            "users_chart": users_chart,
            "has_data": has_data,
        },
    )
