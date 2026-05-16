"""Tests for the Telegram → local user *lookup* used by the bot.

The web is the source of truth for accounts. The bot never auto-creates
a row for an incoming Telegram user — it only looks one up. These tests
exercise that contract end-to-end (lookup_telegram_user + DB schema).
"""

from unittest.mock import patch

import pytest

from utils import db
from utils.auth import lookup_telegram_user


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db_file = str(tmp_path / "bot_lookup.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        yield db_file


class TestLookupTelegramUser:
    def test_unlinked_returns_none_and_detected_lang(self):
        local_id, lang = lookup_telegram_user(7777001, "en")
        assert local_id is None
        assert lang == "en"

    def test_unlinked_unknown_lang_falls_back_to_default(self):
        local_id, lang = lookup_telegram_user(7777002, "klingon")
        assert local_id is None
        assert lang == "pt"

    def test_linked_returns_local_id_and_stored_lang(self):
        # Web user signs up first, then links Telegram.
        web_id = db.create_web_user("alice", "secret123", email="a@example.com")
        db.set_lang(web_id, "ja")
        assert db.link_telegram_to_user(web_id, 7777003) is True

        local_id, lang = lookup_telegram_user(7777003, "en")
        assert local_id == web_id
        # Stored lang takes precedence over Telegram metadata.
        assert lang == "ja"

    def test_lookup_does_not_create_row(self):
        """The whole point of the new flow: bot lookups must NEVER insert."""
        before = self._count_users()
        lookup_telegram_user(8888888, "pt")
        lookup_telegram_user(8888889, "en")
        after = self._count_users()
        assert before == after == 0

    def test_two_linked_users_are_distinct(self):
        a = db.create_web_user("aa", "pw_aaaaaa", email="aa@example.com")
        b = db.create_web_user("bb", "pw_bbbbbb", email="bb@example.com")
        db.link_telegram_to_user(a, 9001)
        db.link_telegram_to_user(b, 9002)

        ra, _ = lookup_telegram_user(9001, "pt")
        rb, _ = lookup_telegram_user(9002, "pt")
        assert ra == a
        assert rb == b
        assert ra != rb

    @staticmethod
    def _count_users() -> int:
        with db._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return row["n"]


class TestLinkInteropWithDB:
    def test_lookup_after_link_works_with_transactions(self):
        web_id = db.create_web_user("spender", "pw_secret", email="s@example.com")
        db.link_telegram_to_user(web_id, 9100)

        local_id, _ = lookup_telegram_user(9100, "pt")
        assert local_id == web_id

        tx_id = db.store_transaction(
            local_id, "spender", "jantar", 30.0, "Refeição", "expense",
        )
        txs = db.get_transactions(local_id, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(txs) == 1
        assert txs[0]["id"] == tx_id

    def test_link_collision_blocks_second_user(self):
        a = db.create_web_user("aa", "pw_aaaaaa", email="aa@example.com")
        b = db.create_web_user("bb", "pw_bbbbbb", email="bb@example.com")
        assert db.link_telegram_to_user(a, 9200) is True
        # Second account claiming the same Telegram id is rejected.
        assert db.link_telegram_to_user(b, 9200) is False
