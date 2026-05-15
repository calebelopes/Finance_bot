"""Resolve the Telegram bot username for use in deep-link buttons.

Resolution order (first non-empty wins):
  1. BOT_USERNAME env var (manual override).
  2. Telegram getMe() called with the TOKEN env var (cached for the
     lifetime of the process).
  3. Empty string — the caller MUST fall back to a username-less UX
     instead of rendering a wrong/placeholder t.me link.

Until v2.0.0 the fallback was the literal string ``your_finance_bot``,
which actually exists on Telegram and belongs to a third party — so
users clicking "Link Telegram" landed on the wrong bot. We never want
that to happen again, even if BOT_USERNAME is missing on the server.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_cached: str | None = None
_TIMEOUT_S = 4.0


def _from_env() -> str:
    raw = (os.getenv("BOT_USERNAME") or "").strip().lstrip("@")
    # Reject the example placeholder explicitly so a forgotten copy of
    # .env.example doesn't redirect users to a stranger's bot.
    if raw and raw.lower() != "your_finance_bot":
        return raw
    return ""


def _from_telegram_api() -> str:
    token = (os.getenv("TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        return ""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return ""
    if not payload.get("ok"):
        return ""
    return (payload.get("result", {}) or {}).get("username", "") or ""


def get_bot_username() -> str:
    """Return the bot's @username (without the @), or '' if unknown."""
    global _cached
    if _cached is not None:
        return _cached
    resolved = _from_env() or _from_telegram_api()
    _cached = resolved
    return resolved


def reset_cache_for_tests() -> None:
    """Clear the cached username (test-only helper)."""
    global _cached
    _cached = None
