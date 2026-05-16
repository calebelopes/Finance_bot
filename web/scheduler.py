"""Recurring transaction scheduler that runs inside the FastAPI app.

Pre-v2.x the recurring engine lived inside ``bot/main.py`` and was
agendado via ``Application.job_queue``. That coupled a core product
feature to the bot process: if you brought up only the ``web`` service,
no recurring transactions ever fired. The web is the canonical source
of truth post-pivot, so the scheduler now lives here and the bot only
acts as a notifier (``bot.main._notify_pending_recurring``).

Design points:

* Tick cadence is hourly. ``next_run`` granularity is one calendar day,
  so anything finer is wasted CPU; anything coarser delays catch-ups
  after a redeploy.
* The loop sleeps on an :class:`asyncio.Event` so shutdown is prompt
  (no “stuck for 1h after Ctrl+C”).
* DB writes are synchronous (``utils.db`` is sqlite-on-stdlib); we run
  them in a thread to keep the event loop responsive when the workload
  grows. For today's volume (single-user / handful of users) it's
  a non-issue, but the indirection costs nothing.
* Idempotency: ``execute_due_recurring`` advances ``next_run`` after
  inserting the transaction, so re-running it on the same database is
  a no-op until the next month.
"""

from __future__ import annotations

import asyncio
import logging

from utils import db

log = logging.getLogger(__name__)


# Hourly tick is plenty: ``next_run`` is a date, not a timestamp.
DEFAULT_TICK_SECONDS = 60 * 60


def execute_due_recurring() -> int:
    """Run all overdue recurring rules. Returns how many were executed.

    Each due rule produces one transaction, one ``recurring_logs`` row
    (with ``notified_at = NULL`` so the bot picks it up later), and
    advances ``next_run`` by one month. Errors on a single rule are
    logged and don't abort the rest of the batch.
    """
    due = db.get_due_recurring()
    executed = 0
    for rule in due:
        try:
            cat = rule.get("category") or "Outros"
            tx_id = db.store_transaction(
                rule["user_id"],
                None,
                rule["description"],
                rule["amount"],
                cat,
                rule["type"],
                currency_code=rule.get("currency_code", "BRL"),
                source="recurring",
                recurring_id=rule["id"],
            )
            db.log_recurring_execution(rule["id"], tx_id)
            db.advance_recurring(rule["id"])
            executed += 1
            log.info(
                "scheduler: executed recurring #%d -> tx #%d for user %d",
                rule["id"], tx_id, rule["user_id"],
            )
        except Exception:
            log.exception(
                "scheduler: error executing recurring rule #%d", rule["id"],
            )
    return executed


async def _scheduler_loop(stop_event: asyncio.Event,
                           tick_seconds: float = DEFAULT_TICK_SECONDS) -> None:
    """Run :func:`execute_due_recurring` once per *tick_seconds*.

    Wakes immediately on ``stop_event.set()`` so app shutdown is fast.
    A failure inside one tick never breaks the loop; we log and wait
    for the next tick.
    """
    log.info("recurring scheduler started (tick=%ss)", tick_seconds)
    # Catch up on anything overdue at boot before we settle into the
    # cadence — useful after a long downtime.
    try:
        await asyncio.to_thread(execute_due_recurring)
    except Exception:
        log.exception("scheduler: initial catch-up tick failed")

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=tick_seconds)
            # If wait_for returns, the event was set → time to stop.
            break
        except asyncio.TimeoutError:
            pass
        try:
            await asyncio.to_thread(execute_due_recurring)
        except Exception:
            log.exception("scheduler: tick failed")
    log.info("recurring scheduler stopped")
