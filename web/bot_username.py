"""Resolve the Telegram bot username for use in deep-link buttons.

This project always points to a single bot: ``Folhinha_bot``. We expose
an env override (``BOT_USERNAME``) only so that forks running a
different bot can swap it without a code change.

Resolution order:
  1. BOT_USERNAME env var (manual override; ``your_finance_bot`` —
     the placeholder from .env.example — is explicitly rejected so a
     forgotten copy of the example file can never redirect users to a
     stranger's bot).
  2. ``Folhinha_bot`` — the canonical default.
"""

from __future__ import annotations

import os

DEFAULT_BOT_USERNAME = "Folhinha_bot"


def get_bot_username() -> str:
    """Return the bot's @username (without the @)."""
    raw = (os.getenv("BOT_USERNAME") or "").strip().lstrip("@")
    if raw and raw.lower() != "your_finance_bot":
        return raw
    return DEFAULT_BOT_USERNAME
