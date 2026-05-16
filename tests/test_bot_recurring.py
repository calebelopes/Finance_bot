"""Tests for the recurring split: ``web.scheduler.execute_due_recurring``
runs the rule, ``bot.main._notify_pending_recurring`` pushes the DM.

Pre-v2.x the bot owned both halves and shipped a regression where
notifications used the local ``users.id`` as a Telegram ``chat_id``.
After the v2.x rework:

* ``web.scheduler.execute_due_recurring`` materializes the transaction,
  writes a ``recurring_logs`` row with ``notified_at = NULL``, and
  advances ``next_run`` — no Telegram dependency.
* ``bot.main._notify_pending_recurring`` polls those unflagged log rows
  and sends DMs to users with a linked ``telegram_id``. Web-only users
  are stamped silently (no DM attempt at all).

The tests below pin both sides of that contract.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot import main as bot_main
from utils import db
from web import scheduler as web_scheduler


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "recurring.db")
    monkeypatch.setenv("WEB_URL", "http://test.local")
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        yield


def _make_due_rule(local_user_id: int, *, description: str = "Netflix",
                   amount: float = 39.90) -> int:
    """Create a recurring rule and force its next_run into the past."""
    rec_id = db.add_recurring(
        local_user_id,
        description=description,
        amount=amount,
        category="Outros",
        action_type="expense",
        currency_code="BRL",
    )
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    with db._connect() as conn:
        conn.execute(
            "UPDATE recurring_transactions SET next_run = ? WHERE id = ?",
            (yesterday, rec_id),
        )
        conn.commit()
    return rec_id


def _mock_application() -> MagicMock:
    application = MagicMock()
    application.bot = MagicMock()
    application.bot.send_message = AsyncMock()
    return application


# ---------------------------------------------------------------------------
# web.scheduler.execute_due_recurring
# ---------------------------------------------------------------------------

class TestExecuteDueRecurring:
    def test_due_rule_creates_tx_log_and_advances(self):
        local_id = db.create_web_user("alice", "pass1234")
        rec_id = _make_due_rule(local_id)

        executed = web_scheduler.execute_due_recurring()
        assert executed == 1

        with db._connect() as conn:
            tx_count = conn.execute(
                "SELECT COUNT(*) AS c FROM transactions "
                "WHERE user_id = ? AND recurring_id = ?",
                (local_id, rec_id),
            ).fetchone()["c"]
            log_row = conn.execute(
                "SELECT notified_at FROM recurring_logs WHERE recurring_id = ?",
                (rec_id,),
            ).fetchone()
            next_run = conn.execute(
                "SELECT next_run FROM recurring_transactions WHERE id = ?",
                (rec_id,),
            ).fetchone()["next_run"]
        assert tx_count == 1
        assert log_row is not None
        assert log_row["notified_at"] is None, (
            "logs must start unnotified so the bot picks them up"
        )
        assert next_run > datetime.date.today().isoformat()

    def test_running_twice_is_idempotent(self):
        """next_run advances on the first tick, so the second tick is
        a no-op until the next month."""
        local_id = db.create_web_user("bob", "pass1234")
        _make_due_rule(local_id)

        first = web_scheduler.execute_due_recurring()
        second = web_scheduler.execute_due_recurring()
        assert first == 1
        assert second == 0

    def test_failed_rule_does_not_block_others(self):
        good = db.create_web_user("good", "pass1234")
        bad = db.create_web_user("bad", "pass1234")
        _make_due_rule(good, description="Spotify", amount=19.90)
        bad_rec_id = _make_due_rule(bad, description="poison", amount=1.0)

        original = db.store_transaction
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            # Fail only when storing the bad rule's transaction.
            calls["n"] += 1
            if kwargs.get("recurring_id") == bad_rec_id:
                raise RuntimeError("simulated DB hiccup")
            return original(*args, **kwargs)

        with patch.object(db, "store_transaction", side_effect=flaky):
            executed = web_scheduler.execute_due_recurring()

        assert executed == 1, "the good rule must still execute"
        with db._connect() as conn:
            good_tx = conn.execute(
                "SELECT COUNT(*) AS c FROM transactions WHERE source = 'recurring'"
            ).fetchone()["c"]
        assert good_tx == 1


# ---------------------------------------------------------------------------
# bot.main._notify_pending_recurring
# ---------------------------------------------------------------------------

class TestNotifyPendingRecurring:
    async def test_dm_is_sent_to_telegram_id_not_local_id(self):
        """Regression guard for the v2.0.x ``chat_id`` bug."""
        local_id = db.create_web_user("alice", "pass1234")
        telegram_id = 555_000_001
        assert db.link_telegram_to_user(local_id, telegram_id) is True
        _make_due_rule(local_id)
        web_scheduler.execute_due_recurring()

        application = _mock_application()
        await bot_main._notify_pending_recurring(application)

        application.bot.send_message.assert_awaited_once()
        call = application.bot.send_message.await_args
        assert call.args[0] == telegram_id
        assert call.args[0] != local_id, (
            "regression: notification used the local users.id instead of "
            "the linked telegram_id"
        )

        with db._connect() as conn:
            stamp = conn.execute(
                "SELECT notified_at FROM recurring_logs"
            ).fetchone()["notified_at"]
        assert stamp is not None, (
            "notified_at must be set after a successful DM so we don't "
            "spam the user every tick"
        )

    async def test_web_only_user_is_stamped_silently(self):
        """A user with no linked Telegram still has their log row
        marked notified — otherwise the bot would re-evaluate it forever."""
        local_id = db.create_web_user("bob", "pass1234")
        _make_due_rule(local_id, description="Spotify", amount=19.90)
        web_scheduler.execute_due_recurring()

        application = _mock_application()
        await bot_main._notify_pending_recurring(application)

        application.bot.send_message.assert_not_awaited()
        with db._connect() as conn:
            stamp = conn.execute(
                "SELECT notified_at FROM recurring_logs"
            ).fetchone()["notified_at"]
        assert stamp is not None

    async def test_send_failure_keeps_row_unflagged_for_retry(self):
        """If Telegram's API blips, the next tick must retry."""
        local_id = db.create_web_user("carol", "pass1234")
        db.link_telegram_to_user(local_id, 777_000_001)
        _make_due_rule(local_id)
        web_scheduler.execute_due_recurring()

        application = _mock_application()
        application.bot.send_message.side_effect = Exception("503 from Telegram")
        await bot_main._notify_pending_recurring(application)

        # Failure must NOT stamp the row.
        with db._connect() as conn:
            stamp = conn.execute(
                "SELECT notified_at FROM recurring_logs"
            ).fetchone()["notified_at"]
        assert stamp is None

        # Next tick succeeds → stamps.
        application.bot.send_message.side_effect = None
        application.bot.send_message.reset_mock()
        await bot_main._notify_pending_recurring(application)
        with db._connect() as conn:
            stamp = conn.execute(
                "SELECT notified_at FROM recurring_logs"
            ).fetchone()["notified_at"]
        assert stamp is not None
        application.bot.send_message.assert_awaited_once()

    async def test_already_notified_rows_are_ignored(self):
        """Pre-stamped rows must never be re-sent."""
        local_id = db.create_web_user("dave", "pass1234")
        db.link_telegram_to_user(local_id, 888_000_001)
        _make_due_rule(local_id)
        web_scheduler.execute_due_recurring()
        with db._connect() as conn:
            log_id = conn.execute(
                "SELECT id FROM recurring_logs"
            ).fetchone()["id"]
        db.mark_recurring_notified(log_id)

        application = _mock_application()
        await bot_main._notify_pending_recurring(application)
        application.bot.send_message.assert_not_awaited()
