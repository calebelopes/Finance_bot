"""Tests for web.bot_username — the resolver behind the t.me link button."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from web import bot_username as bu


@pytest.fixture(autouse=True)
def _reset_cache():
    bu.reset_cache_for_tests()
    yield
    bu.reset_cache_for_tests()


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("BOT_USERNAME", "Folhinha_bot")
    monkeypatch.setenv("TOKEN", "irrelevant")
    assert bu.get_bot_username() == "Folhinha_bot"


def test_env_strips_at_sign(monkeypatch):
    monkeypatch.setenv("BOT_USERNAME", "@MyBot")
    assert bu.get_bot_username() == "MyBot"


def test_placeholder_is_rejected(monkeypatch):
    """The exact string from .env.example must NEVER be used — it points
    to a stranger's bot."""
    monkeypatch.setenv("BOT_USERNAME", "your_finance_bot")
    monkeypatch.delenv("TOKEN", raising=False)
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    assert bu.get_bot_username() == ""


def test_falls_back_to_telegram_api(monkeypatch):
    monkeypatch.delenv("BOT_USERNAME", raising=False)
    monkeypatch.setenv("TOKEN", "fake-token")

    class FakeResp:
        def __init__(self, body: bytes):
            self._body = body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return self._body

    body = b'{"ok":true,"result":{"username":"Folhinha_bot"}}'
    with patch("urllib.request.urlopen", return_value=FakeResp(body)):
        assert bu.get_bot_username() == "Folhinha_bot"


def test_returns_empty_when_telegram_fails(monkeypatch):
    monkeypatch.delenv("BOT_USERNAME", raising=False)
    monkeypatch.setenv("TOKEN", "fake-token")
    with patch("urllib.request.urlopen", side_effect=OSError("boom")):
        assert bu.get_bot_username() == ""


def test_returns_empty_when_no_token(monkeypatch):
    monkeypatch.delenv("BOT_USERNAME", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    assert bu.get_bot_username() == ""


def test_result_is_cached(monkeypatch):
    monkeypatch.setenv("BOT_USERNAME", "Folhinha_bot")
    assert bu.get_bot_username() == "Folhinha_bot"
    monkeypatch.setenv("BOT_USERNAME", "Other_bot")
    assert bu.get_bot_username() == "Folhinha_bot"  # cached
    bu.reset_cache_for_tests()
    assert bu.get_bot_username() == "Other_bot"
