"""Tests for individual bot commands beyond the linked/unlinked gate.

These exercise the *behavior* of each handler once the user is already
authenticated and gated through ``_require_linked_user``: argument
parsing, side effects on the DB, and the reply that lands on Telegram.

The unlinked-user redirect path is already covered exhaustively in
``tests/test_bot_gate.py`` — here we stay focused on positive flows
plus the error branches that don't go through the gate.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot import main as bot_main
from utils import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "bot_commands.db")
    monkeypatch.setenv("WEB_URL", "http://test.local")
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        yield


def _make_update(telegram_id: int, *, username: str | None = None,
                 lang_code: str = "pt", text: str | None = None,
                 args: list[str] | None = None):
    """Build a minimal mock telegram.Update for handlers.

    ``username`` defaults to None on purpose: ``_resolve_linked_user``
    syncs Telegram username changes back to the local user row. With a
    truthy default like ``"tg_user"`` every command would silently
    overwrite the linked user's stored username, which trips up tests
    that assume the username they used in ``create_web_user`` is stable.
    Pass an explicit username only when the test needs that sync path.
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


def _link(username: str, telegram_id: int, *, email_suffix: str = "@example.com") -> int:
    """Create a web user and link them to ``telegram_id``."""
    local_id = db.create_web_user(
        username, "secret123", email=f"{username}{email_suffix}",
    )
    assert db.link_telegram_to_user(local_id, telegram_id) is True
    return local_id


# ---------------------------------------------------------------------------
# /setpassword
# ---------------------------------------------------------------------------

class TestSetPasswordCommand:
    async def test_no_args_replies_with_usage(self):
        _link("alice", 11111)
        update, context = _make_update(11111)
        await bot_main.cmd_setpassword(update, context)
        update.message.reply_text.assert_awaited_once()
        # No password should have been written.
        update.effective_chat.send_message.assert_not_awaited()

    async def test_short_password_rejected(self):
        _link("bob", 22222)
        update, context = _make_update(22222, args=["abc"])
        await bot_main.cmd_setpassword(update, context)
        msg = update.message.reply_text.await_args.args[0]
        # i18n key lives in pt; we assert the human-visible "6" cue.
        assert "6" in msg
        update.effective_chat.send_message.assert_not_awaited()

    async def test_min_length_boundary_5_is_rejected(self):
        """Regression guard for the ≥6-char policy alignment with the web."""
        _link("carol", 33333)
        update, context = _make_update(33333, args=["12345"])
        await bot_main.cmd_setpassword(update, context)
        update.effective_chat.send_message.assert_not_awaited()

    async def test_valid_password_is_persisted_and_original_message_deleted(self):
        _link("dave", 44444)
        update, context = _make_update(44444, args=["new-strong-pw"])

        await bot_main.cmd_setpassword(update, context)

        # The plain-text message must be deleted to avoid the password
        # lingering in the chat history.
        update.message.delete.assert_awaited_once()
        # Confirmation lands via effective_chat.send_message (so it is a
        # *new* message, not a reply to the deleted one).
        update.effective_chat.send_message.assert_awaited_once()
        confirmation = update.effective_chat.send_message.await_args.args[0]
        assert "http://test.local" in confirmation, (
            "/setpassword confirmation should point users to the website"
        )

        # Authenticate via the public API to prove the new password works.
        assert db.authenticate_user("dave", "new-strong-pw") is not None

    async def test_password_with_spaces_is_joined_from_args(self):
        _link("erin", 55555)
        update, context = _make_update(55555, args=["a", "b", "longerpw"])
        await bot_main.cmd_setpassword(update, context)

        update.effective_chat.send_message.assert_awaited_once()
        # The actual stored password is "a b longerpw"; verifies the
        # ``" ".join(args)`` contract.
        assert db.authenticate_user("erin", "a b longerpw") is not None


# ---------------------------------------------------------------------------
# /admin
# ---------------------------------------------------------------------------

class TestAdminCommand:
    async def test_non_owner_is_rejected(self, monkeypatch):
        monkeypatch.setenv("BOT_OWNER", "99999")
        _link("frank", 11111)
        update, context = _make_update(11111)
        await bot_main.cmd_admin(update, context)

        update.message.reply_text.assert_awaited_once()
        # User must NOT have been promoted/demoted.
        looked = db.get_user_by_telegram_id(11111)
        assert looked is not None
        assert db.is_admin(looked["id"]) is False

    async def test_unset_owner_env_rejects_everyone(self, monkeypatch):
        monkeypatch.delenv("BOT_OWNER", raising=False)
        _link("gina", 22222)
        update, context = _make_update(22222)
        await bot_main.cmd_admin(update, context)

        update.message.reply_text.assert_awaited_once()
        looked = db.get_user_by_telegram_id(22222)
        assert db.is_admin(looked["id"]) is False

    async def test_owner_self_promotes_then_demotes(self, monkeypatch):
        monkeypatch.setenv("BOT_OWNER", "33333")
        local_id = _link("hank", 33333)
        update, context = _make_update(33333)

        await bot_main.cmd_admin(update, context)
        assert db.is_admin(local_id) is True

        # Second call toggles back to non-admin.
        update2, context2 = _make_update(33333)
        await bot_main.cmd_admin(update2, context2)
        assert db.is_admin(local_id) is False

    async def test_owner_promotes_other_telegram_id(self, monkeypatch):
        monkeypatch.setenv("BOT_OWNER", "44444")
        owner_local = _link("ivy", 44444)
        target_local = _link("jack", 55555)

        update, context = _make_update(44444, args=["55555"])
        await bot_main.cmd_admin(update, context)

        assert db.is_admin(target_local) is True
        # Owner is unchanged when targeting someone else.
        assert db.is_admin(owner_local) is False

    async def test_owner_targets_unknown_telegram_id(self, monkeypatch):
        monkeypatch.setenv("BOT_OWNER", "66666")
        _link("kate", 66666)
        update, context = _make_update(66666, args=["999999999"])

        await bot_main.cmd_admin(update, context)

        update.message.reply_text.assert_awaited_once()
        # No row should have been created for the unknown id.
        assert db.get_user_by_telegram_id(999999999) is None


