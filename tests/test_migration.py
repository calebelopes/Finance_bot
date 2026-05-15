"""Tests for the web-first schema migration (telegram_id decoupling)."""

import sqlite3
from unittest.mock import patch

import pytest

from utils import db


@pytest.fixture
def legacy_db(tmp_path):
    """Build a legacy-shape database (users.id == telegram_id, no telegram_id column)."""
    db_file = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
    conn.execute(
        "INSERT INTO users (id, username) VALUES (?, ?)", (8000000001, "legacy_user")
    )
    conn.execute(
        "INSERT INTO users (id, username) VALUES (?, ?)", (8000000002, "legacy_user2")
    )
    conn.commit()
    conn.close()
    return db_file


class TestUsersMigration:
    def test_telegram_id_column_added(self, tmp_path):
        db_file = str(tmp_path / "fresh.db")
        with patch.object(db, "_db_path", return_value=db_file):
            db.setup_database()
            with db._connect() as conn:
                cols = db._table_columns(conn, "users")
        assert "telegram_id" in cols

    def test_existing_telegram_users_backfilled(self, legacy_db):
        with patch.object(db, "_db_path", return_value=legacy_db):
            db.setup_database()
            with db._connect() as conn:
                rows = conn.execute(
                    "SELECT id, telegram_id FROM users ORDER BY id"
                ).fetchall()
        assert len(rows) == 2
        for row in rows:
            assert row["telegram_id"] == row["id"]

    def test_migration_is_idempotent(self, legacy_db):
        with patch.object(db, "_db_path", return_value=legacy_db):
            db.setup_database()
            db.setup_database()
            with db._connect() as conn:
                rows = conn.execute(
                    "SELECT COUNT(*) AS c FROM users"
                ).fetchall()
        assert rows[0]["c"] == 2

    def test_telegram_id_unique_constraint(self, tmp_path):
        db_file = str(tmp_path / "unique.db")
        with patch.object(db, "_db_path", return_value=db_file):
            db.setup_database()
            db.ensure_user_by_telegram_id(123, "u1", "pt")
            # second user with the same telegram_id should not insert a new row
            local_id_2 = db.ensure_user_by_telegram_id(123, "u1", "pt")
            with db._connect() as conn:
                rows = conn.execute("SELECT COUNT(*) AS c FROM users").fetchall()
        assert rows[0]["c"] == 1
        assert local_id_2 is not None

    def test_telegram_link_codes_table_created(self, tmp_path):
        db_file = str(tmp_path / "codes.db")
        with patch.object(db, "_db_path", return_value=db_file):
            db.setup_database()
            with db._connect() as conn:
                tables = {
                    r["name"]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
        assert "telegram_link_codes" in tables


@pytest.fixture(autouse=False)
def fresh_db(tmp_path):
    db_file = str(tmp_path / "fresh.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        yield db_file


class TestTelegramResolution:
    def test_create_new_telegram_user(self, fresh_db):
        local_id = db.ensure_user_by_telegram_id(99001, "newuser", "pt")
        assert local_id is not None
        looked = db.get_user_by_telegram_id(99001)
        assert looked is not None
        assert looked["id"] == local_id
        assert looked["username"] == "newuser"
        assert looked["telegram_id"] == 99001

    def test_existing_user_returns_same_local_id(self, fresh_db):
        a = db.ensure_user_by_telegram_id(99002, "u", "pt")
        b = db.ensure_user_by_telegram_id(99002, "u", "pt")
        assert a == b

    def test_username_update(self, fresh_db):
        db.ensure_user_by_telegram_id(99003, "old_handle", "pt")
        db.ensure_user_by_telegram_id(99003, "new_handle", None)
        looked = db.get_user_by_telegram_id(99003)
        assert looked["username"] == "new_handle"

    def test_get_unknown_returns_none(self, fresh_db):
        assert db.get_user_by_telegram_id(404404) is None


class TestWebSignup:
    def test_create_web_user_no_telegram(self, fresh_db):
        local_id = db.create_web_user("alice", "pass1234", lang="en", currency="USD")
        assert local_id is not None
        with db._connect() as conn:
            row = conn.execute(
                "SELECT username, telegram_id, lang FROM users WHERE id = ?", (local_id,)
            ).fetchone()
        assert row["username"] == "alice"
        assert row["telegram_id"] is None
        assert row["lang"] == "en"

    def test_create_web_user_creates_preferences(self, fresh_db):
        local_id = db.create_web_user("bob", "pass1234", currency="JPY", timezone="Asia/Tokyo")
        prefs = db.get_user_preferences(local_id)
        assert prefs["currency_default"] == "JPY"
        assert prefs["timezone"] == "Asia/Tokyo"

    def test_username_collision_returns_none(self, fresh_db):
        first = db.create_web_user("dup", "pass1234")
        second = db.create_web_user("dup", "pass1234")
        assert first is not None
        assert second is None

    def test_authentication_works_after_signup(self, fresh_db):
        local_id = db.create_web_user("charlie", "secret123")
        result = db.authenticate_user("charlie", "secret123")
        assert result is not None
        assert result["id"] == local_id

    def test_authentication_wrong_password(self, fresh_db):
        db.create_web_user("dave", "secret123")
        assert db.authenticate_user("dave", "wrong") is None


class TestTelegramLink:
    def test_link_to_existing_user(self, fresh_db):
        local_id = db.create_web_user("emma", "pass1234")
        assert db.link_telegram_to_user(local_id, 55501) is True
        looked = db.get_user_by_telegram_id(55501)
        assert looked is not None and looked["id"] == local_id

    def test_link_collision_rejected(self, fresh_db):
        a = db.create_web_user("user_a", "pass1234")
        b = db.create_web_user("user_b", "pass1234")
        assert db.link_telegram_to_user(a, 55502) is True
        assert db.link_telegram_to_user(b, 55502) is False

    def test_unlink_clears_telegram_id(self, fresh_db):
        local_id = db.create_web_user("frank", "pass1234")
        db.link_telegram_to_user(local_id, 55503)
        db.unlink_telegram(local_id)
        assert db.get_user_by_telegram_id(55503) is None


class TestLinkCodes:
    def test_create_and_consume(self, fresh_db):
        local_id = db.create_web_user("grace", "pass1234")
        code = db.create_telegram_link_code(local_id)
        assert len(code) == 6
        assert code.isdigit()
        consumed = db.consume_telegram_link_code(code)
        assert consumed == local_id

    def test_consume_twice_fails(self, fresh_db):
        local_id = db.create_web_user("henry", "pass1234")
        code = db.create_telegram_link_code(local_id)
        db.consume_telegram_link_code(code)
        assert db.consume_telegram_link_code(code) is None

    def test_unknown_code_fails(self, fresh_db):
        assert db.consume_telegram_link_code("000000") is None

    def test_replacing_code_invalidates_old(self, fresh_db):
        local_id = db.create_web_user("ivy", "pass1234")
        old_code = db.create_telegram_link_code(local_id)
        new_code = db.create_telegram_link_code(local_id)
        assert db.consume_telegram_link_code(old_code) is None
        assert db.consume_telegram_link_code(new_code) == local_id
