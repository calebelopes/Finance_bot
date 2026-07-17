"""Tiny in-process, fixed-window rate limiter.

Deliberately dependency-free and per-process. The app runs as a single
uvicorn instance today, so a shared store (e.g. Redis) would be premature
complexity. If it's ever scaled horizontally, swap the backing store here
without touching call sites.

Used to blunt password brute-force / credential-stuffing on the auth
endpoints, where each attempt otherwise triggers an expensive PBKDF2
verification.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Request


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_gc = 0.0

    def _gc(self, now: float) -> None:
        """Drop keys whose attempts have all aged out (bounded memory)."""
        if now - self._last_gc < self.window:
            return
        self._last_gc = now
        cutoff = now - self.window
        stale = [k for k, dq in self._hits.items() if not dq or dq[-1] <= cutoff]
        for k in stale:
            self._hits.pop(k, None)

    def check(self, key: str) -> tuple[bool, int]:
        """Register an attempt for *key*.

        Returns ``(allowed, retry_after_seconds)``. When blocked, no new
        attempt is recorded so the window still drains normally.
        """
        now = time.monotonic()
        with self._lock:
            self._gc(now)
            dq = self._hits.setdefault(key, deque())
            cutoff = now - self.window
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= self.max_attempts:
                retry = int(self.window - (now - dq[0])) + 1
                return False, max(retry, 1)
            dq.append(now)
            return True, 0

    def reset(self, key: str) -> None:
        """Forget a key's attempts (e.g. after a successful login)."""
        with self._lock:
            self._hits.pop(key, None)


def client_key(request: Request) -> str:
    """Best-effort client identity for rate-limiting.

    Relies on uvicorn's ``--proxy-headers`` populating ``request.client``
    from ``X-Forwarded-For`` when behind a trusted reverse proxy.
    """
    return request.client.host if request.client else "unknown"
