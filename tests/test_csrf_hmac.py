"""Tests for the stateless HMAC-based CSRF tokens.

Pre-v2.x the implementation kept tokens in a process-local dict. That
silently fell apart under multiple uvicorn workers and lost all
in-flight forms on every restart. The new ``web.auth.issue_csrf_token``
/ ``verify_csrf_token`` pair uses HMAC-SHA256 over a unix timestamp,
so:

* Different processes with the same ``WEB_CSRF_SECRET`` agree on
  validity.
* No server-side store grows over time.
* Tokens still expire after ``CSRF_TTL_SECONDS``.
* Tampering with either half invalidates the token.
"""

from __future__ import annotations

import time

import pytest

from web import auth as web_auth


@pytest.fixture(autouse=True)
def _stable_secret(monkeypatch):
    monkeypatch.setenv("WEB_CSRF_SECRET", "test-secret-please-do-not-reuse")
    yield


class TestCsrfHappyPath:
    def test_freshly_issued_token_validates(self):
        token = web_auth.issue_csrf_token()
        assert web_auth.verify_csrf_token(token) is True

    def test_token_shape_is_two_segments(self):
        token = web_auth.issue_csrf_token()
        ts, sig = token.split(".", 1)
        assert ts.isdigit()
        assert sig  # base64url, not empty

    def test_consecutive_tokens_have_same_secret_so_both_valid(self):
        a = web_auth.issue_csrf_token()
        time.sleep(0.01)
        b = web_auth.issue_csrf_token()
        assert web_auth.verify_csrf_token(a)
        assert web_auth.verify_csrf_token(b)


class TestCsrfRejection:
    def test_empty_token_is_rejected(self):
        assert web_auth.verify_csrf_token("") is False
        assert web_auth.verify_csrf_token(None) is False

    def test_garbage_token_is_rejected(self):
        assert web_auth.verify_csrf_token("not-a-token") is False
        assert web_auth.verify_csrf_token("abc.def") is False  # ts not digit

    def test_tampered_signature_is_rejected(self):
        token = web_auth.issue_csrf_token()
        ts, sig = token.split(".", 1)
        # Flip a single character in the signature.
        bad_sig = ("A" if sig[0] != "A" else "B") + sig[1:]
        assert web_auth.verify_csrf_token(f"{ts}.{bad_sig}") is False

    def test_tampered_timestamp_is_rejected(self):
        """If we move the timestamp, the recomputed HMAC won't match."""
        token = web_auth.issue_csrf_token()
        _, sig = token.split(".", 1)
        forged = f"{int(time.time()) + 9999}.{sig}"
        assert web_auth.verify_csrf_token(forged) is False

    def test_token_older_than_ttl_is_rejected(self):
        old_ts = int(time.time()) - web_auth.CSRF_TTL_SECONDS - 60
        forged = f"{old_ts}.{web_auth._sign(str(old_ts))}"
        assert web_auth.verify_csrf_token(forged) is False

    def test_token_far_in_the_future_is_rejected(self):
        """Skew tolerance is ±60s; anything beyond should be refused
        even if it's signed with the right secret."""
        future_ts = int(time.time()) + 600
        forged = f"{future_ts}.{web_auth._sign(str(future_ts))}"
        assert web_auth.verify_csrf_token(forged) is False


class TestCsrfCrossProcess:
    def test_two_callers_with_same_secret_validate_each_others_tokens(self):
        """The whole point: stateless tokens validate without sharing
        any in-memory dict between callers."""
        # Capture the secret currently in effect.
        token = web_auth.issue_csrf_token()

        # Simulate a "second worker" by clearing any process-local state
        # and validating the token afresh. Since the secret comes from
        # the env var (and the dev fallback would only kick in when
        # unset), this round-trips through the public API.
        web_auth._DEV_SECRET = None
        assert web_auth.verify_csrf_token(token) is True

    def test_changing_secret_invalidates_old_tokens(self, monkeypatch):
        token = web_auth.issue_csrf_token()
        monkeypatch.setenv("WEB_CSRF_SECRET", "different-secret")
        assert web_auth.verify_csrf_token(token) is False


class TestCsrfDevFallback:
    def test_no_env_var_uses_an_ephemeral_secret_that_still_round_trips(
        self, monkeypatch,
    ):
        """When ``WEB_CSRF_SECRET`` is unset, a per-process secret is
        generated. Tokens issued and verified within the same process
        must still work — the operator just loses cross-restart and
        cross-worker validity."""
        monkeypatch.delenv("WEB_CSRF_SECRET", raising=False)
        web_auth._DEV_SECRET = None
        token = web_auth.issue_csrf_token()
        assert web_auth.verify_csrf_token(token) is True
