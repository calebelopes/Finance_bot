"""Full dashboard with 6 Plotly charts, comparison panel, monthly history,
top expenses table, full transaction log with search, and CSV/PDF export.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Annotated, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response

from utils import db
from utils.export import generate_csv, generate_pdf
from utils.i18n import MONTHS, cat_name, d, fmt_currency
from web.auth import require_user_with_email
from web.period import (
    VALID_PERIODS,
    date_range_to_utc,
    get_user_tz,
    previous_range,
    resolve_period,
)
from web.templates_setup import templates

router = APIRouter()


COLOR_PALETTE = [
    "#4CAF50", "#2196F3", "#FF9800", "#E91E63", "#9C27B0",
    "#00BCD4", "#FF5722", "#607D8B", "#795548",
]


def _utc_to_local(utc_iso: str, tz: ZoneInfo) -> datetime.datetime:
    dt = datetime.datetime.fromisoformat(utc_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(tz)


def _aggregate_kpis(txs: list[dict]) -> tuple[float, float, float, int]:
    expense = sum(t["amount_original"] for t in txs if t.get("type", "expense") == "expense")
    income = sum(t["amount_original"] for t in txs if t.get("type") == "income")
    return expense, income, income - expense, len(txs)


def _delta_pct(current: float, previous: float) -> str | None:
    if previous == 0:
        return None
    diff = current - previous
    pct = (diff / previous) * 100
    sign = "+" if diff >= 0 else ""
    return f"{sign}{pct:.0f}%"


def _build_chart_data(
    txs: list[dict], lang: str, currency: str, tz: ZoneInfo,
) -> dict:
    """Build all 6 chart specs for client-side Plotly.js rendering."""
    type_expense_label = d("type_expense", lang)
    type_income_label = d("type_income", lang)

    daily_exp: dict[str, float] = defaultdict(float)
    daily_inc: dict[str, float] = defaultdict(float)
    cat_totals: dict[str, float] = defaultdict(float)
    cumulative_x: list[str] = []
    cumulative_y: list[float] = []
    running = 0.0

    for tx in sorted(txs, key=lambda t: t["created_at"]):
        local_dt = _utc_to_local(tx["created_at"], tz)
        day_key = local_dt.date().isoformat()
        amt = tx["amount_original"]
        is_income = tx.get("type") == "income"
        if is_income:
            daily_inc[day_key] += amt
            running += amt
        else:
            daily_exp[day_key] += amt
            running -= amt
        cat_disp = cat_name(tx.get("category", "Outros"), lang)
        cat_totals[cat_disp] += amt
        cumulative_x.append(local_dt.isoformat())
        cumulative_y.append(running)

    days = sorted(set(daily_exp) | set(daily_inc))
    timeline = {
        "data": [
            {
                "type": "bar", "name": type_expense_label,
                "x": days, "y": [daily_exp.get(d, 0) for d in days],
                "marker": {"color": "#EF5350"},
                "hovertemplate": "%{y:,.2f}<extra>" + type_expense_label + "</extra>",
            },
            {
                "type": "bar", "name": type_income_label,
                "x": days, "y": [daily_inc.get(d, 0) for d in days],
                "marker": {"color": "#4CAF50"},
                "hovertemplate": "%{y:,.2f}<extra>" + type_income_label + "</extra>",
            },
        ],
        "layout": {
            "barmode": "group", "hovermode": "x unified",
            "margin": {"l": 40, "r": 10, "t": 10, "b": 40},
            "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "yaxis": {"title": {"text": d("currency_axis", lang)}},
            "legend": {"orientation": "h", "y": -0.2},
            "font": {"family": "system-ui, sans-serif"},
        },
    }

    cat_sorted = sorted(cat_totals.items(), key=lambda kv: kv[1], reverse=True)
    donut = {
        "data": [{
            "type": "pie",
            "labels": [k for k, _ in cat_sorted],
            "values": [v for _, v in cat_sorted],
            "hole": 0.45,
            "textposition": "inside",
            "textinfo": "percent+label",
            "marker": {"colors": COLOR_PALETTE},
            "hovertemplate": "%{label}: %{value:,.2f}<extra></extra>",
        }],
        "layout": {
            "margin": {"l": 0, "r": 0, "t": 10, "b": 0},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "showlegend": False,
            "font": {"family": "system-ui, sans-serif"},
        },
    }

    cat_asc = list(reversed(cat_sorted))
    bar = {
        "data": [{
            "type": "bar", "orientation": "h",
            "y": [k for k, _ in cat_asc],
            "x": [v for _, v in cat_asc],
            "text": [fmt_currency(v, lang, currency_code=currency) for _, v in cat_asc],
            "textposition": "outside",
            "marker": {"color": COLOR_PALETTE[: len(cat_asc)]},
            "hovertemplate": "%{y}: %{x:,.2f}<extra></extra>",
        }],
        "layout": {
            "margin": {"l": 100, "r": 40, "t": 10, "b": 40},
            "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "xaxis": {"title": {"text": d("currency_axis", lang)}},
            "showlegend": False,
            "font": {"family": "system-ui, sans-serif"},
        },
    }

    cumulative = {
        "data": [{
            "type": "scatter", "mode": "lines",
            "fill": "tozeroy",
            "x": cumulative_x, "y": cumulative_y,
            "line": {"color": "#2196F3"},
            "fillcolor": "rgba(33,150,243,0.2)",
            "hovertemplate": "%{y:,.2f}<extra></extra>",
        }],
        "layout": {
            "margin": {"l": 50, "r": 10, "t": 10, "b": 40},
            "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "yaxis": {"title": {"text": d("cumulative_axis", lang)}},
            "hovermode": "x unified",
            "font": {"family": "system-ui, sans-serif"},
        },
    }

    return {
        "timeline": timeline,
        "donut": donut,
        "bar": bar,
        "cumulative": cumulative,
        "cat_totals": cat_sorted,
    }


def _build_comparison_chart(
    metrics: list[tuple[str, float, float]], lang: str, current_label: str, prev_label: str,
) -> dict:
    return {
        "data": [
            {
                "type": "bar", "name": current_label,
                "x": [m[0] for m in metrics],
                "y": [m[1] for m in metrics],
                "marker": {"color": "#2196F3"},
                "text": [fmt_currency(m[1], lang) for m in metrics],
                "textposition": "outside",
            },
            {
                "type": "bar", "name": prev_label,
                "x": [m[0] for m in metrics],
                "y": [m[2] for m in metrics],
                "marker": {"color": "#90A4AE"},
                "text": [fmt_currency(m[2], lang) for m in metrics],
                "textposition": "outside",
            },
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


def _build_monthly_chart(rows: list[dict], lang: str) -> dict:
    months_list = MONTHS.get(lang, MONTHS["pt"])
    rows = sorted(rows, key=lambda r: r["month"])
    labels = [
        f"{months_list[int(r['month'].split('-')[1])]} {r['month'].split('-')[0]}"
        for r in rows
    ]
    return {
        "data": [
            {
                "type": "bar", "name": d("type_expense", lang),
                "x": labels, "y": [r["expenses"] for r in rows],
                "marker": {"color": "#EF5350"},
                "text": [fmt_currency(r["expenses"], lang) for r in rows],
                "textposition": "outside",
            },
            {
                "type": "bar", "name": d("type_income", lang),
                "x": labels, "y": [r["income"] for r in rows],
                "marker": {"color": "#4CAF50"},
                "text": [fmt_currency(r["income"], lang) for r in rows],
                "textposition": "outside",
            },
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


def _load_monthly_totals(user_id: int, months: int = 12) -> list[dict]:
    """Return per-month {month: 'YYYY-MM', expenses, income} for the last *months*."""
    today = datetime.datetime.now(datetime.UTC).date()
    cutoff = (today.replace(day=1) - datetime.timedelta(days=31 * months)).isoformat()
    with db._connect() as conn:
        rows = conn.execute(
            """SELECT
                 substr(created_at, 1, 7) AS month,
                 SUM(CASE WHEN COALESCE(type,'expense')='expense' THEN amount_original ELSE 0 END) AS expenses,
                 SUM(CASE WHEN type='income' THEN amount_original ELSE 0 END) AS income
               FROM transactions
               WHERE user_id = ? AND COALESCE(status,'confirmed') != 'deleted'
                 AND created_at >= ?
               GROUP BY month
               ORDER BY month""",
            (user_id, cutoff),
        ).fetchall()
    return [{"month": r["month"], "expenses": r["expenses"] or 0, "income": r["income"] or 0} for r in rows]


def _load_transactions(user_id: int, start_iso: str, end_iso: str) -> list[dict]:
    with db._connect() as conn:
        rows = conn.execute(
            """SELECT id, description, amount_original, currency_code,
                      amount_converted, exchange_rate,
                      category, category_id, type, source, status,
                      confidence_score, created_at
               FROM transactions
               WHERE user_id = ? AND created_at >= ? AND created_at < ?
                 AND COALESCE(status,'confirmed') != 'deleted'
               ORDER BY created_at ASC""",
            (user_id, start_iso, end_iso),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    user: Annotated[dict, Depends(require_user_with_email)],
    period: str = "month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    type_filter: Annotated[str, Query(alias="type")] = "all",
    search: str = "",
):
    if period not in VALID_PERIODS:
        period = "month"

    lang = user.get("lang", "pt")
    prefs = db.get_user_preferences(user["id"])
    currency = prefs.get("currency_default", "BRL")
    tz = get_user_tz(user["id"])

    start_date, end_date = resolve_period(user["id"], period, custom_start, custom_end)
    start_iso, end_iso = date_range_to_utc(user["id"], start_date, end_date)
    txs = _load_transactions(user["id"], start_iso, end_iso)
    if type_filter in ("expense", "income"):
        txs = [t for t in txs if t.get("type", "expense") == type_filter]

    prev_start, prev_end = previous_range(start_date, end_date)
    prev_start_iso, prev_end_iso = date_range_to_utc(user["id"], prev_start, prev_end)
    prev_txs = _load_transactions(user["id"], prev_start_iso, prev_end_iso)
    if type_filter in ("expense", "income"):
        prev_txs = [t for t in prev_txs if t.get("type", "expense") == type_filter]

    expense, income, balance, tx_count = _aggregate_kpis(txs)
    p_expense, p_income, p_balance, p_tx = _aggregate_kpis(prev_txs)

    charts = _build_chart_data(txs, lang, currency, tz)

    metrics = [
        (d("delta_expenses", lang), expense, p_expense),
        (d("delta_income", lang), income, p_income),
        (d("delta_balance", lang), balance, p_balance),
    ]
    comparison_chart = (
        _build_comparison_chart(metrics, lang, d("current_period_label", lang), d("previous_period_label", lang))
        if prev_txs else None
    )

    monthly_rows = _load_monthly_totals(user["id"], months=12)
    monthly_chart = _build_monthly_chart(monthly_rows, lang) if monthly_rows else None

    rows_for_table = list(txs)
    if search:
        s_low = search.lower()
        rows_for_table = [t for t in rows_for_table if s_low in (t.get("description") or "").lower()]
    rows_for_table.sort(key=lambda t: t["created_at"], reverse=True)

    top_expenses = sorted(txs, key=lambda t: t["amount_original"], reverse=True)[:10]

    type_display = {"expense": d("type_expense", lang), "income": d("type_income", lang)}

    def _shape(tx: dict) -> dict:
        cur = tx.get("currency_code") or currency
        return {
            "id": tx["id"],
            "time_str": _utc_to_local(tx["created_at"], tz).strftime("%d/%m/%Y %H:%M"),
            "type_display": type_display.get(tx.get("type", "expense"), type_display["expense"]),
            "is_income": tx.get("type") == "income",
            "description": tx["description"],
            "amount_str": fmt_currency(tx["amount_original"], lang, currency_code=cur),
            "currency_code": cur,
            "category_display": cat_name(tx.get("category", "Outros"), lang),
        }

    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "active": "dashboard",
            "lang": lang,
            "user": user,
            "user_currency": currency,
            "period": period,
            "type_filter": type_filter,
            "search": search,
            "custom_start": custom_start or start_date.isoformat(),
            "custom_end": custom_end or end_date.isoformat(),
            "start_date": start_date,
            "end_date": end_date,
            "kpi": {
                "expense": fmt_currency(expense, lang, currency_code=currency),
                "income": fmt_currency(income, lang, currency_code=currency),
                "balance": fmt_currency(balance, lang, currency_code=currency),
                "balance_positive": balance >= 0,
                "tx_count": tx_count,
                "delta_expense": _delta_pct(expense, p_expense),
                "delta_income": _delta_pct(income, p_income),
                "delta_balance": _delta_pct(balance, p_balance),
                "delta_tx": _delta_pct(tx_count, p_tx),
            },
            "charts": charts,
            "comparison_chart": comparison_chart,
            "monthly_chart": monthly_chart,
            "has_data": bool(txs),
            "has_prev_data": bool(prev_txs),
            "prev_start": prev_start.strftime("%d/%m/%Y"),
            "prev_end": prev_end.strftime("%d/%m/%Y"),
            "rows_for_table": [_shape(t) for t in rows_for_table],
            "top_expenses": [_shape(t) for t in top_expenses],
            "total_rows": len(rows_for_table),
            "shown_rows": min(200, len(rows_for_table)),
        },
    )


@router.get("/dashboard/export.csv")
async def export_csv(
    user: Annotated[dict, Depends(require_user_with_email)],
    period: str = "month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
):
    if period not in VALID_PERIODS:
        period = "month"
    lang = user.get("lang", "pt")
    start_date, end_date = resolve_period(user["id"], period, custom_start, custom_end)
    start_iso, end_iso = date_range_to_utc(user["id"], start_date, end_date)
    txs = _load_transactions(user["id"], start_iso, end_iso)
    payload = generate_csv(txs, lang)
    fname = f"finance_{period}_{start_date}_{end_date}.csv"
    return Response(
        payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/dashboard/export.pdf")
async def export_pdf(
    user: Annotated[dict, Depends(require_user_with_email)],
    period: str = "month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
):
    if period not in VALID_PERIODS:
        period = "month"
    lang = user.get("lang", "pt")
    start_date, end_date = resolve_period(user["id"], period, custom_start, custom_end)
    start_iso, end_iso = date_range_to_utc(user["id"], start_date, end_date)
    txs = _load_transactions(user["id"], start_iso, end_iso)
    payload = generate_pdf(txs, lang, period=period)
    fname = f"finance_{period}_{start_date}_{end_date}.pdf"
    return Response(
        payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
