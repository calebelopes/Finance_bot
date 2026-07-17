"""Shared pytest configuration.

Disable the auth rate limiter for the whole suite. The limiter keeps
per-process counters keyed by client IP, and every TestClient request
shares the same "testclient" host — so without this the many login/signup
POSTs across the suite would trip the throttle and cause spurious 429s.
Tests that specifically exercise rate limiting flip the flag back on
locally (see tests/test_ratelimit.py).

Set at import time (before web.routes.auth is imported by any test) so the
module-level ``_RATE_LIMIT_ENABLED`` flag reads the disabled value.
"""

import os

os.environ.setdefault("WEB_RATE_LIMIT_ENABLED", "0")