# ---------------------------------------------------------------------------
# /addrecurring
# ---------------------------------------------------------------------------

class TestAddRecurringCommand:
    async def test_no_args_replies_with_usage(self):
        _link("alice", 11111)
        update, context = _make_update(11111)
        await bot_main.cmd_addrecurring(update, context)
        update.message.reply_text.assert_awaited_once()
        # No rule should have been persisted.
        looked = db.get_user_by_telegram_id(11111)
        assert db.get_recurring(looked["id"]) == []

    async def test_one_arg_is_treated_as_invalid_usage(self):
        _link("bob", 22222)
        update, context = _make_update(22222, args=["netflix"])
        await bot_main.cmd_addrecurring(update, context)
        looked = db.get_user_by_telegram_id(22222)
        assert db.get_recurring(looked["id"]) == []

    async def test_invalid_amount_replies_with_usage(self):
        _link("carol", 33333)
        update, context = _make_update(33333, args=["netflix", "abc"])
        await bot_main.cmd_addrecurring(update, context)
        looked = db.get_user_by_telegram_id(33333)
        assert db.get_recurring(looked["id"]) == []

    async def test_creates_expense_rule_with_default_day(self):
        local_id = _link("dave", 44444)
        update, context = _make_update(
            44444, args=["netflix", "39,90"],
        )
        await bot_main.cmd_addrecurring(update, context)

        rules = db.get_recurring(local_id)
        assert len(rules) == 1
        rule = rules[0]
        assert rule["description"] == "netflix"
        assert rule["amount"] == pytest.approx(39.90)
        assert rule["type"] == "expense"

    async def test_income_marker_plus_prefix(self):
        local_id = _link("erin", 55555)
        update, context = _make_update(
            55555, args=["+salario", "5000", "5"],
        )
        await bot_main.cmd_addrecurring(update, context)

        rules = db.get_recurring(local_id)
        assert len(rules) == 1
        rule = rules[0]
        assert rule["description"] == "salario", (
            "the leading '+' marker must be stripped from the stored description"
        )
        assert rule["type"] == "income"
        assert rule["day_of_month"] == 5

    async def test_day_is_clamped_to_1_28_range(self):
        """Day-of-month above 28 would risk skipping months (Feb has no 30th)."""
        local_id = _link("frank", 66666)
        update, context = _make_update(
            66666, args=["aluguel", "1500", "31"],
        )
        await bot_main.cmd_addrecurring(update, context)

        rules = db.get_recurring(local_id)
        assert rules[0]["day_of_month"] == 28


# ---------------------------------------------------------------------------
# cb_fixcat (inline category-correction button)
# ---------------------------------------------------------------------------

def _make_callback(telegram_id: int, *, data: str, message_text: str = "tx"):
    """Build a minimal mock for callback_query handlers."""
    update = MagicMock()
    query = MagicMock()
    query.from_user = MagicMock(id=telegram_id)
    query.data = data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = MagicMock()
    query.message.text = message_text
    update.callback_query = query

    context = MagicMock()
    return update, context, query


class TestCbFixcat:
    async def test_unknown_user_silently_no_ops(self):
        # Telegram id has never linked to a web account.
        update, context, query = _make_callback(
            99999, data="fixcat:42:Alimentação",
        )
        await bot_main.cb_fixcat(update, context)

        query.answer.assert_awaited_once()
        query.edit_message_text.assert_not_awaited()

    async def test_malformed_callback_data_no_ops(self):
        _link("alice", 11111)
        update, context, query = _make_callback(11111, data="fixcat:42")
        await bot_main.cb_fixcat(update, context)

        query.answer.assert_awaited_once()
        query.edit_message_text.assert_not_awaited()

    async def test_non_numeric_tx_id_no_ops(self):
        _link("bob", 22222)
        update, context, query = _make_callback(
            22222, data="fixcat:notanumber:Outros",
        )
        await bot_main.cb_fixcat(update, context)

        query.edit_message_text.assert_not_awaited()

    async def test_known_user_updates_category_and_edits_message(self):
        local_id = _link("carol", 33333)
        # Create a transaction we can later re-categorize.
        tx_id = db.store_transaction(
            local_id, "carol", "uber", 25.0, "Outros", "expense",
            currency_code="BRL",
        )

        update, context, query = _make_callback(
            33333, data=f"fixcat:{tx_id}:Transporte",
            message_text="Original tx body",
        )
        await bot_main.cb_fixcat(update, context)

        query.edit_message_text.assert_awaited_once()
        rendered = query.edit_message_text.await_args.args[0]
        assert "Original tx body" in rendered, (
            "the edited message must preserve the original body and append "
            "the i18n confirmation line"
        )

        # The DB should reflect the new category.
        with db._connect() as conn:
            cat = conn.execute(
                "SELECT category FROM transactions WHERE id = ?", (tx_id,)
            ).fetchone()["category"]
        assert cat == "Transporte"

    async def test_unknown_tx_id_does_not_edit_message(self):
        """If the tx doesn't belong to this user (or doesn't exist),
        ``update_transaction_category`` returns False and we skip the edit."""
        _link("dave", 44444)
        update, context, query = _make_callback(
            44444, data="fixcat:9999999:Outros",
        )
        await bot_main.cb_fixcat(update, context)

        query.edit_message_text.assert_not_awaited()
