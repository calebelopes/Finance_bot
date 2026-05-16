"""Shared authentication helpers used by both bot and web layers.

Pure-Python: no telegram or web framework imports, so it can be tested in
isolation. Web is the source of truth for accounts — the bot never
auto-creates rows for incoming Telegram users; it only looks them up.
"""

from __future__ import annotations

from utils import db
from utils.i18n import detect_lang


def lookup_telegram_user(
    telegram_id: int,
    language_code: str | None = None,
) -> tuple[int | None, str]:
    """Look up the local user already linked to *telegram_id*.

    Returns (local_user_id, lang). When no link exists yet,
    ``local_user_id`` is None and ``lang`` falls back to the language
    detected from Telegram's ``language_code`` so any redirect-to-web
    message lands in the user's preferred language.
    """
    existing = db.get_user_by_telegram_id(telegram_id)
    if existing is not None:
        return existing["id"], existing["lang"] or detect_lang(language_code)
    return None, detect_lang(language_code)
