"""Tests for web.bot_username — the resolver behind the t.me link button."""

from __future__ import annotations

from web import bot_username as bu


def test_default_is_folhinha_bot(monkeypatch):
    monkeypatch.delenv("BOT_USERNAME", raising=False)
    assert bu.get_bot_username() == "Folhinha_bot"


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("BOT_USERNAME", "AnotherBot")
    assert bu.get_bot_username() == "AnotherBot"


def test_env_strips_at_sign(monkeypatch):
    monkeypatch.setenv("BOT_USERNAME", "@MyBot")
    assert bu.get_bot_username() == "MyBot"


def test_placeholder_is_rejected(monkeypatch):
    """The exact string from .env.example must NEVER be used — it points
    to a stranger's bot. Resolver must fall back to the canonical
    default instead."""
    monkeypatch.setenv("BOT_USERNAME", "your_finance_bot")
    assert bu.get_bot_username() == "Folhinha_bot"


def test_placeholder_rejection_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("BOT_USERNAME", "Your_Finance_Bot")
    assert bu.get_bot_username() == "Folhinha_bot"


def test_blank_env_uses_default(monkeypatch):
    monkeypatch.setenv("BOT_USERNAME", "   ")
    assert bu.get_bot_username() == "Folhinha_bot"
