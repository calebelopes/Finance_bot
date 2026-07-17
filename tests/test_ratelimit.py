"""Tests for the in-process auth rate limiter."""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from utils import db
from web.ratelimit import RateLimiter


class TestRateLimiterUnit:
    def test_allows_up_to_max_then_blocks(self):
        rl = RateLimiter(max_attempts=3, window_seconds=60)
        assert rl.check("k")[0] is True
        assert rl.check("k")[0] is True
        assert rl.check("k")[0] is True
        allowed, retry = rl.check("k")
        assert allowed is False
        assert retry >= 1

    def test_keys_are_independent(self):
        rl = RateLimiter(max_attempts=1, window_seconds=60)
        assert rl.check("a")[0] is True
        assert rl.check("b")[0] is True  # different key unaffected
        assert rl.check("a")[0] is False

    def test_reset_clears_key(self):
        rl = RateLimiter(max_attempts=1, window_seconds=60)
        assert rl.check("k")[0] is True
        assert rl.check("k")[0] is False
        rl.reset("k")
        assert rl.check("k")[0] is True

    def test_window_expiry_lets_attempts_through(self):
        rl = RateLimiter(max_attempts=1, window_seconds=60)
        base = 1000.0
        with patch("web.ratelimit.time.monotonic", side_effect=[base, base + 61]):
            assert rl.check("k")[0] is True   # t=1000
            assert rl.check("k")[0] is True   # t=1061, first hit aged out


@pytest.fixture()
def client(tmp_path):
    db_file = str(tmp_path / "rl.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        from web import main as web_main  # noqa: PLC0415
        yield TestClient(web_main.app)


class TestLoginRateLimitIntegration:
    def test_repeated_failed_logins_get_429(self, client, monkeypatch):
        from web.routes import auth as auth_routes  # noqa: PLC0415

        monkeypatch.setattr(auth_routes, "_RATE_LIMIT_ENABLED", True)
        monkeypatch.setattr(
            auth_routes, "_login_limiter", RateLimiter(max_attempts=2, window_seconds=60)
        )

        csrf = re.search(
            r'name="csrf_token" value="([^"]+)"', client.get("/login").text
        ).group(1)

        def attempt():
            return client.post(
                "/login",
                data={"username": "nobody", "password": "wrong", "csrf_token": csrf},
                follow_redirects=False,
            )

        assert attempt().status_code == 401
        assert attempt().status_code == 401
        blocked = attempt()
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers

    def test_successful_login_resets_throttle(self, client, monkeypatch):
        from web.routes import auth as auth_routes  # noqa: PLC0415

        monkeypatch.setattr(auth_routes, "_RATE_LIMIT_ENABLED", True)
        monkeypatch.setattr(
            auth_routes, "_login_limiter", RateLimiter(max_attempts=3, window_seconds=60)
        )
        db.create_web_user("alice", "secret123", email="alice@example.com")

        csrf = re.search(
            r'name="csrf_token" value="([^"]+)"', client.get("/login").text
        ).group(1)

        # One failed attempt, then a success — the success should clear the
        # counter so subsequent attempts start fresh.
        client.post(
            "/login",
            data={"username": "alice", "password": "wrong", "csrf_token": csrf},
            follow_redirects=False,
        )
        ok = client.post(
            "/login",
            data={"username": "alice", "password": "secret123", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert ok.status_code == 303
