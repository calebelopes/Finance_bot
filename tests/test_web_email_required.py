"""Email-required gate, /email-setup flow, and /settings/email change."""

import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from utils import db


@pytest.fixture
def client_factory(tmp_path):
    db_file = str(tmp_path / "email.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        from web import main as web_main  # noqa: PLC0415

        def _make(username="alice", password="pass1234", email=None, admin=False):
            uid = db.create_web_user(username, password, email=email)
            if admin:
                db.set_admin(uid, True)
            client = TestClient(web_main.app)
            token = db.create_session(uid)
            client.cookies.set("finance_session", token)
            return client, uid

        yield _make


def _csrf(client, path: str) -> str:
    r = client.get(path)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m is not None, f"no csrf token on {path}"
    return m.group(1)


class TestEmailGate:
    """Routes that need a confirmed email redirect bare accounts to /email-setup."""

    @pytest.mark.parametrize("path", ["/app", "/dashboard", "/recurring"])
    def test_no_email_user_is_redirected_to_setup(self, client_factory, path):
        client, _ = client_factory(email=None)
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/email-setup?next=")
        assert path in r.headers["location"]

    def test_admin_route_also_gated(self, client_factory):
        client, _ = client_factory(email=None, admin=True)
        r = client.get("/admin", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/email-setup?next=/admin")

    def test_settings_is_NOT_gated(self, client_factory):
        """/settings must remain reachable so users can fill in their email there."""
        client, _ = client_factory(email=None)
        r = client.get("/settings")
        assert r.status_code == 200

    def test_user_with_email_passes_through(self, client_factory):
        client, _ = client_factory(email="alice@example.com")
        r = client.get("/app", follow_redirects=False)
        assert r.status_code == 200

    def test_htmx_request_gets_hx_redirect(self, client_factory):
        client, _ = client_factory(email=None)
        r = client.post(
            "/app/chat",
            data={"text": "jantar 30", "csrf_token": "x"},
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )
        assert r.status_code == 401
        assert r.headers.get("HX-Redirect", "").startswith("/email-setup?next=")


class TestEmailSetupPage:
    def test_renders_for_user_without_email(self, client_factory):
        client, _ = client_factory(email=None)
        r = client.get("/email-setup")
        assert r.status_code == 200
        assert "csrf_token" in r.text

    def test_user_with_email_redirected_away(self, client_factory):
        client, _ = client_factory(email="alice@example.com")
        r = client.get("/email-setup", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/app"

    def test_anonymous_redirected_to_login(self, tmp_path):
        db_file = str(tmp_path / "anon.db")
        with patch.object(db, "_db_path", return_value=db_file):
            db.setup_database()
            from web import main as web_main  # noqa: PLC0415
            client = TestClient(web_main.app)
            r = client.get("/email-setup", follow_redirects=False)
            assert r.status_code == 303
            assert r.headers["location"] == "/login"

    def test_post_saves_email_and_redirects_to_next(self, client_factory):
        client, uid = client_factory(email=None)
        csrf = _csrf(client, "/email-setup?next=/dashboard")
        r = client.post(
            "/email-setup",
            data={"email": "new@example.com", "next": "/dashboard", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/dashboard"
        assert db.get_user_email(uid) == "new@example.com"

    def test_post_unsafe_next_is_rewritten(self, client_factory):
        client, uid = client_factory(email=None)
        csrf = _csrf(client, "/email-setup")
        r = client.post(
            "/email-setup",
            data={"email": "ok@example.com", "next": "//evil.example/", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/app"

    def test_invalid_email_shows_form_with_error(self, client_factory):
        client, uid = client_factory(email=None)
        csrf = _csrf(client, "/email-setup")
        r = client.post(
            "/email-setup",
            data={"email": "not-an-email", "next": "/app", "csrf_token": csrf},
        )
        assert r.status_code == 400
        assert db.get_user_email(uid) is None

    def test_taken_email_rejected(self, client_factory):
        client_a, _ = client_factory("alice", email="taken@example.com")
        client_b, uid_b = client_factory("bob", email=None)
        csrf = _csrf(client_b, "/email-setup")
        r = client_b.post(
            "/email-setup",
            data={"email": "TAKEN@example.com", "next": "/app", "csrf_token": csrf},
        )
        assert r.status_code == 400
        assert db.get_user_email(uid_b) is None

    def test_csrf_required(self, client_factory):
        client, _ = client_factory(email=None)
        r = client.post(
            "/email-setup",
            data={"email": "x@example.com", "next": "/app", "csrf_token": "wrong"},
        )
        assert r.status_code == 400


class TestSettingsEmailChange:
    def test_change_email(self, client_factory):
        client, uid = client_factory(email="old@example.com")
        csrf = _csrf(client, "/settings")
        r = client.post(
            "/settings/email",
            data={"email": "new@example.com", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "email_saved=1" in r.headers["location"]
        assert db.get_user_email(uid) == "new@example.com"

    def test_can_resave_same_email(self, client_factory):
        """Re-submitting the same address shouldn't trigger 'taken' check on self."""
        client, uid = client_factory(email="same@example.com")
        csrf = _csrf(client, "/settings")
        r = client.post(
            "/settings/email",
            data={"email": "SAME@Example.com", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert db.get_user_email(uid).lower() == "same@example.com"

    def test_change_to_taken_email_rejected(self, client_factory):
        client_a, _ = client_factory("alice", email="alice@example.com")
        _, _ = client_factory("bob", email="bob@example.com")
        csrf = _csrf(client_a, "/settings")
        r = client_a.post(
            "/settings/email",
            data={"email": "bob@example.com", "csrf_token": csrf},
        )
        assert r.status_code == 400

    def test_invalid_email_rejected(self, client_factory):
        client, _ = client_factory(email="alice@example.com")
        csrf = _csrf(client, "/settings")
        r = client.post(
            "/settings/email",
            data={"email": "garbage", "csrf_token": csrf},
        )
        assert r.status_code == 400

    def test_user_without_email_can_set_one_in_settings(self, client_factory):
        client, uid = client_factory(email=None)
        csrf = _csrf(client, "/settings")
        r = client.post(
            "/settings/email",
            data={"email": "first@example.com", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert db.get_user_email(uid) == "first@example.com"

    def test_csrf_required(self, client_factory):
        client, _ = client_factory(email="alice@example.com")
        r = client.post(
            "/settings/email",
            data={"email": "x@example.com", "csrf_token": "wrong"},
        )
        assert r.status_code == 400
