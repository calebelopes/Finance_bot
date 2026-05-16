"""Tests for the bot's web-first identity gate.

The bot is a *companion* to the website. Every authenticated command
must check that the incoming Telegram id is already linked to a web
account; otherwise it replies with a "register on the website first"
message instead of doing anything.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot import main as bot_main
from utils import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "bot_gate.db")
    monkeypatch.setenv("WEB_URL", "http://test.local")
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        yield


def _make_update(telegram_id: int, *, username: str = "tg_user",
                 lang_code: str = "pt", text: str | None = None,
                 args: list[str] | None = None):
    """Build a minimal mock telegram.Update suitable for the bot handlers.

    Returns (update, context) tuple. The ``update.message.reply_text`` and
    ``context.args`` attributes are the things handlers actually touch.
    """
    update = MagicMock()
    update.effective_user = MagicMock(
        id=telegram_id, username=username, language_code=lang_code,
    )
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.delete = AsyncMock()
    update.message.text = text
    update.effective_chat = MagicMock()
    update.effective_chat.send_message = AsyncMock()

    context = MagicMock()
    context.args = args or []
    return update, context


class TestStartCommand:
    async def test_unlinked_user_gets_redirect_to_web(self):
        update, context = _make_update(11111, lang_code="en")
        await bot_main.cmd_start(update, context)

        update.message.reply_text.assert_awaited_once()
        msg = update.message.reply_text.await_args.args[0]
        assert "http://test.local" in msg
        assert "Welcome" in msg or "create your account" in msg.lower()

    async def test_linked_user_gets_friendly_start(self):
        web_id = db.create_web_user("alice", "secret123", email="a@example.com")
        db.link_telegram_to_user(web_id, 22222)

        update, context = _make_update(22222)
        await bot_main.cmd_start(update, context)

        msg = update.message.reply_text.await_args.args[0]
        # Welcome / start copy mentions /help and the bem-vindo greeting.
        assert "/help" in msg

    async def test_link_deep_link_attaches_telegram_to_existing_web_user(self):
        web_id = db.create_web_user("bob", "secret123", email="b@example.com")
        code = db.create_telegram_link_code(web_id, ttl_minutes=10)

        update, context = _make_update(33333, args=[f"link_{code}"])
        await bot_main.cmd_start(update, context)

        looked = db.get_user_by_telegram_id(33333)
        assert looked is not None
        assert looked["id"] == web_id

    async def test_link_deep_link_with_invalid_code_does_not_create_user(self):
        update, context = _make_update(44444, args=["link_DEADBEEF"])
        await bot_main.cmd_start(update, context)
        assert db.get_user_by_telegram_id(44444) is None


class TestHelpCommand:
    async def test_unlinked_user_gets_redirect(self):
        update, context = _make_update(55555, lang_code="pt")
        await bot_main.cmd_help(update, context)

        msg = update.message.reply_text.await_args.args[0]
        assert "http://test.local" in msg
        assert "/today" not in msg  # don't reveal commands they can't use

    async def test_linked_user_gets_full_help(self):
        web_id = db.create_web_user("carol", "secret123", email="c@example.com")
        db.link_telegram_to_user(web_id, 66666)

        update, context = _make_update(66666)
        await bot_main.cmd_help(update, context)

        msg = update.message.reply_text.await_args.args[0]
        assert "http://test.local" in msg
        assert "/today" in msg


class TestFreeTextHandler:
    async def test_unlinked_user_message_is_not_stored(self):
        update, context = _make_update(77777, text="jantar 30,50")
        await bot_main.handle_message(update, context)

        msg = update.message.reply_text.await_args.args[0]
        assert "http://test.local" in msg
        assert db.get_user_by_telegram_id(77777) is None

    async def test_linked_user_message_stores_transaction(self):
        web_id = db.create_web_user("dave", "secret123", email="d@example.com")
        db.link_telegram_to_user(web_id, 88888)

        update, context = _make_update(88888, text="jantar 30,50")
        await bot_main.handle_message(update, context)

        txs = db.get_transactions(web_id, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(txs) == 1
        assert txs[0]["amount_original"] == pytest.approx(30.50)


class TestNoPhantomCallbacks:
    async def test_currency_callback_ignores_unlinked_user(self):
        query = MagicMock()
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.from_user = MagicMock(id=99999, username="who", language_code="pt")
        query.data = "currency:USD"

        update = MagicMock()
        update.callback_query = query

        await bot_main.cb_setcurrency(update, MagicMock())
        # Critical: must not insert a phantom row for an unlinked user.
        assert db.get_user_by_telegram_id(99999) is None
        query.edit_message_text.assert_not_awaited()
