"""Tests for the FastAPI lifespan-managed recurring scheduler.

These pin two contracts that the rest of the suite doesn't:

* The scheduler **runs by default** in production and **can be disabled
  for tests** via ``WEB_SCHEDULER_DISABLED=1``. All other test files
  (``test_web_phase*``) rely on the disabled mode to avoid a 1-hour
  background loop leaking into pytest.
* The :func:`web.scheduler._scheduler_loop` reacts promptly to its
  stop event (we wait at most 50ms) so app shutdown isn't blocked by
  the hourly tick interval.
"""

from __future__ import annotations

import asyncio
import datetime
import os
from unittest.mock import patch

import pytest

from utils import db
from web import scheduler as web_scheduler


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "scheduler.db")
    monkeypatch.setenv("WEB_SCHEDULER_DISABLED", "1")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        yield


def _make_due_rule(local_user_id: int) -> int:
    rec_id = db.add_recurring(
        local_user_id, "Netflix", 39.90, "Outros",
        action_type="expense", currency_code="BRL",
    )
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    with db._connect() as conn:
        conn.execute(
            "UPDATE recurring_transactions SET next_run = ? WHERE id = ?",
            (yesterday, rec_id),
        )
        conn.commit()
    return rec_id


class TestSchedulerLoop:
    async def test_initial_catchup_runs_then_stops_on_event(self):
        """The loop processes overdue rules at boot, then stops within
        a few ms when the stop event fires."""
        local_id = db.create_web_user("alice", "pass1234")
        _make_due_rule(local_id)

        stop_event = asyncio.Event()
        # Big tick interval — we want to prove the loop never sleeps
        # the full hour because the event short-circuits it.
        loop_task = asyncio.create_task(
            web_scheduler._scheduler_loop(stop_event, tick_seconds=10_000)
        )
        # Yield control so the catch-up tick can run.
        await asyncio.sleep(0.05)
        stop_event.set()
        await asyncio.wait_for(loop_task, timeout=1.0)

        # The catch-up tick should have executed the due rule.
        with db._connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM transactions WHERE source = 'recurring'"
            ).fetchone()["c"]
        assert n == 1

    async def test_stop_event_set_before_loop_starts_exits_cleanly(self):
        """Edge case: shutdown racing startup must not deadlock."""
        stop_event = asyncio.Event()
        stop_event.set()
        await asyncio.wait_for(
            web_scheduler._scheduler_loop(stop_event, tick_seconds=10_000),
            timeout=1.0,
        )

    async def test_tick_failure_is_logged_but_loop_keeps_going(self):
        """If a single tick raises, the loop must not crash."""
        stop_event = asyncio.Event()
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("simulated tick failure")
            return 0

        with patch.object(web_scheduler, "execute_due_recurring", side_effect=boom):
            task = asyncio.create_task(
                web_scheduler._scheduler_loop(stop_event, tick_seconds=0.05)
            )
            # Wait long enough for the failing tick + at least one retry.
            await asyncio.sleep(0.2)
            stop_event.set()
            await asyncio.wait_for(task, timeout=1.0)

        assert calls["n"] >= 2, (
            "the loop must keep ticking after a transient failure"
        )


class TestLifespan:
    async def test_lifespan_disabled_flag_skips_scheduler(self, monkeypatch):
        """``WEB_SCHEDULER_DISABLED=1`` must keep the lifespan a no-op
        so test suites don't accidentally race the loop."""
        from fastapi import FastAPI

        from web.main import lifespan as web_lifespan

        monkeypatch.setenv("WEB_SCHEDULER_DISABLED", "1")
        app = FastAPI()
        async with web_lifespan(app):
            # If the scheduler had started, an asyncio task would be
            # alive in the running loop.
            tasks = [t for t in asyncio.all_tasks() if "_scheduler_loop" in repr(t.get_coro())]
            assert tasks == [], (
                "scheduler must not start when WEB_SCHEDULER_DISABLED=1"
            )

    async def test_lifespan_starts_and_stops_scheduler_when_enabled(
        self, monkeypatch,
    ):
        """When the disable flag is off, the lifespan must spin up the
        loop and tear it down cleanly on exit."""
        from fastapi import FastAPI

        from web.main import lifespan as web_lifespan

        monkeypatch.delenv("WEB_SCHEDULER_DISABLED", raising=False)

        # We don't want a real 1h tick to fire during the test, but we
        # also don't want to mock out _scheduler_loop entirely (we want
        # the lifespan to manage a real task). So we replace
        # ``execute_due_recurring`` with a fast no-op and let the loop
        # block on its stop event.
        with patch.object(web_scheduler, "execute_due_recurring", return_value=0):
            app = FastAPI()
            async with web_lifespan(app):
                running = [
                    t for t in asyncio.all_tasks()
                    if "_scheduler_loop" in repr(t.get_coro())
                ]
                assert len(running) == 1, "scheduler task must be running"
            # After the lifespan exit, the task is done.
            running_after = [
                t for t in asyncio.all_tasks()
                if "_scheduler_loop" in repr(t.get_coro()) and not t.done()
            ]
            assert running_after == [], "scheduler must be stopped on exit"

        # Restore the env we're typically expected to leave behind.
        os.environ["WEB_SCHEDULER_DISABLED"] = "1"
