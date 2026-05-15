"""Shared authentication helpers used by both bot and web layers.

Pure-Python: no telegram or web framework imports, so it can be tested in isolation.
"""

from utils import db
from utils.i18n import detect_lang


def resolve_telegram_user(
    telegram_id: int,
    username: str | None,
    language_code: str | None,
) -> tuple[int, str]:
    """Resolve a Telegram user to a local users.id, creating the row on first contact.

    Returns (local_user_id, lang). Used by the bot to map every Telegram update to
    the local primary key, and by the web /link-telegram callback. Auto-detects
    initial language from Telegram metadata only on first contact.
    """
    detected_lang = detect_lang(language_code)
    existing = db.get_user_by_telegram_id(telegram_id)
    if existing:
        if username and username != existing["username"]:
            db.ensure_user_by_telegram_id(telegram_id, username, None)
        return existing["id"], existing["lang"]
    local_id = db.ensure_user_by_telegram_id(telegram_id, username, detected_lang)
    return local_id, detected_lang
