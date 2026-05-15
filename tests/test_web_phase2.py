"""Phase 2 tests: landing, signup, login, logout, settings, CSRF."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from utils import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db_file = str(tmp_path / "phase2.db")
    with patch.object(db, "_db_path", return_value=db_file):
        # setup_database is called inside web.main on import-time, so force
        # a fresh schema in the temp file before importing the app.
        db.setup_database()
        from web import main as web_main  # noqa: PLC0415
        yield TestClient(web_main.app)


class TestLanding:
    def test_landing_renders_for_anonymous(self, fresh_db):
        client = fresh_db
        r = client.get("/")
        assert r.status_code == 200
        assert "Finance" in r.text

    def test_landing_redirects_authenticated(self, fresh_db):
        client = fresh_db
        uid = db.create_web_user("alice", "pass1234")
        token = db.create_session(uid)
        r = client.get("/", cookies={"finance_session": token}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/app"


class TestSignup:
    def test_signup_form_renders(self, fresh_db):
        client = fresh_db
        r = client.get("/signup")
        assert r.status_code == 200
        assert "csrf_token" in r.text

    def test_signup_creates_user_and_logs_in(self, fresh_db):
        client = fresh_db
        # Need to grab a real CSRF token from the form
        r = client.get("/signup")
        import re
        m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
        assert m is not None
        csrf = m.group(1)

        r = client.post(
            "/signup",
            data={
                "username": "bob",
                "password": "secret123",
                "password_confirm": "secret123",
                "lang": "en",
                "currency": "USD",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/app"
        assert r.cookies.get("finance_session") is not None
        # Verify user persisted
        assert db.username_exists("bob")

    def test_signup_rejects_short_password(self, fresh_db):
        client = fresh_db
        r = client.get("/signup")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/signup",
            data={
                "username": "carol", "password": "abc", "password_confirm": "abc",
                "lang": "pt", "currency": "BRL", "csrf_token": csrf,
            },
        )
        assert r.status_code == 400

    def test_signup_rejects_password_mismatch(self, fresh_db):
        client = fresh_db
        r = client.get("/signup")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/signup",
            data={
                "username": "dave", "password": "secret123", "password_confirm": "different",
                "lang": "pt", "currency": "BRL", "csrf_token": csrf,
            },
        )
        assert r.status_code == 400

    def test_signup_with_email_persists_it(self, fresh_db):
        client = fresh_db
        r = client.get("/signup")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/signup",
            data={
                "username": "nora",
                "email": "nora@example.com",
                "password": "secret123",
                "password_confirm": "secret123",
                "lang": "pt", "currency": "BRL", "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert db.email_exists("nora@example.com")

    def test_signup_rejects_invalid_email(self, fresh_db):
        client = fresh_db
        r = client.get("/signup")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/signup",
            data={
                "username": "olivia",
                "email": "not-an-email",
                "password": "secret123", "password_confirm": "secret123",
                "lang": "pt", "currency": "BRL", "csrf_token": csrf,
            },
        )
        assert r.status_code == 400

    def test_signup_rejects_duplicate_email(self, fresh_db):
        client = fresh_db
        db.create_web_user("paul", "secret123", email="paul@example.com")
        r = client.get("/signup")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/signup",
            data={
                "username": "paul2",
                "email": "PAUL@example.com",
                "password": "secret123", "password_confirm": "secret123",
                "lang": "pt", "currency": "BRL", "csrf_token": csrf,
            },
        )
        assert r.status_code == 400

    def test_signup_rejects_duplicate_username(self, fresh_db):
        client = fresh_db
        db.create_web_user("emma", "exist123")
        r = client.get("/signup")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/signup",
            data={
                "username": "emma", "password": "another1", "password_confirm": "another1",
                "lang": "pt", "currency": "BRL", "csrf_token": csrf,
            },
        )
        assert r.status_code == 400

    def test_signup_rejects_missing_csrf(self, fresh_db):
        client = fresh_db
        r = client.post(
            "/signup",
            data={
                "username": "frank", "password": "pass1234", "password_confirm": "pass1234",
                "lang": "pt", "currency": "BRL", "csrf_token": "bogus",
            },
        )
        assert r.status_code == 400

    def test_signup_honeypot_rejects_bots(self, fresh_db):
        client = fresh_db
        r = client.get("/signup")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/signup",
            data={
                "username": "bot_user", "password": "pass1234", "password_confirm": "pass1234",
                "lang": "pt", "currency": "BRL", "csrf_token": csrf,
                "honeypot": "i_am_a_bot",
            },
        )
        assert r.status_code == 400

    def test_signup_creates_preferences(self, fresh_db):
        client = fresh_db
        r = client.get("/signup")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        client.post(
            "/signup",
            data={
                "username": "grace", "password": "pass1234", "password_confirm": "pass1234",
                "lang": "ja", "currency": "JPY", "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        with db._connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = 'grace'"
            ).fetchone()
        prefs = db.get_user_preferences(row["id"])
        assert prefs["currency_default"] == "JPY"


class TestLogin:
    def test_login_form_renders(self, fresh_db):
        client = fresh_db
        r = client.get("/login")
        assert r.status_code == 200
        assert "csrf_token" in r.text

    def test_login_with_correct_credentials(self, fresh_db):
        client = fresh_db
        db.create_web_user("henry", "secret123")
        r = client.get("/login")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/login",
            data={
                "username": "henry", "password": "secret123",
                "csrf_token": csrf, "next": "/app",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.cookies.get("finance_session") is not None

    def test_login_with_wrong_password(self, fresh_db):
        client = fresh_db
        db.create_web_user("ivy", "secret123")
        r = client.get("/login")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/login",
            data={"username": "ivy", "password": "wrong", "csrf_token": csrf},
        )
        assert r.status_code == 401

    def test_login_with_email_address(self, fresh_db):
        """Users who set an email at signup can log in with it."""
        client = fresh_db
        db.create_web_user("kate", "secret123", email="kate@example.com")
        r = client.get("/login")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/login",
            data={
                "username": "kate@example.com", "password": "secret123",
                "csrf_token": csrf, "next": "/app",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.cookies.get("finance_session") is not None

    def test_login_email_case_insensitive(self, fresh_db):
        client = fresh_db
        db.create_web_user("liam", "secret123", email="liam@example.com")
        r = client.get("/login")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/login",
            data={
                "username": "LIAM@Example.COM", "password": "secret123",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_login_unknown_email_rejected(self, fresh_db):
        client = fresh_db
        db.create_web_user("mia", "secret123", email="mia@example.com")
        r = client.get("/login")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/login",
            data={
                "username": "ghost@example.com", "password": "secret123",
                "csrf_token": csrf,
            },
        )
        assert r.status_code == 401

    def test_login_redirect_safe_next(self, fresh_db):
        client = fresh_db
        db.create_web_user("jack", "secret123")
        r = client.get("/login")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        # Hostile next (protocol-relative URL) should be rewritten to /app
        r = client.post(
            "/login",
            data={
                "username": "jack", "password": "secret123",
                "csrf_token": csrf, "next": "//evil.example/",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/app"


class TestLogout:
    def test_logout_clears_session_cookie(self, fresh_db):
        client = fresh_db
        uid = db.create_web_user("kate", "pass1234")
        token = db.create_session(uid)
        client.cookies.set("finance_session", token)

        r = client.post("/logout", follow_redirects=False)
        assert r.status_code == 303
        # Cookie deletion sets max-age=0 in the response
        assert "finance_session" in r.headers.get("set-cookie", "")


class TestRequireUser:
    def test_settings_requires_login(self, fresh_db):
        client = fresh_db
        r = client.get("/settings", follow_redirects=False)
        # 303 redirect to /login
        assert r.status_code == 303
        assert "/login" in r.headers["location"]

    def test_settings_works_for_authenticated(self, fresh_db):
        client = fresh_db
        uid = db.create_web_user("liam", "pass1234")
        token = db.create_session(uid)
        client.cookies.set("finance_session", token)
        r = client.get("/settings")
        assert r.status_code == 200


class TestSettingsUpdate:
    def _login(self, client, username="mike", password="pass1234"):
        uid = db.create_web_user(username, password)
        token = db.create_session(uid)
        client.cookies.set("finance_session", token)
        return uid

    def test_update_preferences(self, fresh_db):
        client = fresh_db
        uid = self._login(client)
        r = client.get("/settings")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/settings/preferences",
            data={"lang": "en", "currency": "EUR", "timezone": "Europe/London", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303
        prefs = db.get_user_preferences(uid)
        assert prefs["currency_default"] == "EUR"
        assert prefs["timezone"] == "Europe/London"
        assert db.get_user_lang(uid) == "en"

    def test_change_password(self, fresh_db):
        client = fresh_db
        self._login(client, "noah", "oldpass1")
        r = client.get("/settings")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/settings/password",
            data={
                "current_password": "oldpass1",
                "new_password": "newpass2",
                "new_password_confirm": "newpass2",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        # New password works
        assert db.authenticate_user("noah", "newpass2") is not None
        # Old password no longer works
        assert db.authenticate_user("noah", "oldpass1") is None

    def test_link_telegram_generates_code(self, fresh_db):
        client = fresh_db
        self._login(client, "olivia", "pass1234")
        r = client.get("/settings")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/settings/link-telegram", data={"csrf_token": csrf},
        )
        assert r.status_code == 200
        # Page should display a 6-digit code
        m = re.search(r'class="font-mono text-5xl[^"]*">\s*(\d{6})\s*<', r.text)
        assert m is not None

    def test_unlink_telegram_clears_link(self, fresh_db):
        client = fresh_db
        uid = self._login(client, "peter", "pass1234")
        db.link_telegram_to_user(uid, 999111)
        r = client.get("/settings")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/settings/unlink-telegram", data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert db.get_user_by_telegram_id(999111) is None

    def test_delete_account_removes_user_and_data(self, fresh_db):
        client = fresh_db
        uid = self._login(client, "quinn", "pass1234")
        db.store_transaction(uid, "quinn", "test", 10.0, "Outros")
        r = client.get("/settings")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/settings/delete-account",
            data={"confirm_username": "quinn", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert not db.username_exists("quinn")
        # Transactions gone
        assert db.get_transactions(uid, "2000-01-01T00:00:00", "2099-01-01T00:00:00") == []

    def test_delete_account_requires_username_confirmation(self, fresh_db):
        client = fresh_db
        self._login(client, "rachel", "pass1234")
        r = client.get("/settings")
        import re
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

        r = client.post(
            "/settings/delete-account",
            data={"confirm_username": "wrong", "csrf_token": csrf},
        )
        assert r.status_code == 400
        assert db.username_exists("rachel")
