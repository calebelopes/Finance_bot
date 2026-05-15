"""Period (date range) helpers used by both /app and /dashboard.

Calculates current/previous UTC ranges based on the user's preferred timezone.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from utils import db

VALID_PERIODS = {
    "today", "week", "month", "last_month",
    "3months", "6months", "year", "all", "custom",
}


def get_user_tz(user_id: int) -> ZoneInfo:
    prefs = db.get_user_preferences(user_id)
    tz_name = prefs.get("timezone") or "America/Sao_Paulo"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("America/Sao_Paulo")


def _to_iso_utc(dt_local: datetime.datetime) -> str:
    return dt_local.astimezone(datetime.UTC).replace(microsecond=0).isoformat()


def resolve_period(
    user_id: int,
    period: str,
    custom_start: str | None = None,
    custom_end: str | None = None,
) -> tuple[datetime.date, datetime.date]:
    """Resolve a period spec into local-date (start, end) inclusive."""
    tz = get_user_tz(user_id)
    today = datetime.datetime.now(tz).date()

    if period == "today":
        return today, today
    if period == "week":
        start = today - datetime.timedelta(days=today.weekday())
        return start, today
    if period == "month":
        return today.replace(day=1), today
    if period == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - datetime.timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    if period == "3months":
        return today - datetime.timedelta(days=89), today
    if period == "6months":
        return today - datetime.timedelta(days=179), today
    if period == "year":
        return today - datetime.timedelta(days=364), today
    if period == "all":
        return datetime.date(2000, 1, 1), today
    if period == "custom":
        try:
            s = datetime.date.fromisoformat(custom_start) if custom_start else today.replace(day=1)
            e = datetime.date.fromisoformat(custom_end) if custom_end else today
        except ValueError:
            s, e = today.replace(day=1), today
        if s > e:
            s, e = e, s
        return s, e
    return today.replace(day=1), today


def date_range_to_utc(
    user_id: int, start_date: datetime.date, end_date: datetime.date,
) -> tuple[str, str]:
    """Convert (start_date, end_date) inclusive to UTC ISO range [start, end_exclusive)."""
    tz = get_user_tz(user_id)
    start_local = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=tz)
    end_local_exclusive = datetime.datetime.combine(
        end_date + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz,
    )
    return _to_iso_utc(start_local), _to_iso_utc(end_local_exclusive)


def previous_range(start_date: datetime.date, end_date: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Return the same-length range immediately before [start_date, end_date]."""
    span = (end_date - start_date).days
    prev_end = start_date - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=span)
    return prev_start, prev_end
