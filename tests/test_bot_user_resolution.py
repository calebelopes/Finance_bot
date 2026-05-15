"""Tests for the Telegram → local user resolver shared by bot and web layers."""

from unittest.mock import patch

import pytest

from utils import db
from utils.auth import resolve_telegram_user


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db_file = str(tmp_path / "bot_resolve.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        yield db_file


class TestResolveTelegramUser:
    def test_creates_new_local_user_on_first_contact(self):
        local_id, lang = resolve_telegram_user(7777001, "alice", "en")

        assert local_id is not None
        assert lang == "en"
        looked = db.get_user_by_telegram_id(7777001)
        assert looked is not None
        assert looked["id"] == local_id
        assert looked["username"] == "alice"

    def test_returns_existing_local_id_on_repeat(self):
        first_id, _ = resolve_telegram_user(7777002, "bob", "pt")
        second_id, _ = resolve_telegram_user(7777002, "bob", "pt")
        assert first_id == second_id

    def test_uses_stored_lang_over_telegram_metadata(self):
        # First contact registers user with lang detected from Telegram metadata
        resolve_telegram_user(7777003, "carol", "en")
        # User changes language preference manually
        looked = db.get_user_by_telegram_id(7777003)
        db.set_lang(looked["id"], "ja")

        # Subsequent updates should now report the stored lang, not Telegram's
        _, lang = resolve_telegram_user(7777003, "carol", "en")
        assert lang == "ja"

    def test_username_change_is_persisted(self):
        resolve_telegram_user(7777004, "old_handle", "pt")
        resolve_telegram_user(7777004, "new_handle", "pt")
        looked = db.get_user_by_telegram_id(7777004)
        assert looked["username"] == "new_handle"

    def test_two_telegram_users_get_distinct_local_ids(self):
        a, _ = resolve_telegram_user(7777005, "x", "pt")
        b, _ = resolve_telegram_user(7777006, "y", "pt")
        assert a != b

    def test_local_ids_are_independent_of_telegram_ids(self):
        # The whole point of the migration: huge Telegram ids don't become local ids
        local_id, _ = resolve_telegram_user(8000000099, "huge", "pt")
        looked = db.get_user_by_telegram_id(8000000099)
        assert looked["telegram_id"] == 8000000099
        assert looked["id"] == local_id
        # local_id should be small (autoincrement starting low on a fresh db)
        assert local_id < 100

    def test_unknown_lang_falls_back_to_default(self):
        _, lang = resolve_telegram_user(7777007, "zz", "klingon")
        assert lang == "pt"

    def test_none_username_does_not_overwrite(self):
        resolve_telegram_user(7777008, "set_handle", "pt")
        resolve_telegram_user(7777008, None, "pt")
        looked = db.get_user_by_telegram_id(7777008)
        assert looked["username"] == "set_handle"


class TestResolveInteropWithRestOfDB:
    def test_resolved_id_works_with_store_transaction(self):
        local_id, _ = resolve_telegram_user(7777010, "spender", "pt")

        tx_id = db.store_transaction(
            local_id, "spender", "jantar", 30.0, "Refeição", "expense",
        )
        txs = db.get_transactions(local_id, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(txs) == 1
        assert txs[0]["id"] == tx_id

    def test_resolved_id_works_with_user_preferences(self):
        local_id, _ = resolve_telegram_user(7777011, "configger", "ja")

        prefs = db.get_user_preferences(local_id)
        assert prefs["currency_default"] == "BRL"
        db.set_user_preference(local_id, "currency_default", "JPY")
        assert db.get_user_preferences(local_id)["currency_default"] == "JPY"

    def test_link_existing_web_user(self):
        # Web user signs up first, then links Telegram
        web_id = db.create_web_user("websigner", "secretpass")
        assert db.link_telegram_to_user(web_id, 7777012) is True

        # Subsequent bot contact resolves to the same local id
        resolved_id, _ = resolve_telegram_user(7777012, "websigner", "pt")
        assert resolved_id == web_id
