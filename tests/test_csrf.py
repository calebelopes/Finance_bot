"""Tests for the double-submit-cookie CSRF protection.

Pre-v2.x CSRF used a stateless HMAC-over-timestamp token. That token was
not bound to the browser/session: any freshly issued token validated for
any user, so it provided no real per-user protection. The current scheme
(``web.auth.CSRFMiddleware`` + ``issue_csrf_token`` / ``verify_csrf_token``)
binds each form token to a random, per-browser ``finance_csrf`` cookie, so
a token minted in one browser is worthless in another.
"""

from __future__ import annotations

import re
import types
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from utils import db
from web import auth as web_auth


def _fake_request(cookie: str | None = None, state_token: str | None = None):
    req = types.SimpleNamespace()
    req.cookies = {}
    if cookie is not None:
        req.cookies[web_auth.CSRF_COOKIE] = cookie
    req.state = types.SimpleNamespace()
    if state_token is not None:
        req.state.csrf_token = state_token
    return req


class TestVerify:
    def test_matching_token_and_cookie_accepted(self):
        req = _fake_request(cookie="abc123")
        assert web_auth.verify_csrf_token(req, "abc123") is True

    def test_mismatched_token_rejected(self):
        req = _fake_request(cookie="abc123")
        assert web_auth.verify_csrf_token(req, "different") is False

    def test_missing_cookie_rejected(self):
        req = _fake_request()
        assert web_auth.verify_csrf_token(req, "abc123") is False

    def test_empty_token_rejected(self):
        req = _fake_request(cookie="abc123")
        assert web_auth.verify_csrf_token(req, "") is False
        assert web_auth.verify_csrf_token(req, None) is False

    def test_state_fallback_when_cookie_not_yet_set(self):
        # On the very first request the cookie isn't in request.cookies yet;
        # the middleware stashes the value on request.state instead.
        req = _fake_request(state_token="statetok")
        assert web_auth.verify_csrf_token(req, "statetok") is True
        assert web_auth.verify_csrf_token(req, "nope") is False


class TestIssue:
    def test_returns_state_token(self):
        req = _fake_request(state_token="from-middleware")
        assert web_auth.issue_csrf_token(req) == "from-middleware"

    def test_generates_and_caches_when_missing(self):
        req = _fake_request()
        tok = web_auth.issue_csrf_token(req)
        assert tok
        assert web_auth.issue_csrf_token(req) == tok


class TestCookieSecureFlag:
    def test_defaults_off(self, monkeypatch):
        monkeypatch.delenv("WEB_COOKIE_SECURE", raising=False)
        assert web_auth._cookie_secure() is False

    @pytest.mark.parametrize("val", ["1", "true", "YES", "on"])
    def test_enabled_values(self, monkeypatch, val):
        monkeypatch.setenv("WEB_COOKIE_SECURE", val)
        assert web_auth._cookie_secure() is True


@pytest.fixture()
def client(tmp_path):
    db_file = str(tmp_path / "csrf.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        from web import main as web_main  # noqa: PLC0415
        yield TestClient(web_main.app)


class TestIntegration:
    def _login(self, client, username="alice"):
        uid = db.create_web_user(username, "secret123", email=f"{username}@ex.com")
        token = db.create_session(uid)
        client.cookies.set("finance_session", token)
        return uid

    def test_middleware_sets_csrf_cookie(self, client):
        r = client.get("/login")
        assert r.status_code == 200
        assert "finance_csrf" in r.headers.get("set-cookie", "")

    def test_own_token_is_accepted(self, client):
        self._login(client)
        r = client.get("/app")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
        r = client.post(
            "/app/chat",
            data={"text": "coffee 5", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 200

    def test_foreign_token_is_rejected(self, client):
        """A token minted in a *different* browser must not validate here —
        this is the property the old stateless scheme lacked."""
        self._login(client)
        client.get("/app")  # establishes this browser's finance_csrf cookie

        # Attacker mints a valid token from their own anonymous session.
        attacker = TestClient(client.app)
        stolen = re.search(
            r'name="csrf_token" value="([^"]+)"', attacker.get("/login").text
        ).group(1)

        r = client.post(
            "/app/chat",
            data={"text": "forged", "csrf_token": stolen},
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 400
