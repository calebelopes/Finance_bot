"""Shared Jinja2 environment with i18n helpers registered as globals."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from utils.i18n import (
    CURRENCY_LABELS,
    DEFAULT_LANG,
    LANG_LABELS,
    SUPPORTED_LANGS,
    TIMEZONE_LABELS,
    cat_name,
    d,
    fmt_currency,
    t,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

templates.env.globals["t"] = t
templates.env.globals["d"] = d
templates.env.globals["fmt_currency"] = fmt_currency
templates.env.globals["cat_name"] = cat_name
templates.env.globals["LANG_LABELS"] = LANG_LABELS
templates.env.globals["CURRENCY_LABELS"] = CURRENCY_LABELS
templates.env.globals["TIMEZONE_LABELS"] = TIMEZONE_LABELS
templates.env.globals["SUPPORTED_LANGS"] = SUPPORTED_LANGS
templates.env.globals["DEFAULT_LANG"] = DEFAULT_LANG


def lang_for(user: dict | None, default: str = DEFAULT_LANG) -> str:
    if user is None:
        return default
    return user.get("lang") or default
